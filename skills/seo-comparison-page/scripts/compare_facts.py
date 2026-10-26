#!/usr/bin/env python3
"""Audit a comparison page's vendor-facts.csv: overdue and upcoming rechecks, own-product facts still
pending, contradictions, draft values without a row, and optionally whether each literal
string is still present at its source.

Usage: python3 scripts/compare_facts.py --facts vendor-facts.csv --today YYYY-MM-DD
           [--draft page.md] [--fetch] [--due-days 14] [--out report.json]

Network: none by default. With --fetch (alias --live): one read-only GET per distinct
source_url through seokit.fetch (robots.txt respected, ~2 req/s, size cap); a host answering
401/403/429 is not asked again and its facts are marked "not read".

The script never writes to vendor-facts.csv: it never changes a status, read_on or recheck_by.
String presence is not verification; someone re-reads the source before marking `verified`.
Exit codes: 0 nothing blocking, 1 blocking items found (overdue, pending-owner, contradiction,
absent string), 2 bad input, 3 a source site blocked the fetch.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
import urllib.parse
from typing import Dict, List, Optional, Tuple

from seokit.fetch import BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args
from seokit.html import parse_html
from seokit.report import emit_json, today, untrusted
from seokit.tables import TableError, read_tables
from seokit.text import find_literal, normalize

REQUIRED_COLUMNS = [
    "fact_id", "product", "is_own_product", "attribute", "value_on_page", "literal_string",
    "source_url", "read_on", "volatility", "recheck_by", "status",
]

# references/recheck-cadence.md (heuristic, to calibrate on the category)
CADENCE_DAYS = {"very-high": 14, "high": 30, "medium": 90, "low": 180}
DEFAULT_DUE_DAYS = 14
STATUSES = {"verified", "changed", "pending-owner", "contradicted", "not-read"}

AMOUNT = r"(?:\d{1,3}(?:[ \u00a0\u202f.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
DRAFT_PATTERNS = [
    # "$10/mo", "390 € HT", "3 000 €", "20 € HT /mois". "€\b" never matched: there is no word
    # boundary between "€" and the space after it.
    ("price", re.compile(
        rf"(?:[$€£¥]\s?{AMOUNT}(?:\s?(?:k|m)\b)?|(?<![\d.,]){AMOUNT}\s?(?:[$€£¥]|(?:USD|EUR|GBP|CHF)\b))"
        r"(?:\s?(?:HT|TTC|HTVA)\b)?(?:\s?/\s?\w+)?", re.I)),
    ("version", re.compile(r"\bv(?:ersion)?\s?\d+(?:\.\d+)+\b|\b\d+\.\d+\.\d+\b", re.I)),
    ("percent", re.compile(r"\b\d[\d.,]*\s?%")),
    ("number_with_unit", re.compile(
        r"\b\d[\d.,]*\s?(?:[KMGT]B|GiB|MiB|users?|seats?|members?|projects?|days?|months?|"
        r"years?|weeks?|hours?|minutes?|requests?|calls?|emails?|pages?|sites?|integrations?|"
        r"utilisateurs?|jours?|semaines?|mois|ans|heures?|go|mo|to)\b", re.I)),
]


def parse_date(value: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def is_yes(value: str) -> bool:
    return normalize(value) in ("yes", "y", "true", "1", "oui", "x")


def load_facts(path: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """Rows of the first table plus the list of missing required columns."""
    tables = read_tables(path)

    if not tables:
        raise TableError(f"{path}: no table found")

    table = tables[0]
    headers = [h.strip().lower() for h in table.headers]
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    rows = []

    for row in table.rows:
        values = row + [""] * (len(headers) - len(row))
        record = {headers[i]: (values[i] or "").strip() for i in range(len(headers))}

        if any(record.values()):
            rows.append(record)

    return rows, missing


def fact_summary(row: Dict[str, str]) -> dict:
    return {
        "fact_id": untrusted(row.get("fact_id"), 80),
        "product_text": untrusted(row.get("product"), 120),
        "attribute_text": untrusted(row.get("attribute"), 120),
        "value_on_page_text": untrusted(row.get("value_on_page"), 200),
        "source_url_text": untrusted(row.get("source_url"), 300),
        "status": untrusted(row.get("status"), 40),
        "read_on": untrusted(row.get("read_on"), 20),
        "recheck_by": untrusted(row.get("recheck_by"), 20),
    }


def effective_recheck(row: Dict[str, str]) -> Tuple[Optional[datetime.date], str]:
    """recheck_by from the file, else read_on + cadence. Returns (date, how it was found)."""
    given = parse_date(row.get("recheck_by", ""))

    if given:
        return given, "recheck_by"

    read_on = parse_date(row.get("read_on", ""))
    cadence = CADENCE_DAYS.get(normalize(row.get("volatility", "")))

    if read_on and cadence:
        return read_on + datetime.timedelta(days=cadence), "computed from read_on + cadence"

    return None, "not computable"


def audit_dates(rows: List[Dict[str, str]], now: datetime.date, due_days: int) -> dict:
    """Facts overdue for a recheck, due within due_days, undated, and with a recheck later than their cadence."""
    overdue, due_soon, undated, cadence_notes = [], [], [], []
    horizon = now + datetime.timedelta(days=due_days)

    for row in rows:
        recheck, how = effective_recheck(row)
        summary = fact_summary(row)

        if recheck is None:
            summary["problem"] = "no valid recheck_by and no read_on + volatility to compute it"
            undated.append(summary)
            continue

        summary["effective_recheck_by"] = recheck.isoformat()
        summary["recheck_source"] = how
        note = cadence_mismatch(row, recheck)

        if note:
            cadence_notes.append(dict(fact_summary(row), note=note))

        if recheck < now:
            summary["days_overdue"] = (now - recheck).days
            overdue.append(summary)
            continue

        if recheck <= horizon:
            summary["days_left"] = (recheck - now).days
            due_soon.append(summary)

    overdue.sort(key=lambda item: item["effective_recheck_by"])
    due_soon.sort(key=lambda item: item["effective_recheck_by"])

    return {"overdue": overdue, "due_soon": due_soon, "undated": undated,
            "cadence_notes": cadence_notes}


def cadence_mismatch(row: Dict[str, str], recheck: datetime.date) -> Optional[str]:
    """Flag a recheck_by later than read_on + cadence (event facts use their end date)."""
    read_on = parse_date(row.get("read_on", ""))
    cadence = CADENCE_DAYS.get(normalize(row.get("volatility", "")))

    if not read_on or not cadence:
        return None

    limit = read_on + datetime.timedelta(days=cadence)

    if recheck <= limit:
        return None

    return (f"recheck_by later than read_on + {cadence} days for volatility "
            f"'{normalize(row.get('volatility', ''))}' (expected by {limit.isoformat()})")


def pending_own(rows: List[Dict[str, str]]) -> List[dict]:
    pending = []

    for row in rows:
        status = normalize(row.get("status", ""))

        if status == "pending-owner":
            pending.append(fact_summary(row))
            continue

        if is_yes(row.get("is_own_product", "")) and status != "verified":
            pending.append(dict(fact_summary(row), note="own-product fact not verified"))

    return pending


def contradictions(rows: List[Dict[str, str]]) -> List[dict]:
    """Product and attribute pairs whose rows give different page values or are marked contradicted."""
    groups: Dict[Tuple[str, str], List[Dict[str, str]]] = {}

    for row in rows:
        key = (normalize(row.get("product", "")), normalize(row.get("attribute", "")))

        if not key[0] or not key[1]:
            continue

        groups.setdefault(key, []).append(row)

    found = []

    for members in groups.values():
        values = {normalize(m.get("value_on_page", "")) for m in members}
        values.discard("")
        marked = any(normalize(m.get("status", "")) == "contradicted" for m in members)

        if len(values) < 2 and not marked:
            continue

        found.append({
            "product_text": untrusted(members[0].get("product"), 120),
            "attribute_text": untrusted(members[0].get("attribute"), 120),
            "distinct_values": len(values),
            "marked_contradicted": marked,
            "facts": [fact_summary(m) for m in members],
        })

    return found


def unknown_statuses(rows: List[Dict[str, str]]) -> List[dict]:
    return [fact_summary(r) for r in rows if normalize(r.get("status", "")) not in STATUSES]


def draft_values(draft_text: str) -> List[Tuple[str, str]]:
    seen, values = set(), []

    for kind, pattern in DRAFT_PATTERNS:
        for match in pattern.finditer(draft_text):
            value = match.group(0).strip()
            key = normalize(value)

            if key in seen:
                continue

            seen.add(key)
            values.append((kind, value))

    return values


def compact(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text))


def unmatched_draft_values(draft_text: str, rows: List[Dict[str, str]]) -> List[dict]:
    known = " | ".join(
        compact(r.get("value_on_page", "")) + " | " + compact(r.get("literal_string", ""))
        for r in rows
    )
    missing = []

    for kind, value in draft_values(draft_text):
        # Bounded on digits: "90 €" is not covered by a row saying "390 € HT".
        if re.search(rf"(?<![\d.,]){re.escape(compact(value))}(?![.,]?\d)", known):
            continue

        context = find_literal(draft_text, value, context=60)
        missing.append({
            "kind": kind,
            "draft_value_text": untrusted(value, 80),
            "draft_context_quote": untrusted(context[0].context if context else value, 200),
        })

    return missing


def page_text(response) -> str:
    if response.is_html or "<html" in response.text()[:2000].lower():
        page = parse_html(response.text(), response.final_url)

        return f"{page.title or ''} {page.text}"

    return response.text()


def check_sources(rows: List[Dict[str, str]], fetcher) -> Tuple[List[dict], List[str]]:
    """Fetch each distinct source URL once; report literal string presence per fact."""
    cache: Dict[str, Tuple[Optional[str], str]] = {}
    blocked_hosts: Dict[str, int] = {}
    results = []

    for row in rows:
        url = row.get("source_url", "").strip()
        literal = row.get("literal_string", "")
        result = dict(fact_summary(row), literal_string_text=untrusted(literal, 300))

        if not url.lower().startswith(("http://", "https://")):
            result.update(presence="not read", reason="source_url is not an http(s) URL")
            results.append(result)
            continue

        if not literal.strip():
            result.update(presence="not read", reason="no literal_string to look for")
            results.append(result)
            continue

        if url not in cache:
            cache[url] = fetch_text(url, fetcher, blocked_hosts)

        text, reason = cache[url]

        if text is None:
            result.update(presence="not read", reason=reason)
            results.append(result)
            continue

        matches = find_literal(text, literal, context=80)

        if matches:
            result.update(presence="present", evidence_quote=untrusted(matches[0].context, 300))
        else:
            result.update(presence="absent",
                          reason="literal string not found in the static HTML text; "
                                 "may be reworded, moved, or rendered by JavaScript")

        results.append(result)

    hosts = [f"{host} ({status})" for host, status in blocked_hosts.items()]

    return results, hosts


def fetch_text(url: str, fetcher, blocked_hosts: Dict[str, int]) -> Tuple[Optional[str], str]:
    host = urllib.parse.urlsplit(url).netloc.lower()

    if host in blocked_hosts:
        return None, f"host answered {blocked_hosts[host]} earlier; not asked again"

    print(f"Fetching {untrusted(url)} ...", file=sys.stderr)
    response = fetcher.get(url)

    if response.status in BLOCKING_STATUSES:
        blocked_hosts[host] = response.status

        return None, f"HTTP {response.status}: site blocks automated reads; read it manually"

    if response.status is None:
        return None, response.error or "network error"

    if not response.ok:
        return None, f"HTTP {response.status}"

    return page_text(response), "ok"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit vendor-facts.csv: overdue rechecks, pending own-product facts, "
                    "contradictions, draft values without a row, optional live string check. "
                    "Cadences are heuristic, to calibrate (references/recheck-cadence.md). "
                    "Never edits vendor-facts.csv.")
    parser.add_argument("--facts", required=True, help="path to vendor-facts.csv")
    parser.add_argument("--today", help="reference date YYYY-MM-DD (default: system date)")
    parser.add_argument("--due-days", type=int, default=DEFAULT_DUE_DAYS,
                        help="window for 'due soon' (default 14 days)")
    parser.add_argument("--draft", help="draft page (Markdown/text) to scan for values with no row")
    parser.add_argument("--fetch", "--live", dest="fetch", action="store_true",
                        help="GET each source_url and report if the literal string is present")
    parser.add_argument("--out", help="write the JSON report to this path instead of stdout")
    add_fetch_arguments(parser)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Audit the facts file and print or write the JSON.

    Returns 3 when a source host blocked, 1 when something blocks publication, 2 on bad input.
    """
    args = build_parser().parse_args(argv)
    now = parse_date(args.today) if args.today else datetime.date.today()

    if now is None:
        print("--today must be YYYY-MM-DD", file=sys.stderr)
        return 2

    try:
        rows, missing = load_facts(args.facts)
    except (OSError, TableError) as error:
        print(f"cannot read facts file: {error}", file=sys.stderr)
        return 2

    if missing:
        print(f"facts file lacks required columns: {', '.join(missing)}", file=sys.stderr)
        return 2

    draft_text = None

    if args.draft:
        try:
            with open(args.draft, encoding="utf-8", errors="replace") as handle:
                draft_text = handle.read(2_000_000)
        except OSError as error:
            print(f"cannot read draft: {error}", file=sys.stderr)
            return 2

    report = build_report(rows, now, args, draft_text)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            emit_json(report, handle)
    else:
        emit_json(report)

    if report["blocked_hosts"]:
        return 3

    return 1 if report["blocking"] else 0


def build_report(rows, now, args, draft_text) -> dict:
    """The JSON report: dates, pending own-product facts, contradictions, then draft and source checks if asked."""
    dates = audit_dates(rows, now, args.due_days)
    pending = pending_own(rows)
    conflicts = contradictions(rows)
    report = {
        "generated_on": today(),
        "reference_date": now.isoformat(),
        "facts_file": os.path.basename(args.facts),
        "fact_count": len(rows),
        "overdue": dates["overdue"],
        "due_soon": dates["due_soon"],
        "due_soon_window_days": args.due_days,
        "undated": dates["undated"],
        "cadence_notes": dates["cadence_notes"],
        "pending_owner": pending,
        "contradictions": conflicts,
        "unknown_status": unknown_statuses(rows),
        "draft_values_without_row": None,
        "source_checks": None,
        "blocked_hosts": [],
        "limits": [
            "Cadences are heuristic, to calibrate on the category.",
            "This script never updates status, read_on or recheck_by: re-read the source, "
            "then edit vendor-facts.csv by hand.",
        ],
    }

    if draft_text is not None:
        report["draft_values_without_row"] = unmatched_draft_values(draft_text, rows)
        report["limits"].append("Draft check is pattern-based: facts written in words are missed.")
    else:
        report["limits"].append("No --draft given: draft values not checked.")

    if args.fetch:
        checks, blocked = check_sources(rows, fetcher_from_args(args))
        report["source_checks"] = checks
        report["blocked_hosts"] = blocked
        report["limits"].append(
            "String presence is not verification: a present string may sit in an outdated "
            "section, an absent one may be a rewording. Static HTML only, no JavaScript.")
    else:
        report["limits"].append("No --fetch: sources not re-read.")

    absent = [c for c in (report["source_checks"] or []) if c["presence"] != "present"]
    report["blocking"] = bool(dates["overdue"] or pending or conflicts or absent)

    return report


if __name__ == "__main__":
    sys.exit(main())
