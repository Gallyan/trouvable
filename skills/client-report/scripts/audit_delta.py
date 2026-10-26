#!/usr/bin/env python3
"""Compare two runs of the same audit: two issues CSV files (one row per check or finding),
or two JSON summaries. Says what was fixed, what is new, what is still open, by severity and
by domain, how measured figures moved between the two dates, and whether the runs compare.

Usage: python3 scripts/audit_delta.py --before old/issues.csv --after new/issues.csv
       --before-date YYYY-MM-DD --after-date YYYY-MM-DD
       [--before-summary old/summary.json --after-summary new/summary.json]
       [--key check_id] [--domain-column area] [--checked-ratio 0.2] [--csv delta.csv] [--out delta.json]
       python3 scripts/audit_delta.py --before old.json --after new.json [--before-date ... --after-date ...]

Network: none. Inputs are only read.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

from seokit.report import emit_json, today, untrusted, write_csv
from seokit.tables import TableError, parse_number, read_tables

MAX_JSON_BYTES = 20_000_000
MAX_LEAVES = 20_000
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
OPEN = "fail"
MEASURED = ("pass", "fail", "not-applicable")
KNOWN_STATUSES = ("pass", "fail", "not-measured", "not-applicable")
TRUE_VALUES = ("yes", "true", "1", "y", "oui")
SCOPE_KEYS = {
    "start_url", "site", "mode", "max_pages", "stop_reason", "offline", "sections", "date_range",
    "export_type", "market", "markets", "engines", "brand", "brand_terms", "min_runs", "panel",
    "search_type", "country", "device",
}
CSV_FIELDS = [
    "key", "change", "severity", "domain", "status_before", "status_after", "affected_before",
    "affected_after", "checked_before", "checked_after", "label_before", "label_after",
    "date_before", "date_after", "example_url_text", "note",
]
FIGURE_FIELDS = ["path", "before", "after", "change", "date_before", "date_after", "label_before", "label_after"]
CHANGE_ORDER = (
    "fixed", "new", "still-open", "no-longer-measured", "missing-from-after", "newly-measured",
    "lost-coverage", "unchanged",
)


class DeltaError(ValueError):
    pass


def parse_date(value: Optional[str], flag: str) -> Optional[str]:
    if value is None:
        return None

    if not DATE_PATTERN.fullmatch(value):
        raise DeltaError(f"{flag} must be YYYY-MM-DD, got {untrusted(value, 40)!r}")

    try:
        datetime.date.fromisoformat(value)
    except ValueError as error:
        raise DeltaError(f"{flag}: {error}") from error

    return value


def check_order(before: Optional[str], after: Optional[str]) -> None:
    if before and after and before >= after:
        raise DeltaError(f"--before-date {before} is not earlier than --after-date {after}")


# ---------------------------------------------------------------- CSV runs


def load_issues(path: str, keys: List[str]) -> Tuple[List[str], Dict[str, Dict[str, str]], List[str]]:
    """Read an issues file: its lowercased headers, its rows by key, and the keys marked dropped.

    Raises DeltaError on an unreadable file, a missing column, an empty or duplicate key, or no row.
    """
    try:
        tables = read_tables(path)
    except (OSError, TableError) as error:
        raise DeltaError(f"cannot read {path}: {error}") from error

    if not tables:
        raise DeltaError(f"{path}: no table found")

    table = tables[0]
    headers = [h.strip().lower() for h in table.headers]
    missing = [c for c in keys + ["status"] if c not in headers]

    if missing:
        raise DeltaError(f"{path}: missing column(s) {', '.join(missing)}")

    rows: Dict[str, Dict[str, str]] = {}
    dropped: List[str] = []

    for raw in table.rows:
        record = {h: (raw[i].strip() if i < len(raw) else "") for i, h in enumerate(headers)}

        if not any(record.values()):
            continue

        key = " | ".join(record[k] for k in keys)

        if not key.strip(" |"):
            raise DeltaError(f"{path}: a row has an empty key ({', '.join(keys)})")

        # seo-audit marks a false positive with status=dropped; a `dropped` column is accepted too.
        if record.get("dropped", "").lower() in TRUE_VALUES or record.get("status", "").strip().lower() == "dropped":
            dropped.append(key)
            continue

        if key in rows:
            raise DeltaError(f"{path}: duplicate key {untrusted(key, 80)!r}; pass more columns to --key")

        rows[key] = record

    if not rows:
        raise DeltaError(f"{path}: no data row")

    return headers, rows, dropped


def status_of(record: Optional[Dict[str, str]]) -> str:
    if record is None:
        return "absent"

    value = record.get("status", "").lower().replace(" ", "-").replace("_", "-")

    return value if value in KNOWN_STATUSES else "unknown"


def classify(before: str, after: str) -> str:
    """The change category (one of CHANGE_ORDER) of a check from its status in each run."""
    if after == "absent":
        return "missing-from-after" if before == OPEN else "unchanged"

    if before == OPEN and after == OPEN:
        return "still-open"

    if before == OPEN and after == "pass":
        return "fixed"

    if before == OPEN:
        return "no-longer-measured"

    if after == OPEN:
        return "new"

    if before in MEASURED and after == "not-measured":
        return "lost-coverage"

    if before in ("not-measured", "absent") and after in MEASURED:
        return "newly-measured"

    return "unchanged"


def number(value: str) -> Optional[float]:
    return parse_number(value) if value else None


def compare_issues(args: argparse.Namespace) -> Tuple[dict, List[dict]]:
    """Compare two issues CSV runs key by key.

    Returns the JSON result (unchanged rows left out of its "rows") and every compared row, for the CSV.
    """
    if not args.before_date or not args.after_date:
        raise DeltaError("--before-date and --after-date are required with CSV runs (issues CSV files carry no date)")

    keys = [k.strip().lower() for k in args.key.split(",") if k.strip()]
    domain_column = args.domain_column.strip().lower()
    _, before_rows, before_dropped = load_issues(args.before, keys)
    _, after_rows, after_dropped = load_issues(args.after, keys)
    shared = [k for k in before_rows if k in after_rows]

    if not shared:
        raise DeltaError("the two runs share no key: not two runs of the same audit (check --key)")

    reasons: List[str] = []
    only_before = [k for k in before_rows if k not in after_rows]
    only_after = [k for k in after_rows if k not in before_rows]

    if only_before or only_after:
        reasons.append(f"{len(only_before)} key(s) only in the first run, {len(only_after)} only in the second "
                       "(rubric or scope changed)")

    rows: List[dict] = []
    unknown: List[str] = []

    for key in list(before_rows) + only_after:
        old = before_rows.get(key)
        new = after_rows.get(key)
        status_before = status_of(old)
        status_after = status_of(new)

        for status, record in ((status_before, old), (status_after, new)):
            if status == "unknown" and record is not None:
                unknown.append(f"{untrusted(key, 80)}: {untrusted(record.get('status'), 40)!r}")

        latest = new or old or {}
        notes: List[str] = []

        if old and new and old.get("severity", "") != new.get("severity", ""):
            notes.append("severity changed between runs")

        if old and new and old.get("label", "") != new.get("label", ""):
            notes.append("label changed between runs")

        checked_old = number(old.get("checked", "")) if old else None
        checked_new = number(new.get("checked", "")) if new else None

        drift = abs(checked_new - checked_old) / checked_old if checked_old and checked_new is not None else 0

        if drift > args.checked_ratio:
            notes.append("checked base differs beyond --checked-ratio")

        rows.append({
            "key": untrusted(key, 200),
            "change": classify(status_before, status_after),
            "severity": untrusted((latest.get("severity") or "unknown").lower(), 40),
            "domain": untrusted(latest.get(domain_column) or "unknown", 80),
            "status_before": status_before,
            "status_after": status_after,
            "affected_before": old.get("affected", "") if old else "",
            "affected_after": new.get("affected", "") if new else "",
            "checked_before": old.get("checked", "") if old else "",
            "checked_after": new.get("checked", "") if new else "",
            "label_before": untrusted(old.get("label", ""), 40) if old else "",
            "label_after": untrusted(new.get("label", ""), 40) if new else "",
            "date_before": args.before_date,
            "date_after": args.after_date,
            "example_url_text": untrusted(latest.get("example_url", ""), 300),
            "note": "; ".join(notes),
        })

    for flag, count in (
        ("severity changed between runs", "severity"),
        ("label changed between runs", "label"),
        ("checked base differs beyond --checked-ratio", "checked base"),
    ):
        hits = sum(1 for r in rows if flag in r["note"])

        if hits:
            reasons.append(f"{hits} check(s): {count} differs between runs")

    reasons.extend(scope_differences(args.before_summary, args.after_summary))
    by_change = {c: sum(1 for r in rows if r["change"] == c) for c in CHANGE_ORDER}
    result = {
        "generated_on": today(),
        "kind": "issues",
        "before": {"file": args.before, "date": args.before_date, "rows": len(before_rows),
                   "dropped": len(before_dropped)},
        "after": {"file": args.after, "date": args.after_date, "rows": len(after_rows), "dropped": len(after_dropped)},
        "key_columns": keys,
        "comparable": not reasons,
        "comparability_reasons": reasons,
        "by_change": by_change,
        "by_severity": breakdown(rows, "severity"),
        "by_domain": breakdown(rows, "domain"),
        "open_before": sum(1 for r in rows if r["status_before"] == OPEN),
        "open_after": sum(1 for r in rows if r["status_after"] == OPEN),
        "unknown_statuses": unknown,
        "rows": [r for r in rows if r["change"] != "unchanged"],
        "limits": [
            "A check missing from the second run or no longer measured is not counted as fixed.",
            "Counts compare the two files as given; nothing is re-measured.",
            "Labels and dates are carried from the inputs and the date flags, not checked against the site.",
        ],
    }

    return result, rows


def breakdown(rows: List[dict], field: str) -> Dict[str, Dict[str, int]]:
    """Counts of changed rows per value of field, then per change, sorted by value."""
    table: Dict[str, Dict[str, int]] = {}

    for row in rows:
        if row["change"] == "unchanged":
            continue

        bucket = table.setdefault(row[field], {})
        bucket[row["change"]] = bucket.get(row["change"], 0) + 1

    return dict(sorted(table.items()))


# ---------------------------------------------------------------- JSON runs


def load_json(path: Optional[str]) -> Optional[object]:
    if path is None:
        return None

    try:
        if os.path.getsize(path) > MAX_JSON_BYTES:
            raise DeltaError(f"{path}: larger than {MAX_JSON_BYTES} bytes")

        with open(path, encoding="utf-8-sig") as handle:
            return json.load(handle)
    except OSError as error:
        raise DeltaError(f"cannot read {path}: {error}") from error
    except ValueError as error:
        raise DeltaError(f"{path}: not valid JSON ({error})") from error
    except RecursionError as error:
        raise DeltaError(f"{path}: JSON nested too deeply") from error


def flatten(data: object, prefix: str = "", out: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    """JSON leaves by dotted path (list items as [i]); bounded to 100 levels and MAX_LEAVES values."""
    out = {} if out is None else out

    if prefix.count(".") + prefix.count("[") > 100:
        raise DeltaError("JSON summary nested more than 100 levels deep")

    if len(out) > MAX_LEAVES:
        raise DeltaError(f"more than {MAX_LEAVES} values in a JSON summary")

    if isinstance(data, dict):
        for key, value in data.items():
            flatten(value, f"{prefix}.{key}" if prefix else str(key), out)
        return out

    if isinstance(data, list):
        for index, value in enumerate(data):
            flatten(value, f"{prefix}[{index}]", out)
        return out

    out[prefix] = data

    return out


def segments(path: str) -> List[str]:
    return [s for s in re.split(r"[.\[\]]", path) if s and not s.isdigit()]


def is_scope(path: str) -> bool:
    return any(s in SCOPE_KEYS for s in segments(path))


def scope_differences(before_path: Optional[str], after_path: Optional[str]) -> List[str]:
    """Scope differences between the two summary files given with the CSV runs; [] when neither is given."""
    if not before_path and not after_path:
        return []

    if not before_path or not after_path:
        raise DeltaError("pass both --before-summary and --after-summary, or neither")

    before = flatten(load_json(before_path))
    after = flatten(load_json(after_path))

    return scope_reasons(before, after)


def scope_reasons(before: Dict[str, object], after: Dict[str, object]) -> List[str]:
    """One reason per scope setting (SCOPE_KEYS) whose value differs between two flattened summaries."""
    reasons = []

    for path in sorted(set(before) | set(after)):
        if not is_scope(path):
            continue

        old = before.get(path, "(absent)")
        new = after.get(path, "(absent)")

        if old != new:
            reasons.append(f"scope differs at {untrusted(path, 120)}: {untrusted(str(old), 80)!r} then "
                           f"{untrusted(str(new), 80)!r}")

    return reasons


def label_for(flat: Dict[str, object], path: str) -> str:
    """The label sitting next to a figure in a flattened summary, or "" when there is none."""
    parent = path.rsplit(".", 1)[0] if "." in path else ""
    value = flat.get(f"{parent}.label" if parent else "label")

    return (untrusted(value, 40)) if isinstance(value, str) else ""


def numeric_leaves(flat: Dict[str, object]) -> Dict[str, float]:
    """The int and float values of a flattened summary, booleans left out, in their original order."""
    return {p: v for p, v in flat.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def compare_summaries(args: argparse.Namespace) -> Tuple[dict, List[dict]]:
    """Compare the numeric figures of two JSON summaries from the same tool.

    Returns the JSON result and its figures. Dates default to each summary's generated_on.
    """
    before_data = load_json(args.before)
    after_data = load_json(args.after)

    if not isinstance(before_data, dict) or not isinstance(after_data, dict):
        raise DeltaError("each JSON summary must be an object")

    before = flatten(before_data)
    after = flatten(after_data)
    date_before = args.before_date or parse_date(str(before.get("generated_on", ""))[:10] or None, "generated_on")
    date_after = args.after_date or parse_date(str(after.get("generated_on", ""))[:10] or None, "generated_on")

    if not date_before or not date_after:
        raise DeltaError("no generated_on in a summary: pass --before-date and --after-date")

    check_order(date_before, date_after)

    if before.get("tool") != after.get("tool"):
        raise DeltaError(f"summaries come from different tools: {untrusted(str(before.get('tool')), 60)!r} "
                         f"and {untrusted(str(after.get('tool')), 60)!r}")

    before_numbers = numeric_leaves(before)
    after_numbers = numeric_leaves(after)
    numeric = list(before_numbers)
    shared = [p for p in numeric if p in after_numbers]

    if not shared:
        raise DeltaError("the two summaries share no numeric figure: not two runs of the same tool")

    reasons = scope_reasons(before, after)

    if any("[" in p for p in shared):
        reasons.append("some figures sit in lists; list positions may not hold the same item in both runs")

    figures = []

    for path in shared:
        if is_scope(path) or path.endswith("generated_on"):
            continue

        old, new = before_numbers[path], after_numbers[path]
        figures.append({
            "path": untrusted(path, 200),
            "before": old,
            "after": new,
            "change": round(new - old, 6),
            "date_before": date_before,
            "date_after": date_after,
            "label_before": label_for(before, path),
            "label_after": label_for(after, path),
        })

    result = {
        "generated_on": today(),
        "kind": "summary",
        "before": {"file": args.before, "date": date_before},
        "after": {"file": args.after, "date": date_after},
        "comparable": not reasons,
        "comparability_reasons": reasons,
        "figures": figures,
        "only_before": sorted(untrusted(p, 200) for p in numeric if p not in shared),
        "only_after": sorted(untrusted(p, 200) for p in after_numbers if p not in before),
        "limits": [
            "Figures are copied from the two summaries; nothing is re-measured or re-estimated.",
            "An empty label means the summary gave none: take it from the source report.",
        ],
    }

    return result, figures


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two runs of the same audit (offline).")
    parser.add_argument("--before", required=True, help="first run: issues CSV or JSON summary")
    parser.add_argument("--after", required=True, help="second run, same format as --before")
    parser.add_argument("--before-date", help="YYYY-MM-DD of the first run (required for CSV runs)")
    parser.add_argument("--after-date", help="YYYY-MM-DD of the second run (required for CSV runs)")
    parser.add_argument("--before-summary", help="summary.json of the first CSV run, for scope checks")
    parser.add_argument("--after-summary", help="summary.json of the second CSV run, for scope checks")
    parser.add_argument("--key", default="check_id", help="comma-separated key column(s), default check_id")
    parser.add_argument("--domain-column", default="area", help="column grouping checks by domain, default area")
    parser.add_argument("--checked-ratio", type=float, default=0.2,
                        help="relative change of a check's 'checked' base that makes runs not comparable (0.2)")
    parser.add_argument("--csv", help="write the delta rows or figures as CSV to this path ('-' for stdout)")
    parser.add_argument("--out", help="write the JSON result to this path instead of stdout")

    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    """Compare two CSV runs or two JSON summaries and write the JSON and optional CSV; returns 2 on bad input."""
    args = parse_args(argv)

    try:
        args.before_date = parse_date(args.before_date, "--before-date")
        args.after_date = parse_date(args.after_date, "--after-date")
        check_order(args.before_date, args.after_date)
        kinds = {os.path.splitext(p)[1].lower() == ".json" for p in (args.before, args.after)}

        if len(kinds) != 1:
            raise DeltaError("--before and --after must be the same format (two CSV or two JSON files)")

        if kinds == {True}:
            result, rows = compare_summaries(args)
            fields = FIGURE_FIELDS
        else:
            result, rows = compare_issues(args)
            fields = CSV_FIELDS
    except DeltaError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.csv:
        write_csv([r for r in rows if r.get("change") != "unchanged"], fields, args.csv)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            emit_json(result, handle)
    elif args.csv != "-":
        emit_json(result)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
