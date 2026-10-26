#!/usr/bin/env python3
"""Check that each register fact's source page still shows its recorded string.

For every row of a decay-register.csv that has a source_url and a source_string, fetches
the source once (one GET per distinct URL) and reports whether the string is still
`present`, `absent`, or `not read` (blocked, error, non-200, challenge or login page,
JavaScript shell, nearly empty). Unreadable pages are never reported as `absent`.

The result only flags which source to re-read. It never marks a fact as verified and never
writes to the register: a string can stay while the fact changed around it, and can
disappear after a harmless rewording.

Usage:
    python3 scripts/source_watch.py --register decay-register.csv [--only overdue,due-soon]
        [--today YYYY-MM-DD] [--out watch.csv]

Network: one GET per distinct source URL through seokit.fetch (identifiable user agent,
about 2 requests per second, robots.txt respected, timeouts, size cap). A host answering
401/403/429 is not asked again in the run; exit code 3 when that happens.
"""

from __future__ import annotations

import argparse
import datetime
import html as html_lib
import os
import re
import sys
import urllib.parse
from typing import Dict, List, Optional, Tuple

from readability import inside_longer_number, unreadable_reason
from seokit.fetch import BLOCKING_STATUSES, Fetcher, add_fetch_arguments, fetcher_from_args
from seokit.html import parse_html
from seokit.report import today, untrusted, write_csv
from seokit.tables import TableError, read_tables
from seokit.text import find_literal

FIELDS = ["fact_id", "source_url", "http_status", "result", "reason", "source_string_quoted",
          "context_quoted", "fetched_at", "register_status"]
STATUSES = ("overdue", "due-soon", "ok", "page-dated", "no-date", "future-date", "event-passed")


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def parse_day(value: Optional[str]) -> Optional[datetime.date]:
    match = re.match(r"^\s*((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})", value or "")

    if not match:
        return None

    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def effective_status(row: Dict[str, str], today_date: datetime.date) -> str:
    """Register status, moved to overdue when its next_check date has passed since."""
    status = row.get("status", "").strip().lower()
    due = parse_day(row.get("next_check"))

    if status in ("ok", "due-soon") and due and due < today_date:
        return "overdue"

    return status


class SourceCache:
    """One GET per distinct URL; hosts that blocked are not asked again."""

    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher
        self.pages: Dict[str, dict] = {}
        self.blocked_hosts: Dict[str, int] = {}

    def get(self, url: str) -> dict:
        """Fetched page entry (status, unreadable reason, raw and text haystacks), cached per URL."""
        if url in self.pages:
            return self.pages[url]

        host = urllib.parse.urlsplit(url).netloc.lower()

        if host in self.blocked_hosts:
            skipped = f"host answered HTTP {self.blocked_hosts[host]} earlier in this run: not asked again"

            return {"status": None, "reason": skipped,
                    "haystacks": {}, "truncated": False, "fetched_at": ""}

        print(f"Fetching {untrusted(url)} ...", file=sys.stderr)
        response = self.fetcher.get(url)
        raw = response.text() if response.body else ""
        page = parse_html(raw, response.final_url) if (response.ok and response.is_html) else None
        reason = unreadable_reason(response, raw.lower(), page.word_count if page else None)
        haystacks: Dict[str, str] = {}

        if response.status in BLOCKING_STATUSES:
            self.blocked_hosts[host] = response.status

        if response.ok and raw:
            haystacks["raw"] = html_lib.unescape(raw)

        if page is not None:
            haystacks["text"] = " ".join([page.title or "", page.text])

        entry = {"status": response.status, "reason": reason, "haystacks": haystacks,
                 "truncated": response.truncated, "fetched_at": now()}
        self.pages[url] = entry

        return entry


def watch_row(row: Dict[str, str], cache: SourceCache, status: str) -> dict:
    """Whether the row's source still shows its recorded string: present, absent, not read or not checked."""
    url = row.get("source_url", "").strip()
    needle = row.get("source_string", "")
    result = {
        "fact_id": untrusted(row.get("fact_id", "")),
        "source_url": untrusted(url, limit=2000),
        "http_status": "",
        "result": "not read",
        "reason": "",
        "source_string_quoted": untrusted(needle, limit=500),
        "context_quoted": "",
        "fetched_at": "",
        "register_status": untrusted(status),
    }

    if not url or not needle.strip():
        result.update(result="not checked", reason="no source_url or source_string in the register")
        return result

    if not re.match(r"^https?://", url, re.I):
        result.update(result="not checked", reason="source_url is not an http(s) URL")
        return result

    page = cache.get(url)
    result["http_status"] = page["status"] if page["status"] is not None else ""
    result["fetched_at"] = page["fetched_at"]
    matches = []

    for haystack in page["haystacks"].values():
        matches = [m for m in find_literal(haystack, needle, context=120)
                   if not inside_longer_number(haystack, needle, m.start)]

        if matches:
            break

    if matches:
        result.update(result="present", reason="string still on the page: re-read the source to verify the fact",
                      context_quoted=untrusted(matches[0].context, limit=600))
        return result

    if page["reason"]:
        result["reason"] = page["reason"]
        return result

    if page["truncated"]:
        result["reason"] = "response above the size cap: string not in the part read"
        return result

    result.update(result="absent", reason="string not on the readable page: re-read the source")

    return result


def read_register(path: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
    if not os.path.isfile(path):
        return [], f"no such register file: {path}"

    try:
        tables = read_tables(path)
    except (TableError, OSError) as error:
        return [], f"register not readable: {error}"

    rows = [record for table in tables for record in table.records()]

    if not rows:
        return [], "register has no rows"

    if not any("source_url" in row for row in rows):
        return [], "register has no source_url column (templates/decay-register.csv format expected)"

    return rows, None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report whether each register fact's source still shows its recorded string "
                    "(present / absent / not read). Never marks a fact verified; never edits the register. "
                    "Readability checks are heuristic, to calibrate.",
    )
    parser.add_argument("--register", required=True, help="decay-register.csv (source_url and source_string columns)")
    parser.add_argument("--only", help="comma-separated statuses to check, e.g. overdue,due-soon")
    parser.add_argument("--today", help="date YYYY-MM-DD used to age next_check (default: today)")
    parser.add_argument("--out", help="write the CSV here instead of stdout")
    add_fetch_arguments(parser)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Check the register rows (filtered by --only) against their sources and write the CSV.

    Returns 3 when a host blocked, 2 on bad input; the register itself is never written.
    """
    args = build_parser().parse_args(argv)
    today_date = parse_day(args.today) if args.today else datetime.date.today()

    if today_date is None:
        print("error: --today must be YYYY-MM-DD", file=sys.stderr)
        return 2

    only = [s.strip().lower() for s in args.only.split(",") if s.strip()] if args.only else []
    unknown = [s for s in only if s not in STATUSES]

    if unknown:
        print(f"error: unknown status in --only: {', '.join(unknown)}", file=sys.stderr)
        return 2

    if args.out and os.path.abspath(args.out) == os.path.abspath(args.register):
        print("error: --out must not overwrite the register", file=sys.stderr)
        return 2

    rows, error = read_register(args.register)

    if error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    cache = SourceCache(fetcher_from_args(args))
    results = []
    skipped = 0

    for row in rows:
        status = effective_status(row, today_date)

        if only and status not in only:
            skipped += 1
            continue

        results.append(watch_row(row, cache, status))

    write_csv(results, FIELDS, args.out)
    counts: Dict[str, int] = {}

    for item in results:
        counts[item["result"]] = counts.get(item["result"], 0) + 1

    print(f"[source_watch] {today()}: {len(results)} row(s) checked, {skipped} filtered out by --only; "
          f"{counts}. 'present' is not 'verified': re-read flagged sources.", file=sys.stderr)

    return 3 if cache.blocked_hosts else 0


if __name__ == "__main__":
    sys.exit(main())
