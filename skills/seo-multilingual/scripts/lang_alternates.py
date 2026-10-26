#!/usr/bin/env python3
"""Audit hreflang annotations from HTML, HTTP Link headers and sitemap xhtml:link entries.

Builds clusters of alternates and runs the checks H01-H12 of references/hreflang-checks.md:
self-reference, reciprocity, code format, duplicate codes, status/redirect/noindex of targets,
canonical conflicts, disagreement between sources, absolute URLs, x-default, declared vs
<html lang>, pages outside any cluster, cluster completeness. Results are leads to confirm.

Usage:
    python3 scripts/lang_alternates.py --sitemap <url> [--urls <file|url,url>] [--from-crawl <dir>]
                                      [--max 200] [--offline] [--out hreflang.json]

Network: GET only through seokit.fetch (robots.txt respected, about 2 requests per second, size
cap). Fetches the sitemap, the listed pages and every annotated target up to --max pages.
Stops on 401/403/429 and reports the rest as "not read". --from-crawl with --offline uses no
network at all.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse
from collections import deque
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple

from seokit import crawl as crawl_mod
from seokit import report, sitemap
from seokit.fetch import BLOCKING_STATUSES, Fetcher, add_fetch_arguments, fetcher_from_args, normalize_url
from seokit.html import parse_html

DEFAULT_MAX = 200
LISTED = 50
SOURCES = ("html", "header", "sitemap")
CODE_FORMAT = r"^([a-z]{2})(?:-([a-z]{2}))?$"
SCRIPT_FORMAT = r"^([a-z]{2})-([a-z]{4})(?:-([a-z]{2}))?$"


class Annotation:
    """One hreflang annotation: language code, absolute target URL and the href as written."""

    __slots__ = ("code", "url", "raw")

    def __init__(self, code: str, url: str, raw: str) -> None:
        self.code = code.strip()
        self.url = url
        self.raw = raw

    def key(self) -> Tuple[str, str]:
        return self.code.lower(), normalize_url(self.url)

    def quote(self) -> str:
        return report.untrusted(f"{self.code} {self.raw}", 500)


class PageInfo:
    """What is known about one URL: read or not and why, status, canonical, lang, noindex, annotations by source."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.read = False
        self.reason: Optional[str] = None
        self.status: Optional[int] = None
        self.final_url = url
        self.redirected = False
        self.canonical: Optional[str] = None
        self.lang: Optional[str] = None
        self.noindex = False
        self.annotations: Dict[str, List[Annotation]] = {source: [] for source in SOURCES}

    def all_annotations(self) -> List[Annotation]:
        return [a for source in SOURCES for a in self.annotations[source]]

    def sources_used(self) -> List[str]:
        return [source for source in SOURCES if self.annotations[source]]

    def own_keys(self) -> Set[str]:
        return {normalize_url(self.url), normalize_url(self.final_url)}


# ---------------------------------------------------------------- extraction

class _RawAlternates(HTMLParser):
    """Raw href values of <link rel=alternate hreflang> (seokit gives absolute URLs only)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: List[Tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return

        attributes = {key.lower(): (value or "") for key, value in attrs}

        rel = attributes.get("rel", "").lower().split()

        if "alternate" in rel and attributes.get("hreflang") and attributes.get("href"):
            self.found.append((attributes["hreflang"].strip(), attributes["href"].strip()))

    handle_startendtag = handle_starttag


def raw_alternates(html_text: str) -> List[Tuple[str, str]]:
    """(hreflang, raw href) of each <link rel=alternate hreflang>; [] when the HTML cannot be parsed."""
    parser = _RawAlternates()

    try:
        parser.feed(html_text)
        parser.close()
    except (AssertionError, ValueError):
        pass

    return parser.found


def parse_link_header(value: str, base: str) -> Tuple[List[Annotation], Optional[str]]:
    """hreflang alternates and canonical from an HTTP Link header (repeated headers joined by ', ')."""
    annotations: List[Annotation] = []
    canonical = None

    for part in re.split(r",\s*(?=<)", value or ""):
        match = re.match(r"\s*<([^>]*)>(.*)", part, re.S)

        if not match:
            continue

        target, params = match.group(1).strip(), match.group(2)
        rel = param(params, "rel").lower().split()
        hreflang = param(params, "hreflang")

        if "alternate" in rel and hreflang:
            annotations.append(Annotation(hreflang, urllib.parse.urljoin(base, target), target))
        elif "canonical" in rel and canonical is None:
            canonical = urllib.parse.urljoin(base, target)

    return annotations, canonical


def param(params: str, name: str) -> str:
    """Value of a parameter of an HTTP Link header entry (quoted or bare), or ''."""
    match = re.search(r";\s*" + name + r'\s*=\s*"([^"]*)"', params, re.I)

    if not match:
        match = re.search(r";\s*" + name + r"\s*=\s*([^;\s,]+)", params, re.I)

    return match.group(1).strip() if match else ""


def fill_from_response(info: PageInfo, status: Optional[int], final_url: str, chain: list,
                       headers: Dict[str, str], html_text: Optional[str]) -> None:
    """Fill a PageInfo from an answer: status, redirect, Link header and, for a 2xx HTML page, its HTML annotations."""
    info.status = status
    info.final_url = final_url
    info.redirected = bool(chain)
    header_annotations, header_canonical = parse_link_header(headers.get("link", ""), final_url)
    info.annotations["header"] = header_annotations
    info.canonical = header_canonical
    robots_header = headers.get("x-robots-tag", "").lower()
    info.noindex = "noindex" in robots_header

    if status is None or not (200 <= status < 300):
        info.read = True
        info.reason = f"HTTP {status}"
        return

    info.read = True

    if html_text is None:
        return

    page = parse_html(html_text, final_url)
    raw = raw_alternates(html_text)
    raws = [href for _, href in raw] if len(raw) == len(page.alternates) else [url for _, url in page.alternates]
    info.annotations["html"] = [Annotation(code, url, raws[i]) for i, (code, url) in enumerate(page.alternates)]
    info.canonical = page.canonical or info.canonical
    info.lang = page.lang
    info.noindex = info.noindex or "noindex" in page.robots or "none" in re.split(r"[\s,]+", page.robots)


# ---------------------------------------------------------------- collection

class Collector:
    """Gathers pages and their annotations from the sitemap, a crawl and live fetches."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.pages: Dict[str, PageInfo] = {}
        self.sitemap_locs: List[str] = []
        self.blocked = False
        self.fetched = 0
        self.notes: List[str] = []
        self.fetcher = None if args.offline else fetcher_from_args(args)

    def info(self, url: str) -> PageInfo:
        key = normalize_url(url)

        if key not in self.pages:
            self.pages[key] = PageInfo(key)

        return self.pages[key]

    def load_sitemap(self) -> None:
        """Register the sitemap's locations and their xhtml:link alternates."""
        if self.fetcher is None:
            self.notes.append("sitemap not read: --offline")
            return

        loaded = sitemap.load(self.fetcher, [self.args.sitemap])

        for error in loaded.errors:
            self.notes.append(f"sitemap: {report.untrusted(error)}")

        if loaded.truncated:
            self.notes.append(f"sitemap truncated: {loaded.left_out} URL(s) left out")

        for entry in loaded.urls:
            info = self.info(entry.loc)
            self.sitemap_locs.append(info.url)

            for code, href in entry.alternates:
                info.annotations["sitemap"].append(Annotation(code, urllib.parse.urljoin(entry.loc, href), href))

    def load_crawl(self, directory: str) -> None:
        """Fill pages from a seokit crawl directory; blocked or unanswered records keep a reason."""
        meta, records = crawl_mod.load_crawl(directory)

        for record in records:
            info = self.info(record["url"])
            html_text = crawl_mod.read_html(directory, record)
            headers = record.get("headers") or {}

            if record.get("status") in BLOCKING_STATUSES or record.get("status") is None:
                info.reason = f"not read in the crawl: {record.get('status') or record.get('error')}"
                continue

            fill_from_response(info, record.get("status"), record.get("final_url") or record["url"],
                               record.get("chain") or [], headers, html_text)

        self.notes.append(f"crawl reused: {report.untrusted(meta.get('start_url'))}, "
                          f"stop reason: {report.untrusted(meta.get('stop_reason'))}")

        if not self.args.sitemap:
            self.notes.append("crawl.json keeps sitemap locations only, not xhtml:link alternates: "
                              "sitemap annotations not read (add --sitemap)")

    def fetch(self, url: str, fetcher: Fetcher) -> None:
        """Fetch one page and fill its PageInfo; a 401/403/429 marks the whole run as blocked."""
        info = self.info(url)
        print(f"fetching {report.untrusted(url)}", file=sys.stderr)
        response = fetcher.get(url)
        self.fetched += 1

        if response.status in BLOCKING_STATUSES:
            self.blocked = True
            info.reason = f"HTTP {response.status}: stopped, no workaround attempted"
            return

        if response.status is None:
            info.reason = f"not read: {report.untrusted(response.error, 120)}"
            return

        html_text = response.text() if response.ok and response.is_html else None
        fill_from_response(info, response.status, response.final_url, response.chain, response.headers, html_text)

    def run(self, seeds: List[str]) -> None:
        """Fetch the seeds and every annotated target breadth-first, up to --max pages, until blocked."""
        queue = deque(normalize_url(u) for u in seeds)
        seen: Set[str] = set(queue)

        for info in list(self.pages.values()):
            for annotation in info.all_annotations():
                key = normalize_url(annotation.url)

                if key not in seen:
                    seen.add(key)
                    queue.append(key)

        while queue:
            key = queue.popleft()
            info = self.info(key)

            if info.read or info.reason:
                self.enqueue_targets(info, queue, seen)
                continue

            if not key.startswith(("http://", "https://")):
                info.reason = "not an absolute http(s) URL"
                continue

            if self.fetcher is None:
                info.reason = "not read: --offline and not in the crawl"
                continue

            if self.blocked:
                info.reason = "not read: run stopped after a 401/403/429"
                continue

            if self.fetched >= self.args.max:
                info.reason = f"not read: cap of {self.args.max} pages reached"
                continue

            self.fetch(key, self.fetcher)
            self.enqueue_targets(info, queue, seen)

    @staticmethod
    def enqueue_targets(info: PageInfo, queue: deque, seen: Set[str]) -> None:
        for annotation in info.all_annotations():
            key = normalize_url(annotation.url)

            if key not in seen:
                seen.add(key)
                queue.append(key)


# ---------------------------------------------------------------- checks

class Checker:
    """Runs the H01-H12 checks over the collected pages and groups them into clusters."""

    def __init__(self, pages: Dict[str, PageInfo], sitemap_locs: List[str], languages: Optional[Set[str]],
                 regions: Optional[Set[str]]) -> None:
        self.pages = pages
        self.sitemap_locs = sitemap_locs
        self.languages = languages
        self.regions = regions
        self.findings: List[dict] = []
        self.not_checked: List[dict] = []
        self.parent: Dict[str, str] = {}

    def add(self, check_id: str, severity: str, url: str, note: str, **extra) -> None:
        item = {"id": check_id, "severity": severity, "url": report.untrusted(url, 2000), "note": note}
        item.update(extra)
        self.findings.append(item)

    def annotating(self) -> List[PageInfo]:
        return [p for p in self.pages.values() if p.all_annotations()]

    def run(self) -> None:
        """Build the clusters, then run the per-page, per-target and site-wide checks."""
        self.build_clusters()
        checked_codes: Set[str] = set()
        targets: Dict[str, List[str]] = {}

        for page in self.annotating():
            self.check_codes(page, checked_codes)
            self.check_absolute(page)

            for source in page.sources_used():
                self.check_self_reference(page, source)
                self.check_duplicates(page, source)

            self.check_sources_agree(page)
            self.check_reciprocity(page)

            for annotation in page.all_annotations():
                targets.setdefault(normalize_url(annotation.url), []).append(page.url)

        for target, referrers in targets.items():
            self.check_target(target, sorted(set(referrers)))

        self.check_declared_language()
        self.check_x_default()
        self.check_outside_clusters(targets)
        self.check_home_fallback()

    # clusters ------------------------------------------------------------

    def find(self, key: str) -> str:
        """Root of a URL's cluster (union-find with path halving)."""
        self.parent.setdefault(key, key)

        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]

        return key

    def union(self, a: str, b: str) -> None:
        """Merge the clusters of two URLs."""
        self.parent[self.find(a)] = self.find(b)

    def build_clusters(self) -> None:
        for page in self.annotating():
            for annotation in page.all_annotations():
                self.union(page.url, normalize_url(annotation.url))

    def clusters(self) -> List[dict]:
        """Each cluster with its language codes, x-default presence and members."""
        groups: Dict[str, Dict[str, Set[str]]] = {}

        for page in self.annotating():
            for annotation in page.all_annotations():
                root = self.find(page.url)
                members = groups.setdefault(root, {})
                members.setdefault(page.url, set())
                members.setdefault(normalize_url(annotation.url), set()).add(annotation.code.lower())

        result = []

        for index, members in enumerate(sorted(groups.values(), key=lambda m: sorted(m)[0]), start=1):
            codes = sorted({c for values in members.values() for c in values})
            result.append({
                "cluster": index,
                "languages": codes,
                "has_x_default": "x-default" in codes,
                "members": [{"url": report.untrusted(url, 2000), "codes": sorted(values),
                             "read": self.pages.get(url) is not None and self.pages[url].read
                             and self.pages[url].reason is None}
                            for url, values in sorted(members.items())],
            })

        return result

    # per page ------------------------------------------------------------

    def check_codes(self, page: PageInfo, checked: Set[str]) -> None:
        """H03: each distinct hreflang code that is malformed or outside the given ISO lists."""
        for annotation in page.all_annotations():
            code = annotation.code

            if code.lower() in checked:
                continue

            checked.add(code.lower())
            problem, severity = self.code_problem(code)

            if problem:
                self.add("H03", severity, page.url, problem, annotation_quote=annotation.quote())

    def code_problem(self, code: str) -> Tuple[Optional[str], str]:
        """The H03 problem with a code and its severity, or (None, '') when the code is valid."""
        lower = code.lower()

        if lower == "x-default":
            return None, ""

        # Google's "Localized versions" page (read 2026-10-24): ISO 639-1 language, optional
        # ISO 3166-1 alpha-2 region, optional ISO 15924 script (zh-Hant, zh-Hans-US); codes
        # such as es-419 are not supported.
        match = re.match(CODE_FORMAT, lower)
        script = re.match(SCRIPT_FORMAT, lower)

        if script:
            language, region = script.group(1), script.group(3)
        elif match:
            language, region = match.group(1), match.group(2)
        elif re.match(r"^[a-z]{2}-\d{3}$", lower):
            return "numeric region (UN M.49, e.g. es-419): not supported by Google, use ISO 3166-1 alpha-2", "error"
        else:
            return ("value does not follow language[-Script][-REGION] "
                    "(ISO 639-1, ISO 15924, ISO 3166-1 alpha-2)"), "error"

        if self.languages is not None and language not in self.languages:
            return f"language '{language}' not in the ISO 639-1 list given", "error"

        if region and self.regions is not None and region not in self.regions:
            return f"region '{region.upper()}' not in the ISO 3166-1 list given", "error"

        return None, ""

    def check_absolute(self, page: PageInfo) -> None:
        """H08: targets that are relative, not http(s), or differ from the page only by scheme or www."""
        own = urllib.parse.urlsplit(page.final_url)

        for annotation in page.all_annotations():
            raw = annotation.raw.strip()
            parts = urllib.parse.urlsplit(raw)
            problem = None

            if not parts.scheme or not parts.netloc:
                problem = "relative URL: hreflang targets must be absolute"
            elif parts.scheme not in ("http", "https"):
                problem = f"scheme {parts.scheme} is not http(s)"
            elif parts.hostname == own.hostname and parts.scheme != own.scheme:
                problem = f"protocol differs from the page ({parts.scheme} vs {own.scheme})"
            elif parts.hostname and own.hostname and parts.hostname != own.hostname and \
                    parts.hostname.replace("www.", "", 1) == own.hostname.replace("www.", "", 1):
                problem = "host differs from the page only by www."

            if problem:
                self.add("H08", "error", page.url, problem, annotation_quote=annotation.quote())

    def check_self_reference(self, page: PageInfo, source: str) -> None:
        """H01: a source of annotations that does not list the page itself."""
        targets = {normalize_url(a.url) for a in page.annotations[source]}

        if targets & page.own_keys():
            return

        self.add("H01", "warning", page.url, f"the {source} annotations do not list the page itself",
                 source=source, annotations_quote=[a.quote() for a in page.annotations[source]])

    def check_duplicates(self, page: PageInfo, source: str) -> None:
        """H04: one code pointing to several URLs within one source."""
        by_code: Dict[str, Set[str]] = {}

        for annotation in page.annotations[source]:
            by_code.setdefault(annotation.code.lower(), set()).add(normalize_url(annotation.url))

        for code, urls in sorted(by_code.items()):
            if len(urls) > 1:
                self.add("H04", "error", page.url, f"'{code}' points to {len(urls)} different URLs ({source})",
                         source=source, annotations_quote=[a.quote() for a in page.annotations[source]
                                                           if a.code.lower() == code])

    def check_sources_agree(self, page: PageInfo) -> None:
        """H07: HTML, Link header and sitemap annotations of a page that differ."""
        used = page.sources_used()

        if len(used) < 2:
            return

        sets = {source: {a.key() for a in page.annotations[source]} for source in used}

        if len({frozenset(s) for s in sets.values()}) == 1:
            return

        self.add("H07", "error", page.url, f"annotations differ between {', '.join(used)}",
                 annotations_by_source_quote={s: [a.quote() for a in page.annotations[s]] for s in used})

    def check_reciprocity(self, page: PageInfo) -> None:
        """H02: targets that do not link back; targets not readable go to not_checked."""
        for annotation in page.all_annotations():
            target_key = normalize_url(annotation.url)

            if target_key in page.own_keys():
                continue

            target = self.pages.get(target_key)
            why = reciprocity_blocker(target)

            if why or target is None:
                self.not_checked.append({"url": report.untrusted(page.url, 2000),
                                         "target": report.untrusted(annotation.url, 2000), "why": why})
                continue

            back = {normalize_url(a.url) for a in target.all_annotations()}

            if back & page.own_keys():
                continue

            self.add("H02", "error", page.url, "the target does not link back to this page",
                     target=report.untrusted(annotation.url, 2000), annotation_quote=annotation.quote(),
                     target_annotations_quote=[a.quote() for a in target.all_annotations()][:20])

    # per target ----------------------------------------------------------

    def check_target(self, target_key: str, referrers: List[str]) -> None:
        """H05/H06: annotated URLs that do not answer 200, redirect, are noindex or canonicalise elsewhere."""
        target = self.pages.get(target_key)

        if target is None or target.reason and not target.read:
            return

        shown = [report.untrusted(r, 2000) for r in referrers[:10]]

        if target.status != 200:
            self.add("H05", "error", target_key, f"annotated URL answers HTTP {target.status}", referrers=shown)
            return

        if target.redirected:
            self.add("H05", "error", target_key, "annotated URL redirects",
                     final_url=report.untrusted(target.final_url, 2000), referrers=shown)

        if target.noindex:
            self.add("H05", "error", target_key, "annotated URL is noindex (meta robots or X-Robots-Tag)",
                     referrers=shown)

        if target.canonical and normalize_url(target.canonical) not in target.own_keys():
            note = "canonical points elsewhere: hreflang should target the canonical URL"
            other = self.pages.get(normalize_url(target.canonical))

            if other is not None and self.find(normalize_url(target.canonical)) == self.find(target_key):
                note = "canonical points to another member of the cluster (possibly another language)"

            self.add("H06", "error", target_key, note,
                     canonical_quote=report.untrusted(target.canonical, 2000), referrers=shown)

    def check_declared_language(self) -> None:
        """H10: hreflang language that differs from the target's <html lang>."""
        reported: Set[Tuple[str, str]] = set()

        for page in self.annotating():
            for annotation in page.all_annotations():
                code = annotation.code.lower()
                target = self.pages.get(normalize_url(annotation.url))

                if code == "x-default" or target is None or not target.lang or target.status != 200:
                    continue

                declared = re.split(r"[-_]", code)[0]
                actual = target.lang.strip().lower().replace("_", "-").split("-")[0]
                pair = (target.url, code)

                if declared == actual or pair in reported:
                    continue

                reported.add(pair)
                self.add("H10", "warning", target.url,
                         f"declared as '{code}' but <html lang> says '{report.untrusted(target.lang, 20)}'",
                         declared_by=report.untrusted(page.url, 2000))

    def check_x_default(self) -> None:
        """H09: clusters of 2+ members without x-default."""
        for cluster in self.clusters():
            if cluster["has_x_default"] or len(cluster["members"]) < 2:
                continue

            self.add("H09", "info", cluster["members"][0]["url"],
                     "cluster has no x-default (needed only when a language selector or default page exists)",
                     cluster=cluster["cluster"])

    def check_outside_clusters(self, targets: Dict[str, List[str]]) -> None:
        """H11: sitemap URLs that belong to no cluster, when the site uses hreflang."""
        outside = [url for url in self.sitemap_locs
                   if not self.pages[url].all_annotations() and url not in targets]

        if outside and self.annotating():
            self.findings.append({
                "id": "H11", "severity": "info",
                "note": f"{len(outside)} sitemap URL(s) belong to no cluster: confirm they are knowingly "
                        "single-language",
                "urls": [report.untrusted(u, 2000) for u in outside[:LISTED]],
            })

    def check_home_fallback(self) -> None:
        """H12: deep pages whose alternate is a language home page."""
        for page in self.annotating():
            depth = path_depth(page.url)

            for annotation in page.all_annotations():
                target = normalize_url(annotation.url)

                if target in page.own_keys() or annotation.code.lower() == "x-default":
                    continue

                if depth >= 2 and path_depth(target) <= 1:
                    self.add("H12", "warning", page.url,
                             "a deep page points to a language home page: the translation may be missing",
                             annotation_quote=annotation.quote())

    def missing_languages(self, clusters: List[dict]) -> List[dict]:
        """Languages that most clusters have and a given cluster lacks (data for H12)."""
        counts: Dict[str, int] = {}
        multi = [c for c in clusters if len(c["members"]) >= 2]

        for cluster in multi:
            for code in cluster["languages"]:
                counts[code] = counts.get(code, 0) + 1

        common = {code for code, n in counts.items() if n / max(1, len(multi)) >= 0.5 and code != "x-default"}
        missing = []

        for cluster in multi:
            lacking = sorted(common - set(cluster["languages"]))

            if lacking:
                missing.append({"cluster": cluster["cluster"], "missing_languages": lacking})

        return missing


def reciprocity_blocker(target: Optional[PageInfo]) -> Optional[str]:
    """Why reciprocity cannot be checked against this target, or None when it can."""
    if target is None or not target.read:
        return target.reason if target and target.reason else "target not read"

    if target.reason or target.status != 200:
        return target.reason or f"target answers HTTP {target.status} (see H05)"

    if target.redirected:
        return "target redirects (see H05)"

    return None


def path_depth(url: str) -> int:
    return len([s for s in urllib.parse.urlsplit(url).path.split("/") if s])


# ---------------------------------------------------------------- main

def read_code_list(path: Optional[str]) -> Optional[Set[str]]:
    """First token of each non-comment line of a code file, lowercased; None without a file."""
    if not path:
        return None

    codes = set()

    with open(path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()

            if not line or line.startswith("#"):
                continue

            for token in re.split(r"[,;\s]+", line)[:1]:
                if token:
                    codes.add(token.lower())

    return codes


def read_url_list(value: str) -> List[str]:
    """URLs from a file (one per line, '#' comments skipped) or from a comma-separated value."""
    if os.path.isfile(value):
        with open(value, encoding="utf-8", errors="replace") as handle:
            lines = [line.strip() for line in handle]

        return [line for line in lines if line and not line.startswith("#")]

    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit hreflang in HTML, HTTP Link headers and sitemaps (checks H01-H12 of "
                    "references/hreflang-checks.md; IDs and severities are a design choice, to calibrate). "
                    "Read-only. Cannot tell whether a search engine used an annotation.",
    )
    parser.add_argument("--sitemap", help="sitemap or sitemap index URL (xhtml:link alternates are read)")
    parser.add_argument("--urls", help="file with one URL per line, or comma-separated URLs")
    parser.add_argument("--from-crawl", help="reuse a seokit crawl directory instead of fetching those pages")
    parser.add_argument("--offline", action="store_true",
                        help="with --from-crawl: fetch nothing; pages missing from the crawl are 'not read'")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX,
                        help=f"cap on pages fetched, targets included (default {DEFAULT_MAX}, heuristic)")
    parser.add_argument("--language-codes", help="file of valid ISO 639-1 codes, one per line (optional)")
    parser.add_argument("--region-codes", help="file of valid ISO 3166-1 alpha-2 codes, one per line (optional)")
    parser.add_argument("--out", help="write the JSON report to this file instead of stdout")
    add_fetch_arguments(parser)

    return parser


def validate(args: argparse.Namespace) -> Optional[str]:
    """First problem with the options, or None."""
    if not (args.sitemap or args.urls or args.from_crawl):
        return "give --sitemap, --urls or --from-crawl"

    if args.offline and not args.from_crawl:
        return "--offline needs --from-crawl"

    if args.offline and args.sitemap:
        return "--offline cannot read a --sitemap"

    if args.from_crawl and not os.path.isfile(os.path.join(args.from_crawl, "crawl.json")):
        return f"not a crawl directory: {args.from_crawl}"

    if args.max < 1:
        return "--max must be at least 1"

    if args.sitemap and urllib.parse.urlsplit(args.sitemap).scheme not in ("http", "https"):
        return "--sitemap must be an http(s) URL"

    return None


def main(argv: Optional[List[str]] = None) -> int:
    """Collect pages, run the checks and write the JSON report.

    Returns 2 on bad input, 3 when the site answered 401/403/429, 0 otherwise."""
    args = build_parser().parse_args(argv)
    problem = validate(args)

    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    try:
        seeds = read_url_list(args.urls) if args.urls else []
        languages = read_code_list(args.language_codes)
        regions = read_code_list(args.region_codes)
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    bad = [u for u in seeds if urllib.parse.urlsplit(u).scheme not in ("http", "https")]

    if bad:
        print(f"error: not an http(s) URL: {report.untrusted(bad[0], 100)}", file=sys.stderr)
        return 2

    collector = Collector(args)

    try:
        if args.from_crawl:
            collector.load_crawl(args.from_crawl)
    except (OSError, ValueError, KeyError) as error:
        print(f"error: unreadable crawl directory: {error}", file=sys.stderr)
        return 2

    if args.sitemap:
        collector.load_sitemap()

    collector.run(seeds + collector.sitemap_locs)

    if not collector.pages:
        print("error: no URL to check (empty list or unreadable sitemap)", file=sys.stderr)
        return 2

    result = build_result(args, collector, languages, regions)
    write_output(result, args.out)

    return 3 if collector.blocked else 0


def build_result(args, collector: Collector, languages, regions) -> dict:
    """The JSON report: summary counts, notes, limits, code inventory, findings by severity, clusters."""
    checker = Checker(collector.pages, collector.sitemap_locs, languages, regions)
    checker.run()
    clusters = checker.clusters()
    not_read = [{"url": report.untrusted(p.url, 2000), "reason": p.reason}
                for p in collector.pages.values() if p.reason and p.status is None]
    severities = [f["severity"] for f in checker.findings]
    code_inventory: Dict[str, int] = {}

    for page in checker.annotating():
        for annotation in page.all_annotations():
            code_inventory[annotation.code] = code_inventory.get(annotation.code, 0) + 1

    limits = [
        "cannot tell whether a search engine used an annotation",
        "static HTML only, no JavaScript",
        "H10 compares with <html lang> only; the text language is not detected",
        "reciprocity (H02) is checked only when the target page was read",
    ]

    if languages is None or regions is None:
        limits.append("H03 checks the code format only: membership in the ISO 639-1 / ISO 3166-1 lists is "
                      "not checked without --language-codes / --region-codes (e.g. en-UK passes the format)")

    if collector.blocked:
        limits.insert(0, "the site answered 401/403/429: the run stopped, remaining pages not read")

    return {
        "generated_on": report.today(),
        "tool": "lang_alternates.py",
        "summary": {
            "pages_known": len(collector.pages),
            "pages_read": sum(1 for p in collector.pages.values() if p.read),
            "pages_not_read": len(not_read),
            "pages_fetched_now": collector.fetched,
            "max": args.max,
            "annotating_pages": len(checker.annotating()),
            "clusters": len(clusters),
            "errors": severities.count("error"),
            "warnings": severities.count("warning"),
            "info": severities.count("info"),
            "reciprocity_not_checked": len(checker.not_checked),
        },
        "notes": collector.notes,
        "limits": limits,
        "code_inventory_text": {report.untrusted(k, 40): v for k, v in sorted(code_inventory.items())},
        "findings": sorted(checker.findings, key=lambda f: (severity_rank(f["severity"]), f["id"])),
        "clusters": clusters,
        "missing_languages_by_cluster": checker.missing_languages(clusters),
        "reciprocity_not_checked": checker.not_checked[:LISTED],
        "not_read": not_read[:LISTED],
    }


def severity_rank(severity: str) -> int:
    return {"error": 0, "warning": 1, "info": 2}.get(severity, 3)


def write_output(result: dict, out: Optional[str]) -> None:
    if not out:
        report.emit_json(result)
        return

    with open(out, "w", encoding="utf-8") as handle:
        report.emit_json(result, handle)

    print(f"written {out}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
