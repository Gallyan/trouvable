"""Breadth-first crawl of one site, saved as a reusable crawl directory.

Layout of a crawl directory:
    crawl.json      run metadata (start URL, caps, counts, stop reason, sitemap info)
    pages.jsonl     one JSON object per fetched URL (see API.md)
    html/<id>.html  raw body of each HTML page
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import urllib.parse
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from . import sitemap as sitemap_mod
from .fetch import BLOCKING_STATUSES, Fetcher, normalize_url, same_site
from .html import parse_html
from .report import untrusted

SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".pdf", ".zip",
    ".gz", ".mp4", ".webm", ".mp3", ".woff", ".woff2", ".ttf", ".css", ".js", ".json",
    ".xml", ".txt", ".dmg", ".exe",
)


@dataclass
class CrawlResult:
    """Summary of a crawl run; the pages themselves are in the crawl directory."""

    directory: str
    pages: int = 0
    stop_reason: str = "completed"
    sitemap_urls: List[str] = field(default_factory=list)
    queued_not_fetched: int = 0


def page_id(url: str) -> str:
    """Stable 16-hex-digit id of a URL, used for html/<id>.html."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def crawlable(url: str, root: str) -> bool:
    """http(s), same site as root, not a static asset."""
    parts = urllib.parse.urlsplit(url)

    if parts.scheme not in ("http", "https"):
        return False

    if not same_site(url, root):
        return False

    return not parts.path.lower().endswith(SKIP_EXTENSIONS)


def crawl(
    start_url: str,
    fetcher: Fetcher,
    out_dir: str,
    max_pages: int = 300,
    use_sitemap: bool = True,
    extra_urls: Optional[List[str]] = None,
    progress=None,
) -> CrawlResult:
    """Crawl start_url's site. Stops at max_pages, or when the site answers 401/403/429."""
    os.makedirs(os.path.join(out_dir, "html"), exist_ok=True)
    result = CrawlResult(directory=out_dir)
    start = normalize_url(start_url)
    sitemap_info: Dict[str, object] = {"declared": [], "files": [], "errors": [], "url_count": 0}
    sitemap_set: Dict[str, Optional[str]] = {}

    if use_sitemap:
        declared = sitemap_mod.discover(fetcher, start)
        loaded = sitemap_mod.load(fetcher, declared)
        sitemap_info = {
            "declared": declared,
            "files": loaded.files,
            "errors": loaded.errors,
            "url_count": len(loaded.urls),
            "truncated": loaded.truncated,
        }

        for entry in loaded.urls:
            sitemap_set[normalize_url(entry.loc)] = entry.lastmod

        result.sitemap_urls = list(sitemap_set)

    # Links found on pages are crawled first, so that depth is the click depth from the
    # start URL. Sitemap and extra URLs come after, with depth None unless a link reaches them.
    queue: deque = deque([(start, 0, None)])
    queued = {start}
    backlog: deque = deque(
        url for url in list(sitemap_set) + [normalize_url(u) for u in (extra_urls or [])]
        if crawlable(url, start)
    )
    blocked_streak = 0

    with open(os.path.join(out_dir, "pages.jsonl"), "w", encoding="utf-8") as out:
        while (queue or backlog) and result.pages < max_pages:
            if queue:
                url, depth, referrer = queue.popleft()
            else:
                url, depth, referrer = backlog.popleft(), None, None

                if url in queued:
                    continue

                queued.add(url)

            if progress:
                progress(f"[{result.pages + 1}/{max_pages}] {untrusted(url)}")

            response = fetcher.get(url)
            record = response.to_dict()
            record.update({
                "id": page_id(url),
                "depth": depth,
                "referrer": referrer,
                "in_sitemap": url in sitemap_set,
                "sitemap_lastmod": sitemap_set.get(url),
                "content_type": response.content_type,
                "html_path": None,
            })
            result.pages += 1

            if response.status in BLOCKING_STATUSES:
                blocked_streak += 1

                if result.pages == 1 or blocked_streak >= 3:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    result.stop_reason = f"site answered HTTP {response.status}: crawl stopped, no workaround attempted"
                    break
            else:
                blocked_streak = 0

            if response.status is not None and 200 <= response.status < 300 and response.is_html:
                path = os.path.join("html", f"{record['id']}.html")

                with open(os.path.join(out_dir, path), "wb") as handle:
                    handle.write(response.body)

                record["html_path"] = path
                final = normalize_url(response.final_url)

                if same_site(final, start):
                    page = parse_html(response.text(), response.final_url)
                    next_depth = (depth + 1) if depth is not None else None

                    for link in page.links:
                        target = normalize_url(link.url) if link.url else ""

                        if target and target not in queued and crawlable(target, start):
                            queued.add(target)
                            queue.append((target, next_depth, url))

            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    pending = len(queue) + sum(1 for url in backlog if url not in queued)

    if pending and result.stop_reason == "completed":
        result.stop_reason = f"page cap reached ({max_pages})"

    result.queued_not_fetched = pending
    meta = {
        "start_url": start,
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "user_agent": fetcher.user_agent,
        "max_pages": max_pages,
        "pages_fetched": result.pages,
        "queued_not_fetched": result.queued_not_fetched,
        "stop_reason": result.stop_reason,
        "sitemap": sitemap_info,
        "sitemap_urls": result.sitemap_urls,
        "robots_txt": fetcher.robots_text(start),
    }

    with open(os.path.join(out_dir, "crawl.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)

    return result


def path_matches(url: str, prefixes: List[str]) -> bool:
    """True when the URL's path starts with one of the prefixes (plain string prefixes)."""
    path = urllib.parse.urlsplit(url).path or "/"

    return any(path.startswith(prefix) for prefix in prefixes)


def spread_sample(urls: List[str], count: int) -> List[str]:
    """Round-robin over first path segments, so every sitemap section gets its share."""
    groups: Dict[str, List[str]] = OrderedDict()

    for url in urls:
        segments = [s for s in urllib.parse.urlsplit(url).path.split("/") if s]
        groups.setdefault(segments[0] if segments else "", []).append(url)

    picked: List[str] = []
    index = 0

    while len(picked) < count and any(index < len(group) for group in groups.values()):
        for group in groups.values():
            if index < len(group) and len(picked) < count:
                picked.append(group[index])

        index += 1

    return picked


def crawl_listed(
    start: str,
    fetcher: Fetcher,
    out_dir: str,
    cap: int,
    sample: bool,
    sections: List[str],
    sitemap_urls: Dict[str, Optional[str]],
    sitemap_info: Optional[dict] = None,
    progress=None,
) -> dict:
    """Sampled or section crawl from sitemap URLs (url -> lastmod), same directory layout.

    crawl() follows links breadth-first before sitemap URLs, so it cannot spread a cap across
    sitemap sections; this does. Click depth is unknown here (None) except for the start.
    With sections, links found on fetched pages are followed when they stay in a section.
    """
    os.makedirs(os.path.join(out_dir, "html"), exist_ok=True)
    on_site = [u for u in sitemap_urls if crawlable(u, start)]
    planned = [start]

    if sections:
        planned += [u for u in on_site if path_matches(u, sections)]

    if sample:
        chosen = set(planned)
        rest = [u for u in on_site if u not in chosen]
        planned += spread_sample(rest, max(cap - len(planned), 0))

    queue = deque(OrderedDict.fromkeys(planned))
    queued = set(queue)
    fetched = 0
    blocked_streak = 0
    stop_reason = "completed"

    with open(os.path.join(out_dir, "pages.jsonl"), "w", encoding="utf-8") as out:
        while queue and fetched < cap:
            url = queue.popleft()

            if progress:
                progress(f"[{fetched + 1}/{cap}] {untrusted(url)}")

            response = fetcher.get(url)
            fetched += 1
            record = response.to_dict()
            record.update({
                "id": page_id(url),
                "depth": 0 if url == start else None,
                "referrer": None,
                "in_sitemap": url in sitemap_urls,
                "sitemap_lastmod": sitemap_urls.get(url),
                "content_type": response.content_type,
                "html_path": None,
            })

            if response.status in BLOCKING_STATUSES:
                blocked_streak += 1

                if fetched == 1 or blocked_streak >= 3:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    stop_reason = f"site answered HTTP {response.status}: crawl stopped, no workaround attempted"
                    break
            else:
                blocked_streak = 0

            if response.ok and response.is_html:
                path = os.path.join("html", f"{record['id']}.html")

                with open(os.path.join(out_dir, path), "wb") as handle:
                    handle.write(response.body)

                record["html_path"] = path

                if sections and same_site(normalize_url(response.final_url), start):
                    for link in parse_html(response.text(), response.final_url).links:
                        target = normalize_url(link.url) if link.url else ""

                        if (target and target not in queued and crawlable(target, start)
                                and path_matches(target, sections)):
                            queued.add(target)
                            queue.append(target)

            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    if queue and stop_reason == "completed":
        stop_reason = f"page cap reached ({cap})"

    meta = {
        "start_url": start,
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "user_agent": fetcher.user_agent,
        "max_pages": cap,
        "pages_fetched": fetched,
        "queued_not_fetched": len(queue),
        "stop_reason": stop_reason,
        "sitemap": sitemap_info or {},
        "sitemap_urls": list(sitemap_urls),
        "robots_txt": fetcher.robots_text(start),
        "mode": "sample" if sample else "sections",
        "sections": sections,
    }

    with open(os.path.join(out_dir, "crawl.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)

    return meta


def load_crawl(directory: str) -> Tuple[dict, List[dict]]:
    """crawl.json and the records of pages.jsonl of a crawl directory."""
    with open(os.path.join(directory, "crawl.json"), encoding="utf-8") as handle:
        meta = json.load(handle)

    records = []

    with open(os.path.join(directory, "pages.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))

    return meta, records


def read_html(directory: str, record: dict) -> Optional[str]:
    """Decoded saved HTML of a page record; None when none was saved or its path leaves the directory."""
    path = record.get("html_path")

    if not path:
        return None

    from .fetch import decode_body

    full = os.path.realpath(os.path.join(directory, path))

    if not full.startswith(os.path.realpath(directory) + os.sep):
        return None

    with open(full, "rb") as handle:
        return decode_body(handle.read(), record.get("headers", {}).get("content-type", ""))


def iter_pages(directory: str) -> Iterator[Tuple[dict, Optional[str]]]:
    """Each page record of a crawl with its HTML (None when not saved)."""
    _, records = load_crawl(directory)

    for record in records:
        yield record, read_html(directory, record)
