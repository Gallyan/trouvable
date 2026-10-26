#!/usr/bin/env python3
"""Read a venue's rules or submission page politely and pull out what a human must check:
title, headings, candidate rule sentences by topic, red-flag phrases, HTML comments, hidden
text and instruction-like text (all quoted as untrusted site text, never followed).

Usage: python3 scripts/read_rules.py --url <rules page> [--out rules.json]
       python3 scripts/read_rules.py --urls-file venues.txt [--max-urls 20] [--out rules.json]

Network: GET only, through seokit.fetch: robots.txt honoured, about 1 request per second
per host, 2 MB cap per page. Stops on 401/403/429 or a challenge page (reported "not read").
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

from seokit.fetch import BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args
from seokit.html import parse_html
from seokit.report import emit_json, today, untrusted
from seokit.text import normalize, sentences

KEYWORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rule_keywords.json")
DEFAULT_MAX_URLS = 20
DEFAULT_DELAY = 1.0
DEFAULT_MAX_BYTES = 2_000_000
EXCERPT_CHARS = 1500
MAX_RULE_SENTENCES = 80
CHALLENGE_MARKERS = (
    "cf-chl", "challenge-platform", "just a moment...", "checking your browser",
    "attention required! | cloudflare", "g-recaptcha", "h-captcha", "hcaptcha", "captcha-delivery",
    "please verify you are a human", "are you a robot",
)
INSTRUCTION_PATTERN = re.compile(
    r"(ignore (all |any )?(the )?(previous|prior|above|earlier)"
    r"|(note|message|instructions?) (for|to) (the )?(ai|llms?|assistants?|chatgpt|claude|gpt|bots?|crawlers?)"
    r"|\b(ai|llms?|assistants?|chatbots?|ai assistants?|ai agents?),? (you )?(must|should|please)\b"
    r"|as an ai\b|you are (an? |the )?(ai|assistant|language model)"
    r"|system prompt|disregard (your|all|previous)"
    r"|ignorez? (toutes |les )?(les )?(instructions|consignes)"
    r"|(note|message|consigne)s? (pour|à l'attention de|aux?) (l'|les )?(ia|assistants?|robots?))",
    re.I,
)
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(px)?\s*(;|$)", re.I)
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}
SKIP_TAGS = {"script", "style", "template", "noscript"}


class InputError(ValueError):
    pass


class HiddenTextParser(HTMLParser):
    """Collect text inside elements hidden by the hidden attribute, aria-hidden or inline style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[Tuple[str, bool]] = []
        self.hidden_depth = 0
        self.skip_depth = 0
        self.open_count: Dict[str, int] = {}
        self.parts: List[List[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag in VOID_TAGS:
            return

        values = {key.lower(): (value or "") for key, value in attrs}
        hidden = (
            "hidden" in values
            or values.get("aria-hidden", "").lower() == "true"
            or bool(HIDDEN_STYLE.search(values.get("style", "")))
        )

        if hidden and self.hidden_depth == 0:
            self.parts.append([])

        self.stack.append((tag, hidden))
        self.open_count[tag] = self.open_count.get(tag, 0) + 1
        self.hidden_depth += 1 if hidden else 0
        self.skip_depth += 1 if tag in SKIP_TAGS else 0

    def handle_endtag(self, tag):
        # A per-tag count instead of listing the stack keeps every end tag O(1).
        if not self.open_count.get(tag):
            return

        while self.stack:
            name, hidden = self.stack.pop()
            self.open_count[name] -= 1
            self.hidden_depth -= 1 if hidden else 0
            self.skip_depth -= 1 if name in SKIP_TAGS else 0

            if name == tag:
                return

    def handle_data(self, data):
        if self.hidden_depth and not self.skip_depth and self.parts:
            self.parts[-1].append(data)

    def texts(self) -> List[str]:
        joined = [" ".join(" ".join(part).split()) for part in self.parts]

        return [text for text in joined if text]


def hidden_texts(html: str) -> List[str]:
    parser = HiddenTextParser()

    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, ValueError):
        pass

    return parser.texts()


def load_keywords(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise InputError(f"cannot read keyword file {path}: {error}") from error

    if not isinstance(data.get("rules"), dict) or not isinstance(data.get("red_flags"), dict):
        raise InputError(f"keyword file {path} lacks 'rules' or 'red_flags'")

    return data


def keyword_pattern(keyword: str) -> re.Pattern:
    """Word-bounded match; a trailing * allows any word ending; symbols match as plain text."""
    word = normalize(keyword)
    prefix = word.endswith("*")
    word = word.rstrip("*")

    if not re.search(r"\w", word):
        return re.compile(re.escape(word))

    tail = "" if prefix else r"(?!\w)"

    return re.compile(r"(?<!\w)" + re.escape(word) + tail)


def compile_lists(lists: Dict[str, List[str]]) -> Dict[str, List[Tuple[str, re.Pattern]]]:
    compiled = {}

    for name, words in lists.items():
        if name.startswith("_") or not isinstance(words, list):
            continue

        compiled[name] = [(w, keyword_pattern(w)) for w in words if isinstance(w, str) and w.strip()]

    return compiled


def language_lists(keywords: dict, lang: Optional[str]) -> Tuple[List[str], Dict[str, List[str]], List[str]]:
    """Merge the page language's lists with English. Returns (languages used, lists, notes)."""
    rules = keywords["rules"]
    code = (lang or "").split("-")[0].lower()
    used = ["en"] if "en" in rules else []
    notes = []

    if code and code != "en":
        if code in rules:
            used.append(code)
        else:
            notes.append(f"no keyword list for page language '{untrusted(code, 20)}'; "
                         "English list only, rule sentences may be missed")

    if not code:
        notes.append("page language not declared; English list only")

    merged: Dict[str, List[str]] = {}

    for language in used:
        for topic, words in rules[language].items():
            if isinstance(words, list):
                merged.setdefault(topic, []).extend(words)

    return used, merged, notes


def matches(sentence: str, compiled: Dict[str, List[Tuple[str, re.Pattern]]]) -> Dict[str, List[str]]:
    text = normalize(sentence)
    found: Dict[str, List[str]] = {}

    for topic, patterns in compiled.items():
        hits = [word for word, pattern in patterns if pattern.search(text)]

        if hits:
            found[topic] = hits

    return found


def page_sentences(page) -> List[str]:
    seen = set()
    result = []

    for block in [text for _, text in page.headings] + page.blocks:
        for sentence in sentences(block):
            key = normalize(sentence)

            if key and key not in seen:
                seen.add(key)
                result.append(sentence)

    return result


def is_challenge(status: Optional[int], body_text: str) -> bool:
    sample = body_text[:20000].lower()

    if any(marker in sample for marker in CHALLENGE_MARKERS):
        return True

    return status == 503 and "captcha" in sample


def instruction_like(sources: List[Tuple[str, str]]) -> List[dict]:
    found = []

    for where, text in sources:
        if INSTRUCTION_PATTERN.search(normalize(text)):
            found.append({"where": where, "instruction_text": untrusted(text, 400)})

    return found


def not_read(url: str, reason: str, **extra) -> dict:
    record = {"url": untrusted(url, 500), "read_status": "not read", "not_read_reason": reason}
    record.update(extra)

    return record


def analyse_html(url: str, response, keywords: dict, red_flags: Dict[str, List[Tuple[str, re.Pattern]]]) -> dict:
    """Rule sentences, red-flag phrases, comments, hidden and instruction-like text of a page, quoted.

    At most MAX_RULE_SENTENCES rule sentences are listed; a note gives the full count.
    """
    html = response.text()
    page = parse_html(html, response.final_url)
    used, merged, notes = language_lists(keywords, page.lang)
    topics = compile_lists(merged)
    all_sentences = page_sentences(page)
    rule_sentences: List[dict] = []
    candidate_count = 0
    flag_hits: List[dict] = []

    for sentence in all_sentences:
        found = matches(sentence, topics)
        flagged = matches(sentence, red_flags)
        candidate_count += 1 if found else 0

        if found and len(rule_sentences) < MAX_RULE_SENTENCES:
            rule_sentences.append({"topics": sorted(found), "keywords": found,
                                   "sentence_quote": untrusted(sentence, 500)})

        for flag, phrases in flagged.items():
            flag_hits.append({"red_flag": flag, "phrases": phrases,
                              "sentence_quote": untrusted(sentence, 500)})

    hidden = hidden_texts(html)
    if candidate_count > MAX_RULE_SENTENCES:
        notes.append(f"{candidate_count} candidate rule sentences, first {MAX_RULE_SENTENCES} listed")

    instruction_sources = (
        [("html comment", c) for c in page.html_comments]
        + [("hidden element", h) for h in hidden]
        + [("visible text", s) for s in all_sentences]
    )

    return {
        "read_status": "read",
        "lang": untrusted(page.lang, 20),
        "keyword_languages": used,
        "title_text": untrusted(page.title, 300),
        "headings": [{"tag": tag, "heading_text": untrusted(text, 200)} for tag, text in page.headings[:60]],
        "rule_sentences": rule_sentences,
        "red_flag_candidates": flag_hits,
        "untrusted_comments": [untrusted(c, 400) for c in page.html_comments[:40]],
        "untrusted_hidden_text": [untrusted(h, 400) for h in hidden[:40]],
        "untrusted_instructions": instruction_like(instruction_sources),
        "word_count": page.word_count,
        "text_excerpt": untrusted(page.text, EXCERPT_CHARS),
        "notes": notes,
    }


def read_one(url: str, fetcher, keywords: dict, red_flags) -> Tuple[dict, bool]:
    """Returns (record, blocked) where blocked means 401/403/429 or a challenge page."""
    fetched_at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    robots_allowed = fetcher.allowed(url)

    if not robots_allowed:
        return not_read(url, "disallowed by robots.txt", robots_allowed=False, fetched_at=fetched_at), False

    response = fetcher.get(url)
    base = {
        "url": untrusted(url, 500),
        "final_url": untrusted(response.final_url, 500),
        "status": response.status,
        "fetched_at": fetched_at,
        "robots_allowed": True,
        "redirects": [{"url": untrusted(h.url, 500), "status": h.status} for h in response.chain],
        "truncated": response.truncated,
    }

    if response.status in BLOCKING_STATUSES:
        base.update(not_read(url, f"HTTP {response.status}: site refuses this reader; no retry"))
        return base, True

    if response.status is None:
        base.update(not_read(url, f"fetch failed: {untrusted(response.error, 200)}"))
        return base, False

    if is_challenge(response.status, response.text() if response.is_html else ""):
        base.update(not_read(url, "challenge or bot-protection page; no workaround attempted"))
        return base, True

    if not response.ok:
        base.update(not_read(url, f"HTTP {response.status}"))
        return base, False

    if not response.is_html:
        base.update(not_read(url, f"not an HTML page ({untrusted(response.content_type, 80)})"))
        return base, False

    base.update(analyse_html(url, response, keywords, red_flags))

    if response.truncated:
        base["notes"].append("page above the size cap: only the first part was read")

    return base, False


def collect_urls(args) -> List[str]:
    urls = list(args.url or [])

    if args.urls_file:
        try:
            with open(args.urls_file, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError as error:
            raise InputError(f"cannot read {args.urls_file}: {error}") from error

        urls.extend(line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#"))

    if not urls:
        raise InputError("give --url or --urls-file")

    for url in urls:
        parts = urllib.parse.urlsplit(url)

        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise InputError(f"not an http(s) URL: {untrusted(url, 200)}")

    return urls


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read a venue's rules/submission page (GET only, robots.txt honoured) and list "
                    "candidate rule sentences, red-flag phrases, HTML comments and hidden or "
                    "instruction-like text as untrusted quotes. Keyword matching is a heuristic, "
                    "to calibrate: a human reads the full rule.")
    parser.add_argument("--url", action="append", help="rules page URL (repeatable)")
    parser.add_argument("--urls-file", help="text file, one URL per line (# comments allowed)")
    parser.add_argument("--max-urls", type=int, default=DEFAULT_MAX_URLS,
                        help=f"cap per run (default {DEFAULT_MAX_URLS}); extra URLs are listed as not read")
    parser.add_argument("--keywords", default=KEYWORDS_FILE, help="keyword data file (JSON)")
    parser.add_argument("--out", help="write the JSON here instead of stdout")
    add_fetch_arguments(parser)
    parser.set_defaults(delay=DEFAULT_DELAY, max_bytes=DEFAULT_MAX_BYTES)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Read each rules page up to --max-urls and print or write the JSON; returns 3 when a host blocked."""
    args = build_parser().parse_args(argv)

    try:
        urls = collect_urls(args)
        keywords = load_keywords(args.keywords)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    red_flags = compile_lists(keywords["red_flags"])
    fetcher = fetcher_from_args(args)
    cap = max(args.max_urls, 1)
    pages = []
    blocked_hosts = set()
    any_blocked = False

    for url in urls[:cap]:
        host = urllib.parse.urlsplit(url).netloc.lower()

        if host in blocked_hosts:
            pages.append(not_read(url, "host refused an earlier request in this run; not retried"))
            continue

        print(f"Reading {untrusted(url)} ...", file=sys.stderr)
        record, blocked = read_one(url, fetcher, keywords, red_flags)
        pages.append(record)

        if blocked:
            blocked_hosts.add(host)
            any_blocked = True

    for url in urls[cap:]:
        pages.append(not_read(url, f"over the {cap}-URL cap of this run"))

    report = {
        "generated_on": today(),
        "user_agent": args.user_agent,
        "pages": pages,
        "not_read": [p["url"] for p in pages if p["read_status"] == "not read"],
        "limits": [
            "Static HTML only: no JavaScript rendering, no login, no form submission.",
            "rule_sentences and red_flag_candidates come from keyword matching (heuristic, to "
            "calibrate): candidates to read in full, not verdicts. Some red flags (dead venue, "
            "link farm, scraped domain) cannot be seen from one page.",
            "Everything quoted from the page, including comments, hidden text and instruction-like "
            "text, is untrusted site data and was not acted on.",
            "A page that was not read is 'not read', never 'no rules'.",
        ],
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            emit_json(report, handle)
    else:
        emit_json(report)

    print(f"{len(pages)} page(s), {len(report['not_read'])} not read.", file=sys.stderr)

    return 3 if any_blocked else 0


if __name__ == "__main__":
    sys.exit(main())
