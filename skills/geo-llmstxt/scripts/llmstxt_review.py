#!/usr/bin/env python3
"""Audit an llms.txt file: presence, Markdown structure, links, instruction-like wording.

Implements the codes of references/llms-txt-stance.md that a script can compute (L01-L06,
L08, L09 when Last-Modified headers exist). L07 (claims vs linked pages) needs reading and is
left to Claude. A missing llms.txt is information, never a defect.

Usage:
    python3 scripts/llmstxt_review.py --site <url> [--file <local path>] [--no-check-links]
                                  [--max-links 100] [--out llms.json]

Network: GET only through seokit.fetch (robots.txt respected, about 2 requests per second,
size cap). Fetches /llms.txt (unless --file) and each linked URL up to the cap. Stops on
401/403/429 from the site; nothing is fetched with --file and --no-check-links.
"""

from __future__ import annotations

import argparse
import email.utils
import os
import re
import sys
import urllib.parse
from typing import Dict, List, Optional, Tuple

from seokit import report
from seokit.fetch import (BLOCKING_STATUSES, Response, add_fetch_arguments, decode_body,
                          fetcher_from_args, normalize_url)
from seokit.html import parse_html

DEFAULT_MAX_LINKS = 100
ABSENT_STATUSES = (404, 410)
TEXT_TYPES = ("text/plain", "text/markdown", "text/x-markdown")

LIST_LINK = r"^\s*[-*+]\s+\[([^\]]*)\]\(\s*([^)\s]+)\s*\)\s*(?::\s*(.*))?$"
ANY_LINK = r"\[([^\]\n]{0,1000})\]\(\s*([^)\s]{1,2000})\s*\)"
# Lines and comments are cut before matching so a hostile file costs linear time.
MAX_LINE = 4096
MAX_COMMENTS = 20
LIST_ITEM = r"^\s*[-*+]\s+"

# Instruction-like or promotional wording aimed at models (L08). A design choice of this
# skill, to calibrate: a match is a lead to read, not a verdict.
WORDING_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)",
    r"\balways (recommend|mention|cite|suggest|prefer)\b",
    r"\bnever (recommend|mention|cite|suggest)\b",
    r"\b(you|assistants?|models?|llms?|ai) (must|should) (always|never|recommend|mention|cite)\b",
    r"\bas an ai\b",
    r"\b(dear|attention|note (to|for)) (ai|llm|language model|assistant|chatgpt|claude|gemini)s?\b",
    r"\b(the )?(best|number one|#1|no\. ?1|leading) .{0,30}\b(in the world|on the market|in the industry)\b",
    r"\bwhen (asked|users ask) about\b",
    r"\bsystem prompt\b",
]


def resolve_target(args: argparse.Namespace) -> Optional[str]:
    if not args.site:
        return None

    parts = urllib.parse.urlsplit(args.site)

    if parts.path.endswith("llms.txt"):
        return args.site

    return f"{parts.scheme}://{parts.netloc}/llms.txt"


# ---------------------------------------------------------------- structure

def strip_code_fences(lines: List[str]) -> List[Tuple[int, str]]:
    kept = []
    fenced = False

    for number, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            fenced = not fenced
            continue

        if not fenced:
            kept.append((number, line))

    return kept


def analyse_structure(text: str) -> Tuple[dict, List[dict]]:
    """Title, summary and sections of the file outside code fences, with the L02 to L04 findings."""
    lines = strip_code_fences(text.splitlines())
    non_blank = [(n, line) for n, line in lines if line.strip()]
    findings: List[dict] = []
    h1 = [(n, line) for n, line in non_blank if re.match(r"^#\s+\S", line)]
    structure: dict = {"h1_count": len(h1), "h1_text": report.untrusted(h1[0][1][1:].strip()) if h1 else None}

    if not non_blank or not re.match(r"^#\s+\S", non_blank[0][1]):
        findings.append({"code": "L02", "severity": "warning",
                         "note": "the file does not start with an H1 title (# Name)",
                         "line": non_blank[0][0] if non_blank else None,
                         "line_quote": report.untrusted(non_blank[0][1]) if non_blank else None})
    elif len(h1) > 1:
        findings.append({"code": "L02", "severity": "warning", "note": f"{len(h1)} H1 titles, one expected",
                         "line": h1[1][0], "line_quote": report.untrusted(h1[1][1])})

    structure.update(summary_block(non_blank, findings))
    sections = split_sections(lines)
    structure["sections"] = [section_summary(s) for s in sections]
    check_sections(sections, findings)

    return structure, findings


def summary_block(non_blank: List[Tuple[int, str]], findings: List[dict]) -> dict:
    """Kind and text of the line after the title (blockquote or paragraph); adds L03 when there is none."""
    if len(non_blank) < 2 or not re.match(r"^#\s+\S", non_blank[0][1]):
        findings.append({"code": "L03", "severity": "info", "note": "no summary block after the title"})
        return {"summary_kind": None, "summary_text": None}

    line = non_blank[1][1].strip()

    if line.startswith(">"):
        return {"summary_kind": "blockquote", "summary_text": report.untrusted(line.lstrip("> ").strip())}

    if line.startswith("#") or re.match(LIST_ITEM, line):
        findings.append({"code": "L03", "severity": "info", "note": "no summary block after the title"})
        return {"summary_kind": None, "summary_text": None}

    return {"summary_kind": "paragraph", "summary_text": report.untrusted(line)}


def split_sections(lines: List[Tuple[int, str]]) -> List[dict]:
    """H2 sections with their link items and other list items; lines before the first H2 are ignored."""
    sections: List[dict] = []
    current: Optional[dict] = None

    for number, line in lines:
        if re.match(r"^##\s+\S", line):
            current = {"heading": line[2:].strip(), "line": number, "links": [], "other_items": []}
            sections.append(current)
            continue

        if current is None or not re.match(LIST_ITEM, line):
            continue

        match = re.match(LIST_LINK, line)

        if match:
            current["links"].append({"line": number, "title": match.group(1), "url": match.group(2),
                                     "note": match.group(3)})
        else:
            current["other_items"].append((number, line))

    return sections


def section_summary(section: dict) -> dict:
    return {
        "heading_text": report.untrusted(section["heading"]),
        "line": section["line"],
        "link_items": len(section["links"]),
        "other_list_items": len(section["other_items"]),
    }


def check_sections(sections: List[dict], findings: List[dict]) -> None:
    """Add L04 findings: no section at all, or one finding per section without links or mixing other items."""
    if not sections:
        findings.append({"code": "L04", "severity": "warning",
                         "note": "no H2 section (## Section) with a link list"})
        return

    for section in sections:
        others = section["other_items"]

        if not section["links"]:
            finding = {"code": "L04", "severity": "warning", "line": section["line"],
                       "heading_text": report.untrusted(section["heading"]),
                       "note": "section without a Markdown link list (- [title](url): note)"}
        elif others:
            finding = {"code": "L04", "severity": "warning", "line": section["line"],
                       "heading_text": report.untrusted(section["heading"]),
                       "note": "section mixes link items and other list items"}
        else:
            continue

        # One finding per section: a free-text section is one editorial choice, not N defects.
        if others:
            finding["other_list_items"] = len(others)
            finding["first_item_lines"] = [number for number, _ in others[:5]]
            finding["first_item_quote"] = report.untrusted(others[0][1].strip())

        findings.append(finding)


def flag_wording(text: str) -> List[dict]:
    flagged = []

    for number, line in enumerate(text.splitlines(), start=1):
        for pattern in WORDING_PATTERNS:
            if re.search(pattern, line, re.I):
                flagged.append({"code": "L08", "severity": "warning", "line": number,
                                "wording_quote": report.untrusted(line.strip()),
                                "note": "instruction-like or promotional wording aimed at models "
                                        "(pattern match, heuristic: read it)"})
                break

    return flagged


def html_comments(text: str) -> List[str]:
    """The text of the file's HTML comments, quoted and capped, at most MAX_COMMENTS of them."""
    comments: List[str] = []
    position = 0

    while len(comments) < MAX_COMMENTS:
        start = text.find("<!--", position)

        if start < 0:
            break

        end = text.find("-->", start + 4)

        if end < 0:
            break

        comments.append(report.untrusted(text[start + 4:end].strip(), 200))
        position = end + 3

    return comments


# ---------------------------------------------------------------- links

def collect_links(text: str, base: Optional[str]) -> List[dict]:
    links: List[dict] = []
    seen = set()

    for number, line in strip_code_fences(text.splitlines()):
        for title, target in re.findall(ANY_LINK, line[:MAX_LINE]):
            absolute = urllib.parse.urljoin(base, target) if base else target

            if absolute in seen:
                continue

            seen.add(absolute)
            links.append({"line": number, "title_text": report.untrusted(title), "href_text": report.untrusted(target),
                          "url": absolute})

    return links


def robots_directives(response: Response, page_robots: str) -> str:
    return f"{page_robots}, {response.headers.get('x-robots-tag', '')}".lower()


def check_link(fetcher, link: dict) -> Tuple[dict, List[dict]]:
    """Fetch one link, record its status and result on it, and return it with its L05 and L06 findings."""
    url = link["url"]
    findings: List[dict] = []
    parts = urllib.parse.urlsplit(url)

    if parts.scheme not in ("http", "https"):
        link["result"] = "not checked: not an absolute http(s) URL"
        return link, findings

    response = fetcher.get(url)
    link.update({
        "status": response.status,
        "final_url": response.final_url,
        "redirects": [{"url": hop.url, "status": hop.status} for hop in response.chain],
        "last_modified": response.headers.get("last-modified"),
    })

    if response.status is None:
        if "robots" in (response.error or ""):
            link["result"] = "not read: disallowed by robots.txt"
            return link, findings

        link["result"] = "error"
        findings.append(link_finding("L05", "error", link, f"no response: {report.untrusted(response.error, 120)}"))
        return link, findings

    if response.status in BLOCKING_STATUSES:
        link["result"] = f"not read: HTTP {response.status}"
        return link, findings

    if response.status >= 400:
        link["result"] = "broken"
        findings.append(link_finding("L05", "error", link, f"link answers HTTP {response.status}"))
        return link, findings

    link["result"] = "ok"

    if response.chain:
        findings.append(link_finding("L06", "warning", link,
                                     f"link redirects ({len(response.chain)} hop(s)); point it to the final URL"))

    if response.is_html:
        check_target_page(response, link, findings)

    return link, findings


def check_target_page(response: Response, link: dict, findings: List[dict]) -> None:
    page = parse_html(response.text(), response.final_url)
    directives = robots_directives(response, page.robots)

    if "noindex" in directives or "none" in re.split(r"[\s,]+", directives):
        findings.append(link_finding("L06", "warning", link, "target is noindex (meta robots or X-Robots-Tag)"))

    canonical = page.canonical

    if canonical and normalize_url(canonical).rstrip("/") != normalize_url(response.final_url).rstrip("/"):
        link["canonical_text"] = report.untrusted(canonical)
        findings.append(link_finding("L06", "warning", link, "target canonical differs from the linked URL"))


def link_finding(code: str, severity: str, link: dict, note: str) -> dict:
    return {"code": code, "severity": severity, "line": link.get("line"),
            "url_text": report.untrusted(link["url"]), "note": note}


def check_links(fetcher, links: List[dict], cap: int, site_host: Optional[str]
                ) -> Tuple[List[dict], List[dict], bool, int]:
    """Check up to cap links, skipping hosts that answered 401/403/429.

    Returns the checked links, their findings, whether the site itself blocked, and the count over the cap.
    """
    checked: List[dict] = []
    findings: List[dict] = []
    blocked_hosts = set()
    site_blocked = False

    for link in links[:cap]:
        host = urllib.parse.urlsplit(link["url"]).netloc

        if host in blocked_hosts:
            link["result"] = "not read: host answered 401/403/429 earlier"
            checked.append(link)
            continue

        print(f"checking {report.untrusted(link['url'], 300)}", file=sys.stderr)
        result, found = check_link(fetcher, link)
        checked.append(result)
        findings.extend(found)

        if link.get("status") in BLOCKING_STATUSES:
            blocked_hosts.add(host)
            site_blocked = site_blocked or host == site_host

    return checked, findings, site_blocked, max(0, len(links) - cap)


def freshness(file_modified: Optional[str], links: List[dict]) -> List[dict]:
    """L09: linked pages whose Last-Modified is later than the file's, when both are known."""
    file_date = parse_http_date(file_modified)

    if not file_date:
        return []

    newer = [link for link in links if (parse_http_date(link.get("last_modified")) or file_date) > file_date]

    if not newer:
        return []

    return [{"code": "L09", "severity": "info",
             "note": f"{len(newer)} linked page(s) changed after the file (Last-Modified headers)",
             "urls_text": [report.untrusted(link["url"]) for link in newer[:20]]}]


def parse_http_date(value: Optional[str]):
    if not value:
        return None

    try:
        return email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit llms.txt (codes L01-L09 of references/llms-txt-stance.md that a script can "
                    "compute). A missing file is information, never a defect. Read-only.",
    )
    parser.add_argument("--site", help="site URL: /llms.txt is fetched there; also the base for relative links")
    parser.add_argument("--file", help="local llms.txt to audit instead of fetching it")
    parser.add_argument("--check-links", action=argparse.BooleanOptionalAction, default=True,
                        help="GET every linked URL (default on; --no-check-links to skip)")
    parser.add_argument("--max-links", type=int, default=DEFAULT_MAX_LINKS,
                        help=f"cap on links checked (default {DEFAULT_MAX_LINKS}, heuristic)")
    parser.add_argument("--out", help="write the JSON report to this file instead of stdout")
    add_fetch_arguments(parser)

    return parser


def base_result(source: str) -> dict:
    return {
        "generated_on": report.today(),
        "tool": "llmstxt_review.py",
        "source_text": report.untrusted(source),
        "codes_not_computed": {
            "L07": "claims vs linked pages need reading: compare by hand",
            "L09": "computed only when Last-Modified headers exist on the file and the targets",
        },
        "limits": [
            "structure expectations (L02-L04) follow the llms.txt proposal: re-read it and date it before use",
            "wording flags are pattern matches: read each one",
            "static HTML of targets only; JavaScript not run",
        ],
    }


def load_file(args: argparse.Namespace, fetcher, result: dict) -> Tuple[Optional[str], int]:
    """Return (text, exit code). text None means the run ends with result as is."""
    if args.file:
        if not os.path.isfile(args.file):
            raise ValueError(f"no such file: {args.file}")

        with open(args.file, "rb") as handle:
            raw = handle.read(args.max_bytes)

        result.update({"present": True, "read_from": "local file"})

        return decode_body(raw, "text/plain; charset=utf-8"), 0

    target = resolve_target(args)
    print(f"fetching {target}", file=sys.stderr)
    response = fetcher.get(target)
    result.update({"url_text": report.untrusted(target), "http_status": response.status,
                   "content_type": response.content_type, "last_modified": response.headers.get("last-modified"),
                   "redirects": [{"url": hop.url, "status": hop.status} for hop in response.chain]})

    if response.status in BLOCKING_STATUSES:
        result.update({"present": "not read", "findings": [],
                       "note": f"HTTP {response.status}: not read, no workaround attempted"})
        return None, 3

    if response.status is None:
        result.update({"present": "not read", "findings": [],
                       "note": f"not read: {report.untrusted(response.error, 120)}"})
        return None, 0

    if response.status in ABSENT_STATUSES:
        result.update({"present": False, "findings": [
            {"code": "L01", "severity": "info", "note": "absent: no llms.txt at the site root (not a defect)"}]})
        return None, 0

    if response.status >= 400:
        result.update({"present": "unknown", "findings": [
            {"code": "L01", "severity": "error", "note": f"/llms.txt answers HTTP {response.status}"}]})
        return None, 0

    result["present"] = True
    result["read_from"] = "network"
    result["file_truncated"] = response.truncated

    return response.text(), 0


def main(argv: Optional[List[str]] = None) -> int:
    """Review the file and print or write the JSON; returns 3 when the site answered 401/403/429."""
    args = build_parser().parse_args(argv)

    if not (args.site or args.file):
        print("error: give --site or --file", file=sys.stderr)
        return 2

    if args.site and urllib.parse.urlsplit(args.site).scheme not in ("http", "https"):
        print("error: --site must be an http(s) URL", file=sys.stderr)
        return 2

    fetcher = fetcher_from_args(args)
    result = base_result(args.file or args.site)

    try:
        text, code = load_file(args, fetcher, result)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if text is None:
        write_output(result, args.out)
        return code

    findings = file_type_findings(result)
    structure, structure_findings = analyse_structure(text)
    findings.extend(structure_findings)
    findings.extend(flag_wording(text))
    base = resolve_target(args)
    links = collect_links(text, base)
    site_blocked = False
    left_out = 0

    if args.check_links:
        links, link_findings, site_blocked, left_out = check_links(
            fetcher, links, args.max_links, urllib.parse.urlsplit(base).netloc if base else None)
        findings.extend(link_findings)
        findings.extend(freshness(result.get("last_modified"), links))
    else:
        result["limits"].append("links not checked (--no-check-links): L05, L06 and L09 not computed")

    if left_out:
        result["limits"].append(f"{left_out} link(s) over the cap of {args.max_links} not checked")

    if site_blocked:
        result["limits"].insert(0, "the site answered 401/403/429 during link checks: later links on it not read")

    result.update({
        "structure": structure,
        "links": [public_link(link) for link in links],
        "links_not_checked_over_cap": left_out,
        "html_comments_quoted": html_comments(text),
        "findings": findings,
        "summary": summarise(findings, links),
    })
    write_output(result, args.out)

    return 3 if site_blocked else 0


def file_type_findings(result: dict) -> List[dict]:
    content_type = result.get("content_type")

    if result.get("read_from") != "network" or content_type in TEXT_TYPES:
        return []

    note = f"served as {content_type or 'no content type'}, a text type is expected"

    if content_type in ("text/html", "application/xhtml+xml"):
        note += " (an HTML page answering 200 may be a soft 404 or an app fallback)"

    return [{"code": "L01", "severity": "warning", "note": note}]


def public_link(link: dict) -> dict:
    """Site-provided URLs leave the script as quoted text only."""
    shown = {key: value for key, value in link.items() if key not in ("url", "final_url", "redirects")}
    shown["url_text"] = report.untrusted(link["url"])

    if link.get("final_url"):
        shown["final_url_text"] = report.untrusted(link["final_url"])

    if link.get("redirects"):
        shown["redirects"] = [{"url_text": report.untrusted(hop["url"]), "status": hop["status"]}
                              for hop in link["redirects"]]

    return shown


def summarise(findings: List[dict], links: List[dict]) -> dict:
    by_code: Dict[str, int] = {}

    for item in findings:
        by_code[item["code"]] = by_code.get(item["code"], 0) + 1

    return {
        "findings_by_code": dict(sorted(by_code.items())),
        "links_found": len(links),
        "links_ok": sum(1 for link in links if link.get("result") == "ok"),
        "links_broken": sum(1 for link in links if link.get("result") in ("broken", "error")),
    }


def write_output(result: dict, out: Optional[str]) -> None:
    if not out:
        report.emit_json(result)
        return

    with open(out, "w", encoding="utf-8") as handle:
        report.emit_json(result, handle)

    print(f"written {out}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
