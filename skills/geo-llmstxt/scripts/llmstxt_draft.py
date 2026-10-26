#!/usr/bin/env python3
"""Draft an llms.txt from the pages of a site: only what the pages state, placeholders elsewhere.

Reads a seokit crawl (--from-crawl, e.g. the one seo-audit wrote) or crawls the site itself
(--site). Keeps indexable HTML pages (status 200, no noindex, canonical to itself, no query
string), groups them by first path segment and writes a Markdown draft: H1, summary, one
section per group, `- [title](url): description`. A value the site does not state is written
as a `{placeholder}`. The draft is checked against the same wording patterns as
llmstxt_review.py (L08) before it is written.

Usage:
    python3 scripts/llmstxt_draft.py --site <url> [--max-pages 200] --out llms.txt [--report draft.json]
    python3 scripts/llmstxt_draft.py --from-crawl <dir> --out llms.txt

Network: with --site only, GET through seokit.fetch (robots.txt respected, about 2 requests
per second, size cap); stops on 401/403/429. --from-crawl is offline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.parse
from collections import Counter, OrderedDict
from typing import Dict, List, Optional, Set, Tuple

from llmstxt_review import WORDING_PATTERNS
from seokit import crawl as crawl_mod
from seokit import report
from seokit.fetch import BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args, normalize_url, same_site
from seokit.html import parse_html

DEFAULT_MAX_PAGES = 200
TITLE_MAX = 90
DESCRIPTION_MAX = 200
# A title suffix shared by at least this share of pages is the site name (" | Acme").
# Heuristic, to calibrate.
SUFFIX_SHARE = 0.5
# A path segment needs at least this many pages to get its own section; the rest go to
# MAIN_SECTION. Heuristic, to calibrate.
MIN_SECTION_PAGES = 2
MAIN_SECTION = "Pages"
SEPARATORS = (" | ", " - ", " – ", " — ", " · ", " :: ")
PLACEHOLDER_NAME = "{site name}"
PLACEHOLDER_SUMMARY = "{one-sentence summary of what the site offers}"
PLACEHOLDER_DESCRIPTION = "{description}"


def clean(text: Optional[str], limit: int) -> str:
    """Site text on one line, without Markdown link syntax, cut at a word boundary."""
    value = re.sub(r"\s+", " ", text or "").strip()
    value = re.sub(r"[\[\]<>]", "", value).replace("](", " ").replace("`", "'")

    if len(value) <= limit:
        return value

    cut = value[:limit].rsplit(" ", 1)[0]

    return f"{cut}…"


def split_suffix(title: str) -> Tuple[str, Optional[str]]:
    for separator in SEPARATORS:
        if separator in title:
            head, tail = title.rsplit(separator, 1)

            return head.strip(), tail.strip()

    return title.strip(), None


def site_name(pages: List[dict]) -> Tuple[str, str]:
    """(name, basis): og:site_name of the home page, else a title suffix most pages share."""
    for page in pages:
        if page["is_home"] and page["og_site_name"]:
            return clean(page["og_site_name"], TITLE_MAX), "og:site_name"

    suffixes = Counter(split_suffix(page["title"])[1] for page in pages if page["title"])
    suffixes.pop(None, None)

    if suffixes:
        suffix, count = suffixes.most_common(1)[0]

        if count >= max(2, SUFFIX_SHARE * len(pages)):
            return clean(suffix, TITLE_MAX), "shared title suffix"

    return PLACEHOLDER_NAME, "not stated"


def page_title(page: dict, name: str) -> str:
    if page["h1"]:
        return clean(page["h1"], TITLE_MAX)

    head, suffix = split_suffix(page["title"] or "")

    if suffix and suffix == name:
        return clean(head, TITLE_MAX)

    return clean(page["title"], TITLE_MAX) or "{title}"


def link_url(url: str) -> str:
    """The page URL as one Markdown link destination: ( ) [ ] < > and spaces percent-encoded,
    existing %-escapes kept, so a crafted path cannot close the link and open another one."""
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%:@!$&'*+,;=-._~")

    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def section_of(url: str) -> Optional[str]:
    segments = [part for part in urllib.parse.urlsplit(url).path.split("/") if part]

    if len(segments) < 2:
        return None

    return segments[0]


def section_title(segment: str) -> str:
    words = re.sub(r"[-_]+", " ", urllib.parse.unquote(segment)).strip()

    return clean(words[:1].upper() + words[1:], TITLE_MAX)


def exclusion(record: dict, page, start_url: str) -> Optional[str]:
    """Why a crawled page stays out of the draft, or None when it goes in."""
    if record.get("status") != 200:
        return f"status {record.get('status')}"

    if page is None:
        return "not HTML"

    url = record.get("final_url") or record.get("url") or ""

    if not same_site(url, start_url):
        return "other site"

    if urllib.parse.urlsplit(url).query:
        return "query string"

    header_robots = (record.get("headers") or {}).get("x-robots-tag", "")

    if "noindex" in page.robots or "noindex" in header_robots.lower():
        return "noindex"

    if page.canonical and normalize_url(page.canonical) != normalize_url(url):
        return "canonical elsewhere"

    return None


def read_pages(crawl_dir: str) -> Tuple[dict, List[dict], Counter]:
    """The crawl metadata, the fields of each page kept for the draft, and the count of pages left out by reason."""
    meta, _ = crawl_mod.load_crawl(crawl_dir)
    start = meta.get("start_url", "")
    kept: List[dict] = []
    excluded: Counter[str] = Counter()
    seen: Set[str] = set()

    for record, raw in crawl_mod.iter_pages(crawl_dir):
        url = record.get("final_url") or record.get("url") or ""
        page = parse_html(raw, url) if raw else None
        reason = exclusion(record, page, start)

        if reason or page is None:
            excluded[reason or "not HTML"] += 1
            continue

        key = normalize_url(url)

        if key in seen:
            excluded["duplicate"] += 1
            continue

        seen.add(key)
        headings = [text for tag, text in page.content_headings if tag == "h1"] or \
                   [text for tag, text in page.headings if tag == "h1"]
        kept.append({
            "url": url,
            "is_home": urllib.parse.urlsplit(url).path in ("", "/"),
            "depth": record.get("depth"),
            "title": page.title or "",
            "h1": headings[0] if headings else "",
            "description": page.description or "",
            "og_site_name": page.meta_first("og:site_name") or "",
        })

    return meta, kept, excluded


def group(pages: List[dict]) -> "OrderedDict[str, List[dict]]":
    """Pages by section: main section first, then larger sections; small sections fold into the main one."""
    by_segment: Dict[Optional[str], List[dict]] = {}

    for page in pages:
        by_segment.setdefault(section_of(page["url"]), []).append(page)

    sections: Dict[str, List[dict]] = {}

    for segment, members in by_segment.items():
        if segment is None or len(members) < MIN_SECTION_PAGES:
            sections.setdefault(MAIN_SECTION, []).extend(members)
        else:
            sections[section_title(segment)] = members

    order = sorted(sections, key=lambda name: (name != MAIN_SECTION, -len(sections[name]), name))

    def depth(page: dict) -> tuple:
        return page["depth"] if page["depth"] is not None else 99, page["url"]

    return OrderedDict((name, sorted(sections[name], key=depth)) for name in order)


def build_draft(pages: List[dict]) -> Tuple[str, dict]:
    """The llms.txt Markdown draft and the facts it rests on (name basis, sections, placeholder count)."""
    name, name_basis = site_name(pages)
    home = next((page for page in pages if page["is_home"]), None)
    summary = clean(home["description"], DESCRIPTION_MAX) if home and home["description"] else ""
    lines = [f"# {name}", "", f"> {summary or PLACEHOLDER_SUMMARY}", ""]
    placeholders = int(name == PLACEHOLDER_NAME) + int(not summary)
    sections = group(pages)

    for title, members in sections.items():
        lines += [f"## {title}", ""]

        for page in members:
            description = clean(page["description"], DESCRIPTION_MAX)
            placeholders += int(not description)
            lines.append(f"- [{page_title(page, name)}]({link_url(page['url'])}): "
                         f"{description or PLACEHOLDER_DESCRIPTION}")

        lines.append("")

    facts = {"site_name": name, "site_name_basis": name_basis,
             "summary_basis": "home page meta description" if summary else "not stated",
             "sections": {title: len(members) for title, members in sections.items()},
             "placeholders": placeholders}

    return "\n".join(lines).rstrip() + "\n", facts


def wording_leads(draft: str) -> List[dict]:
    leads = []

    for number, line in enumerate(draft.splitlines(), 1):
        for pattern in WORDING_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                leads.append({"code": "L08", "line": number, "wording_quote": report.untrusted(line, 200)})
                break

    return leads


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft an llms.txt from the indexable pages of a site.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--site", help="site to crawl (start URL)")
    source.add_argument("--from-crawl", help="seokit crawl directory to reuse (offline)")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        help=f"crawl cap with --site (default {DEFAULT_MAX_PAGES}, heuristic)")
    parser.add_argument("--out", required=True, help="where to write the Markdown draft")
    parser.add_argument("--report", help="write the JSON summary here instead of stdout")
    add_fetch_arguments(parser)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Crawl or reuse a crawl, write the draft, then print or write the JSON summary; 3 when the site blocked."""
    args = build_parser().parse_args(argv)

    if args.max_pages < 1:
        print("--max-pages must be at least 1", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as work:
        crawl_dir = args.from_crawl

        if args.site:
            crawl_dir = os.path.join(work, "crawl")
            crawl_mod.crawl(args.site, fetcher_from_args(args), crawl_dir, max_pages=args.max_pages)

        if not os.path.isfile(os.path.join(crawl_dir, "crawl.json")):
            print(f"no crawl.json in {crawl_dir}", file=sys.stderr)
            return 2

        meta, pages, excluded = read_pages(crawl_dir)

    stop = str(meta.get("stop_reason") or "")
    blocked = any(f"HTTP {code}" in stop for code in BLOCKING_STATUSES)

    if not pages:
        print(f"no indexable HTML page to list ({stop or 'empty crawl'})", file=sys.stderr)
        return 3 if blocked else 2

    draft, facts = build_draft(pages)

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(draft)

    summary = {
        "generated_on": report.today(),
        "start_url": meta.get("start_url"),
        "pages_read": len(pages) + sum(excluded.values()),
        "pages_listed": len(pages),
        "pages_left_out": dict(excluded),
        "crawl_stop_reason": meta.get("stop_reason"),
        **facts,
        "wording_leads": wording_leads(draft),
        "draft": args.out,
        "limits": [
            "Static HTML only: pages rendered by JavaScript may be missing or untitled.",
            "Titles and descriptions are copied from the pages; review every line before publishing.",
            "Sections follow the URL structure, not the site's own menu; reorder them by importance.",
            f"Pages beyond the crawl cap ({args.max_pages}) are not listed.",
        ],
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)

    if blocked:
        print(f"stopped: {stop}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
