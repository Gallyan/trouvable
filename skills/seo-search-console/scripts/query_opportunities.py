#!/usr/bin/env python3
"""Read Search Console Performance exports and print an honest JSON summary.

Sample verdict (non-brand only), brand / non-brand split, near-page-one queries, the
site's own CTR-by-position curve (or "not computable yet"), click-through gaps against
that curve, competing pages when a query+page table exists, Discover / News detection,
and an optional comparison with a previous-period export.

Usage:
    python3 scripts/query_opportunities.py --queries Queries.csv --pages Pages.csv --brand "acme,acmé"
    python3 scripts/query_opportunities.py --queries export.zip --pages export.zip --brand acme --compare prev.zip

Network: none. Reads local CSV, XLSX or ZIP files only.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from seokit import gsc
from seokit.report import emit_json, today, untrusted
from seokit.tables import Table, TableError, parse_number, read_tables

HEURISTIC = "heuristic, to calibrate"

# references/sample-verdict.md
INSUFFICIENT_IMPRESSIONS = 300
INSUFFICIENT_QUERIES = 20
USABLE_IMPRESSIONS = 3000
USABLE_CLICKS = 30
CURVE_MIN_BUCKET_IMPRESSIONS = 50
CURVE_MIN_BUCKETS = 5

# references/manual-route.md and SKILL.md step 4
NEAR_MIN_POSITION = 8.0
NEAR_MAX_POSITION = 20.0
NEAR_TOP = 20
COMPETING_TOP_QUERIES = 10

# Script design choices (not in the references): heuristic, to calibrate.
GAP_RATIO = 0.5
GAP_MIN_IMPRESSIONS = 50
COMPETING_MIN_SHARE = 0.2
SHORT_RANGE_DAYS = 28
ANONYMISED_NOTE_SHARE = 0.2

URL_RE = re.compile(r"^https?://", re.I)


class InputError(Exception):
    pass


# --------------------------------------------------------------------------- helpers

def fold(text: str) -> str:
    """Case- and accent-insensitive form (seokit.text.normalize keeps accents)."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))

    return " ".join(stripped.casefold().split())


def parse_brand_terms(value: Optional[str]) -> List[str]:
    if not value:
        return []

    return [fold(term) for term in value.split(",") if fold(term)]


def is_brand(query: str, terms: List[str]) -> bool:
    folded = fold(query)

    return any(term in folded for term in terms)


def ratio(numerator: float, denominator: float) -> Optional[float]:
    if not denominator:
        return None

    return round(numerator / denominator, 4)


def load_tables(path: str) -> List[Table]:
    if not os.path.isfile(path):
        raise InputError(f"file not found: {path}")

    try:
        return read_tables(path)
    except TableError as error:
        raise InputError(f"{path}: {error}") from error
    except (OSError, ValueError) as error:
        raise InputError(f"{path}: not readable ({error})") from error


def unmapped_columns(table: Table, detected: gsc.GscTable) -> List[str]:
    """Headers of the table that no detected column role uses, quoted."""
    known = set(detected.columns.values())

    if detected.key:
        known.add(detected.key)

    return [untrusted(h, 80) for h in table.headers if h and h not in known]


def describe(table: Table, detected: gsc.GscTable) -> dict:
    return {
        "table_name": untrusted(table.name, 120),
        "kind": detected.kind,
        "rows": len(table.rows),
        "truncated": table.truncated,
        "columns_mapped": {role: untrusted(h, 80) for role, h in detected.columns.items()},
        "columns_not_mapped": unmapped_columns(table, detected),
        "notes": [untrusted(n, 200) for n in detected.notes],
    }


def pick_table(candidates: List[Tuple[Table, gsc.GscTable]], wanted: str,
               notes: List[str]) -> Optional[Tuple[Table, gsc.GscTable]]:
    """Pick the queries or pages table among the tables of one file."""
    exact = [c for c in candidates if c[1].kind == wanted]

    if exact:
        return exact[0]

    if wanted == "page":
        return None

    loose = [c for c in candidates if c[1].kind == "query-or-other" and "clicks" in c[1].columns]

    if not loose:
        return None

    if len(loose) > 1:
        loose.sort(key=lambda c: len(c[0].rows), reverse=True)
        notes.append(f"several text-keyed tables found; '{untrusted(loose[0][0].name, 80)}' "
                     "used as the queries table because it has the most rows: confirm with the user")

    return loose[0]


# --------------------------------------------------------------------------- query+page table

def number_at(row: List[str], index: Optional[int]) -> float:
    if index is None or index >= len(row):
        return 0.0

    return parse_number(row[index]) or 0.0


def find_query_page_table(tables: List[Table]) -> Optional[dict]:
    """A table with one URL column and one other text column, plus clicks/impressions."""
    for table in tables:
        if len(table.rows) == 0:
            continue

        url_col = None
        text_col = None

        for index in range(len(table.headers)):
            values = [r[index] for r in table.rows[:500] if index < len(r) and r[index]]

            if not values:
                continue

            urls = sum(bool(URL_RE.match(v)) for v in values)
            numbers = sum(parse_number(v) is not None for v in values)

            if urls >= 0.8 * len(values) and url_col is None:
                url_col = index
            elif numbers < 0.9 * len(values) and text_col is None:
                text_col = index

        if url_col is None or text_col is None:
            continue

        detected = gsc.detect(table)

        if "impressions" not in detected.columns:
            continue

        impressions_index = table.headers.index(detected.columns["impressions"])
        clicks_index = table.headers.index(detected.columns["clicks"]) if "clicks" in detected.columns else None
        rows = []

        for raw in table.rows:
            if url_col >= len(raw) or text_col >= len(raw):
                continue

            rows.append({
                "query": raw[text_col],
                "page": raw[url_col],
                "impressions": number_at(raw, impressions_index),
                "clicks": number_at(raw, clicks_index),
            })

        return {"table_name": table.name, "rows": rows}

    return None


# --------------------------------------------------------------------------- analyses

def totals(rows: List[dict]) -> dict:
    """Clicks, impressions, CTR and the number of queries with impressions."""
    clicks = sum(r.get("clicks") or 0 for r in rows)
    impressions = sum(r.get("impressions") or 0 for r in rows)

    return {
        "queries": sum(1 for r in rows if (r.get("impressions") or 0) > 0),
        "clicks": int(clicks),
        "impressions": int(impressions),
        "ctr": ratio(clicks, impressions),
    }


def brand_split(rows: List[dict], terms: List[str]) -> Tuple[List[dict], List[dict], dict]:
    """Split query rows into brand and non-brand; return both lists and their totals.

    Without brand terms every row counts as non-brand and the summary says the split is not measurable."""
    if not terms:
        return [], rows, {
            "status": "not measurable: no brand terms given (--brand)",
            "all_queries": totals(rows),
            "label": "measured",
        }

    brand = [r for r in rows if is_brand(r["key"], terms)]
    non_brand = [r for r in rows if not is_brand(r["key"], terms)]
    brand_totals = totals(brand)
    non_totals = totals(non_brand)
    all_clicks = brand_totals["clicks"] + non_totals["clicks"]
    all_impressions = brand_totals["impressions"] + non_totals["impressions"]

    summary = {
        "brand": brand_totals,
        "non_brand": non_totals,
        "non_brand_click_share": ratio(non_totals["clicks"], all_clicks),
        "non_brand_impression_share": ratio(non_totals["impressions"], all_impressions),
        "label": "measured",
        "match_rule": "query contains a brand term, case- and accent-insensitive",
    }

    return brand, non_brand, summary


def sample_verdict(non_brand: List[dict], thresholds: argparse.Namespace) -> dict:
    """Whether the non-brand sample is insufficient, limited or usable, against the thresholds."""
    numbers = totals(non_brand)
    reasons = []

    if numbers["impressions"] < thresholds.min_impressions:
        reasons.append(f"non-brand impressions {numbers['impressions']} < {thresholds.min_impressions}")

    if numbers["queries"] < thresholds.min_queries:
        reasons.append(f"non-brand queries with impressions {numbers['queries']} < {thresholds.min_queries}")

    if reasons:
        verdict = "insufficient"
    else:
        if numbers["impressions"] < thresholds.usable_impressions:
            reasons.append(f"non-brand impressions {numbers['impressions']} < {thresholds.usable_impressions}")

        if numbers["clicks"] < thresholds.usable_clicks:
            reasons.append(f"non-brand clicks {numbers['clicks']} < {thresholds.usable_clicks}")

        verdict = "limited" if reasons else "usable"

    return {
        "verdict": verdict,
        "non_brand_impressions": numbers["impressions"],
        "non_brand_queries_with_impressions": numbers["queries"],
        "non_brand_clicks": numbers["clicks"],
        "reasons": reasons,
        "label": "measured",
        "rule": "references/sample-verdict.md (" + HEURISTIC + "; a design choice of the skill, not a Google rule)",
    }


def ctr_curve(rows: List[dict], min_bucket: int, min_buckets: int) -> dict:
    """The site's own non-brand CTR by rounded position 1-10, or 'not computable yet' with too few buckets."""
    buckets: Dict[int, List[float]] = defaultdict(lambda: [0.0, 0.0])

    for row in rows:
        position = row.get("position")

        if position is None or position <= 0:
            continue

        bucket = int(round(position))

        if bucket < 1 or bucket > 10:
            continue

        buckets[bucket][0] += row.get("clicks") or 0
        buckets[bucket][1] += row.get("impressions") or 0

    points = []
    skipped = []

    for position in sorted(buckets):
        clicks, impressions = buckets[position]

        if impressions < min_bucket:
            skipped.append({"position": position, "impressions": int(impressions)})
            continue

        points.append({
            "position": position,
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": ratio(clicks, impressions),
        })

    if len(points) < min_buckets:
        return {
            "status": "not computable yet",
            "why": f"{len(points)} position buckets with {min_bucket}+ non-brand impressions, "
                   f"{min_buckets} needed ({HEURISTIC})",
            "points": points,
            "buckets_skipped": skipped,
        }

    return {
        "status": "computed",
        "source": "this site's own non-brand rows, grouped by rounded position 1-10",
        "label": "measured",
        "points": points,
        "buckets_skipped": skipped,
    }


def query_out(row: dict) -> dict:
    """A query row as output: quoted query text, clicks, impressions, CTR, position."""
    clicks = row.get("clicks") or 0
    impressions = row.get("impressions") or 0
    ctr = row.get("ctr")

    return {
        "query_text": untrusted(row["key"], 200),
        "clicks": int(clicks),
        "impressions": int(impressions),
        "ctr": ctr if ctr is not None else ratio(clicks, impressions),
        "position": row.get("position"),
    }


def near_page_one(rows: List[dict], args: argparse.Namespace) -> List[dict]:
    """Queries ranking just beyond page one, by impressions, at most --top."""
    candidates = [
        r for r in rows
        if r.get("position") is not None
        and args.near_min_position <= r["position"] <= args.near_max_position
        and (r.get("impressions") or 0) >= args.near_min_impressions
        and (r.get("impressions") or 0) > 0
    ]
    candidates.sort(key=lambda r: r.get("impressions") or 0, reverse=True)

    return [query_out(r) for r in candidates[: args.top]]


def ctr_gaps(rows: List[dict], curve: dict, args: argparse.Namespace) -> List[dict]:
    """Queries whose CTR is far below the site curve at their position, by clicks missed; [] without a curve."""
    if curve["status"] != "computed":
        return []

    by_position = {p["position"]: p["ctr"] for p in curve["points"]}
    gaps = []

    for row in rows:
        position = row.get("position")
        impressions = row.get("impressions") or 0

        if position is None or impressions < args.gap_min_impressions:
            continue

        expected = by_position.get(int(round(position)))

        if not expected:
            continue

        actual = (row.get("clicks") or 0) / impressions

        if actual >= expected * args.gap_ratio:
            continue

        item = query_out(row)
        item["site_curve_ctr_at_position"] = expected
        item["clicks_at_site_curve"] = round(expected * impressions, 1)
        item["clicks_at_site_curve_label"] = "estimated (site curve CTR x impressions; real effect ranges from zero)"
        gaps.append(item)

    gaps.sort(key=lambda g: g["clicks_at_site_curve"] - g["clicks"], reverse=True)

    return gaps[: args.top]


def competing_pages(query_pages: Optional[dict], terms: List[str], args: argparse.Namespace) -> dict:
    """Non-brand queries where 2+ URLs each hold a large share of the impressions, at most --top."""
    if query_pages is None:
        return {
            "status": "not measurable with these exports",
            "why": "needs a query+page table (one query, several URLs); "
                   "see references/what-to-export.md",
        }

    grouped: Dict[str, List[dict]] = defaultdict(list)

    for row in query_pages["rows"]:
        if terms and is_brand(row["query"], terms):
            continue

        grouped[row["query"]].append(row)

    findings: List[Dict[str, Any]] = []

    for query, rows in grouped.items():
        total = sum(r["impressions"] for r in rows)

        if total <= 0:
            continue

        sharing = [r for r in rows if r["impressions"] / total >= args.competing_min_share]

        if len(sharing) < 2:
            continue

        sharing.sort(key=lambda r: r["impressions"], reverse=True)
        findings.append({
            "query_text": untrusted(query, 200),
            "query_impressions": int(total),
            "pages": [
                {
                    "page_url": untrusted(r["page"], 300),
                    "impressions": int(r["impressions"]),
                    "clicks": int(r["clicks"]),
                    "impression_share": ratio(r["impressions"], total),
                }
                for r in sharing
            ],
        })

    findings.sort(key=lambda f: f["query_impressions"], reverse=True)

    return {
        "status": "measured",
        "source_table": untrusted(query_pages["table_name"], 120),
        "rule": f"2+ URLs each holding at least {args.competing_min_share:.0%} of a non-brand query's "
                f"impressions ({HEURISTIC})",
        "findings": findings[: args.top],
    }


def date_range(tables: List[Table]) -> dict:
    """First and last day of the dates table, when the export has one."""
    for table in tables:
        detected = gsc.detect(table)

        if detected.kind != "date":
            continue

        dates = sorted(r["key"] for r in detected.rows if r["key"])

        if not dates:
            continue

        days = len(set(dates))
        result = {"first_day": dates[0], "last_day": dates[-1], "days_with_data": days, "label": "reported"}

        if days < SHORT_RANGE_DAYS:
            result["note"] = f"range shorter than {SHORT_RANGE_DAYS} days: noisy for a small site"

        return result

    return {"status": "not measurable: no dates table in the export; ask the user for the date range"}


def anonymised_share(query_rows: List[dict], page_rows: Optional[List[dict]]) -> dict:
    """Share of the Pages total impressions missing from the Queries table (anonymised queries)."""
    if page_rows is None:
        return {"status": "not measurable: no pages table"}

    q = totals(query_rows)
    p = totals(page_rows)
    result = {
        "queries_table_impressions": q["impressions"],
        "pages_table_impressions": p["impressions"],
        "queries_table_clicks": q["clicks"],
        "pages_table_clicks": p["clicks"],
        "label": "measured",
    }

    if p["impressions"] <= 0:
        return result

    share = max(0.0, 1 - q["impressions"] / p["impressions"])
    result["impressions_missing_from_queries_share"] = round(share, 4)

    if share >= ANONYMISED_NOTE_SHARE:
        result["note"] = ("Pages total is much larger than Queries total: Search Console omits rare "
                          "(anonymised) queries from query-level tables, the brand split covers only listed queries")

    return result


def pages_out(page_rows: List[dict], top: int) -> List[dict]:
    rows = sorted(page_rows, key=lambda r: r.get("clicks") or 0, reverse=True)

    return [
        {
            "page_url": untrusted(r["key"], 300),
            "clicks": int(r.get("clicks") or 0),
            "impressions": int(r.get("impressions") or 0) if r.get("impressions") is not None else None,
        }
        for r in rows[:top]
    ]


def comparison(current_rows: List[dict], previous_rows: List[dict], terms: List[str]) -> dict:
    """Brand and non-brand clicks and impressions now versus the previous-period export."""
    _, cur_non, cur = brand_split(current_rows, terms)
    _, prev_non, prev = brand_split(previous_rows, terms)

    def delta(part: str) -> dict:
        if part not in cur or part not in prev:
            return {}

        return {
            "clicks_now": cur[part]["clicks"],
            "clicks_before": prev[part]["clicks"],
            "clicks_change": cur[part]["clicks"] - prev[part]["clicks"],
            "impressions_now": cur[part]["impressions"],
            "impressions_before": prev[part]["impressions"],
            "impressions_change": cur[part]["impressions"] - prev[part]["impressions"],
        }

    if not terms:
        return {"all_queries": {
            "clicks_now": cur["all_queries"]["clicks"],
            "clicks_before": prev["all_queries"]["clicks"],
            "impressions_now": cur["all_queries"]["impressions"],
            "impressions_before": prev["all_queries"]["impressions"],
        }, "label": "measured", "note": "no brand terms: trend not split"}

    return {"brand": delta("brand"), "non_brand": delta("non_brand"), "label": "measured",
            "note": "compare equal-length periods; seasonality is not removed"}


# --------------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    """Command-line options, thresholds included."""
    parser = argparse.ArgumentParser(
        description="Offline reading of Search Console Performance exports (CSV, XLSX, ZIP). "
                    "No network. JSON on stdout.")
    parser.add_argument("--queries", required=True, help="Queries export (or the whole export ZIP/XLSX)")
    parser.add_argument("--pages", help="Pages export (may be the same ZIP/XLSX as --queries)")
    parser.add_argument("--brand", help='comma-separated brand terms, e.g. "acme,acmé,acme shop"')
    parser.add_argument("--compare", help="previous-period export (queries table) for the trend")
    parser.add_argument("--query-pages", help="optional query+page table, enables competing pages")
    parser.add_argument("--out", help="write the JSON here instead of stdout")
    parser.add_argument("--top", type=int, default=NEAR_TOP, help="max items per list (default 20)")

    group = parser.add_argument_group(f"thresholds ({HEURISTIC})")
    group.add_argument("--min-impressions", type=int, default=INSUFFICIENT_IMPRESSIONS)
    group.add_argument("--min-queries", type=int, default=INSUFFICIENT_QUERIES)
    group.add_argument("--usable-impressions", type=int, default=USABLE_IMPRESSIONS)
    group.add_argument("--usable-clicks", type=int, default=USABLE_CLICKS)
    group.add_argument("--near-min-position", type=float, default=NEAR_MIN_POSITION)
    group.add_argument("--near-max-position", type=float, default=NEAR_MAX_POSITION)
    group.add_argument("--near-min-impressions", type=int, default=0,
                       help="min impressions for near-page-one (default 0: top N by impressions)")
    group.add_argument("--curve-min-bucket", type=int, default=CURVE_MIN_BUCKET_IMPRESSIONS,
                       help="min impressions per position bucket (default 50)")
    group.add_argument("--curve-min-buckets", type=int, default=CURVE_MIN_BUCKETS,
                       help="buckets needed for a curve (default 5)")
    group.add_argument("--gap-ratio", type=float, default=GAP_RATIO,
                       help="flag a query whose CTR is below this fraction of the site curve (default 0.5)")
    group.add_argument("--gap-min-impressions", type=int, default=GAP_MIN_IMPRESSIONS)
    group.add_argument("--competing-min-share", type=float, default=COMPETING_MIN_SHARE,
                       help="share of a query's impressions a URL needs to count as competing (default 0.2)")

    return parser


def gather(paths: List[str]) -> Tuple[List[Table], List[Tuple[Table, gsc.GscTable]]]:
    """Tables of the given files (each real path read once), with their detected Search Console kind."""
    tables: List[Table] = []
    seen = set()

    for path in paths:
        real = os.path.realpath(path)

        if real in seen:
            continue

        seen.add(real)
        tables.extend(load_tables(path))

    return tables, [(t, gsc.detect(t)) for t in tables]


def analyse(args: argparse.Namespace) -> dict:
    """Read the exports and compute every section of the JSON summary.

    Raises InputError when a file is unreadable or holds no queries or pages table."""
    notes: List[str] = []
    terms = parse_brand_terms(args.brand)

    _, query_candidates = gather([args.queries])
    page_candidates: List[Tuple[Table, gsc.GscTable]] = []

    if args.pages:
        _, page_candidates = gather([args.pages])

    all_tables = [c[0] for c in query_candidates]

    if args.pages and os.path.realpath(args.pages) != os.path.realpath(args.queries):
        all_tables += [c[0] for c in page_candidates]

    query_pick = pick_table(query_candidates, "query", notes)
    page_pick = pick_table(page_candidates or query_candidates, "page", notes)

    if query_pick is None and page_pick is None:
        found = [f"{untrusted(t.name, 80)}: {d.kind}" for t, d in query_candidates + page_candidates]
        raise InputError("no queries or pages table recognised; tables found: " + "; ".join(found or ["none"]))

    same_file = args.pages and os.path.realpath(args.pages) == os.path.realpath(args.queries)
    described = query_candidates if same_file else query_candidates + page_candidates
    tables_read = [describe(t, d) for t, d in described]
    page_rows = page_pick[1].rows if page_pick else None
    has_position = query_pick is not None and "position" in query_pick[1].columns

    result: dict = {
        "generated_on": today(),
        "tool": "query_opportunities.py",
        "network": "none",
        "files": {"queries": os.path.basename(args.queries),
                  "pages": os.path.basename(args.pages) if args.pages else None},
        "tables_read": tables_read,
        "date_range": date_range(all_tables),
        "notes": notes,
    }

    if query_pick is None or not has_position:
        result["export_type"] = "discover-or-news"
        result["export_type_why"] = "no queries table with a position column"
        result["pages"] = pages_out(page_rows or (query_pick[1].rows if query_pick else []), args.top)
        result["not_measured"] = [
            "brand split, sample verdict, near page one, CTR curve, CTR gaps, competing pages: "
            "Discover and News exports have no queries or positions",
        ]

        return result

    query_rows = [r for r in query_pick[1].rows if r["key"]]
    result["export_type"] = "web-search"
    _, non_brand, split = brand_split(query_rows, terms)
    result["brand_split"] = split
    result["anonymised_queries"] = anonymised_share(query_rows, page_rows)
    verdict = sample_verdict(non_brand, args)
    result["sample_verdict"] = verdict

    not_measured = []

    if not terms:
        not_measured.append("brand split: no brand terms given; verdict computed on all queries")

    if page_rows is None:
        not_measured.append("pages: no pages table found (--pages)")

    if args.compare:
        _, previous = gather([args.compare])
        prev_pick = pick_table(previous, "query", notes)

        if prev_pick is None:
            not_measured.append("trend: no queries table recognised in --compare file")
        else:
            result["trend"] = comparison(query_rows, [r for r in prev_pick[1].rows if r["key"]], terms)
    else:
        result["trend"] = {"status": "not measurable: no comparison period (--compare)"}

    query_page_source = all_tables

    if args.query_pages:
        query_page_source = load_tables(args.query_pages)

    query_pages = find_query_page_table(query_page_source)

    if verdict["verdict"] == "insufficient":
        result["analyses"] = {
            "status": "skipped: sample insufficient",
            "advice": "too early to judge SEO: no ranked query list. Watch non-brand impressions and "
                      "the number of non-brand queries; look again when the export has grown past the "
                      "minimum thresholds",
        }
        result["not_measured"] = not_measured

        return result

    curve = ctr_curve(non_brand, args.curve_min_bucket, args.curve_min_buckets)
    result["analyses"] = {
        "provisional": verdict["verdict"] == "limited",
        "near_page_one": {
            "rule": f"non-brand, position {args.near_min_position:g}-{args.near_max_position:g}, "
                    f"sorted by impressions, top {args.top}",
            "label": "measured",
            "queries": near_page_one(non_brand, args),
        },
        "ctr_curve": curve,
        "ctr_gaps": {
            "rule": f"CTR below {args.gap_ratio:g} x site curve at the rounded position, "
                    f"{args.gap_min_impressions}+ impressions ({HEURISTIC})",
            "status": "computed" if curve["status"] == "computed" else "not computable yet",
            "queries": ctr_gaps(non_brand, curve, args),
        },
        "competing_pages": competing_pages(query_pages, terms, args),
    }

    if page_rows is not None:
        result["pages"] = pages_out(page_rows, args.top)

    result["not_measured"] = not_measured + [
        "why Google ranks a page where it does: the exports show outcomes, not causes",
        "live search results: check page one before recommending (SKILL.md step 5)",
    ]

    return result


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = analyse(args)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            emit_json(result, handle)

        print(f"written to {args.out}", file=sys.stderr)
        return 0

    emit_json(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
