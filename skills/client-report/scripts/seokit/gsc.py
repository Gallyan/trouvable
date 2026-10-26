"""Search Console Performance exports: column detection that does not depend on language.

Header names change with the interface language. Columns are recognised from known
English headers first, then from their content:
    key          the text column (query, page URL, country, date…)
    ctr          values written with '%' or all within [0, 1] with decimals
    position     decimals mostly above 1 and below 200
    clicks       integers, the column with the smaller sum of the two integer columns
    impressions  integers, the larger sum
Non-English header names are only an extra hint: add them from real exports, never
from memory (see HEADER_HINTS).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

from .tables import Table, parse_number

# Headers of the Performance export. English: verified. French: read on real XLSX
# exports downloaded on 2026-10-21. Other languages: add from real exports only.
HEADER_HINTS: Dict[str, List[str]] = {
    "clicks": ["clicks", "clics"],
    "impressions": ["impressions"],
    "ctr": ["ctr"],
    "position": ["position"],
    "query": ["top queries", "query", "queries", "requêtes les plus fréquentes"],
    "page": ["top pages", "page", "pages", "pages les plus populaires"],
}

# Other sheets of the same export, so they are never mistaken for the queries table.
# French names read on the same real exports; English names not verified, left out.
DIMENSION_HINTS: Dict[str, List[str]] = {
    "country": ["pays"],
    "device": ["appareil"],
    "search-appearance": ["apparence dans les résultats de recherche"],
    "filters": ["filtre"],
}

URL_PATTERN = re.compile(r"^https?://", re.I)


@dataclass
class GscTable:
    """A Performance export table with its columns mapped to roles and its rows parsed.

    `kind` is query, page, date, query-or-other, a DIMENSION_HINTS key, or unknown; `notes`
    say which columns were recognised from their values rather than their headers.
    """

    name: str
    kind: str
    key: Optional[str]
    columns: Dict[str, str] = field(default_factory=dict)
    rows: List[dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _norm(header: str) -> str:
    return " ".join(header.lower().split())


def _column_values(table: Table, index: int, limit: int = 2000) -> List[str]:
    return [row[index] for row in table.rows[:limit] if index < len(row) and row[index] != ""]


def detect(table: Table) -> GscTable:
    """Map the columns of a Search Console table to key, clicks, impressions, ctr and position.

    Known headers win; the remaining columns are recognised from their values. Rows are
    returned with numbers parsed (None when a cell is not a number).
    """
    result = GscTable(name=table.name, kind="unknown", key=None)
    used = _match_headers(table.headers, result)

    if result.key is None:
        _match_dimension(table.headers, result, used)

    numeric, percent_cols = _numeric_columns(table, result, used)
    _find_ctr(table.headers, result, numeric, percent_cols)
    _find_position(table.headers, result, numeric)
    _find_counts(table, result, numeric)

    if result.kind == "unknown" and result.key:
        _guess_kind(table, result)

    result.rows = _parsed_rows(table, result)

    if "position" not in result.columns and "clicks" in result.columns:
        result.notes.append("no position column: Discover or News export, or a trimmed table")

    return result


def _match_headers(headers: List[str], result: GscTable) -> Set[int]:
    """Assign roles from known header names; returns the indexes of the columns taken."""
    used: Set[int] = set()

    for role, hints in HEADER_HINTS.items():
        for index, header in enumerate(headers):
            if index in used or _norm(header) not in hints:
                continue

            if role not in ("query", "page"):
                result.columns[role] = header
                used.add(index)
            elif result.key is None:
                result.key = header
                result.kind = role
                used.add(index)

            break

    return used


def _match_dimension(headers: List[str], result: GscTable, used: Set[int]) -> None:
    """Take the key from the header of another sheet of the export (country, device…)."""
    for kind, hints in DIMENSION_HINTS.items():
        found = next((i for i, h in enumerate(headers) if _norm(h) in hints), None)

        if found is not None:
            result.key = headers[found]
            result.kind = kind
            used.add(found)
            return


def _numeric_columns(table: Table, result: GscTable, used: Set[int]) -> Tuple[Dict[int, List[float]], Set[int]]:
    """Parsed values of the free columns that are at least 90% numbers, and those written in %.

    The first free column that is not numeric becomes the key when none was found.
    """
    numeric: Dict[int, List[float]] = {}
    percent_cols: Set[int] = set()

    for index, header in enumerate(table.headers):
        if index in used:
            continue

        values = _column_values(table, index)

        if not values:
            continue

        parsed = [parse_number(v) for v in values]

        if sum(p is not None for p in parsed) >= 0.9 * len(values):
            numeric[index] = [p for p in parsed if p is not None]

            if sum(v.strip().endswith("%") for v in values) >= 0.5 * len(values):
                percent_cols.add(index)
        elif result.key is None:
            result.key = header
            result.notes.append(f"key column '{header}' inferred from content")

    return numeric, percent_cols


def _find_ctr(headers: List[str], result: GscTable, numeric: Dict[int, List[float]], percent_cols: Set[int]) -> None:
    for index in list(numeric):
        if "ctr" in result.columns:
            break

        numbers = numeric[index]
        ratio_like = bool(numbers) and all(0 <= v <= 1 for v in numbers) and any(v != int(v) for v in numbers)

        if index in percent_cols or ratio_like:
            result.columns["ctr"] = headers[index]
            result.notes.append(f"'{headers[index]}' read as CTR from its values")
            del numeric[index]


def _find_position(headers: List[str], result: GscTable, numeric: Dict[int, List[float]]) -> None:
    for index in list(numeric):
        if "position" in result.columns:
            break

        numbers = numeric[index]

        if numbers and any(v != int(v) for v in numbers) and all(0 < v < 200 for v in numbers):
            result.columns["position"] = headers[index]
            result.notes.append(f"'{headers[index]}' read as position from its values")
            del numeric[index]


def _find_counts(table: Table, result: GscTable, numeric: Dict[int, List[float]]) -> None:
    """Tell clicks from impressions among the integer columns: clicks never exceed impressions."""
    headers = table.headers
    integer_cols = [(sum(vals), i) for i, vals in numeric.items() if all(v == int(v) for v in vals)]
    integer_cols.sort()
    missing = [role for role in ("clicks", "impressions") if role not in result.columns]

    if len(missing) == 2 and len(integer_cols) >= 2:
        result.columns["clicks"] = headers[integer_cols[0][1]]
        result.columns["impressions"] = headers[integer_cols[-1][1]]
        result.notes.append("clicks and impressions told apart by their totals (clicks <= impressions)")
        return

    if len(missing) != 1 or len(integer_cols) != 1:
        return

    known = headers.index(result.columns["impressions" if missing == ["clicks"] else "clicks"])
    known_sum = sum(v for v in (parse_number(r[known]) if known < len(r) else None
                                for r in table.rows) if v is not None)
    candidate_sum, index = integer_cols[0]
    fits = candidate_sum <= known_sum if missing == ["clicks"] else candidate_sum >= known_sum

    if fits:
        result.columns[missing[0]] = headers[index]
        result.notes.append(f"'{headers[index]}' read as {missing[0]} from its values "
                            "(clicks <= impressions)")


def _guess_kind(table: Table, result: GscTable) -> None:
    """Kind of a key column found without a known header: page URLs, dates, or other text."""
    sample = _column_values(table, table.headers.index(result.key or ""), 50)

    if sample and sum(bool(URL_PATTERN.match(v)) for v in sample) >= 0.8 * len(sample):
        result.kind = "page"
    elif sample and all(re.match(r"^\d{4}-\d{2}-\d{2}$", v) for v in sample):
        result.kind = "date"
    else:
        result.kind = "query-or-other"
        result.notes.append("key column holds text that is not a URL: assumed queries, confirm with the user")


def _parsed_rows(table: Table, result: GscTable) -> List[dict]:
    rows: List[dict] = []

    for raw in table.rows:
        record = dict(zip(table.headers, raw))
        row: Dict[str, Union[str, float, None]] = {"key": record.get(result.key, "") if result.key else ""}

        for role, header in result.columns.items():
            row[role] = parse_number(record.get(header, ""))

        rows.append(row)

    return rows
