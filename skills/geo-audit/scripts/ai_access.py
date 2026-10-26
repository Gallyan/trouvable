#!/usr/bin/env python3
"""Can AI assistants reach and quote the site? robots.txt per AI agent, page-level controls,
static text, llms.txt presence.

For each agent token of references/ai-agents.md, reads the site's robots.txt (RFC 9309, via
seokit.robots) and says whether each sampled URL is allowed, with the deciding line. Then
fetches each sampled page with this tool's own user agent and records what limits quoting:
noindex, nosnippet, noarchive, nocache, max-snippet, data-nosnippet, and how much text is in the static HTML.
The agent list is a reading dated in the reference: re-check it before quoting it.

Usage:
    python3 scripts/ai_access.py --site <url> [--urls <file>] [--sample 10] --out access.json
    python3 scripts/ai_access.py --site <url> --robots-file robots.txt --no-pages

Network: GET only through seokit.fetch (robots.txt respected for this tool, about 2 requests
per second, size cap). It never sends a vendor's user agent. Stops on 401/403/429.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from typing import List, Optional, Union

from seokit import report
from seokit import robots as robots_mod
from seokit import sitemap as sitemap_mod
from seokit.fetch import BLOCKING_STATUSES, add_fetch_arguments, fetcher_from_args, normalize_url
from seokit.html import parse_html

DEFAULT_SAMPLE = 10
LOW_STATIC_WORDS = 150

# Read on vendor pages on 2026-10-24 (references/ai-agents.md). Role decides how a block is
# reported: blocking a search agent is a finding, blocking training is a choice.
AGENTS = [
    ("OpenAI", "OAI-SearchBot", "search"),
    ("OpenAI", "GPTBot", "training"),
    ("OpenAI", "ChatGPT-User", "user-triggered"),
    ("Anthropic", "Claude-SearchBot", "search"),
    ("Anthropic", "ClaudeBot", "training"),
    ("Anthropic", "Claude-User", "user-triggered"),
    ("Perplexity", "PerplexityBot", "search"),
    ("Perplexity", "Perplexity-User", "user-triggered"),
    ("Mistral", "MistralAI-Index", "search"),
    ("Mistral", "MistralAI-User", "user-triggered"),
    ("Mistral", "MistralAI-Training", "training"),
    ("Google", "Googlebot", "search"),
    ("Google", "Google-Extended", "control token"),
    ("Microsoft", "Bingbot", "search"),
]


def sample_urls(fetcher, site: str, extra: List[str], size: int) -> List[str]:
    """Up to size URLs: the home page, the given URLs, then sitemap URLs spread evenly; duplicates dropped."""
    urls = [site] + extra

    if len(urls) < size:
        found = sitemap_mod.load(fetcher, sitemap_mod.discover(fetcher, site), max_urls=5000).urls
        locs = [entry.loc for entry in found]
        step = max(1, len(locs) // max(1, size - len(urls)))
        urls += locs[::step]

    seen, ordered = set(), []

    for url in urls:
        key = normalize_url(url)

        if key not in seen:
            seen.add(key)
            ordered.append(url)

    return ordered[:size]


def agent_rows(groups, urls: List[str]) -> List[dict]:
    """For each known AI agent, whether robots.txt lets it fetch each sampled URL, with the blocking lines."""
    rows = []

    for vendor, token, role in AGENTS:
        blocked = []

        for url in urls:
            rule = robots_mod.disallowing_rule(groups, token, url)

            if rule:
                agents, literal = rule
                blocked.append({"url": url, "group": ", ".join(agents), "line_quote": report.untrusted(literal, 160)})

        named = token.lower() in {agent for group in groups for agent in group[0]}
        status = "allowed" if not blocked else ("disallowed" if len(blocked) == len(urls) else "partially disallowed")
        rows.append({
            "vendor": vendor, "token": token, "role": role, "status": status,
            "group_used": token if named else "*",
            "blocked_urls": blocked,
            "finding": role == "search" and bool(blocked),
            "note": "a Disallow for a user-triggered fetcher may not be applied by the vendor"
                    if role == "user-triggered" and blocked else "",
        })

    return rows


def page_controls(response) -> dict:
    """The snippet and indexing controls of a fetched page (meta robots, X-Robots-Tag, data-nosnippet)."""
    page = parse_html(response.text(), response.final_url or response.url)
    raw = response.text()
    header = response.headers.get("x-robots-tag", "").lower()
    directives = f"{page.robots} {header}"
    snippet = re.search(r"max-snippet\s*:\s*(-?\d+)", directives)

    return {
        "url": response.final_url or response.url,
        "status": response.status,
        "noindex": "noindex" in directives,
        "nosnippet": "nosnippet" in directives,
        "noarchive": "noarchive" in directives,
        "nocache": "nocache" in directives,
        "max_snippet": int(snippet.group(1)) if snippet else None,
        "data_nosnippet_elements": len(re.findall(r"\bdata-nosnippet\b", raw, re.IGNORECASE)),
        "robots_directives_quote": report.untrusted(directives.strip(), 200),
        "static_words": page.word_count,
        "little_static_text": page.word_count < LOW_STATIC_WORDS,
        "canonical": page.canonical,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check how AI agents may reach and quote a site.")
    parser.add_argument("--site", required=True, help="home page URL")
    parser.add_argument("--urls", help="file with key URLs to include in the sample, one per line")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE,
                        help=f"URLs checked (default {DEFAULT_SAMPLE}: home, given URLs, then sitemap spread)")
    parser.add_argument("--robots-file", help="local robots.txt to read instead of fetching it")
    parser.add_argument("--no-pages", action="store_true", help="robots.txt only, fetch no page")
    parser.add_argument("--out", help="write the JSON here instead of stdout")
    add_fetch_arguments(parser)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run the check and print or write the JSON; returns 3 when the site blocked the run, 2 on bad input."""
    args = build_parser().parse_args(argv)

    if args.sample < 1:
        print("--sample must be at least 1", file=sys.stderr)
        return 2

    fetcher = fetcher_from_args(args)
    extra = []
    robots_status: Union[str, Optional[int]]

    try:
        if args.urls:
            with open(args.urls, encoding="utf-8") as handle:
                extra = [line.strip() for line in handle if line.strip() and not line.startswith("#")]

        if args.robots_file:
            with open(args.robots_file, encoding="utf-8", errors="replace") as handle:
                robots_text, robots_status = handle.read(), "local file"
        else:
            robots_url = urllib.parse.urljoin(args.site, "/robots.txt")
            response = fetcher.get(robots_url, check_robots=False)
            robots_status = response.status

            if response.status in BLOCKING_STATUSES:
                print(f"robots.txt answered HTTP {response.status}: stopped", file=sys.stderr)
                return 3

            robots_text = response.text() if response.ok else ""
    except OSError as error:
        print(f"cannot read input: {error}", file=sys.stderr)
        return 2

    groups = robots_mod.parse(robots_text)
    urls = [args.site] + extra if args.no_pages else sample_urls(fetcher, args.site, extra, args.sample)
    pages, not_read, stop = [], [], None

    if not args.no_pages:
        for url in urls:
            response = fetcher.get(url)

            if response.status in BLOCKING_STATUSES:
                stop = f"site answered HTTP {response.status}: stopped, no workaround attempted"
                not_read.append({"url": url, "reason": f"HTTP {response.status}"})
                break

            if not response.ok or not response.is_html:
                not_read.append({"url": url, "reason": response.error or f"status {response.status}"})
                continue

            pages.append(page_controls(response))

    llms = None if args.no_pages else fetcher.get(urllib.parse.urljoin(args.site, "/llms.txt")).status
    rows = agent_rows(groups, urls)
    result = {
        "generated_on": report.today(),
        "site": args.site,
        "agents_read_on": "2026-10-24 (references/ai-agents.md): re-check vendor pages before quoting",
        "robots_txt": {"status": robots_status, "groups": len(groups),
                       "text_quote": report.untrusted(robots_text, 1500)},
        "sample": urls,
        "agents": rows,
        "search_agents_blocked": [row["token"] for row in rows if row["finding"]],
        "pages": pages,
        "pages_not_read": not_read,
        "stop_reason": stop,
        "llms_txt_status": llms,
        "limits": [
            "robots.txt says what the site asks; a firewall or CDN may still block agents, which is not visible here.",
            "No vendor user agent is sent: what each assistant actually fetches is not tested.",
            "Static HTML only: how each engine renders JavaScript is not known here.",
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
