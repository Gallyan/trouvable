#!/usr/bin/env python3
"""Are the city or area pages of a site the same page with the place name swapped?

Reads the main text of each page, replaces every place name given with one token, then
compares pages two by two on shared word sequences (shingles). A pair that stays almost
identical once the place is removed is a lead for the doorway check of
references/city-pages.md; the decision is the reading of the pages, not this ratio.

Usage:
    python3 scripts/city_pages.py --urls city-pages.txt --places "Lyon,Villeurbanne,Bron" --out city.json
    python3 scripts/city_pages.py --file lyon.html --file bron.html --places-file places.txt

Network: GET only through seokit.fetch (robots.txt respected, about 2 requests per second,
size cap). Stops on 401/403/429.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from collections import Counter
from typing import List, Optional, TypedDict

from seokit import report
from seokit.fetch import BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args, read_file_body
from seokit.html import parse_html
from seokit.text import normalize, shingles

MAX_PAGES = 200
# Words of main text compared per page: enough for any real city page, and it keeps the
# pairwise comparison (pages squared) bounded whatever a page weighs.
MAX_WORDS = 20_000
SHINGLE = 5
# Heuristics, to calibrate: a pair above NEAR shares most of its text once places are removed;
# a page under THIN words has little room for anything specific to its place.
NEAR = 0.8
REPORTED_PAIR = 0.5
THIN = 250


class Pair(TypedDict):
    a: str
    b: str
    similarity: float
    near_duplicate: bool


def read_list(path: str) -> List[str]:
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip() and not line.startswith("#")]


def main_text(html: str, url: str) -> tuple:
    page = parse_html(html, url)
    text = page.main_content_text or page.content_text or page.text

    return page, text


def without_places(text: str, places: List[str]) -> str:
    value = normalize(text)

    for place in sorted(places, key=len, reverse=True):
        value = re.sub(rf"(?<!\w){re.escape(normalize(place))}(?!\w)", " lieu ", value)

    return value


def jaccard(left: set, right: set) -> float:
    if not left or not right:
        return 0.0

    return len(left & right) / len(left | right)


def analyse(pages: List[dict], places: List[str], size: int) -> dict:
    """Pairwise similarity of the pages once place names are removed, and per page its unique share and leads.

    Only pairs at or above REPORTED_PAIR are listed, most similar first.
    """
    for page in pages:
        page["_shingles"] = shingles(without_places(page["_text"], places), size)

    seen_on = Counter(item for page in pages for item in page["_shingles"])

    pairs: List[Pair] = []

    for left, right in itertools.combinations(pages, 2):
        score = jaccard(left["_shingles"], right["_shingles"])

        if score >= REPORTED_PAIR:
            pairs.append({"a": report.untrusted(left["url"], 300), "b": report.untrusted(right["url"], 300),
                          "similarity": round(score, 3),
                          "near_duplicate": score >= NEAR})

    rows = []

    for page in pages:
        own = page["_shingles"]
        unique = sum(1 for item in own if seen_on[item] == 1) / len(own) if own else 0.0
        url = report.untrusted(page["url"], 300)
        best = max((pair["similarity"] for pair in pairs if url in (pair["a"], pair["b"])), default=0.0)
        words = len(page["_text"].split())
        leads = []

        if best >= NEAR:
            leads.append("near-duplicate")

        if words < THIN:
            leads.append("thin")

        rows.append({
            "url": url,
            "title_quote": page["title_quote"],
            "h1_quote": page["h1_quote"],
            "places_named": [place for place in places
                             if re.search(rf"(?<!\w){re.escape(normalize(place))}(?!\w)", normalize(page["_text"]))],
            "main_words": words,
            "text_truncated": page["_truncated"],
            "unique_share": round(unique, 3),
            "closest_similarity": best,
            "leads": leads,
        })

    pairs.sort(key=lambda pair: -pair["similarity"])

    return {"pages": rows, "pairs": pairs}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare city or area pages once the place names are removed.")
    parser.add_argument("--urls", help="file with one page URL per line")
    parser.add_argument("--url", action="append", default=[], help="page URL (repeatable)")
    parser.add_argument("--file", action="append", default=[], help="local HTML file (repeatable)")
    parser.add_argument("--places", default="", help="comma-separated place names to neutralise")
    parser.add_argument("--places-file", help="file with one place name per line")
    parser.add_argument("--shingle", type=int, default=SHINGLE, help=f"words per sequence (default {SHINGLE})")
    parser.add_argument("--out", help="write the JSON here instead of stdout")
    add_fetch_arguments(parser)

    return parser


def page_record(html: str, url: str) -> dict:
    """Main text (capped at MAX_WORDS words), title and H1 of a page; keys starting with _ stay internal."""
    page, text = main_text(html, url)
    h1 = next((value for level, value in page.headings if level == "h1"), None)
    words = text.split()

    return {
        "url": url,
        "_text": " ".join(words[:MAX_WORDS]),
        "_truncated": len(words) > MAX_WORDS,
        "title_quote": report.untrusted(page.title, 200),
        "h1_quote": report.untrusted(h1, 200),
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Read the pages, compare them and print or write the JSON; returns 3 when the site blocked the run."""
    args = build_parser().parse_args(argv)

    if args.shingle < 2:
        print("--shingle must be at least 2", file=sys.stderr)
        return 2

    try:
        urls = (read_list(args.urls) if args.urls else []) + args.url
        places = [place.strip() for place in args.places.split(",") if place.strip()]
        places += read_list(args.places_file) if args.places_file else []
        files = []

        for path in args.file[:MAX_PAGES]:
            files.append((path, read_file_body(path, args.max_bytes)))
    except (OSError, ValueError) as error:
        print(f"cannot read input: {error}", file=sys.stderr)
        return 2

    if len(urls) + len(files) < 2:
        print("give at least two pages (--urls, --url or --file)", file=sys.stderr)
        return 2

    fetcher = fetcher_from_args(args)
    pages, not_read, stop = [], [], None

    room = max(0, MAX_PAGES - len(files))

    for url in urls[:room]:
        print(f"reading {report.untrusted(url, 200)}", file=sys.stderr)
        response = fetcher.get(url)

        if response.status in BLOCKING_STATUSES:
            stop = f"site answered HTTP {response.status}: stopped, no workaround attempted"
            not_read.append({"url": url, "reason": f"HTTP {response.status}"})
            break

        if not response.ok or not response.is_html:
            not_read.append({"url": url, "reason": response.error or f"status {response.status}"})
            continue

        pages.append(page_record(response.text(), response.final_url or url))

    pages += [page_record(html, path) for path, html in files]
    not_read += [{"url": url, "reason": f"over the cap of {MAX_PAGES} pages"} for url in urls[room:]]
    not_read += [{"url": path, "reason": f"over the cap of {MAX_PAGES} pages"} for path in args.file[MAX_PAGES:]]
    not_read = [dict(item, url=report.untrusted(item["url"], 300)) for item in not_read]
    result = {
        "generated_on": report.today(),
        "places": places,
        "shingle_words": args.shingle,
        "thresholds": {"near_duplicate": NEAR, "reported_pair": REPORTED_PAIR, "thin_words": THIN,
                       "note": "heuristics, to calibrate: leads for reading, not verdicts"},
        **analyse(pages, places, args.shingle),
        "pages_not_read": not_read,
        "stop_reason": stop,
        "limits": [
            "Main text of the static HTML only: content shown by JavaScript is not compared.",
            "Place names not listed in --places stay in the text and lower the similarity.",
            "Similarity measures shared wording, not usefulness: a near-duplicate pair can still be legitimate, "
            "and a low score does not prove a page is useful.",
        ],
    }

    text = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)

    return 3 if stop else 0


if __name__ == "__main__":
    sys.exit(main())
