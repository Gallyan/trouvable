#!/usr/bin/env python3
"""Find every page that repeats a string (an old price, a wrong label) across a site.

Searches a local content folder (Markdown, HTML, text), the pages of a sitemap, or a list
of URLs for one or more literal strings, after whitespace, quote and dash normalisation.
With --fuzzy-numbers, a number also matches its formatting variants (thousands
separators, decimal comma, trailing zeros, currency symbol or code, before or after).
Each hit is reported with its location (title, h2, p3, table row 2, json-ld…) and the
sentence around it, quoted as site text. Pages that could not be read are listed as
"not read", never as pages without the string.

Usage:
    python3 scripts/site_search.py --dir <content folder> --find "<old string>" [--find ...]
    python3 scripts/site_search.py --sitemap <url> --find "<string>" [--max-pages 200] [--fuzzy-numbers]
    python3 scripts/site_search.py --urls <file> --find "<string>" [--out hits.csv]

Network: none with --dir. With --sitemap or --urls: GET only through seokit.fetch (about
2 requests per second, robots.txt respected, timeouts, size cap); the run stops on
401/403/429 (first page, or 3 in a row) with exit code 3.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Iterator, List, Optional, Tuple, TypedDict

from claim_scan import MAX_FILE_BYTES, Segment, html_segments, markdown_segments, text_segments
from seokit import sitemap as sitemap_mod
from seokit.fetch import BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args
from seokit.html import parse_html
from seokit.report import today, untrusted, write_csv
from seokit.tables import parse_number
from seokit.text import find_literal, normalize, sentences

FIELDS = [
    "url_or_path", "location", "string_searched", "matched_string", "sentence_quoted", "result", "note",
    "checked_on",
]
FILE_EXTENSIONS = (".html", ".htm", ".md", ".markdown", ".mdx", ".txt")
DEFAULT_MAX_PAGES = 200
MAX_DIR_FILES = 5000


class SearchInfo(TypedDict):
    """Run totals reported at the end: pages searched and left out, stop reason, sitemap errors."""

    pages_searched: int
    left_out: int
    stopped: Optional[str]
    sitemap_errors: List[str]

NUMBER_TOKEN = r"\d{1,3}(?:[ .,']\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
CURRENCY_GROUPS = [
    ("€", "eur", "euro", "euros"),
    ("$", "usd", "us$", "dollar", "dollars"),
    ("£", "gbp", "pound", "pounds"),
    ("chf",),
    ("¥", "jpy", "yen"),
    ("r$", "brl", "reais", "real"),
]
CURRENCY_TOKEN = "|".join(
    re.escape(token) for token in sorted({t for group in CURRENCY_GROUPS for t in group}, key=len, reverse=True)
)


# ------------------------------------------------------------------ fuzzy numbers

def number_pattern(token: str) -> str:
    value = parse_number(token.replace(" ", "").replace("'", ""))

    if value is None:
        return re.escape(token)

    whole = str(int(abs(value)))
    groups: List[str] = []

    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]

    integer = "[ .,']?".join(groups)
    fraction = f"{abs(value) - int(abs(value)):.6f}"[2:].rstrip("0")
    decimals = f"[.,]{fraction}0*" if fraction else "(?:[.,]0+)?"

    return rf"(?<![\d.,]){integer}{decimals}(?![.,]?\d)"


def currency_pattern(token: str) -> str:
    for group in CURRENCY_GROUPS:
        if token in group:
            alternatives = sorted(group, key=len, reverse=True)

            return "(?:" + "|".join(re.escape(a) + (r"\b" if a[-1].isalpha() else "") for a in alternatives) + ")"

    return re.escape(token)


def fuzzy_regex(needle: str) -> re.Pattern:
    """Pattern matching the needle with any formatting of its numbers and currencies."""
    text = normalize(needle)
    pair = re.fullmatch(rf"({CURRENCY_TOKEN})\s?({NUMBER_TOKEN})|({NUMBER_TOKEN})\s?({CURRENCY_TOKEN})", text)

    if pair:
        currency = currency_pattern(pair.group(1) or pair.group(4))
        number = number_pattern(pair.group(2) or pair.group(3))

        return re.compile(rf"(?:{currency}\s?{number}|{number}\s?{currency})")

    parts = re.split(rf"({NUMBER_TOKEN}|{CURRENCY_TOKEN})", text)
    pattern = []

    for index, part in enumerate(parts):
        if not part:
            continue

        if index % 2 == 0:
            pattern.append(r"\s*".join(re.escape(word) for word in part.split(" ")))
        elif re.fullmatch(NUMBER_TOKEN, part):
            pattern.append(number_pattern(part))
        else:
            pattern.append(currency_pattern(part))

    return re.compile("".join(pattern))


# ------------------------------------------------------------------ matching

def sentence_for(segment_text: str, matched: str) -> str:
    target = normalize(matched)

    for sentence in sentences(segment_text):
        if target and target in normalize(sentence):
            return sentence

    return segment_text


def literal_matches(text: str, needle: str) -> List[str]:
    """find_literal hits, minus those cut out of a longer number ('19 €' inside '119 €')."""
    hay = normalize(text)
    pin = normalize(needle)
    hits = []

    for match in find_literal(text, needle, context=0):
        before = hay[match.start - 1] if match.start > 0 else ""
        after = hay[match.start + len(pin): match.start + len(pin) + 2]

        if pin[:1].isdigit() and before and (before.isdigit() or before in ".,"):
            continue

        if pin[-1:].isdigit() and re.match(r"[.,]?\d", after):
            continue

        hits.append(hay[match.start: match.start + len(pin)])

    return hits


def matches_in(segment: Segment, needle: str, regex: Optional[re.Pattern]) -> List[str]:
    if regex is None:
        return literal_matches(segment.text, needle)

    return [m.group(0) for m in regex.finditer(normalize(segment.text))]


def search_segments(where: str, segments: List[Segment], needles: List[str], fuzzy: bool) -> List[dict]:
    rows = []

    for needle in needles:
        regex = fuzzy_regex(needle) if fuzzy else None

        for segment in segments:
            for matched in matches_in(segment, needle, regex):
                rows.append({
                    "url_or_path": where,
                    "location": segment.location,
                    "string_searched": untrusted(needle, limit=500),
                    "matched_string": untrusted(matched, limit=500),
                    "sentence_quoted": untrusted(sentence_for(segment.text, matched), limit=1000),
                    "result": "found",
                    "note": "fuzzy number match" if fuzzy else "",
                    "checked_on": today(),
                })

    return rows


def segments_of(content: str, name: str, kind: str) -> List[Segment]:
    if kind == "html":
        segments, _, _, _ = html_segments(content, name)
        page = parse_html(content, name)

        for index, block in enumerate(page.jsonld):
            segments.append(Segment("json-ld" if index == 0 else f"json-ld #{index + 1}", block, len(segments)))

        return segments

    if kind == "markdown":
        return markdown_segments(content)[0]

    return text_segments(content)


def kind_of(name: str, content: str) -> str:
    extension = os.path.splitext(name.split("?", maxsplit=1)[0])[1].lower()

    if extension in (".md", ".markdown", ".mdx"):
        return "markdown"

    if extension in (".html", ".htm") or re.match(r"\s*(<!doctype html|<html)", content[:500], re.I):
        return "html"

    return "text"


def not_read(where: str, reason: str) -> dict:
    return {"url_or_path": where, "location": "", "string_searched": "", "matched_string": "",
            "sentence_quoted": "", "result": "not read", "note": reason, "checked_on": today()}


# ------------------------------------------------------------------ sources

def iter_dir(root: str) -> Iterator[str]:
    real_root = os.path.realpath(root)

    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))

        for name in sorted(files):
            path = os.path.join(folder, name)

            if not name.lower().endswith(FILE_EXTENSIONS):
                continue

            if not os.path.realpath(path).startswith(real_root + os.sep):
                continue

            yield path


def grep_dir(args: argparse.Namespace, needles: List[str], info: SearchInfo) -> List[dict]:
    rows = []

    for path in iter_dir(args.dir):
        if info["pages_searched"] >= MAX_DIR_FILES:
            info["left_out"] += 1
            continue

        if os.path.getsize(path) > MAX_FILE_BYTES:
            rows.append(not_read(path, f"file above {MAX_FILE_BYTES} bytes"))
            continue

        with open(path, "rb") as handle:
            content = handle.read().decode("utf-8-sig", errors="replace")

        info["pages_searched"] += 1
        segments = segments_of(content, path, kind_of(path, content))
        rows.extend(search_segments(path, segments, needles, args.fuzzy_numbers))

    return rows


def url_list(args: argparse.Namespace, fetcher, info: SearchInfo) -> Tuple[List[str], Optional[str]]:
    if args.urls:
        if not os.path.isfile(args.urls):
            return [], f"no such file: {args.urls}"

        with open(args.urls, encoding="utf-8", errors="replace") as handle:
            urls = [line.strip() for line in handle if line.strip() and not line.startswith("#")]

        return [u for u in urls if re.match(r"^https?://", u, re.I)], None

    loaded = sitemap_mod.load(fetcher, [args.sitemap])
    info["sitemap_errors"] = loaded.errors
    info["left_out"] += loaded.left_out

    if not loaded.urls and loaded.errors:
        return [], f"sitemap not read: {loaded.errors[0]}"

    return [entry.loc for entry in loaded.urls], None


def grep_urls(args: argparse.Namespace, needles: List[str], info: SearchInfo) -> Tuple[List[dict], Optional[str]]:
    """Search the needles in each page of the URL list or sitemap, at most --max-pages.

    Stops when the first page or three in a row are blocked (401/403/429), and says so in info.
    """
    fetcher = fetcher_from_args(args)
    urls, error = url_list(args, fetcher, info)

    if error:
        return [], error

    info["left_out"] += max(0, len(urls) - args.max_pages)
    rows = []
    blocked_streak = 0

    for index, url in enumerate(urls[: args.max_pages]):
        print(f"[{index + 1}/{min(len(urls), args.max_pages)}] {untrusted(url)}", file=sys.stderr)
        response = fetcher.get(url)

        if response.status in BLOCKING_STATUSES:
            blocked_streak += 1
            rows.append(not_read(url, f"HTTP {response.status}: blocked, no workaround attempted"))

            if index == 0 or blocked_streak >= 3:
                info["stopped"] = f"site answered HTTP {response.status}: run stopped"
                info["left_out"] += min(len(urls), args.max_pages) - index - 1
                break

            continue

        blocked_streak = 0

        if not response.ok:
            rows.append(not_read(url, f"HTTP {response.status}" if response.status else str(response.error)))
            continue

        if not response.is_html and not response.content_type.startswith("text/"):
            rows.append(not_read(url, f"content type '{response.content_type}' not searched"))
            continue

        content = response.text()
        kind = "html" if response.is_html else kind_of(url, content)
        info["pages_searched"] += 1
        rows.extend(search_segments(url, segments_of(content, response.final_url, kind), needles, args.fuzzy_numbers))

        if response.truncated:
            rows.append(not_read(url, "response above the size cap: only the first part was searched"))

    return rows, None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find a literal string (an old value) across a content folder, a sitemap or "
                    "a URL list. CSV on stdout. The sitemap page cap is heuristic.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dir", help="local folder of Markdown, HTML or text files (offline)")
    source.add_argument("--sitemap", help="sitemap or sitemap index URL")
    source.add_argument("--urls", help="text file with one URL per line")
    parser.add_argument("--find", action="append", required=True, help="string to find (repeatable)")
    parser.add_argument("--fuzzy-numbers", action="store_true",
                        help="match number variants: separators, decimal comma, currency symbol/code and position")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        help=f"cap on pages fetched with --sitemap/--urls (default {DEFAULT_MAX_PAGES}, heuristic)")
    parser.add_argument("--out", help="write the CSV here instead of stdout")
    add_fetch_arguments(parser)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Search the strings in the folder or the pages, write the CSV and print a summary.

    Returns 0, 2 on bad input, 3 when the site blocked the run.
    """
    args = build_parser().parse_args(argv)
    needles = [n for n in args.find if n.strip()]

    if not needles:
        print("error: give at least one non-empty --find", file=sys.stderr)
        return 2

    info: SearchInfo = {"pages_searched": 0, "left_out": 0, "stopped": None, "sitemap_errors": []}

    if args.dir:
        if not os.path.isdir(args.dir):
            print(f"error: no such folder: {args.dir}", file=sys.stderr)
            return 2

        rows = grep_dir(args, needles, info)
    else:
        if args.sitemap and not re.match(r"^https?://", args.sitemap, re.I):
            print("error: --sitemap needs an http(s) URL", file=sys.stderr)
            return 2

        rows, error = grep_urls(args, needles, info)

        if error:
            print(f"error: {error}", file=sys.stderr)
            return 2

    if info["left_out"]:
        rows.append({"url_or_path": f"({info['left_out']} pages)", "location": "", "string_searched": "",
                     "matched_string": "", "sentence_quoted": "", "result": "left out",
                     "note": "not searched: page cap or stop", "checked_on": today()})

    write_csv(rows, FIELDS, args.out)
    found = sum(1 for row in rows if row["result"] == "found")
    unread = sum(1 for row in rows if row["result"] == "not read")
    print(f"[site_search] {today()}: {found} match(es) in {info['pages_searched']} page(s) searched; "
          f"{unread} not read; {info['left_out']} left out. Static HTML only, no JavaScript run.",
          file=sys.stderr)

    for error in info["sitemap_errors"]:
        print(f"  sitemap: {untrusted(error, 300)}", file=sys.stderr)

    if info["stopped"]:
        print(f"  {untrusted(info['stopped'], 300)}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
