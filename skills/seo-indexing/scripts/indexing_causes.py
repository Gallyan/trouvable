#!/usr/bin/env python3
"""Read a Search Console Page indexing export and collect live evidence per status.

Status labels are matched against the English table of references/cause-classes.md only;
any other label is kept as UNMAPPED with its literal text (never translated). Sample URLs
per status are fetched politely and the literal evidence is recorded: status chain,
X-Robots-Tag, meta robots, canonical href, matching robots.txt line, sitemap membership,
lastmod, title, word count. Pages younger than the age gate are set aside.

Usage:
    python3 scripts/indexing_causes.py --export export.zip --sitemap https://example.com/sitemap.xml \\
        --sample 50 --out indexing/

Network: GET only, through seokit.fetch (robots.txt respected, ~2 requests/s, size and
redirect caps). Stops on 429, and on 401/403 when the whole site answers so.
Writes url-evidence.csv in --out and prints a JSON summary on stdout.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

from seokit import robots
from seokit import sitemap as sitemap_mod
from seokit.fetch import Fetcher, Response, add_fetch_arguments, fetcher_from_args, normalize_url
from seokit.html import parse_html
from seokit.report import emit_json, today, untrusted, write_csv
from seokit.tables import Table, TableError, parse_number, read_tables
from seokit.text import normalize

HEURISTIC = "heuristic, to calibrate"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CLASSES = os.path.join(HERE, "..", "references", "cause-classes.md")
DEFAULT_AGE_DAYS = 21
DEFAULT_SAMPLE = 50
LASTMOD_UNIFORM_SHARE = 0.5
CONSECUTIVE_BLOCKS = 3

URL_RE = re.compile(r"^https?://", re.I)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
DATE_PUBLISHED_RE = re.compile(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})')

# Which technical signals explain a status of each cause class.
CLASS_SIGNALS = {
    "ACCESS": {"robots_disallowed", "http_5xx", "http_401", "http_403"},
    "DIRECTIVE": {"noindex_meta", "noindex_header"},
    "STATUS": {"http_404", "http_410", "http_4xx", "redirect_error"},
    "CANONICAL": {"canonical_elsewhere", "canonical_missing"},
    "EXPECTED": {"redirected", "canonical_elsewhere"},
}
BLOCKING_SIGNALS = (CLASS_SIGNALS["ACCESS"] | CLASS_SIGNALS["DIRECTIVE"] | CLASS_SIGNALS["STATUS"]
                    | {"canonical_elsewhere"})
LABEL_ONLY_CLASSES = ("DISCOVERY", "SELECTION")
JUDGED_WITHOUT_BODY = {"robots_disallowed", "redirect_error"}

CSV_FIELDS = [
    "url", "status_in_export", "cause_class", "sampled", "fetched", "fetch_error", "http_status",
    "status_chain", "final_url", "x_robots_tag", "meta_robots_literal", "canonical_href",
    "robots_txt_line", "robots_txt_group", "in_sitemap", "lastmod", "age_days", "age_source",
    "too_early", "title_text", "word_count", "body_bytes", "www_authenticate", "server_header",
    "html_comment_quote", "signals", "evidence_verdict",
]


class InputError(Exception):
    pass


class Blocked(Exception):
    pass


@dataclass
class UrlItem:
    url: str
    status: str
    classes: List[str]
    row: dict = field(default_factory=dict)


class Export(TypedDict):
    """What read_export gathered from the Page indexing export files."""

    files: List[str]
    tables: List[Dict[str, Any]]
    items: List[UrlItem]
    counts: Counter[str]
    ratio: Optional[Dict[str, Any]]
    unassigned_tables: List[Optional[str]]
    labels_seen: Dict[str, List[str]]


class SitemapInfo(TypedDict):
    """Sitemap URLs (normalised URL → lastmod) and how the reading went."""

    source: Optional[str]
    urls: Dict[str, Optional[str]]
    files: List[str]
    errors: List[Optional[str]]
    truncated: bool


# --------------------------------------------------------------------------- cause classes

def label_key(text: str) -> str:
    return normalize(text or "").strip(" .")


def load_cause_classes(path: str) -> Dict[str, Tuple[str, List[str]]]:
    """English labels → (label as written, classes), read from the reference table."""
    if not os.path.isfile(path):
        raise InputError(f"cause classes file not found: {path}")

    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    mapping: Dict[str, Tuple[str, List[str]]] = {}
    in_table = False

    for line in lines:
        if line.startswith("## "):
            in_table = "status" in line.lower() and "class" in line.lower()
            continue

        if not in_table or not line.startswith("|"):
            continue

        cells = [c.strip() for c in line.strip().strip("|").split("|")]

        if len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0].lower().startswith("status label"):
            continue

        classes = re.findall(r"`([A-Z-]+)`", cells[1])

        if classes:
            mapping[label_key(cells[0])] = (cells[0], classes)

    if not mapping:
        raise InputError(f"no status table found in {path}")

    return mapping


# --------------------------------------------------------------------------- export reading

def column_profile(table: Table, index: int, known: Dict[str, Tuple[str, List[str]]]) -> dict:
    """Shares of URLs, numbers and dates in a column (first 5000 rows), and how many cells are known labels."""
    values = [r[index] for r in table.rows[:5000] if index < len(r) and r[index].strip()]
    count = len(values) or 1

    return {
        "values": values,
        "urls": sum(bool(URL_RE.match(v)) for v in values) / count,
        "numbers": sum(parse_number(v) is not None for v in values) / count,
        "dates": sum(bool(DATE_RE.match(v)) for v in values) / count,
        "labels": sum(label_key(v) in known for v in values),
        "empty": not values,
    }


def classify_table(table: Table, known: Dict[str, Tuple[str, List[str]]]) -> dict:
    """Guess a table's role (urls, chart, status-counts, context, not-recognised) and its key columns."""
    profiles = [column_profile(table, i, known) for i in range(len(table.headers))]
    url_col = next((i for i, p in enumerate(profiles) if not p["empty"] and p["urls"] >= 0.8), None)
    date_col = next((i for i, p in enumerate(profiles) if not p["empty"] and p["dates"] >= 0.8), None)
    number_cols = [i for i, p in enumerate(profiles)
                   if not p["empty"] and p["numbers"] >= 0.9 and i not in (url_col, date_col)]
    text_cols = [i for i, p in enumerate(profiles)
                 if not p["empty"] and i not in number_cols and i not in (url_col, date_col)]
    labelled = sorted((i for i in text_cols if profiles[i]["labels"] > 0),
                      key=lambda i: profiles[i]["labels"], reverse=True)
    status_col = labelled[0] if labelled else None

    if url_col is not None:
        return {"role": "urls", "url_col": url_col, "status_col": status_col}

    if date_col is not None and number_cols:
        return {"role": "chart", "date_col": date_col, "number_cols": number_cols}

    if status_col is not None and number_cols:
        return {"role": "status-counts", "status_col": status_col, "count_col": number_cols[-1]}

    if status_col is not None:
        return {"role": "context", "status_col": status_col}

    if text_cols and number_cols and len(table.rows) <= 100:
        # Labels in another language: counts per label, every label UNMAPPED.
        status_col = max(text_cols, key=lambda i: len(set(profiles[i]["values"])))
        return {"role": "status-counts", "status_col": status_col, "count_col": number_cols[-1]}

    return {"role": "not-recognised"}


def classes_for(label: str, known: Dict[str, Tuple[str, List[str]]]) -> List[str]:
    entry = known.get(label_key(label))

    return list(entry[1]) if entry else ["UNMAPPED"]


INDEXED_HEADERS = ("indexed", "dans l'index")
NOT_INDEXED_HEADERS = ("not indexed", "non-indexed", "non indexées")


def ratio_from_chart(table: Table, info: dict) -> Optional[dict]:
    """Header hints: English ('Indexed', 'Not indexed') are the status names of Google's Help
    page (read 2026-10-24), not yet seen as column headers of a real English export; French
    ('Dans l'index', 'Non indexées') read on real exports. Days with empty counts are skipped."""
    headers = [normalize(h) for h in table.headers]
    indexed = next((i for i in info["number_cols"] if headers[i] in INDEXED_HEADERS), None)
    not_indexed = next((i for i in info["number_cols"] if headers[i] in NOT_INDEXED_HEADERS), None)

    if indexed is None or not_indexed is None or not table.rows:
        return None

    dated = sorted((r for r in table.rows if len(r) > max(indexed, not_indexed)
                    and parse_number(r[indexed]) is not None and parse_number(r[not_indexed]) is not None),
                   key=lambda r: r[info["date_col"]])

    if not dated:
        return None

    last = dated[-1]
    indexed_count = parse_number(last[indexed]) or 0
    not_indexed_count = parse_number(last[not_indexed]) or 0
    total = indexed_count + not_indexed_count
    result = {
        "date": untrusted(last[info["date_col"]], 40),
        "indexed": int(indexed_count),
        "not_indexed": int(not_indexed_count),
        "ratio_indexed": round(indexed_count / total, 4) if total else None,
        "label": "reported",
        "scope": "pages in the export's scope (all known pages, or the sitemap filter the user chose)",
    }

    if len(dated) > 1:
        first = dated[0]
        result["first_date"] = untrusted(first[info["date_col"]], 40)
        result["indexed_first_date"] = int(parse_number(first[indexed]) or 0)

    return result


def read_export(paths: List[str], known: Dict[str, Tuple[str, List[str]]]) -> Export:
    """Read every export file: tables and their roles, listed URLs, counts per status, ratio.

    Raises InputError on a missing or unreadable file."""
    result: Export = {
        "files": [], "tables": [], "items": [], "counts": Counter(), "ratio": None,
        "unassigned_tables": [], "labels_seen": {},
    }

    for path in paths:
        if not os.path.isfile(path):
            raise InputError(f"export not found: {path}")

        try:
            tables = read_tables(path)
        except TableError as error:
            raise InputError(f"{path}: {error}") from error
        except (OSError, ValueError) as error:
            raise InputError(f"{path}: not readable ({error})") from error

        result["files"].append(os.path.basename(path))
        infos = [(t, classify_table(t, known)) for t in tables]
        context: Set[str] = set()

        for table, info in infos:
            if info["role"] == "context":
                for row in table.rows:
                    cell = row[info["status_col"]] if info["status_col"] < len(row) else ""

                    if label_key(cell) in known:
                        context.add(cell)

        for table, info in infos:
            result["tables"].append({"table_name": untrusted(table.name, 120), "role": info["role"],
                                     "rows": len(table.rows), "truncated": table.truncated})
            read_table(table, info, known, context, result)

    return result


def read_table(table: Table, info: dict, known: Dict[str, Tuple[str, List[str]]],
               context: Set[str], result: Export) -> None:
    """Add one classified table to the export result according to its role."""
    role = info["role"]

    if role == "chart" and result["ratio"] is None:
        result["ratio"] = ratio_from_chart(table, info)
        return

    if role == "status-counts":
        for row in table.rows:
            if info["status_col"] >= len(row) or info["count_col"] >= len(row):
                continue

            label = row[info["status_col"]]
            count = parse_number(row[info["count_col"]])

            if label and count is not None:
                result["counts"][label] += int(count)
                result["labels_seen"][label] = classes_for(label, known)

        return

    if role != "urls":
        return

    table_status = None

    if info["status_col"] is None:
        if len(context) == 1:
            table_status = next(iter(context))
        elif label_key(table.name) in known:
            table_status = table.name
        else:
            result["unassigned_tables"].append(untrusted(table.name, 120))
            table_status = "UNASSIGNED"

    for row in table.rows:
        if info["url_col"] >= len(row):
            continue

        url = row[info["url_col"]].strip()

        if not URL_RE.match(url):
            continue

        if table_status is None:
            label = row[info["status_col"]] if info["status_col"] < len(row) else ""
        else:
            label = table_status

        classes = classes_for(label, known) if label != "UNASSIGNED" else ["UNASSIGNED"]
        result["labels_seen"][label] = classes
        result["items"].append(UrlItem(url=url, status=label, classes=classes))


def read_url_list(path: str) -> List[str]:
    if not os.path.isfile(path):
        raise InputError(f"URL list not found: {path}")

    urls = []

    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            value = line.strip().split(",")[0].strip()

            if URL_RE.match(value):
                urls.append(value)

    return urls


def read_published(path: Optional[str]) -> Dict[str, str]:
    """Publication dates reported by the user, as normalised URL → first date found on its row."""
    if not path:
        return {}

    if not os.path.isfile(path):
        raise InputError(f"publication dates file not found: {path}")

    try:
        tables = read_tables(path)
    except TableError as error:
        raise InputError(f"{path}: {error}") from error

    dates: Dict[str, str] = {}

    for table in tables:
        for row in [table.headers] + table.rows:
            url = next((c for c in row if URL_RE.match(c or "")), None)
            matches = (DATE_RE.search(c or "") for c in row)
            date = next((m.group(1) for m in matches if m), None)

            if url and date:
                dates[normalize_url(url)] = date

    return dates


# --------------------------------------------------------------------------- sitemap

def read_sitemap(source: Optional[str], fetcher: Fetcher) -> SitemapInfo:
    """Read a sitemap URL (with its child sitemaps) or a local sitemap file.

    Raises Blocked when the sitemap answers 401, 403 or 429, InputError on a bad local file."""
    info: SitemapInfo = {"source": untrusted(source, 300) if source else None, "urls": {}, "files": [],
            "errors": [], "truncated": False}

    if not source:
        info["errors"].append("no --sitemap given: sitemap membership not measured")
        return info

    if URL_RE.match(source):
        loaded = sitemap_mod.load(fetcher, [source])

        for error in loaded.errors:
            if re.search(r": (401|403|429)$", error):
                raise Blocked(f"sitemap answered {error.rsplit(': ', 1)[-1]}: {untrusted(error, 300)}")

        info["files"] = loaded.files
        info["errors"] = [untrusted(e, 300) for e in loaded.errors]
        info["truncated"] = loaded.truncated
        info["urls"] = {normalize_url(u.loc): u.lastmod for u in loaded.urls}

        return info

    if not os.path.isfile(source):
        raise InputError(f"sitemap file not found: {source}")

    with open(source, "rb") as handle:
        data = handle.read(sitemap_mod.MAX_DECOMPRESSED + 1)

    try:
        kind, urls, children = sitemap_mod.parse_sitemap_bytes(data, source=source)
    except Exception as error:  # noqa: BLE001 - any parse failure is bad input
        raise InputError(f"{source}: not a readable sitemap ({error})") from error

    info["files"] = [os.path.basename(source)]
    info["urls"] = {normalize_url(u.loc): u.lastmod for u in urls}

    if children:
        info["errors"].append(f"sitemap index file: {len(children)} child sitemaps not read (pass the URL instead)")

    return info


def lastmod_check(lastmods: Dict[str, Optional[str]], share: float) -> dict:
    """Whether sitemap lastmod values may stand for page age: not when too many share one date."""
    matches = (DATE_RE.search(v) for v in lastmods.values() if v)
    days = [m.group(1) for m in matches if m]

    if not days:
        return {"usable_as_age": False, "why": "no lastmod values"}

    value, count = Counter(days).most_common(1)[0]
    top_share = count / len(days)

    if len(days) > 1 and top_share > share:
        return {
            "usable_as_age": False,
            "warning": f"{count} of {len(days)} lastmod values share the date {value}: "
                       "not used as page age",
            "rule": f"more than {share:.0%} on one date ({HEURISTIC})",
        }

    return {"usable_as_age": True, "label": "assumed", "why": "lastmod is only an assumed age"}


# --------------------------------------------------------------------------- robots.txt

def robots_line(text: str, url: str, agent: str = "googlebot") -> Tuple[Optional[str], Optional[str]]:
    """The Disallow line deciding this URL (RFC 9309: longest match wins, Allow wins ties),
    and its group."""
    hit = robots.disallowing_rule(robots.parse(text), agent, url)

    if hit is None:
        return None, None

    agents, literal = hit

    return literal, ", ".join(agents)


# --------------------------------------------------------------------------- evidence

def transport_signals(response: Response) -> List[str]:
    """Signals read from the fetch itself: redirects, fetch errors and HTTP status classes."""
    signals: List[str] = []
    status = response.status

    if response.chain:
        signals.append("redirected")

    if response.error and "robots" not in response.error:
        signals.append("redirect_error" if "redirect" in response.error else "fetch_error")

    if status is None:
        return signals

    if status >= 500:
        signals.append("http_5xx")
    elif status in (401, 403, 404, 410):
        signals.append(f"http_{status}")
    elif 400 <= status < 500:
        signals.append("http_4xx")

    return signals


def html_evidence(response: Response, record: Dict[str, Any], signals: List[str]) -> None:
    """Add what the HTML says to the record: robots meta, canonical, title, word count,
    first HTML comment, datePublished; append the matching signals."""
    page = parse_html(response.text(), response.final_url)
    robots_meta: List[str] = []

    for name, values in page.meta.items():
        if name == "robots" or name.endswith("bot") or name.startswith("googlebot"):
            robots_meta.extend(f"{name}: {v}" for v in values)

    record["meta_robots_literal"] = untrusted(" | ".join(robots_meta), 300) if robots_meta else None
    record["canonical_href"] = untrusted(page.canonical, 300)
    record["title_text"] = untrusted(page.title, 200)
    record["word_count"] = page.word_count
    record["html_comment_quote"] = untrusted(page.html_comments[0], 200) if page.html_comments else None

    if any("noindex" in v.lower() for v in robots_meta):
        signals.append("noindex_meta")

    if page.canonical is None:
        signals.append("canonical_missing")
    elif normalize_url(page.canonical) != normalize_url(response.final_url):
        signals.append("canonical_elsewhere")

    for blob in page.jsonld:
        match = DATE_PUBLISHED_RE.search(blob)

        if match:
            record["date_published_on_page"] = match.group(1)
            break


def page_evidence(response: Response, url: str) -> Dict[str, Any]:
    """Literal evidence from one fetch, as CSV fields plus a "signals" list of technical causes.

    The HTML is read only for a 2xx HTML answer."""
    signals = transport_signals(response)
    x_robots_tag = untrusted(response.headers.get("x-robots-tag"), 200)
    record: Dict[str, Any] = {
        "http_status": response.status,
        "status_chain": " > ".join([str(h.status) for h in response.chain] + [str(response.status or "-")]),
        "final_url": untrusted(response.final_url, 300),
        "fetch_error": untrusted(response.error, 200),
        "x_robots_tag": x_robots_tag,
        "www_authenticate": untrusted(response.headers.get("www-authenticate"), 200),
        "server_header": untrusted(response.headers.get("server"), 120),
        "body_bytes": len(response.body),
        "signals": signals,
    }

    if response.error and "robots" in response.error:
        # The fetcher's own refusal is not evidence; the matched robots.txt line is (see fetch_items).
        record["fetch_error"] = f"not fetched: {untrusted(response.error, 160)} for this client"

    if x_robots_tag and "noindex" in x_robots_tag.lower():
        signals.append("noindex_header")

    if response.ok and response.is_html:
        html_evidence(response, record, signals)

    return record


def evidence_verdict(classes: List[str], signals: List[str]) -> str:
    """Whether the fetch shows a technical signal matching the status's cause class."""
    present = set(signals)

    if "fetch_error" in present and len(present) == 1:
        return "not read"

    if any(c in LABEL_ONLY_CLASSES for c in classes):
        found = present & BLOCKING_SIGNALS
        return "technical cause found" if found else "technical causes ruled out on this fetch"

    wanted = set()

    for name in classes:
        wanted |= CLASS_SIGNALS.get(name, set())

    if not wanted:
        return "no rule for this status"

    return "literal evidence found" if present & wanted else "no literal evidence"


def age_days(date_text: Optional[str], reading: datetime.date) -> Optional[int]:
    if not date_text:
        return None

    match = DATE_RE.search(date_text)

    if not match:
        return None

    try:
        day = datetime.date.fromisoformat(match.group(1))
    except ValueError:
        return None

    return (reading - day).days


# --------------------------------------------------------------------------- sampling

def spread_sample(items: List[UrlItem], total: int) -> List[UrlItem]:
    """Round-robin across statuses so every status gets examples."""
    by_status: Dict[str, List[UrlItem]] = defaultdict(list)

    for item in items:
        by_status[item.status].append(item)

    queues = [list(v) for _, v in sorted(by_status.items())]
    picked: List[UrlItem] = []

    while len(picked) < total and any(queues):
        for queue in queues:
            if queue and len(picked) < total:
                picked.append(queue.pop(0))

    return picked


def site_host(sitemap_source: Optional[str], items: List[UrlItem]) -> Optional[str]:
    """Host of the audited site: the sitemap URL's host, else the most common host of the URLs."""
    if sitemap_source and URL_RE.match(sitemap_source):
        return urllib.parse.urlsplit(sitemap_source).hostname

    hosts = Counter(urllib.parse.urlsplit(i.url).hostname for i in items)

    return hosts.most_common(1)[0][0] if hosts else None


def strip_www(host: Optional[str]) -> str:
    host = host or ""

    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Page indexing export reader and live evidence collector. GET only, robots.txt "
                    "respected. Writes url-evidence.csv in --out, JSON summary on stdout.")
    parser.add_argument("--export", action="append", default=[],
                        help="Page indexing export (CSV, XLSX or ZIP as downloaded); repeat for "
                             "per-status example exports")
    parser.add_argument("--sitemap", help="sitemap URL or local file")
    parser.add_argument("--urls", help="plain list of URLs to check (one per line)")
    parser.add_argument("--published", help="CSV of url,publication date (YYYY-MM-DD), reported by the user")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE,
                        help="URLs fetched in total, spread across statuses (default 50)")
    parser.add_argument("--today", help="reading date YYYY-MM-DD (default today)")
    parser.add_argument("--out", default=".", help="directory for url-evidence.csv (default current directory)")
    parser.add_argument("--classes", default=DEFAULT_CLASSES,
                        help="cause classes reference (default ../references/cause-classes.md)")
    parser.add_argument("--age-days", type=int, default=DEFAULT_AGE_DAYS,
                        help=f"age gate in days (default 21, {HEURISTIC})")
    parser.add_argument("--lastmod-uniform-share", type=float, default=LASTMOD_UNIFORM_SHARE,
                        help=f"share of lastmod values on one date above which lastmod is ignored "
                             f"(default 0.5, {HEURISTIC})")
    add_fetch_arguments(parser)

    return parser


def collect_items(args: argparse.Namespace, export: Export, sitemap_info: SitemapInfo) -> List[UrlItem]:
    """URLs to examine: the export's, plus --urls; the sitemap's when there is no other."""
    items = list(export["items"])

    if args.urls:
        items += [UrlItem(url=u, status="(from --urls)", classes=["NONE"]) for u in read_url_list(args.urls)]

    if not items:
        items = [UrlItem(url=u, status="(from sitemap)", classes=["NONE"]) for u in sitemap_info["urls"]]

    return items


def apply_age_gate(item: UrlItem, published: Dict[str, str], sitemap_info: SitemapInfo,
                   lastmod_ok: bool, reading: datetime.date, gate: int) -> None:
    """Record sitemap membership, lastmod and age; mark the item too early under the age gate."""
    key = normalize_url(item.url)
    lastmod = sitemap_info["urls"].get(key)
    item.row["in_sitemap"] = key in sitemap_info["urls"] if sitemap_info["source"] else "not measured"
    item.row["lastmod"] = untrusted(lastmod, 40)

    if key in published:
        item.row["age_days"] = age_days(published[key], reading)
        item.row["age_source"] = "publication date (reported)"
    elif lastmod and lastmod_ok:
        item.row["age_days"] = age_days(lastmod, reading)
        item.row["age_source"] = "sitemap lastmod (assumed)"

    days = item.row.get("age_days")
    item.row["too_early"] = days is not None and days < gate


def fetch_items(sample: List[UrlItem], fetcher: Fetcher, host: Optional[str],
                reading: datetime.date, gate: int) -> Optional[str]:
    """Fetch each sampled URL; return a stop reason when the site blocks."""
    consecutive = 0

    for index, item in enumerate(sample, start=1):
        if host and strip_www(urllib.parse.urlsplit(item.url).hostname) != strip_www(host):
            item.row["fetch_error"] = "not fetched: not on the user's host"
            continue

        print(f"[{index}/{len(sample)}] {untrusted(item.url, 300)}", file=sys.stderr)
        response = fetcher.get(item.url)
        evidence = page_evidence(response, item.url)
        signals = evidence.pop("signals")
        item.row.update(evidence)
        item.row["fetched"] = response.status is not None

        line, group = robots_line(fetcher.robots_text(item.url), item.url)

        if line:
            item.row["robots_txt_line"] = untrusted(line, 200)
            item.row["robots_txt_group"] = untrusted(group, 120)

            if "robots_disallowed" not in signals:
                signals.append("robots_disallowed")

        if item.row.get("date_published_on_page") and item.row.get("age_days") is None:
            item.row["age_days"] = age_days(item.row["date_published_on_page"], reading)
            item.row["age_source"] = "datePublished on the page (measured)"
            item.row["too_early"] = item.row["age_days"] is not None and item.row["age_days"] < gate

        item.row["signals"] = signals
        item.row["judged"] = response.status is not None or bool(set(signals) & JUDGED_WITHOUT_BODY)

        if response.status == 429:
            return f"429 Too Many Requests on {untrusted(item.url, 200)}: stopped, not retried"

        access_expected = "ACCESS" in item.classes

        if response.status in (401, 403) and not access_expected:
            consecutive += 1
        else:
            consecutive = 0

        if consecutive >= CONSECUTIVE_BLOCKS:
            return f"{CONSECUTIVE_BLOCKS} consecutive 401/403 answers: the site blocks this client, stopped"

    return None


def status_summary(items: List[UrlItem], export: Export) -> List[dict]:
    """One row per status label: classes, counts, sampled and judged URLs, verdicts, confidence."""
    labels = set(export["labels_seen"]) | {i.status for i in items}
    rows = []

    for label in sorted(labels):
        group = [i for i in items if i.status == label]
        classes = export["labels_seen"].get(label) or (group[0].classes if group else ["UNMAPPED"])
        sampled = [i for i in group if i.row.get("sampled")]
        fetched = [i for i in sampled if i.row.get("judged") and not i.row.get("too_early")]
        verdicts = Counter(i.row.get("evidence_verdict") for i in fetched)
        rows.append({
            "status_label_quoted": untrusted(label, 200),
            "cause_class": classes,
            "urls_in_export_counts": export["counts"].get(label),
            "urls_listed": len(group),
            "sampled": len(sampled),
            "fetched_and_judged": len(fetched),
            "too_early": sum(1 for i in group if i.row.get("too_early")),
            "evidence": dict(verdicts),
            "confidence": confidence(classes, len(fetched), verdicts),
        })

    return rows


def confidence(classes: List[str], fetched: int, verdicts: Counter) -> str:
    """Confidence in a status's cause class, from the share of judged URLs with literal evidence."""
    if any(c in ("UNMAPPED", "UNASSIGNED", "NONE") for c in classes):
        return "none: status not mapped"

    if any(c in LABEL_ONLY_CLASSES for c in classes):
        return "low (class from the label alone)"

    found = verdicts.get("literal evidence found", 0)

    if fetched == 0:
        return "low (no URL fetched)"

    if found > fetched / 2:
        return "high"

    if found > 0:
        return "medium"

    return "low"


def run(args: argparse.Namespace) -> Tuple[dict, int]:
    """Read the inputs, fetch the sample, write url-evidence.csv; return the summary and exit code.

    The exit code is 3 when the site blocked the run (429, repeated 401/403), 0 otherwise."""
    reading = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    known = load_cause_classes(args.classes)

    if not args.export and not args.sitemap and not args.urls:
        raise InputError("give at least one of --export, --sitemap, --urls")

    export = read_export(args.export, known)
    published = read_published(args.published)
    fetcher = fetcher_from_args(args)
    stop_reason = None
    exit_code = 0

    try:
        sitemap_info = read_sitemap(args.sitemap, fetcher)
    except Blocked as error:
        sitemap_info = {"source": untrusted(args.sitemap, 300), "urls": {}, "files": [],
                        "errors": [str(error)], "truncated": False}
        stop_reason = str(error)
        exit_code = 3

    lastmod = lastmod_check(sitemap_info["urls"], args.lastmod_uniform_share)
    items = collect_items(args, export, sitemap_info)

    for item in items:
        apply_age_gate(item, published, sitemap_info, lastmod["usable_as_age"], reading, args.age_days)

    candidates = [i for i in items if not i.row.get("too_early")]
    sample = spread_sample(candidates, max(args.sample, 0))

    for item in sample:
        item.row["sampled"] = True

    if stop_reason is None and sample:
        stop_reason = fetch_items(sample, fetcher, site_host(args.sitemap, items), reading, args.age_days)

        if stop_reason:
            exit_code = 3

    for item in sample:
        if item.row.get("judged") and not item.row.get("too_early"):
            item.row["evidence_verdict"] = evidence_verdict(item.classes, item.row.get("signals", []))

    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "url-evidence.csv")
    write_csv([csv_row(i) for i in items], CSV_FIELDS, csv_path)

    unclean = [
        untrusted(i.url, 300) for i in sample
        if i.row.get("in_sitemap") is True and i.row.get("judged")
        and (i.row.get("http_status") != 200
             or set(i.row.get("signals", [])) & (BLOCKING_SIGNALS | {"redirected"}))
    ]
    by_class: Counter[str] = Counter()

    for row in status_summary(items, export):
        for name in row["cause_class"]:
            by_class[name] += row["urls_in_export_counts"] or row["urls_listed"]

    summary = {
        "generated_on": today(),
        "reading_date": reading.isoformat(),
        "tool": "indexing_causes.py",
        "labels_source": "references/cause-classes.md: English labels as last known, French labels read on "
                         "real exports (2026-10-21). Verify them against Google's current Page indexing "
                         "documentation and date the reading. Labels in other languages are reported as "
                         "UNMAPPED, never translated.",
        "export": {
            "files": export["files"],
            "tables": export["tables"],
            "url_tables_without_status": export["unassigned_tables"],
        },
        "ratio": export["ratio"] or {"status": "not measurable from this export" if args.export
                                     else "not measurable here: no Page indexing export"},
        "statuses": status_summary(items, export),
        "unmapped_labels_quoted": sorted(untrusted(label, 200) for label, c in export["labels_seen"].items()
                                         if c == ["UNMAPPED"]),
        "urls_by_cause_class": dict(by_class),
        "too_early": {
            "count": sum(1 for i in items if i.row.get("too_early")),
            "rule": f"younger than {args.age_days} days at the reading date ({HEURISTIC}); not diagnosed",
            "urls_without_known_age": sum(1 for i in items if i.row.get("age_days") is None),
        },
        "sitemap": {
            "source": sitemap_info["source"],
            "files_read": len(sitemap_info["files"]),
            "urls": len(sitemap_info["urls"]),
            "errors": sitemap_info["errors"],
            "truncated": sitemap_info["truncated"],
            "lastmod": lastmod,
            "sampled_sitemap_urls_not_clean_200": unclean,
        },
        "sample": {
            "requested": args.sample,
            "candidates": len(candidates),
            "sampled": len(sample),
            "fetched": sum(1 for i in sample if i.row.get("fetched")),
            "not_sampled": len(candidates) - len(sample),
        },
        "stop_reason": stop_reason,
        "csv": csv_path,
        "not_measured": not_measured(args, export, sitemap_info),
    }

    return summary, exit_code


def not_measured(args: argparse.Namespace, export: Export, sitemap_info: SitemapInfo) -> List[str]:
    """What this run cannot tell, for the summary."""
    notes = [
        "Google's reasons: the export gives a status, not a reason",
        "inlinks: not counted here (use seo-internal-links)",
        "Blocked by page removal tool: not testable from outside, ask the user to check Removals",
        "JavaScript-rendered content: static HTML only",
        "age from a previous export: not supported, pass --published",
    ]

    if not args.export:
        notes.append("ratio and Google-side statuses: no Page indexing export")

    if args.export and export["ratio"] is None:
        notes.append("ratio: no chart table with recognised 'Indexed' / 'Not indexed' "
                     "(or 'Dans l'index' / 'Non indexées') columns")

    if not sitemap_info["source"]:
        notes.append("sitemap membership: no --sitemap")

    return notes


def csv_row(item: UrlItem) -> dict:
    row = dict(item.row)
    row["url"] = untrusted(item.url, 300)
    row["status_in_export"] = untrusted(item.status, 200)
    row["cause_class"] = "/".join(item.classes)
    row["signals"] = " ".join(row.get("signals", []))

    return row


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.today:
        try:
            datetime.date.fromisoformat(args.today)
        except ValueError:
            print("error: --today must be YYYY-MM-DD", file=sys.stderr)
            return 2

    try:
        summary, code = run(args)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    emit_json(summary)

    return code


if __name__ == "__main__":
    sys.exit(main())
