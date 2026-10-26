#!/usr/bin/env python3
"""Cut pages into passages (a heading and the text under it) and measure what an AI answer
engine needs to quote one on its own: an opening that answers, no dependency on earlier text,
specific facts, a sensible length. Also lists the page's trust signals (author, dates, about
and contact links, sources, structured data types). Leads only: Claude reads each passage.

Thresholds and word lists are design choices of this skill (heuristic, to calibrate); none of
them is a documented rule of any search engine or assistant.

Usage:
    python3 scripts/passage_scan.py --url <url> [--url <url> ...] --out passages.json
    python3 scripts/passage_scan.py --urls <file> [--max-pages 20] --out passages.json
    python3 scripts/passage_scan.py --from-crawl <dir> [--max-pages 20] --out passages.json
    python3 scripts/passage_scan.py --file page.html [--base-url https://example.com/page] --out passages.json

Network: --url/--urls only, GET through seokit.fetch (robots.txt respected, about 2 requests
per second, size cap); stops on 401/403/429. --from-crawl and --file are offline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple, TypedDict

from seokit import crawl as crawl_mod
from seokit import report
from seokit.fetch import BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args, same_site
from seokit.html import parse_html
from seokit.text import sentences

DEFAULT_MAX_PAGES = 20
SHORT_WORDS = 40
LONG_WORDS = 300
OPENING_MAX_WORDS = 35
LOW_STATIC_WORDS = 150

HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
BLOCKS = {"p", "li", "td", "th", "dd", "dt", "blockquote", "figcaption"}
SKIPPED = {"script", "style", "noscript", "template", "svg", "nav", "header", "footer", "aside",
           "form", "button", "select", "pre", "code"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
CHROME_TOKENS = {"nav", "navbar", "menu", "footer", "sidebar", "breadcrumb", "breadcrumbs", "cookie",
                 "cookies", "share", "related", "comments", "newsletter"}

# Words that make an opening sentence lean on what came before it. Six languages, short and
# conservative lists: a hit is a lead, not a verdict.
REFERENCE_OPENERS = {
    "this", "that", "these", "those", "it", "they", "such", "here", "above", "below",
    "ce", "cet", "cette", "ces", "cela", "ça", "il", "elle", "ils", "elles", "ci-dessus", "ci-dessous",
    "esto", "este", "esta", "estos", "estas", "eso", "ello",
    "dies", "diese", "dieser", "dieses", "es", "sie",
    "questo", "questa", "questi", "queste", "ciò",
    "isso", "isto", "esse", "essa",
}
QUESTION_STARTS = {
    "how", "what", "why", "when", "where", "which", "who", "can", "should", "is", "are", "do", "does",
    "comment", "pourquoi", "quand", "quel", "quelle", "quels", "quelles", "qui", "combien", "faut-il", "est-ce",
    "cómo", "qué", "por", "cuándo", "dónde", "cuál", "wie", "was", "warum", "wann", "wo", "welche",
    "come", "cosa", "perché", "quando", "dove", "quale", "como", "porque", "onde",
}
# Bounded and anchored so that a long run of digits without a unit costs linear time.
FIGURE = re.compile(r"(?<![\d.,])\d[\d\s.,]{0,30}?\s?(%|€|\$|£|eur\b|usd\b|ms\b|s\b|kb\b|mb\b|go\b|gb\b|"
                    r"km\b|kg\b|h\b|min\b|"
                    r"jours?\b|days?\b|mois\b|months?\b|ans?\b|years?\b)|\b(19|20)\d{2}\b|\bv?\d+\.\d+(\.\d+)?\b",
                    re.IGNORECASE)
ABOUT_HINTS = ("about", "a-propos", "apropos", "qui-sommes", "qui-suis", "equipe", "team", "uber-uns",
               "chi-siamo", "sobre", "quienes-somos")
CONTACT_HINTS = ("contact", "kontakt", "contatti", "contacto", "contato")


class PassageParser(HTMLParser):
    """Ordered headings and text blocks of the content, outside navigation and page chrome."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.stack: List[Tuple[str, bool]] = []
        self.skipped = 0
        self.open_count: Dict[str, int] = {}
        self.items: List[dict] = []
        self.current: Optional[dict] = None

    def skipping(self) -> bool:
        return self.skipped > 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        tokens = set(re.split(r"[\s_-]+", f"{values.get('class') or ''} {values.get('id') or ''}".lower()))
        skip = (tag in SKIPPED or "hidden" in values or values.get("aria-hidden") == "true"
                or values.get("role") in ("navigation", "banner", "contentinfo", "complementary")
                or bool(tokens & CHROME_TOKENS))

        if tag not in VOID:
            self.stack.append((tag, skip))
            self.skipped += skip
            self.open_count[tag] = self.open_count.get(tag, 0) + 1

        if self.skipping():
            return

        if tag in HEADINGS or tag in BLOCKS:
            self.flush()
            self.current = {"tag": tag, "text": [], "links": []}

        if tag == "a" and self.current is not None and values.get("href"):
            self.current["links"].append(urllib.parse.urljoin(self.base_url, values["href"]))

        if tag in ("ul", "ol", "table"):
            self.items.append({"tag": tag, "text": "", "links": []})

    def handle_endtag(self, tag):
        if tag in VOID:
            return

        # Counters instead of stack walks keep every event O(1) on pages of unclosed tags.
        while self.open_count.get(tag):
            name, skip = self.stack.pop()
            self.skipped -= skip
            self.open_count[name] -= 1

            if name == tag:
                break

        if tag in HEADINGS or tag in BLOCKS:
            self.flush()

    def handle_data(self, data):
        if self.current is not None and not self.skipping():
            self.current["text"].append(data)

    def flush(self) -> None:
        if self.current is None:
            return

        text = " ".join("".join(self.current["text"]).split())

        if text:
            self.items.append({"tag": self.current["tag"], "text": text, "links": self.current["links"]})

        self.current = None

    def close(self):
        super().close()
        self.flush()


def words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def opens_with_reference(sentence: str) -> bool:
    first = re.findall(r"[\w'-]+", sentence.lower())

    return bool(first) and first[0] in REFERENCE_OPENERS


def is_question(heading: str) -> bool:
    first = re.findall(r"[\w'-]+", heading.lower())

    return heading.rstrip().endswith("?") or (bool(first) and first[0] in QUESTION_STARTS)


class Passage(TypedDict):
    heading: Optional[str]
    level: int
    blocks: List[str]
    links: List[str]
    lists: int
    tables: int


def new_passage(heading: Optional[str], level: int) -> Passage:
    return {"heading": heading, "level": level, "blocks": [], "links": [], "lists": 0, "tables": 0}


def build_passages(items: List[dict], page_url: str) -> List[dict]:
    """Cut the page items into passages, one per heading; passages without text are left out."""
    passages: List[Passage] = []
    current = new_passage(None, 0)

    def close(passage: Passage) -> None:
        if passage["blocks"] or passage["heading"]:
            passages.append(passage)

    for item in items:
        if item["tag"] in HEADINGS:
            close(current)
            current = new_passage(item["text"], HEADINGS[item["tag"]])
        elif item["tag"] in ("ul", "ol"):
            current["lists"] += 1
        elif item["tag"] == "table":
            current["tables"] += 1
        else:
            current["blocks"].append(item["text"])
            current["links"].extend(item["links"])

    close(current)

    return [measure(index, passage, page_url) for index, passage in enumerate(passages, 1) if passage["blocks"]]


def measure(index: int, passage: Passage, page_url: str) -> dict:
    """Size, opening, figures and sources of a passage, with the leads that may make it hard to quote."""
    body = " ".join(passage["blocks"])
    first = (sentences(passage["blocks"][0]) or [passage["blocks"][0]])[0]
    count = words(body)
    sources = sorted({link for link in passage["links"]
                      if link.startswith("http") and not same_site(link, page_url)})
    leads = []

    if opens_with_reference(first):
        leads.append("opening leans on earlier text")

    if words(first) > OPENING_MAX_WORDS:
        leads.append("long opening sentence")

    if count < SHORT_WORDS:
        leads.append("short: may not stand alone")

    if count > LONG_WORDS:
        leads.append("long: consider splitting")

    if not FIGURE.search(body):
        leads.append("no figure, date or version")

    heading = passage["heading"]

    if heading is None:
        leads.append("no heading")

    return {
        "id": f"P{index}",
        "heading_quote": report.untrusted(heading or "", 160),
        "level": passage["level"],
        "heading_is_question": bool(heading and is_question(heading)),
        "words": count,
        "opening_quote": report.untrusted(first, 300),
        "opening_words": words(first),
        "figures": len(FIGURE.findall(body)),
        "lists": passage["lists"],
        "tables": passage["tables"],
        "external_sources": [report.untrusted(link, 200) for link in sources[:10]],
        "leads": leads,
    }


def jsonld_types(page) -> List[str]:
    """Every @type found in the page's JSON-LD, sorted; a block that does not parse adds "(unparsable JSON-LD)"."""
    found = set()

    def walk(node):
        if isinstance(node, dict):
            kind = node.get("@type")
            for value in (kind if isinstance(kind, list) else [kind]):
                if isinstance(value, str):
                    found.add(value)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for raw in page.jsonld:
        try:
            walk(json.loads(raw))
        except (ValueError, RecursionError):
            found.add("(unparsable JSON-LD)")

    return sorted(found)


def trust_signals(page, url: str, raw: str) -> dict:
    """Author, date, about and contact signals of a page, and its structured data types."""
    paths = [urllib.parse.urlsplit(link.url).path.lower() for link in page.links if same_site(link.url, url)]
    types = jsonld_types(page)
    author_links = [link for link in page.links if "author" in (link.rel or "").lower() or link.subtype == "author"]

    return {
        "author_meta_quote": report.untrusted(page.meta_first("author") or "", 120),
        "author_links": len(author_links),
        "author_in_structured_data": any(t in types for t in ("Person", "ProfilePage")) or '"author"' in raw,
        "published_or_modified": [report.untrusted(v, 40) for v in
                                  (page.meta_first("article:published_time"), page.meta_first("article:modified_time"))
                                  if v] + re.findall(r'<time\b[^>]{0,512}?datetime="([^"]{4,40})"', raw)[:3],
        "about_link": any(hint in path for path in paths for hint in ABOUT_HINTS),
        "contact_link": any(hint in path for path in paths for hint in CONTACT_HINTS),
        "structured_data_types": types,
    }


def scan_html(raw: str, url: str) -> dict:
    page = parse_html(raw, url)
    parser = PassageParser(url)
    parser.feed(raw)
    parser.close()
    passages = build_passages(parser.items, url)
    static_words = sum(passage["words"] for passage in passages)

    return {
        "url": url,
        "status": "read",
        "lang": page.lang,
        "title_quote": report.untrusted(page.title or "", 200),
        "static_words": static_words,
        "little_static_text": static_words < LOW_STATIC_WORDS,
        "question_headings": sum(1 for passage in passages if passage["heading_is_question"]),
        "trust_signals": trust_signals(page, url, raw),
        "html_comments_quoted": [report.untrusted(comment, 200) for comment in page.html_comments[:10]],
        "passages": passages,
    }


def not_read(url: str, reason: str) -> dict:
    return {"url": url, "status": "not read", "reason": reason}


def from_network(args) -> Tuple[List[dict], Optional[str]]:
    """Fetch and scan the given URLs up to --max-pages; stops at a blocking status and returns the reason."""
    urls = list(args.url or [])

    if args.urls:
        with open(args.urls, encoding="utf-8") as handle:
            urls += [line.strip() for line in handle if line.strip() and not line.startswith("#")]

    fetcher = fetcher_from_args(args)
    pages, stop = [], None

    for url in urls[:args.max_pages]:
        response = fetcher.get(url)

        if response.status in BLOCKING_STATUSES:
            pages.append(not_read(url, f"HTTP {response.status}"))
            stop = f"site answered HTTP {response.status}: stopped, no workaround attempted"
            break

        if not response.ok or not response.is_html:
            pages.append(not_read(url, response.error or f"status {response.status}, {response.content_type}"))
            continue

        pages.append(scan_html(response.text(), response.final_url or url))

    return pages + [not_read(url, "left out: page cap") for url in urls[args.max_pages:]], stop


def from_crawl(args) -> Tuple[List[dict], Optional[str]]:
    """Scan the HTML pages (status 200) saved by a crawl, up to --max-pages, with the crawl's stop reason."""
    meta, _ = crawl_mod.load_crawl(args.from_crawl)
    pages: List[dict] = []

    for record, raw in crawl_mod.iter_pages(args.from_crawl):
        url = record.get("final_url") or record.get("url") or ""

        if record.get("status") != 200 or not raw:
            continue

        if len(pages) >= args.max_pages:
            pages.append(not_read(url, "left out: page cap"))
            continue

        pages.append(scan_html(raw, url))

    return pages, meta.get("stop_reason")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cut pages into passages and list quotability leads.")
    parser.add_argument("--url", action="append", help="page to read (repeatable)")
    parser.add_argument("--urls", help="file with one URL per line")
    parser.add_argument("--from-crawl", help="seokit crawl directory (offline)")
    parser.add_argument("--file", help="local HTML file (offline)")
    parser.add_argument("--base-url", default="https://example.invalid/", help="public URL of --file")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        help=f"page cap (default {DEFAULT_MAX_PAGES}, heuristic)")
    parser.add_argument("--out", help="write the JSON here instead of stdout")
    add_fetch_arguments(parser)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Scan the pages from one source and print or write the JSON; returns 3 when the site blocked the run."""
    args = build_parser().parse_args(argv)
    sources = [bool(args.url or args.urls), bool(args.from_crawl), bool(args.file)]

    if sum(sources) != 1:
        print("give one source: --url/--urls, --from-crawl or --file", file=sys.stderr)
        return 2

    try:
        if args.file:
            with open(args.file, encoding="utf-8", errors="replace") as handle:
                pages, stop = [scan_html(handle.read(), args.base_url)], None
        elif args.from_crawl:
            pages, stop = from_crawl(args)
        else:
            pages, stop = from_network(args)
    except (OSError, ValueError) as error:
        print(f"cannot read input: {error}", file=sys.stderr)
        return 2

    read = [page for page in pages if page["status"] == "read"]
    result = {
        "generated_on": report.today(),
        "pages_read": len(read),
        "pages_not_read": [page for page in pages if page["status"] != "read"],
        "stop_reason": stop,
        "passages": sum(len(page["passages"]) for page in read),
        "thresholds": {"short_words": SHORT_WORDS, "long_words": LONG_WORDS,
                       "opening_max_words": OPENING_MAX_WORDS, "low_static_words": LOW_STATIC_WORDS,
                       "note": "design choices of this skill, heuristic, to calibrate"},
        "pages": read,
        "limits": [
            "Static HTML only: text added by JavaScript is not seen (little_static_text flags it).",
            "Leads only: whether an opening answers the question, and whether a fact is original, takes reading.",
            "Navigation and page chrome are left out by tag and class name; a few content blocks may be lost.",
        ],
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)

    if stop and any(f"HTTP {code}" in str(stop) for code in BLOCKING_STATUSES):
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
