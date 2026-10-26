#!/usr/bin/env python3
"""Extract every JSON-LD block from a sample of pages and compare markup with the visible page.

Reads static HTML only (no JavaScript). Sample: a URL list, a sitemap (evenly spread, cap 25
by default) or local HTML files / a build folder. Reports parse errors, @type inventory,
properties present per entity, and the page-vs-markup codes of references/page-vs-markup.md
that a script can compute. Every finding is a lead to confirm by reading the page.
Required properties are NOT checked: they come from the dated policy table built by hand.

Usage:
    python3 scripts/structured_data.py --urls <file|url,url> [--sitemap <url>] [--dir <folder>]
                                    [--max 25] [--base-url <url>] [--out findings.json]

Network: GET only through seokit.fetch (robots.txt respected, about 2 requests per second,
size cap). Stops on 401/403/429 and reports the remaining pages as "not read". No network
with --dir.
"""

from __future__ import annotations

import argparse
import datetime
import html as htmllib
import json
import os
import re
import sys
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Tuple

from seokit import report, sitemap
from seokit.fetch import (BLOCKING_STATUSES, add_fetch_arguments, decode_body, fetcher_from_args,
                          normalize_url)
from seokit.html import Page, parse_html
from seokit.text import find_literal, normalize, shingles

DEFAULT_MAX = 25
DEFAULT_OVERLAP = 0.6
DEFAULT_NGRAM = 3
LEFT_OUT_LISTED = 100

CODES_COMPUTED = ["M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10", "P01", "P05"]
CODES_PARTIAL = {
    "P03": "only visible <time datetime> or <abbr title> dates newer than dateModified are compared",
    "P04": "'template' approximated by the first URL path segment within the sample",
}
CODES_NOT_COMPUTED = {
    "P02": "needs an earlier state of the page; a current price absent from the page is reported as M05",
}

HIDDEN_STYLE = r"display\s*:\s*none|visibility\s*:\s*hidden"
SKIP_TAGS = {"script", "style", "template", "svg"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "param", "source", "track", "wbr"}

# Partial symbol table, used only to say whether a currency is visible. Codes not listed
# are searched as the literal ISO code only.
CURRENCY_SYMBOLS = {
    "EUR": ["€", "euro"],
    "USD": ["$", "us$"],
    "GBP": ["£"],
    "CAD": ["$", "ca$", "c$"],
    "AUD": ["$", "a$", "au$"],
    "CHF": ["fr."],
    "JPY": ["¥", "円"],
    "INR": ["₹"],
}

ORGANIZATION_TYPES = {"Organization", "Corporation", "LocalBusiness", "OnlineStore", "NGO",
                      "EducationalOrganization", "NewsMediaOrganization"}
MAIN_ENTITY_TYPES = {"Product", "Article", "NewsArticle", "BlogPosting", "Recipe", "Event",
                     "Course", "JobPosting", "SoftwareApplication", "Book", "Movie", "Service"}
P05_PROPERTIES = ["name", "headline", "price", "priceCurrency", "ratingValue", "ratingCount",
                  "reviewCount", "datePublished", "dateModified", "telephone"]


# ---------------------------------------------------------------- visible / hidden text

class _VisibilityParser(HTMLParser):
    """Split body text into visible and hidden parts, and collect <time datetime> values.

    Hidden: inside an element with the `hidden` attribute, an inline display:none or
    visibility:hidden style, or <noscript>. script, style, template and svg are skipped.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[Tuple[str, bool]] = []
        self.hidden_count = 0
        self.head_count = 0
        self.open_count: Dict[str, int] = {}
        self.skip = 0
        self.visible: List[str] = []
        self.hidden: List[str] = []
        self.times: List[str] = []

    def _hidden_now(self) -> bool:
        return self.hidden_count > 0

    def handle_starttag(self, tag, attrs):
        """Open an element: note <time datetime> and dated <abbr title>, track hidden and head nesting."""
        attributes = {key.lower(): (value or "") for key, value in attrs}

        if tag in SKIP_TAGS:
            self.skip += 1
            return

        if tag == "time" and attributes.get("datetime") and not self._hidden_now():
            self.times.append(attributes["datetime"].strip())

        # hAtom microformat (<abbr class="published" title="2025-12-30T14:03:07Z">): same role.
        if tag == "abbr" and re.match(r"\d{4}-\d{2}-\d{2}", attributes.get("title", "")) and not self._hidden_now():
            self.times.append(attributes["title"].strip())

        if tag in VOID_TAGS:
            return

        hidden = (
            "hidden" in attributes
            or tag == "noscript"
            or re.search(HIDDEN_STYLE, attributes.get("style", ""), re.I) is not None
        )
        self.stack.append((tag, hidden))
        self.hidden_count += hidden
        self.head_count += tag == "head"
        self.open_count[tag] = self.open_count.get(tag, 0) + 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return

        # Counters instead of stack walks keep every event O(1) on pages of unclosed tags.
        while self.open_count.get(tag):
            name, hidden = self.stack.pop()
            self.hidden_count -= hidden
            self.head_count -= name == "head"
            self.open_count[name] -= 1

            if name == tag:
                break

    def handle_data(self, data):
        if self.skip:
            return

        if self.head_count:
            return

        if self._hidden_now():
            self.hidden.append(data)
            return

        self.visible.append(data)


def split_visibility(html_text: str) -> Tuple[str, str, List[str]]:
    """Visible body text, hidden body text and visible <time>/<abbr> date values of the HTML."""
    parser = _VisibilityParser()

    try:
        parser.feed(html_text)
        parser.close()
    except (AssertionError, ValueError):
        pass

    visible = " ".join(" ".join(parser.visible).split())
    hidden = " ".join(" ".join(parser.hidden).split())

    return visible, hidden, parser.times


# ---------------------------------------------------------------- JSON-LD helpers

def clean_markup_text(value: object) -> str:
    """Markup strings may hold HTML: decode entities, strip tags, collapse spaces."""
    text = htmllib.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)

    return " ".join(text.split())


def type_names(node: dict) -> List[str]:
    """Short @type names of a node (schema.org prefixes and namespaces removed)."""
    raw = node.get("@type")
    values = raw if isinstance(raw, list) else [raw]
    names = []

    for value in values:
        if not isinstance(value, str):
            continue

        names.append(value.rsplit("/", 1)[-1].rsplit(":", 1)[-1])

    return names


def has_type(node: dict, wanted: Iterable[str]) -> bool:
    return bool(set(type_names(node)) & set(wanted))


def as_list(value: object) -> list:
    if value is None:
        return []

    return value if isinstance(value, list) else [value]


def flatten(data: object, path: str = "", out: Optional[List[Tuple[dict, str]]] = None
            ) -> List[Tuple[dict, str]]:
    """Every dict carrying @type, with a readable path. @graph and top-level lists flattened."""
    out = [] if out is None else out

    if isinstance(data, list):
        for item in data:
            flatten(item, path, out)
        return out

    if not isinstance(data, dict):
        return out

    if "@graph" in data:
        flatten(data["@graph"], path, out)

    if "@type" in data:
        out.append((data, path))

    for key, value in data.items():
        if key in ("@graph", "@context"):
            continue

        if isinstance(value, (dict, list)):
            child_path = f"{path} > {key}" if path else key
            flatten(value, child_path, out)

    return out


def scalar(node: dict, key: str) -> Optional[str]:
    """A string, number or integer property as text; None for objects, lists, booleans and absent keys."""
    value = node.get(key)

    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value)

    return None


def name_of(value: object) -> Optional[str]:
    """The name of a person or organization given as text or as an object with a name."""
    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return scalar(value, "name")

    return None


def parse_blocks(page: Page) -> Tuple[List[dict], List[Tuple[dict, str, int]]]:
    """Parse each JSON-LD block of the page: a description per block and every typed node found.

    A block that fails to parse (or nests too deep) is reported with its error and skipped."""
    blocks = []
    nodes: List[Tuple[dict, str, int]] = []

    for index, raw in enumerate(page.jsonld):
        entry: Dict[str, Any] = {"index": index, "parsed": True, "error": None, "types": []}

        # RecursionError: a site can nest a block deep enough to exhaust the decoder or the
        # walker; that block is unparsable, the rest of the run goes on.
        try:
            data = json.loads(raw)
            found = flatten(data)
        except (ValueError, RecursionError) as error:
            entry["parsed"] = False
            entry["error"] = str(error)[:200]
            entry["raw_excerpt_quote"] = report.untrusted(raw, 200)
            blocks.append(entry)
            continue

        for node, path in found:
            nodes.append((node, path, index))

        entry["types"] = sorted({name for node, _ in found for name in type_names(node)})
        blocks.append(entry)

    return blocks, nodes


# ---------------------------------------------------------------- matching helpers

def phrase_overlap(needle: str, haystack: str, size: int) -> float:
    """Share of the needle's word n-grams found in the haystack (pointer only, not a verdict)."""
    words = re.findall(r"\w+", normalize(needle))

    if not words:
        return 0.0

    size = max(1, min(size, len(words)))
    needle_grams = shingles(needle, size)
    hay_grams = shingles(haystack, size)

    if not needle_grams:
        return 0.0

    return round(len(needle_grams & hay_grams) / len(needle_grams), 3)


def contains(haystack: str, needle: str) -> bool:
    return bool(find_literal(haystack, needle, context=0))


def number_forms(value: float, integer_only: bool = False) -> List[str]:
    """Ways a number is commonly written: 1234.5 → 1234.50, 1234,50, 1 234,50, 1,234.50…"""
    forms = set()
    whole = abs(value - round(value)) < 1e-9

    if whole:
        number = int(round(value))
        forms.update({str(number), f"{number:,}", f"{number:,}".replace(",", " "),
                      f"{number:,}".replace(",", ".")})

        if integer_only:
            return sorted(forms)

    for decimals in (2, 1):
        text = f"{value:.{decimals}f}"
        grouped = f"{value:,.{decimals}f}"
        forms.add(text)
        forms.add(text.replace(".", ","))
        forms.add(grouped)
        forms.add(grouped.replace(",", " ").replace(".", ","))
        forms.add(grouped.replace(",", "#").replace(".", ",").replace("#", "."))

    return sorted(forms)


def number_visible(text: str, value: float, integer_only: bool = False) -> Optional[str]:
    """The first written form of value found in text, with digit boundaries, or None."""
    hay = normalize(text)

    for form in number_forms(value, integer_only):
        pattern = r"(?<![\d.,])" + re.escape(form) + r"(?![\d]|[.,]\d)"
        match = re.search(pattern, hay)

        if match:
            left = max(0, match.start() - 40)

            return hay[left: match.end() + 40]

    return None


def to_number(value: object) -> Optional[float]:
    """A markup number as float, accepting a decimal comma; None for booleans and non-numbers."""
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(" ", "")

    try:
        return float(text)
    except ValueError:
        pass

    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def currency_visible(text: str, code: str) -> bool:
    """Whether the currency code, or one of its symbols, appears in the text."""
    hay = normalize(text)

    if re.search(r"(?<![a-z])" + re.escape(code.lower()) + r"(?![a-z])", hay):
        return True

    return any(symbol in hay for symbol in CURRENCY_SYMBOLS.get(code.upper(), []))


def date_forms(value: str) -> List[str]:
    """Numeric ways an ISO date is commonly written (ISO, d/m/y, m/d/y, d.m.y, d-m-y)."""
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())

    if not match:
        return [value.strip()]

    year, month, day = match.groups()
    d, m = str(int(day)), str(int(month))
    forms = {f"{year}-{month}-{day}"}

    for dd, mm in ((day, month), (d, m)):
        forms.add(f"{dd}/{mm}/{year}")
        forms.add(f"{mm}/{dd}/{year}")
        forms.add(f"{dd}.{mm}.{year}")
        forms.add(f"{dd}-{mm}-{year}")

    return sorted(forms)


MONTHS = {
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
           "octobre", "novembre", "décembre"],
    "en": ["january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december"],
}


def textual_date_forms(value: str) -> List[str]:
    """'2025-12-30' → '30 décembre 2025', 'december 30, 2025', '30 december 2025'; the first
    of the month also as '1er janvier'. French and English month names only."""
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())

    if not match or not 1 <= int(match.group(2)) <= 12:
        return []

    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    fr, en = MONTHS["fr"][month - 1], MONTHS["en"][month - 1]
    forms = [f"{day} {fr} {year}", f"{en} {day}, {year}", f"{en} {day} {year}", f"{day} {en} {year}"]

    if day == 1:
        forms.append(f"1er {fr} {year}")

    return forms


def date_visible(value: str, visible: str, times: List[str]) -> bool:
    """Whether a markup date appears in a visible <time>, or in the visible text as a numeric or textual date."""
    day = value.strip()[:10]

    if any(t.strip().startswith(day) for t in times):
        return True

    if any(contains(visible, form) for form in date_forms(value)):
        return True

    text = normalize(visible)

    return any(re.search(r"(?<!\d)" + re.escape(normalize(form)) + r"(?!\d)", text)
               for form in textual_date_forms(value))


def parse_day(value: str) -> Optional[datetime.date]:
    """The date at the start of an ISO date or date-time string, or None."""
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", (value or "").strip())

    if not match:
        return None

    try:
        return datetime.date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def comparable_url(url: str) -> str:
    return normalize_url(url).rstrip("/")


# ---------------------------------------------------------------- findings

def finding(code: str, severity: str, node: Optional[dict], prop: str, markup_value: object,
            visible: Optional[str], note: str, **extra) -> dict:
    """One finding as reported, with quoted markup and visible values, marked as a lead to confirm."""
    item = {
        "code": code,
        "severity": severity,
        "entity_type": ", ".join(type_names(node)) if node else None,
        "property": prop,
        "markup_value_quote": report.untrusted(clean_markup_text(markup_value)) if markup_value is not None else None,
        "visible_quote": report.untrusted(visible) if visible else "absent from static HTML visible text",
        "note": note,
        "status": "lead: confirm by reading the page",
    }
    item.update(extra)

    return item


class Context:
    """What the checks of one page share: the parsed page, visible and hidden text, options, findings."""

    def __init__(self, page: Page, url: str, visible: str, hidden: str, times: List[str],
                 args: argparse.Namespace, has_url: bool) -> None:
        self.page = page
        self.url = url
        self.visible = visible
        self.hidden = hidden
        self.times = times
        self.args = args
        self.has_url = has_url
        self.findings: List[dict] = []

    def add(self, item: dict) -> None:
        self.findings.append(item)


def check_faq(ctx: Context, nodes: List[Tuple[dict, str, int]]) -> None:
    """M02-M04 and P01: FAQ questions and answers not visible, visible questions missing from the markup."""
    markup_questions = []

    for node, _, _ in nodes:
        if not has_type(node, ["Question"]):
            continue

        question = clean_markup_text(node.get("name") or node.get("text") or "")

        if question:
            markup_questions.append(question)
            check_question(ctx, node, question)

        for key in ("acceptedAnswer", "suggestedAnswer"):
            for answer in as_list(node.get(key)):
                if isinstance(answer, dict):
                    check_answer(ctx, node, answer)

    if any(has_type(node, ["FAQPage"]) for node, _, _ in nodes):
        check_visible_questions(ctx, markup_questions)


def check_question(ctx: Context, node: dict, question: str) -> None:
    """M02: a marked-up question absent from the visible text, noting when it is only hidden."""
    if contains(ctx.visible, question):
        return

    note = "question text not found in the visible static HTML"

    if contains(ctx.hidden, question):
        note = "question found only in hidden content (hidden attribute, display:none or noscript)"

    ctx.add(finding("M02", "error", node, "name", question, None, note))


def check_answer(ctx: Context, question_node: dict, answer: dict) -> None:
    """M03/M04: an answer not found literally, scored by n-gram overlap with the visible and hidden text."""
    text = clean_markup_text(answer.get("text") or "")

    if not text or contains(ctx.visible, text):
        return

    size = ctx.args.ngram
    visible_score = phrase_overlap(text, ctx.visible, size)
    hidden_score = phrase_overlap(text, ctx.hidden, size) if ctx.hidden else 0.0
    threshold = ctx.args.min_overlap

    if visible_score < threshold and (contains(ctx.hidden, text) or hidden_score >= threshold):
        ctx.add(finding("M04", "warning", question_node, "acceptedAnswer.text", text, None,
                        "answer present only in hidden content of the static HTML",
                        overlap_visible=visible_score, overlap_hidden=hidden_score))
        return

    severity = "warning" if visible_score < threshold else "info"
    note = (f"answer not found literally; word {size}-gram overlap with visible text "
            f"{visible_score} (threshold {threshold}, heuristic, to calibrate). "
            "Low overlap is a lead, not a finding, until read; JS-loaded answers are invisible here.")
    ctx.add(finding("M03", severity, question_node, "acceptedAnswer.text", text, None, note,
                    overlap_visible=visible_score))


def visible_question_candidates(page: Page) -> List[str]:
    """Distinct headings and blocks of the page that end with '?' (10 to 200 characters)."""
    texts = [text for _, text in page.headings] + list(page.blocks)
    found = []

    for text in texts:
        cleaned = " ".join(text.split())

        if cleaned.endswith("?") and 10 <= len(cleaned) <= 200 and cleaned not in found:
            found.append(cleaned)

    return found


def check_visible_questions(ctx: Context, markup_questions: List[str]) -> None:
    """P01: visible question-like texts that no marked-up question matches."""
    marked = [normalize(q) for q in markup_questions]

    for candidate in visible_question_candidates(ctx.page):
        norm = normalize(candidate)

        if any(norm in q or q in norm for q in marked):
            continue

        ctx.add(finding("P01", "info", None, "FAQPage.mainEntity", None, candidate,
                        "visible question-like heading or block not present in the FAQ markup"))


def check_prices(ctx: Context, nodes: List[Tuple[dict, str, int]]) -> None:
    """M05: prices that are not numbers or not visible in common written forms, and currencies not shown."""
    for node, _, _ in nodes:
        currency = scalar(node, "priceCurrency")

        for key in ("price", "lowPrice", "highPrice"):
            raw = node.get(key)

            if raw is None or isinstance(raw, (dict, list)):
                continue

            amount = to_number(raw)

            if amount is None:
                ctx.add(finding("M05", "error", node, key, raw, None, "price in markup is not a number"))
                continue

            seen = number_visible(ctx.visible, amount)

            if not seen:
                note = "amount not found in the visible text in common written forms"

                if number_visible(ctx.hidden, amount):
                    note += "; found in hidden content"

                ctx.add(finding("M05", "error", node, key, raw, None, note))

        if currency and not currency_visible(ctx.visible, currency):
            ctx.add(finding("M05", "error", node, "priceCurrency", currency, None,
                            "currency code or its symbol not found in the visible text "
                            "(symbol table partial; confirm by reading)"))


def check_ratings(ctx: Context, nodes: List[Tuple[dict, str, int]]) -> None:
    for node, _, _ in nodes:
        if has_type(node, ["AggregateRating"]):
            check_rating_figures(ctx, node, ["ratingValue", "ratingCount", "reviewCount"])

        if has_type(node, ["Review"]):
            check_review(ctx, node)


def check_rating_figures(ctx: Context, node: dict, keys: List[str]) -> None:
    """M06/M07: rating figures none of which is visible, or one missing while another is visible."""
    present = {}

    for key in keys:
        amount = to_number(node.get(key)) if not isinstance(node.get(key), (dict, list)) else None

        if amount is None:
            continue

        integer_only = key != "ratingValue"
        present[key] = (node.get(key), number_visible(ctx.visible, amount, integer_only))

    if not present:
        return

    if not any(seen for _, seen in present.values()):
        ctx.add(finding("M06", "error", node, ", ".join(present), "; ".join(str(v) for v, _ in present.values()),
                        None, "no rating figure of this markup is visible on the page"))
        return

    for key, (value, seen) in present.items():
        if not seen:
            ctx.add(finding("M07", "error", node, key, value, None,
                            "this rating figure is not visible while another figure of the same rating is"))


def check_review(ctx: Context, node: dict) -> None:
    """M06: a review whose rating or body text is not visible."""
    rating = node.get("reviewRating")

    if isinstance(rating, dict):
        check_rating_figures(ctx, rating, ["ratingValue"])

    body = clean_markup_text(node.get("reviewBody") or "")

    if not body or contains(ctx.visible, body):
        return

    score = phrase_overlap(body, ctx.visible, ctx.args.ngram)

    if score < ctx.args.min_overlap:
        ctx.add(finding("M06", "error", node, "reviewBody", body, None,
                        f"review text not visible (overlap {score}, heuristic)", overlap_visible=score))


def check_bylines(ctx: Context, nodes: List[Tuple[dict, str, int]]) -> None:
    """M08 and P03: author and publisher names, published and modified dates not found on the page."""
    for node, _, _ in nodes:
        for key in ("author", "publisher"):
            for person in as_list(node.get(key)):
                name = name_of(person)

                if name and not contains(ctx.visible, clean_markup_text(name)):
                    ctx.add(finding("M08", "warning", node, f"{key}.name", name, None,
                                    f"{key} name not found in the visible text"))

        for key in ("datePublished", "dateModified"):
            value = scalar(node, key)

            if value and not date_visible(value, ctx.visible, ctx.times):
                ctx.add(finding("M08", "warning", node, key, value, None,
                                "date not found as ISO, numeric or French/English textual date, nor in a "
                                "visible <time datetime> or <abbr title>: confirm by reading",
                                confidence="low"))

        check_modified_vs_visible(ctx, node)


def check_modified_vs_visible(ctx: Context, node: dict) -> None:
    """P03: a visible <time> newer than dateModified."""
    modified = parse_day(scalar(node, "dateModified") or "")

    if not modified:
        return

    newer = sorted({t for t in ctx.times if (parse_day(t) or modified) > modified})

    if newer:
        ctx.add(finding("P03", "info", node, "dateModified", scalar(node, "dateModified"), ", ".join(newer),
                        "a visible <time datetime> is newer than dateModified"))


def check_organizations(ctx: Context, nodes: List[Tuple[dict, str, int]]) -> None:
    """M09: organization name, telephone, email, logo or sameAs profiles not found on the page."""
    link_urls = {comparable_url(link.url) for link in ctx.page.links if link.url}
    image_urls = {comparable_url(image.src) for image in ctx.page.images if image.src}
    compact_visible = re.sub(r"[\s.\-()/]", "", ctx.visible)

    for node, _, _ in nodes:
        types = set(type_names(node))

        if not (types & ORGANIZATION_TYPES or any(t.endswith("Business") for t in types)):
            continue

        name = scalar(node, "name")

        if name and not contains(ctx.visible, clean_markup_text(name)):
            ctx.add(finding("M09", "warning", node, "name", name, None, "organization name not in the visible text"))

        phone = scalar(node, "telephone")

        if phone and re.sub(r"[\s.\-()/]", "", phone) not in compact_visible:
            ctx.add(finding("M09", "warning", node, "telephone", phone, None, "telephone not in the visible text"))

        email = scalar(node, "email")

        if email and not contains(ctx.visible, email.replace("mailto:", "")):
            ctx.add(finding("M09", "warning", node, "email", email, None, "email not in the visible text"))

        logo = node.get("logo")
        logo_url = logo if isinstance(logo, str) else (scalar(logo, "url") if isinstance(logo, dict) else None)

        if logo_url and ctx.has_url and comparable_url(urllib.parse.urljoin(ctx.url, logo_url)) not in image_urls:
            ctx.add(finding("M09", "info", node, "logo", logo_url, None,
                            "logo URL not used by an <img> on this page (may be shown elsewhere)"))

        for profile in as_list(node.get("sameAs")):
            if isinstance(profile, str) and comparable_url(profile) not in link_urls:
                ctx.add(finding("M09", "info", node, "sameAs", profile, None,
                                "profile not linked from this page (compare with the footer or about page)"))


def check_main_entity(ctx: Context, nodes: List[Tuple[dict, str, int]]) -> None:
    """M10: a top-level main entity whose name is not visible, or whose url points to another page."""
    for node, path, _ in nodes:
        if path or not has_type(node, MAIN_ENTITY_TYPES):
            continue

        label = scalar(node, "name") or scalar(node, "headline")
        title = ctx.page.title or ""

        if label and not contains(ctx.visible, clean_markup_text(label)) and not contains(title, label):
            ctx.add(finding("M10", "warning", node, "name", label, None,
                            "main entity name not visible: the markup may describe another entity than the page"))

        if not ctx.has_url:
            continue

        for key in ("url", "mainEntityOfPage"):
            value = node.get(key)
            target = value if isinstance(value, str) else (value.get("@id") if isinstance(value, dict) else None)

            if not isinstance(target, str) or not target.startswith("http"):
                continue

            if comparable_url(target) != comparable_url(ctx.url):
                ctx.add(finding("M10", "warning", node, key, target, ctx.url,
                                "markup points to another URL than the page"))


def check_duplicates(ctx: Context, nodes: List[Tuple[dict, str, int]]) -> None:
    """P05: nodes for the same entity (same type and @id or name) that disagree on a property."""
    groups: Dict[Tuple[str, str], List[dict]] = {}

    for node, _, _ in nodes:
        types = type_names(node)
        key_value = node.get("@id") if isinstance(node.get("@id"), str) else scalar(node, "name")

        if not types or not key_value:
            continue

        groups.setdefault((types[0], normalize(key_value)), []).append(node)

    for (entity_type, _), members in groups.items():
        if len(members) < 2:
            continue

        for prop in P05_PROPERTIES:
            values = {v for v in (comparable_value(m, prop) for m in members) if v is not None}

            if len(values) > 1:
                ctx.add(finding("P05", "warning", members[0], prop, " | ".join(sorted(values)), None,
                                f"{len(members)} {entity_type} nodes for the same entity disagree on {prop}"))


def comparable_value(node: dict, prop: str) -> Optional[str]:
    """A property of a node, or of its offers or aggregateRating, as text for comparison."""
    value = scalar(node, prop)

    if value is not None:
        return value

    for child_key in ("offers", "aggregateRating"):
        for child in as_list(node.get(child_key)):
            if isinstance(child, dict) and scalar(child, prop) is not None:
                return scalar(child, prop)

    return None


def entity_summary(node: dict, path: str, block: int) -> dict:
    """Inventory entry of one typed node: block, types, path, @id, name and properties present."""
    ident = node.get("@id") if isinstance(node.get("@id"), str) else None

    return {
        "block": block,
        "types": type_names(node),
        "path": path or "(top level)",
        "id_text": report.untrusted(ident) if ident else None,
        "name_text": report.untrusted(scalar(node, "name") or scalar(node, "headline")),
        "properties_present": sorted(k for k in node if not k.startswith("@")),
    }


def analyse_page(html_text: str, url: str, args: argparse.Namespace, has_url: bool) -> dict:
    """Parse one page and run every page-vs-markup check; return the page's inventory and findings."""
    page = parse_html(html_text, url)
    visible, hidden, times = split_visibility(html_text)
    blocks, nodes = parse_blocks(page)
    ctx = Context(page, url, visible, hidden, times, args, has_url)

    for block in blocks:
        if not block["parsed"]:
            ctx.add({"code": "M01", "severity": "error", "block": block["index"],
                     "error_text": report.untrusted(block["error"]),
                     "markup_value_quote": block.get("raw_excerpt_quote"),
                     "note": "JSON-LD block does not parse"})

    check_faq(ctx, nodes)
    check_prices(ctx, nodes)
    check_ratings(ctx, nodes)
    check_bylines(ctx, nodes)
    check_organizations(ctx, nodes)
    check_main_entity(ctx, nodes)
    check_duplicates(ctx, nodes)

    return {
        "status": "read",
        "title_text": report.untrusted(page.title),
        "lang": report.untrusted(page.lang, 40),
        "blocks": blocks,
        "types": sorted({t for node, _, _ in nodes for t in type_names(node)}),
        "entities": [entity_summary(node, path, block) for node, path, block in nodes],
        "findings": ctx.findings,
        "visible_words": len(visible.split()),
        "hidden_words": len(hidden.split()),
        "html_comments_quoted": [report.untrusted(c, 200) for c in page.html_comments[:20]],
    }


def check_templates(pages: List[dict]) -> None:
    """P04: a page lacking a type that most read siblings (same first path segment) carry."""
    groups: Dict[str, List[dict]] = {}

    for page in pages:
        if page.get("status") != "read" or not page["url"].startswith("http"):
            continue

        segments = [s for s in urllib.parse.urlsplit(page["url"]).path.split("/") if s]

        if len(segments) < 2:
            continue

        groups.setdefault(segments[0], []).append(page)

    for prefix, members in groups.items():
        if len(members) < 3:
            continue

        for page in members:
            others = [m for m in members if m is not page]

            for entity_type in sorted({t for m in others for t in m["types"]}):
                share = sum(1 for m in others if entity_type in m["types"]) / len(others)

                if share >= 0.5 and entity_type not in page["types"]:
                    page["findings"].append({
                        "code": "P04", "severity": "info", "entity_type": entity_type,
                        "note": f"{round(share * 100)}% of sampled sibling pages under /{prefix}/ carry "
                                f"{entity_type}; this page does not",
                        "status": "lead: confirm by reading the page",
                    })


# ---------------------------------------------------------------- sampling and input

def spread(items: List[str], cap: int) -> List[str]:
    """Up to `cap` items evenly spread over the list, first and last included."""
    if len(items) <= cap:
        return list(items)

    if cap <= 0:
        return []

    if cap == 1:
        return items[:1]

    indexes = sorted({round(i * (len(items) - 1) / (cap - 1)) for i in range(cap)})

    return [items[i] for i in indexes]


def read_url_list(value: str) -> List[str]:
    """URLs from a file (one per line, '#' comments skipped) or from a comma-separated value."""
    if os.path.isfile(value):
        with open(value, encoding="utf-8", errors="replace") as handle:
            lines = [line.strip() for line in handle]

        return [line for line in lines if line and not line.startswith("#")]

    return [part.strip() for part in value.split(",") if part.strip()]


def local_files(path: str) -> List[str]:
    """HTML files under path. Symbolic links are skipped, so a downloaded build folder
    cannot make the run read files outside it."""
    if os.path.isfile(path):
        return [path]

    found = []
    top = os.path.realpath(path)

    for root, dirs, files in os.walk(path):
        dirs.sort()

        for name in sorted(files):
            full = os.path.join(root, name)

            if os.path.islink(full) or not os.path.realpath(full).startswith(top + os.sep):
                continue

            if name.lower().endswith((".html", ".htm")):
                found.append(full)

    return found


def file_url(path: str, root: str, base_url: Optional[str]) -> str:
    """The URL a local file stands for: under --base-url when given, else a file:// URL."""
    if not base_url:
        return "file://" + os.path.abspath(path)

    relative = os.path.relpath(path, root if os.path.isdir(root) else os.path.dirname(root))
    relative = relative.replace(os.sep, "/")

    if relative.endswith("index.html"):
        relative = relative[: -len("index.html")]

    return urllib.parse.urljoin(base_url.rstrip("/") + "/", relative)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract JSON-LD from a page sample and compare markup with the visible static "
                    "HTML (codes M01-M10, P01-P05 of references/page-vs-markup.md). Read-only. "
                    "Findings are leads to confirm by reading the page; required properties are "
                    "not checked (see the dated policy table).",
    )
    parser.add_argument("--urls", help="file with one URL per line, or comma-separated URLs")
    parser.add_argument("--sitemap", help="sitemap URL: the sample is spread evenly over its URLs")
    parser.add_argument("--dir", help="local HTML file or build folder (no network)")
    parser.add_argument("--base-url", help="with --dir: public URL of the folder root, used for URL checks")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX,
                        help=f"sample cap (default {DEFAULT_MAX}, heuristic, design choice to calibrate)")
    parser.add_argument("--min-overlap", type=float, default=DEFAULT_OVERLAP,
                        help=f"phrase overlap under which an answer is a lead (default {DEFAULT_OVERLAP}, "
                             "heuristic, to calibrate)")
    parser.add_argument("--ngram", type=int, default=DEFAULT_NGRAM,
                        help=f"word n-gram size for the overlap score (default {DEFAULT_NGRAM})")
    parser.add_argument("--out", help="write the JSON report to this file instead of stdout")
    add_fetch_arguments(parser)

    return parser


def collect_candidates(args: argparse.Namespace, fetcher) -> Tuple[List[str], List[str], dict]:
    """User-given URLs and the sitemap URLs not among them, with what the sitemap reading reported."""
    given = unique(read_url_list(args.urls)) if args.urls else []
    from_sitemap: List[str] = []
    info: dict = {}

    if args.sitemap:
        loaded = sitemap.load(fetcher, [args.sitemap])
        info = {"sitemap_files": loaded.files, "sitemap_errors_text": [report.untrusted(e) for e in loaded.errors],
                "sitemap_truncated": loaded.truncated}
        from_sitemap = [url for url in unique(e.loc for e in loaded.urls) if url not in given]

    return given, from_sitemap, info


def unique(items: Iterable[str]) -> List[str]:
    seen: List[str] = []

    for item in items:
        if item not in seen:
            seen.append(item)

    return seen


def run_network(args: argparse.Namespace) -> Tuple[List[dict], dict, bool]:
    """Fetch the sample (given URLs first, then sitemap URLs spread evenly) and analyse each page.

    After a 401/403/429 the remaining pages are listed as not read. Raises ValueError on bad or no URLs."""
    fetcher = fetcher_from_args(args)
    given, from_sitemap, info = collect_candidates(args, fetcher)
    candidates = given + from_sitemap
    bad = [u for u in candidates if urllib.parse.urlsplit(u).scheme not in ("http", "https")]

    if bad:
        raise ValueError(f"not an http(s) URL: {bad[0][:100]}")

    if not candidates:
        raise ValueError("no URL to check (empty list or unreadable sitemap)")

    # User-given URLs come first; sitemap URLs fill the rest of the cap, evenly spread.
    selected = given[: args.max] + spread(from_sitemap, max(0, args.max - len(given)))
    info.update(sample_info(candidates, selected, args.max))
    pages: List[Dict[str, Any]] = []
    blocked = False

    for url in selected:
        if blocked:
            pages.append({"url": report.untrusted(url, 2000), "status": "not read",
                          "reason": "run stopped after a 401/403/429"})
            continue

        print(f"fetching {report.untrusted(url)}", file=sys.stderr)
        response = fetcher.get(url)
        entry = {"url": report.untrusted(url, 2000), "final_url": report.untrusted(response.final_url, 2000),
                 "http_status": response.status}

        if response.status in BLOCKING_STATUSES:
            blocked = True
            entry.update({"status": "not read",
                          "reason": f"HTTP {response.status}: stopped, no workaround attempted"})
        elif not response.ok:
            reason = response.error or f"HTTP {response.status}"
            entry.update({"status": "not read", "reason": report.untrusted(reason)})
        elif not response.is_html:
            entry.update({"status": "not read", "reason": f"not HTML ({report.untrusted(response.content_type, 60)})"})
        else:
            entry.update(analyse_page(response.text(), response.final_url, args, True))
            entry["truncated"] = response.truncated

        pages.append(entry)

    return pages, info, blocked


def run_local(args: argparse.Namespace) -> Tuple[List[dict], dict]:
    """Analyse a sample of local HTML files (no network). Raises ValueError when there is none."""
    if not os.path.exists(args.dir):
        raise ValueError(f"no such file or folder: {args.dir}")

    files = local_files(args.dir)

    if not files:
        raise ValueError("no .html file found")

    selected = spread(files, args.max)
    info = sample_info(files, selected, args.max)
    pages = []

    for path in selected:
        url = file_url(path, args.dir, args.base_url)
        print(f"reading {path}", file=sys.stderr)

        with open(path, "rb") as handle:
            raw = handle.read(args.max_bytes)

        entry = {"url": report.untrusted(url, 2000), "file": path}
        entry.update(analyse_page(decode_body(raw), url, args, bool(args.base_url)))
        pages.append(entry)

    return pages, info


def sample_info(candidates: List[str], selected: List[str], cap: int) -> dict:
    """How the sample was drawn: counts, cap, method and the first candidates left out."""
    left_out = [c for c in candidates if c not in selected]

    return {
        "candidates": len(candidates),
        "selected": len(selected),
        "cap": cap,
        "method": "all candidates" if not left_out else "evenly spread over the candidate list",
        "left_out_count": len(left_out),
        "left_out": [report.untrusted(u, 2000) for u in left_out[:LEFT_OUT_LISTED]],
    }


def summarise(pages: List[dict]) -> dict:
    """Counts over the pages: read or not, blocks, parse errors, findings per code, pages per type."""
    by_code: Dict[str, int] = {}
    types: Dict[str, int] = {}

    for page in pages:
        for item in page.get("findings", []):
            by_code[item["code"]] = by_code.get(item["code"], 0) + 1

        for entity_type in page.get("types", []):
            types[entity_type] = types.get(entity_type, 0) + 1

    return {
        "pages_selected": len(pages),
        "pages_read": sum(1 for p in pages if p.get("status") == "read"),
        "pages_not_read": sum(1 for p in pages if p.get("status") != "read"),
        "blocks": sum(len(p.get("blocks", [])) for p in pages),
        "parse_errors": by_code.get("M01", 0),
        "findings_by_code": dict(sorted(by_code.items())),
        "pages_per_type": dict(sorted(types.items())),
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Read the sample (network or --dir), run the checks and write the JSON report.

    Returns 2 on bad input, 3 when the site answered 401/403/429, 0 otherwise."""
    args = build_parser().parse_args(argv)

    if not (args.urls or args.sitemap or args.dir):
        print("error: give --urls, --sitemap or --dir", file=sys.stderr)
        return 2

    if args.max < 1:
        print("error: --max must be at least 1", file=sys.stderr)
        return 2

    blocked = False

    try:
        if args.dir:
            pages, info = run_local(args)
            mode = "local files"
        else:
            pages, info, blocked = run_network(args)
            mode = "network"
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    check_templates(pages)
    limits = [
        "static HTML only: markup or text injected by JavaScript is not seen",
        "required properties are not checked: they come from the dated policy table "
        "(references/policy-table.md), not from this script",
        "no Google eligibility decision, no judgement on review authenticity",
        "visible text excludes script, style, template, svg, and elements hidden by the hidden "
        "attribute, inline display:none / visibility:hidden or noscript; CSS classes are not evaluated",
        "every finding is a lead: confirm on the page, both directions",
    ]

    if blocked:
        limits.insert(0, "the site answered 401/403/429: the run stopped; later pages are not read")

    result = {
        "generated_on": report.today(),
        "tool": "structured_data.py",
        "mode": mode,
        "sample": info,
        "summary": summarise(pages),
        "thresholds": {"min_overlap": args.min_overlap, "ngram": args.ngram,
                       "note": "heuristic, design choice of this skill, to calibrate"},
        "codes_computed": CODES_COMPUTED,
        "codes_partial": CODES_PARTIAL,
        "codes_not_computed": CODES_NOT_COMPUTED,
        "limits": limits,
        "pages": pages,
    }

    write_output(result, args.out)

    return 3 if blocked else 0


def write_output(result: dict, out: Optional[str]) -> None:
    if not out:
        report.emit_json(result)
        return

    with open(out, "w", encoding="utf-8") as handle:
        report.emit_json(result, handle)

    print(f"written {out}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
