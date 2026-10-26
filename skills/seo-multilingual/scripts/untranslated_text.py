#!/usr/bin/env python3
"""Flag declared translations whose main text is largely identical to the other language version.

For each pair of declared translations, extracts the main text of the static HTML (headings and
text blocks, menu and footer link labels dropped), then measures the share of identical
sentences in each direction and the word 8-gram overlap (seokit.text.shingles). Detects copied,
untranslated text only: it says nothing about translation quality.

Usage:
    python3 scripts/untranslated_text.py --pairs <csv of url_a,url_b> [--from-hreflang hreflang.json]
                                     [--from-crawl <dir>] [--max-pairs 100] [--format json|csv]
                                     [--out overlap.json]

Network: GET only through seokit.fetch (robots.txt respected, about 2 requests per second, size
cap) for pages not found in --from-crawl. Stops on 401/403/429. --offline fetches nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from seokit import crawl as crawl_mod
from seokit import report
from seokit.fetch import BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args, normalize_url
from seokit.html import parse_html
from seokit.tables import TableError, read_tables
from seokit.text import normalize, sentences, shingles

DEFAULT_MAX_PAIRS = 100
DEFAULT_THRESHOLD = 0.5
DEFAULT_MIN_WORDS = 5
DEFAULT_SHINGLE = 8
SAMPLES = 5
NON_EDITORIAL_ZONES = ("header", "nav", "footer", "widget")
CSV_FIELDS = ["url_a", "url_b", "lang_a", "lang_b", "status", "sentences_a", "sentences_b",
              "identical_share_b_in_a", "identical_share_a_in_b", "shingle_overlap", "verdict",
              "sample_sentence_quote", "generated_on"]


class Blocked(Exception):
    pass


# ---------------------------------------------------------------- pairs

def pairs_from_csv(path: str) -> List[Tuple[str, str, str, str]]:
    """(url_a, url_b) pairs from the first two columns of the first table; a URL header row counts as data."""
    tables = read_tables(path)

    if not tables:
        raise ValueError("no table found in --pairs")

    table = tables[0]
    rows = list(table.rows)

    if table.headers and table.headers[0].strip().lower().startswith("http"):
        rows.insert(0, table.headers)

    pairs = []

    for row in rows:
        cells = [cell.strip() for cell in row]

        if len(cells) >= 2 and cells[0] and cells[1]:
            pairs.append((cells[0], cells[1], "", ""))

    return pairs


def pairs_from_clusters(clusters: List[Dict[str, List[str]]]) -> List[Tuple[str, str, str, str]]:
    """Every pair of distinct URLs inside each cluster; codes joined as the declared language."""
    pairs = []

    for members in clusters:
        urls = sorted(members)

        for i, url_a in enumerate(urls):
            for url_b in urls[i + 1:]:
                pairs.append((url_a, url_b, declared(members[url_a]), declared(members[url_b])))

    return pairs


def declared(codes: List[str]) -> str:
    return ",".join(sorted(c for c in codes if c and c.lower() != "x-default"))


def clusters_from_hreflang_json(path: str) -> List[Dict[str, List[str]]]:
    """Member URLs and codes of each cluster of 2+ URLs in a lang_alternates.py report."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    clusters = []

    for cluster in data.get("clusters", []):
        members = {}

        for member in cluster.get("members", []):
            url = member.get("url")

            if isinstance(url, str) and url.startswith(("http://", "https://")):
                members[url] = [str(c) for c in member.get("codes", [])]

        if len(members) >= 2:
            clusters.append(members)

    return clusters


def clusters_from_crawl(directory: str) -> List[Dict[str, List[str]]]:
    """Group crawled pages by their HTML hreflang alternates."""
    parent: Dict[str, str] = {}
    codes: Dict[str, set] = {}

    def find(key: str) -> str:
        parent.setdefault(key, key)

        while parent[key] != key:
            key = parent[key]

        return key

    for record, html_text in crawl_mod.iter_pages(directory):
        if not html_text:
            continue

        page = parse_html(html_text, record.get("final_url") or record["url"])

        for code, url in page.alternates:
            target = normalize_url(url)
            codes.setdefault(target, set()).add(code)
            parent[find(normalize_url(record["url"]))] = find(target)

    groups: Dict[str, Dict[str, List[str]]] = {}

    for url in list(parent):
        groups.setdefault(find(url), {})[url] = sorted(codes.get(url, set()))

    return [members for members in groups.values() if len(members) >= 2]


# ---------------------------------------------------------------- text

def main_sentences(html_text: str, url: str, min_words: int) -> Tuple[List[str], str, Optional[str]]:
    """Comparable sentences, joined main text, <html lang>."""
    page = parse_html(html_text, url)
    menu_labels = {normalize(link.text) for link in page.links if link.zone in NON_EDITORIAL_ZONES and link.text}
    blocks = [text for _, text in page.headings] + list(page.blocks)
    kept_blocks = [b for b in blocks if normalize(b) not in menu_labels]
    found = []

    for block in kept_blocks:
        for sentence in sentences(block):
            if len(re.findall(r"\w+", sentence)) >= min_words:
                found.append(sentence)

    return found, " ".join(kept_blocks), page.lang


class TextSource:
    """Main text of each URL, read from the crawl when present, else fetched once; stops after 401/403/429."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.cache: Dict[str, dict] = {}
        self.crawl: Dict[str, dict] = {}
        self.fetcher = None if args.offline else fetcher_from_args(args)
        self.blocked = False

        if args.from_crawl:
            _, records = crawl_mod.load_crawl(args.from_crawl)

            for record in records:
                self.crawl[normalize_url(record["url"])] = record

    def get(self, url: str) -> dict:
        key = normalize_url(url)

        if key not in self.cache:
            self.cache[key] = self.load(key)

        return self.cache[key]

    def load(self, url: str) -> dict:
        """Read one URL's main text, or {'read': False, 'reason': ...} when it cannot be read."""
        record = self.crawl.get(url)

        if record is not None:
            html_text = crawl_mod.read_html(self.args.from_crawl, record)

            if html_text is None:
                return {"read": False, "reason": f"in the crawl without HTML (status {record.get('status')})"}

            return self.extract(html_text, record.get("final_url") or url)

        if self.fetcher is None:
            return {"read": False, "reason": "not in the crawl and --offline"}

        if self.blocked:
            return {"read": False, "reason": "run stopped after a 401/403/429"}

        if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
            return {"read": False, "reason": "not an http(s) URL"}

        print(f"fetching {report.untrusted(url)}", file=sys.stderr)
        response = self.fetcher.get(url)

        if response.status in BLOCKING_STATUSES:
            self.blocked = True
            return {"read": False, "reason": f"HTTP {response.status}: stopped, no workaround attempted"}

        if not response.ok or not response.is_html:
            reason = response.error or f"HTTP {response.status} {response.content_type}"
            return {"read": False, "reason": report.untrusted(reason, 120)}

        return self.extract(response.text(), response.final_url)

    def extract(self, html_text: str, url: str) -> dict:
        found, text, lang = main_sentences(html_text, url, self.args.min_words)

        return {"read": True, "sentences": found, "text": text, "lang": lang}


# ---------------------------------------------------------------- comparison

def compare(a: dict, b: dict, args: argparse.Namespace) -> dict:
    """Identical sentences in each direction and n-gram overlap between two texts, with a verdict."""
    set_a = {normalize(s) for s in a["sentences"]}
    set_b = {normalize(s) for s in b["sentences"]}
    shared = set_a & set_b
    shingles_a = shingles(a["text"], args.shingle_size)
    shingles_b = shingles(b["text"], args.shingle_size)
    smaller = min(len(shingles_a), len(shingles_b))
    result: Dict[str, Any] = {
        "sentences_a": len(set_a),
        "sentences_b": len(set_b),
        "identical_sentences": len(shared),
        "identical_share_b_in_a": share(len(shared), len(set_b)),
        "identical_share_a_in_b": share(len(shared), len(set_a)),
        "shingle_overlap": share(len(shingles_a & shingles_b), smaller),
        "evidence": "measured",
    }
    samples = [s for s in b["sentences"] if normalize(s) in shared][:SAMPLES]
    result["identical_sentences_quoted"] = [report.untrusted(s, 300) for s in samples]
    result["verdict"] = verdict(result, args.threshold, smaller)

    return result


def share(part: int, whole: int) -> Optional[float]:
    if not whole:
        return None

    return round(part / whole, 3)


def verdict(result: dict, threshold: float, smaller_shingles: int) -> str:
    """Verdict of a comparison: not measurable, largely identical, some identical sentences, or text differs."""
    if not result["sentences_a"] and not result["sentences_b"] and not smaller_shingles:
        return "not measurable: too little main text"

    scores = [v for v in (result["identical_share_b_in_a"], result["identical_share_a_in_b"],
                          result["shingle_overlap"]) if v is not None]

    if scores and max(scores) >= threshold:
        return "largely identical: likely untranslated"

    if result["identical_sentences"]:
        return "some identical sentences"

    return "text differs"


def same_language(lang_a: str, lang_b: str) -> bool:
    """Whether two language codes share the primary language (en-GB and en-US do)."""
    first_a = re.split(r"[-_,]", (lang_a or "").lower())[0]
    first_b = re.split(r"[-_,]", (lang_b or "").lower())[0]

    return bool(first_a) and first_a == first_b


def check_pair(source: TextSource, pair: Tuple[str, str, str, str], args: argparse.Namespace) -> dict:
    """Compare the main text of a pair of declared translations; 'not read' when either side is missing."""
    url_a, url_b, declared_a, declared_b = pair
    a = source.get(url_a)
    b = source.get(url_b)
    row = {"url_a": report.untrusted(url_a, 2000), "url_b": report.untrusted(url_b, 2000),
           "declared_a": report.untrusted(declared_a, 40), "declared_b": report.untrusted(declared_b, 40),
           "html_lang_a": report.untrusted(a.get("lang"), 40), "html_lang_b": report.untrusted(b.get("lang"), 40)}

    if not a["read"] or not b["read"]:
        row.update({"status": "not read", "reason_a": a.get("reason"), "reason_b": b.get("reason")})
        return row

    row["status"] = "compared"
    row.update(compare(a, b, args))
    lang_a = declared_a or a.get("lang") or ""
    lang_b = declared_b or b.get("lang") or ""

    if same_language(lang_a, lang_b):
        row["note"] = "same declared language on both sides (regional variants): shared text can be expected"

    return row


def csv_row(row: dict) -> dict:
    """One CSV row of a pair result, with the first identical sentence as sample."""
    samples = row.get("identical_sentences_quoted") or []

    return {
        "url_a": row["url_a"], "url_b": row["url_b"],
        "lang_a": row.get("declared_a") or row.get("html_lang_a") or "",
        "lang_b": row.get("declared_b") or row.get("html_lang_b") or "",
        "status": row["status"],
        "sentences_a": row.get("sentences_a"), "sentences_b": row.get("sentences_b"),
        "identical_share_b_in_a": row.get("identical_share_b_in_a"),
        "identical_share_a_in_b": row.get("identical_share_a_in_b"),
        "shingle_overlap": row.get("shingle_overlap"),
        "verdict": row.get("verdict") or row.get("reason_a") or row.get("reason_b"),
        "sample_sentence_quote": samples[0] if samples else "",
        "generated_on": report.today(),
    }


# ---------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Flag declared translations whose main text is largely identical (untranslated copy). "
                    "Does not rate translation quality. Thresholds are heuristic, to calibrate.",
    )
    parser.add_argument("--pairs", help="CSV (or XLSX) whose first two columns are url_a,url_b")
    parser.add_argument("--from-hreflang", help="JSON written by lang_alternates.py: pairs inside each cluster")
    parser.add_argument("--from-crawl", help="seokit crawl directory: page text read from it; without "
                                             "--pairs/--from-hreflang, pairs come from its HTML hreflang tags")
    parser.add_argument("--offline", action="store_true",
                        help="fetch nothing; pages missing from the crawl are 'not read'")
    parser.add_argument("--max-pairs", type=int, default=DEFAULT_MAX_PAIRS,
                        help=f"cap on pairs compared (default {DEFAULT_MAX_PAIRS})")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"identical share or 8-gram overlap from which a pair is flagged "
                             f"(default {DEFAULT_THRESHOLD}, heuristic, to calibrate)")
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS,
                        help=f"sentences shorter than this are ignored (names, labels; default {DEFAULT_MIN_WORDS})")
    parser.add_argument("--shingle-size", type=int, default=DEFAULT_SHINGLE,
                        help=f"word n-gram size for the overlap (default {DEFAULT_SHINGLE})")
    parser.add_argument("--format", choices=("json", "csv"), default="json", help="output format (default json)")
    parser.add_argument("--out", help="write the report to this file instead of stdout")
    add_fetch_arguments(parser)

    return parser


def collect_pairs(args: argparse.Namespace) -> List[Tuple[str, str, str, str]]:
    """Pairs from --pairs, --from-hreflang or else the crawl's hreflang; same-URL and repeated pairs dropped."""
    pairs: List[Tuple[str, str, str, str]] = []

    if args.pairs:
        pairs.extend(pairs_from_csv(args.pairs))

    if args.from_hreflang:
        pairs.extend(pairs_from_clusters(clusters_from_hreflang_json(args.from_hreflang)))

    if args.from_crawl and not (args.pairs or args.from_hreflang):
        pairs.extend(pairs_from_clusters(clusters_from_crawl(args.from_crawl)))

    unique = []
    seen = set()

    for pair in pairs:
        key = tuple(sorted((normalize_url(pair[0]), normalize_url(pair[1]))))

        if key[0] == key[1] or key in seen:
            continue

        seen.add(key)
        unique.append(pair)

    return unique


def validate(args: argparse.Namespace) -> Optional[str]:
    """First problem with the options, or None."""
    if not (args.pairs or args.from_hreflang or args.from_crawl):
        return "give --pairs, --from-hreflang or --from-crawl"

    if args.offline and not args.from_crawl:
        return "--offline needs --from-crawl"

    if args.from_crawl and not os.path.isfile(os.path.join(args.from_crawl, "crawl.json")):
        return f"not a crawl directory: {args.from_crawl}"

    if args.max_pairs < 1 or args.min_words < 1 or args.shingle_size < 1:
        return "--max-pairs, --min-words and --shingle-size must be at least 1"

    return None


def main(argv: Optional[List[str]] = None) -> int:
    """Collect the pairs, compare up to --max-pairs and write the JSON or CSV report.

    Returns 2 on bad input, 3 when the site answered 401/403/429, 0 otherwise."""
    args = build_parser().parse_args(argv)
    problem = validate(args)

    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    try:
        pairs = collect_pairs(args)
        source = TextSource(args)
    except (OSError, ValueError, KeyError, TableError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not pairs:
        print("error: no pair of distinct URLs to compare", file=sys.stderr)
        return 2

    selected = pairs[: args.max_pairs]
    rows = [check_pair(source, pair, args) for pair in selected]

    if args.format == "csv":
        report.write_csv([csv_row(r) for r in rows], CSV_FIELDS, args.out)
    else:
        write_json(build_result(args, rows, len(pairs), source.blocked), args.out)

    return 3 if source.blocked else 0


def build_result(args: argparse.Namespace, rows: List[dict], total: int, blocked: bool) -> dict:
    """The JSON report: thresholds, counts per verdict, limits and the pair rows."""
    limits = [
        "detects copied (untranslated) text only; says nothing about translation quality",
        "main text = headings and text blocks of the static HTML, minus menu/footer link labels; "
        "boilerplate outside those zones may still count",
        f"sentences under {args.min_words} words ignored (names, labels, prices)",
        "regional variants of one language (en-GB / en-US) are expected to share text",
    ]

    if total > len(rows):
        limits.append(f"{total - len(rows)} pair(s) over the cap of {args.max_pairs} not compared")

    if blocked:
        limits.insert(0, "the site answered 401/403/429: the run stopped, remaining pages not read")

    verdicts: Dict[str, int] = {}

    for row in rows:
        key = row.get("verdict") or row["status"]
        verdicts[key] = verdicts.get(key, 0) + 1

    return {
        "generated_on": report.today(),
        "tool": "untranslated_text.py",
        "thresholds": {"threshold": args.threshold, "min_words": args.min_words, "shingle_size": args.shingle_size,
                       "note": "heuristic, design choice of this skill, to calibrate"},
        "summary": {"pairs_found": total, "pairs_compared": sum(1 for r in rows if r["status"] == "compared"),
                    "pairs_not_read": sum(1 for r in rows if r["status"] != "compared"), "verdicts": verdicts},
        "limits": limits,
        "pairs": rows,
    }


def write_json(result: dict, out: Optional[str]) -> None:
    if not out:
        report.emit_json(result)
        return

    with open(out, "w", encoding="utf-8") as handle:
        report.emit_json(result, handle)

    print(f"written {out}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
