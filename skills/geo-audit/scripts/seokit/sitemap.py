"""Sitemap discovery and parsing (urlset, sitemapindex, .gz), with caps."""

from __future__ import annotations

import gzip
import io
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .fetch import Fetcher, same_site
from .report import untrusted
from .safexml import UnsafeXmlError, parse_xml_bytes

MAX_SITEMAP_FILES = 50
MAX_DECOMPRESSED = 50_000_000


@dataclass
class SitemapUrl:
    """A <url> entry: its loc, lastmod, hreflang alternates and the sitemap file it came from."""

    loc: str
    lastmod: Optional[str] = None
    alternates: List[Tuple[str, str]] = field(default_factory=list)
    source: str = ""


@dataclass
class SitemapResult:
    """URLs gathered from sitemap files; `left_out` counts URLs dropped past the cap."""

    urls: List[SitemapUrl] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    truncated: bool = False
    left_out: int = 0


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _maybe_gunzip(data: bytes) -> bytes:
    if data[:2] != b"\x1f\x8b":
        return data

    with gzip.GzipFile(fileobj=io.BytesIO(data)) as handle:
        out = handle.read(MAX_DECOMPRESSED + 1)

    if len(out) > MAX_DECOMPRESSED:
        raise ValueError("decompressed sitemap above size cap")

    return out


def parse_sitemap_bytes(data: bytes, source: str = "") -> Tuple[str, List[SitemapUrl], List[str]]:
    """Return (kind, urls, child_sitemaps). kind is 'urlset', 'sitemapindex' or 'unknown'."""
    root = parse_xml_bytes(_maybe_gunzip(data))
    kind = _local(root.tag)
    urls: List[SitemapUrl] = []
    children: List[str] = []

    for node in root:
        name = _local(node.tag)

        if name == "sitemap":
            for child in node:
                if _local(child.tag) == "loc" and child.text:
                    children.append(child.text.strip())
        elif name == "url":
            entry = SitemapUrl(loc="", source=source)

            for child in node:
                child_name = _local(child.tag)

                if child_name == "loc" and child.text:
                    entry.loc = child.text.strip()
                elif child_name == "lastmod" and child.text:
                    entry.lastmod = child.text.strip()
                elif child_name == "link" and child.get("rel") == "alternate" and child.get("hreflang"):
                    entry.alternates.append((child.get("hreflang", ""), child.get("href", "")))

            if entry.loc:
                urls.append(entry)

    return (kind if kind in ("urlset", "sitemapindex") else "unknown"), urls, children


def sitemaps_from_robots(robots_text: str) -> List[str]:
    """URLs of the Sitemap: lines of a robots.txt, in order."""
    return [m.group(1).strip() for m in re.finditer(r"(?im)^\s*sitemap:\s*(\S+)", robots_text)]


def discover(fetcher: Fetcher, site_url: str) -> List[str]:
    """Sitemap URLs declared in robots.txt, else /sitemap.xml."""
    declared = sitemaps_from_robots(fetcher.robots_text(site_url))

    if declared:
        return declared

    parts = urllib.parse.urlsplit(site_url)

    return [f"{parts.scheme}://{parts.netloc}/sitemap.xml"]


def load(fetcher: Fetcher, sitemap_urls: List[str], max_urls: int = 50_000) -> SitemapResult:
    """Read sitemaps and the child sitemaps they list. MAX_SITEMAP_FILES bounds the number of
    fetches, failed ones included: a sitemap the user did not choose cannot make the run send
    more requests than that, whatever its children answer."""
    result = SitemapResult()
    queue = deque(sitemap_urls)
    seen = set()
    attempts = 0
    dropped = 0

    while queue and attempts < MAX_SITEMAP_FILES:
        url = queue.popleft()

        if url in seen:
            continue

        seen.add(url)
        attempts += 1
        response = fetcher.get(url)

        if not response.ok:
            result.errors.append(f"{untrusted(url, 300)}: {response.status or response.error}")
            continue

        if response.truncated:
            result.errors.append(f"{untrusted(url, 300)}: response above size cap, read partially")

        try:
            kind, urls, children = parse_sitemap_bytes(response.body, source=url)
        except (ET.ParseError, ValueError, UnsafeXmlError, OSError, EOFError) as error:
            result.errors.append(f"{untrusted(url, 300)}: not a readable sitemap ({untrusted(str(error), 200)})")
            continue

        result.files.append(url)

        for child in children:
            if not same_site(child, url):
                result.errors.append(f"{untrusted(child, 300)}: child sitemap on another host than "
                                     f"{untrusted(url, 300)}, not fetched")
            elif len(queue) + attempts < MAX_SITEMAP_FILES:
                queue.append(child)
            else:
                dropped += 1

        for entry in urls:
            if len(result.urls) >= max_urls:
                result.truncated = True
                result.left_out += 1
                continue

            result.urls.append(entry)

    if queue or dropped:
        result.errors.append(f"{len(queue) + dropped} sitemap file(s) not read: cap of {MAX_SITEMAP_FILES} fetches")

    return result
