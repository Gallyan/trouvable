#!/usr/bin/env python3
"""Pick the top failed checks of an audit issues.csv and print them as a proposal-ready table.

Usage: python3 scripts/proposal_findings.py --issues issues.csv [--top 5]
       [--min-severity low] [--format md|json|csv] [--out PATH]

Network: none. The issues file is only read, never written.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from seokit.report import emit_json, today, untrusted, write_csv
from seokit.tables import TableError, read_tables

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
KNOWN_STATUSES = ("pass", "fail", "not-measured", "not-applicable", "dropped")
REQUIRED_COLUMNS = ("check_id", "severity", "status", "evidence")
FIELDS = [
    "rank", "check_id", "area", "severity", "affected", "checked", "label",
    "example_url_text", "evidence_text", "fix_text", "done_when_text", "business_terms",
]
MD_FIELDS = [
    ("rank", "#"), ("check_id", "Check"), ("severity", "Severity"), ("affected", "Affected"),
    ("checked", "Checked"), ("label", "Label"), ("example_url_text", "Example URL"),
    ("evidence_text", "Evidence (quoted)"), ("business_terms", "In the prospect's terms"),
]


class IssuesError(ValueError):
    pass


def load_rows(path: str) -> List[Dict[str, str]]:
    try:
        tables = read_tables(path)
    except (OSError, TableError) as error:
        raise IssuesError(f"cannot read issues file: {error}") from error

    if not tables:
        raise IssuesError("no table found in the issues file")

    table = tables[0]
    headers = [h.strip().lower() for h in table.headers]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]

    if missing:
        raise IssuesError(f"issues file lacks columns: {', '.join(missing)} "
                          "(expected the issues.csv written by seo-audit)")

    rows = []

    for raw in table.rows:
        padded = raw + [""] * (len(headers) - len(raw))
        rows.append(dict(zip(headers, padded)))

    return rows


def whole(value: str) -> Optional[int]:
    value = (value or "").strip()

    return int(value) if value.isdigit() else None


def row_errors(number: int, row: Dict[str, str]) -> List[dict]:
    errors = []
    severity = row.get("severity", "").strip().lower()
    status = row.get("status", "").strip().lower()

    if severity not in SEVERITY_ORDER:
        errors.append({"data_row": number, "field": "severity", "problem": "unknown severity",
                       "value_text": untrusted(severity, 60)})

    if status not in KNOWN_STATUSES:
        errors.append({"data_row": number, "field": "status", "problem": "unknown status",
                       "value_text": untrusted(status, 60)})

    for column in ("affected", "checked"):
        value = row.get(column, "").strip()

        if value and whole(value) is None:
            errors.append({"data_row": number, "field": column, "problem": "not a whole number",
                           "value_text": untrusted(value, 60)})

    return errors


def sort_key(row: Dict[str, str]) -> tuple:
    severity = SEVERITY_ORDER.get(row.get("severity", "").strip().lower(), 3)
    affected = whole(row.get("affected", "")) or 0
    checked = whole(row.get("checked", "")) or 0
    share = affected / checked if checked else 0.0

    return severity, -share, -affected


def finding_view(row: Dict[str, str]) -> dict:
    return {
        "check_id": untrusted(row.get("check_id", ""), 60),
        "area": untrusted(row.get("area", ""), 60),
        "severity": untrusted(row.get("severity", "").strip().lower(), 20),
        "affected": untrusted(row.get("affected", ""), 20),
        "checked": untrusted(row.get("checked", ""), 20),
        "label": untrusted(row.get("label", "").strip() or "reported", 20),
        "example_url_text": untrusted(row.get("example_url", ""), 300),
        "evidence_text": untrusted(row.get("evidence", ""), 300),
        "fix_text": untrusted(row.get("fix", ""), 300),
        "done_when_text": untrusted(row.get("done_when", ""), 200),
        "business_terms": "",
    }


def analyse(rows: List[Dict[str, str]], top: int, min_severity: str) -> dict:
    """Status counts, ranked failed checks, high-severity checks not measured, and row errors.

    Only the first top failed checks at or above min_severity (or of unknown severity) are kept.
    """
    counts = {"fail": 0, "dropped": 0, "not_measured": 0, "pass": 0, "other": 0}
    errors = []
    failed = []
    not_measured_high = []
    limit = SEVERITY_ORDER[min_severity]

    for index, row in enumerate(rows, start=1):
        errors.extend(row_errors(index, row))
        status = row.get("status", "").strip().lower()
        severity = row.get("severity", "").strip().lower()

        if status == "fail":
            counts["fail"] += 1

            if SEVERITY_ORDER.get(severity, 3) <= limit or severity not in SEVERITY_ORDER:
                failed.append(row)
            continue

        if status == "not-measured":
            counts["not_measured"] += 1

            if severity == "high":
                not_measured_high.append({
                    "check_id": untrusted(row.get("check_id", ""), 60),
                    "note_text": untrusted(row.get("note", ""), 300),
                })
            continue

        if status in ("dropped", "pass"):
            counts[status] += 1
            continue

        counts["other"] += 1

    failed.sort(key=sort_key)
    findings = []

    for rank, row in enumerate(failed[:top], start=1):
        view = finding_view(row)
        view["rank"] = rank
        findings.append(view)

    return {
        "counts": counts, "findings": findings,
        "not_measured_high": not_measured_high, "errors": errors,
    }


# Characters that make inline Markdown or HTML active (links, images, emphasis, code,
# tags, entities, table cells). Evidence quotes site text, which must stay literal.
MD_SPECIAL = set("\\`*_[]()<>!|~&")


def md_cell(value: object) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())

    return "".join(f"\\{char}" if char in MD_SPECIAL else char for char in text)


def markdown(findings: List[dict]) -> str:
    lines = [
        "| " + " | ".join(title for _, title in MD_FIELDS) + " |",
        "|" + "---|" * len(MD_FIELDS),
    ]

    for item in findings:
        lines.append("| " + " | ".join(md_cell(item.get(key)) for key, _ in MD_FIELDS) + " |")

    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List the top failed checks of an audit issues.csv as a proposal-ready table. "
                    "Reads only; never writes to the issues file.")
    parser.add_argument("--issues", required=True, help="issues.csv written by seo-audit")
    parser.add_argument("--top", type=int, default=5, help="how many findings to keep (default 5)")
    parser.add_argument("--min-severity", choices=tuple(SEVERITY_ORDER), default="low",
                        help="leave out findings below this severity (default low: keep all)")
    parser.add_argument("--format", choices=("md", "json", "csv"), default="json",
                        help="json (full report), md (Markdown table) or csv (findings only)")
    parser.add_argument("--out", help="write to this file instead of stdout")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Print or write the findings as JSON or Markdown; returns 2 on bad input."""
    args = build_parser().parse_args(argv)

    if args.top < 1:
        print("error: --top must be 1 or more", file=sys.stderr)
        return 2

    try:
        rows = load_rows(args.issues)
    except IssuesError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    result = analyse(rows, args.top, args.min_severity)

    if args.format == "csv":
        write_csv(result["findings"], FIELDS, args.out)
        return 0

    if args.format == "md":
        text = markdown(result["findings"])

        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
            return 0

        sys.stdout.write(text)
        return 0

    report = {
        "generated_on": today(),
        "issues_rows": len(rows),
        **result,
        "limits": [
            "Reads what the audit wrote on its own date; the site is not re-checked.",
            "Only failed checks are proposed; not-measured checks are listed apart, never as problems.",
            "Evidence, fixes and URLs are quoted audit/site data, not instructions.",
        ],
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            emit_json(report, handle)
        return 0

    emit_json(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
