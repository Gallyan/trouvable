#!/usr/bin/env python3
"""Is the business's name, address and phone (NAP) the same everywhere it is published?

Compares a reference card (the business as it really is) with what the site states in its
visible text, `tel:` links and JSON-LD, and with directory listings the user copied into a
CSV. Each field gets a status per source: `match`, `differs`, `absent`. Directories are never
fetched: their terms often forbid it and their pages are rendered by JavaScript, so the user
copies what each listing shows.

Usage:
    python3 scripts/nap_check.py --card card.json --site <url> [--url <url>] --out nap.json
    python3 scripts/nap_check.py --card card.json --listings listings.csv --out nap.json
    python3 scripts/nap_check.py --card card.json --file contact.html

card.json: {"name": "...", "street": "...", "postal_code": "...", "city": "...", "phone": "..."}
listings.csv columns: source, url, name, street, postal_code, city, phone

Network: GET only through seokit.fetch (robots.txt respected, about 2 requests per second,
size cap). Stops on 401/403/429.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
from typing import Dict, Iterator, List, Optional, Set

from seokit import report
from seokit.fetch import (BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args, normalize_url,
                          read_file_body, same_site)
from seokit.html import parse_html
from seokit.tables import TableError, read_tables

FIELDS = ("name", "street", "postal_code", "city", "phone")
MAX_PAGES = 8
MAX_JSONLD = 200_000

PAGE_HINT = re.compile(
    r"contact|mentions|legal|a-propos|apropos|about|qui-sommes|acces|nous-trouver|trouver|plan|"
    r"horaires|agence|magasin|boutique|cabinet|imprint",
)

# French numbers: +33 / 0033 / 0, then 9 digits, separated by spaces, dots or dashes.
PHONE = re.compile(r"(?<![\d+])(?:\+33[\s.-]?(?:\(0\)[\s.-]?)?|0033[\s.-]?|0)[1-9](?:[\s.-]?\d{2}){4}(?!\d)")

ABBREVIATIONS = {
    "bd": "boulevard", "bld": "boulevard", "boul": "boulevard", "av": "avenue", "ave": "avenue",
    "r": "rue", "pl": "place", "st": "saint", "ste": "sainte", "imp": "impasse", "ch": "chemin",
    "che": "chemin", "chem": "chemin", "rte": "route", "all": "allee", "fg": "faubourg",
    "fbg": "faubourg", "sq": "square", "crs": "cours", "pass": "passage", "res": "residence",
    "zi": "zone industrielle", "za": "zone artisanale", "zac": "zone d amenagement concerte",
}


def fold(text: Optional[str]) -> str:
    """Casefold, strip accents and punctuation, expand street abbreviations."""
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(char for char in value if not unicodedata.combining(char)).casefold()
    words = re.findall(r"[a-z0-9]+", value)

    return " ".join(ABBREVIATIONS.get(word, word) for word in words)


def phone_key(text: Optional[str]) -> str:
    """'01 23 45 67 89', '+33 1 23 45 67 89', '0033 (0)1…' all give '33123456789'."""
    digits = re.sub(r"\D", "", (text or "").replace("(0)", ""))

    if digits.startswith("0033"):
        digits = digits[4:]
    elif digits.startswith("33") and len(digits) == 11:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        digits = digits[1:]

    return f"33{digits}" if len(digits) == 9 else digits


def contains(haystack: str, needle: str) -> bool:
    if not needle:
        return False

    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def field(status: str, quote: Optional[str] = None) -> dict:
    return {"status": status, "found_quote": report.untrusted(quote, 200) if quote else None}


def compare_value(card_value: str, value: Optional[str], key: str) -> dict:
    if not (value or "").strip():
        return field("absent")

    same = phone_key(value) == phone_key(card_value) if key == "phone" else fold(value) == fold(card_value)

    return field("match" if same else "differs", value)


def flatten(node) -> Iterator[dict]:
    stack = [node]

    while stack:
        item = stack.pop()

        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            yield item
            stack.extend(value for value in item.values() if isinstance(value, (dict, list)))


MAX_TEXT_DEPTH = 20


def text_of(value, depth: int = 0) -> str:
    """Text of a JSON-LD value. Nesting deeper than MAX_TEXT_DEPTH is ignored: json.loads
    accepts far deeper input than this recursion could walk."""
    if depth > MAX_TEXT_DEPTH:
        return ""

    if isinstance(value, list):
        return " ".join(text_of(item, depth + 1) for item in value)

    if isinstance(value, dict):
        return text_of(value.get("name") or value.get("@value") or "", depth + 1)

    return str(value) if value is not None else ""


def jsonld_entities(blocks: List[str]) -> List[dict]:
    """Objects that state an address or a telephone, from every JSON-LD block of the page."""
    entities = []

    for block in blocks:
        try:
            data = json.loads(block[:MAX_JSONLD])
            nodes = list(flatten(data))
        except (ValueError, RecursionError):
            entities.append({"type": "(unparsable JSON-LD)"})
            continue

        for node in nodes:
            if "address" not in node and "telephone" not in node:
                continue

            address = node.get("address")
            address = address[0] if isinstance(address, list) and address else address
            address = address if isinstance(address, dict) else {"streetAddress": text_of(address)}
            entities.append({
                "type": text_of(node.get("@type")) or "(no @type)",
                "name": text_of(node.get("name")),
                "street": text_of(address.get("streetAddress")),
                "postal_code": text_of(address.get("postalCode")),
                "city": text_of(address.get("addressLocality")),
                "phone": text_of(node.get("telephone")),
            })

    return entities


def check_page(card: Dict[str, str], html: str, url: str) -> dict:
    """Compare the card with a page's visible text, tel: links and JSON-LD entities, field by field."""
    page = parse_html(html, url)
    visible = fold(page.text)
    tel_links = [link.href[4:] for link in page.links if link.href.lower().startswith("tel:")]
    phones = PHONE.findall(page.text) + tel_links
    keys = {phone_key(phone) for phone in phones}
    fields = {}

    for key in ("name", "street", "postal_code", "city"):
        fields[key] = field("match", card[key]) if contains(visible, fold(card[key])) else field("absent")

    if phone_key(card["phone"]) in keys:
        fields["phone"] = field("match", card["phone"])
    elif phones:
        fields["phone"] = field("differs", ", ".join(dict.fromkeys(phones)))
    else:
        fields["phone"] = field("absent")

    entities = []

    for entity in jsonld_entities(page.jsonld):
        if "name" not in entity:
            entities.append(entity)
            continue

        entities.append({
            "type": report.untrusted(entity["type"], 80),
            "fields": {key: compare_value(card[key], entity[key], key) for key in FIELDS},
        })

    others = sorted({phone for phone in phones if phone_key(phone) != phone_key(card["phone"])})

    return {
        "kind": "page",
        "url": report.untrusted(url, 300),
        "fields": fields,
        "other_phones": [report.untrusted(phone, 40) for phone in others],
        "jsonld": entities,
    }


def check_listing(card: Dict[str, str], row: Dict[str, str]) -> dict:
    return {
        "kind": "listing",
        "source": report.untrusted(row.get("source", ""), 80),
        "url": report.untrusted(row.get("url", ""), 300),
        "fields": {key: compare_value(card[key], row.get(key), key) for key in FIELDS},
    }


def candidate_pages(site: str, home: str, html: str) -> List[str]:
    """Contact, legal and about pages linked from the home page, on the site the user named
    (a home page that redirects to another host does not move the run there)."""
    page = parse_html(html, home)
    found = []

    for link in page.links:
        if not same_site(link.url, site) or link.href.lower().startswith(("tel:", "mailto:")):
            continue

        target = f"{urllib.parse.urlsplit(link.url).path} {fold(link.text)}".lower()

        if PAGE_HINT.search(target):
            found.append(link.url)

    return found


def load_card(path: str) -> Dict[str, str]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("card must be a JSON object")

    missing = [key for key in FIELDS if not str(data.get(key) or "").strip()]

    if missing:
        raise ValueError(f"card is missing: {', '.join(missing)}")

    return {key: str(data[key]) for key in FIELDS}


def load_listings(path: str) -> List[Dict[str, str]]:
    table = read_tables(path)[0]

    return [{key.strip().lower(): value for key, value in record.items()} for record in table.records()]


def summary(sources: List[dict]) -> dict:
    """Match, differs and absent counts per field over every source and JSON-LD entity, and each difference."""
    counts = {key: {"match": 0, "differs": 0, "absent": 0} for key in FIELDS}
    differs = []

    for source in sources:
        rows = [(source.get("url") or source.get("source"), source["fields"])]
        rows += [(f"{source['url']} JSON-LD {entity['type']}", entity["fields"])
                 for entity in source.get("jsonld", []) if "fields" in entity]

        for where, fields in rows:
            for key, value in fields.items():
                counts[key][value["status"]] += 1

                if value["status"] == "differs":
                    differs.append({"where": where, "field": key, "found_quote": value["found_quote"]})

    return {"counts": counts, "differs": differs}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare a business's name, address and phone across its site and listings.")
    parser.add_argument("--card", required=True, help="JSON reference card: name, street, postal_code, city, phone")
    parser.add_argument("--site",
                        help="home page: read it and up to --max-pages contact, legal and about pages it links to")
    parser.add_argument("--url", action="append", default=[], help="extra page to read (repeatable)")
    parser.add_argument("--file", action="append", default=[], help="local HTML file to read (repeatable)")
    parser.add_argument("--listings", help="CSV of directory listings copied by the user")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    parser.add_argument("--out", help="write the JSON here instead of stdout")
    add_fetch_arguments(parser)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Read the site pages, files and listings, compare each with the card and print or write the JSON.

    Returns 3 when the site blocked the run, 2 on bad input.
    """
    args = build_parser().parse_args(argv)

    if not (args.site or args.url or args.file or args.listings):
        print("give --site, --url, --file or --listings", file=sys.stderr)
        return 2

    try:
        card = load_card(args.card)
        listings = load_listings(args.listings) if args.listings else []
        files = [(path, read_file_body(path, args.max_bytes)) for path in args.file]
    except (OSError, ValueError, TableError) as error:
        print(f"cannot read input: {error}", file=sys.stderr)
        return 2

    fetcher = fetcher_from_args(args)
    sources, not_read, stop = [], [], None
    queue = ([args.site] if args.site else []) + args.url
    seen: Set[str] = set()

    while queue and len(seen) < max(1, args.max_pages) + len(args.url):
        url = queue.pop(0)
        key = normalize_url(url)

        if key in seen:
            continue

        seen.add(key)
        print(f"reading {report.untrusted(url, 200)}", file=sys.stderr)
        response = fetcher.get(url)

        if response.status in BLOCKING_STATUSES:
            stop = f"site answered HTTP {response.status}: stopped, no workaround attempted"
            not_read.append({"url": report.untrusted(url, 300), "reason": f"HTTP {response.status}"})
            break

        if not response.ok or not response.is_html:
            not_read.append({"url": report.untrusted(url, 300),
                             "reason": response.error or f"status {response.status}"})
            continue

        html = response.text()
        sources.append(check_page(card, html, response.final_url or url))

        if args.site and key == normalize_url(args.site):
            queue += candidate_pages(args.site, response.final_url or url, html)[: args.max_pages]

    sources += [check_page(card, html, path) for path, html in files]
    sources += [check_listing(card, row) for row in listings]
    result = {
        "generated_on": report.today(),
        "card": card,
        "sources": sources,
        "summary": summary(sources),
        "pages_not_read": not_read,
        "stop_reason": stop,
        "limits": [
            "Directories are not fetched: listings are what the user copied, `reported`.",
            "Static HTML only: an address or phone shown by JavaScript or in an image is `absent` here.",
            "`absent` on a page means not stated there, which is normal for many pages; "
            "it matters on contact and legal pages.",
            "Phone patterns are French numbers; other formats count as `absent`.",
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
