"""Read tabular exports (CSV, XLSX, ZIP of either) safely, without third-party packages.

Used for Search Console exports, Page indexing exports and user CSV files. Sizes are
checked on the archive's declared sizes before anything is decompressed.
"""

from __future__ import annotations

import csv
import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .safexml import parse_xml_bytes

MAX_FILE_BYTES = 200_000_000
MAX_MEMBER_BYTES = 100_000_000
MAX_TOTAL_UNCOMPRESSED = 300_000_000
MAX_RATIO = 200
MAX_ROWS = 500_000
MAX_MEMBERS = 200
MAX_COLUMNS = 16384  # XLSX column XFD
MAX_SHEETS = 50
MAX_CELLS = 20_000_000

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class TableError(ValueError):
    """An export that cannot be read or goes over a size cap."""


@dataclass
class Table:
    """A sheet or CSV file: header row, data rows, and whether a cap cut the rows short."""

    name: str
    headers: List[str]
    rows: List[List[str]] = field(default_factory=list)
    truncated: bool = False

    def records(self) -> List[Dict[str, str]]:
        """Rows as dicts keyed by header, short rows padded with ""."""
        return [dict(zip(self.headers, row + [""] * (len(self.headers) - len(row)))) for row in self.rows]


class _Budget:
    """One per read_tables call: nested workbooks and repeated sheets share it, so the caps
    hold for the whole export, not for each archive taken alone."""

    def __init__(self) -> None:
        self.declared = 0
        self.cells = 0

    def add_declared(self, size: int) -> None:
        """Count a ZIP member's declared size; TableError past MAX_TOTAL_UNCOMPRESSED."""
        self.declared += size

        if self.declared > MAX_TOTAL_UNCOMPRESSED:
            raise TableError("export declared uncompressed size above cap")

    def add_cells(self, count: int) -> None:
        """Count materialised cells, padding included; TableError past MAX_CELLS."""
        self.cells += count

        if self.cells > MAX_CELLS:
            raise TableError(f"export holds more than {MAX_CELLS} cells, refused")


def _check_zip(archive: zipfile.ZipFile, budget: _Budget) -> None:
    members = archive.infolist()

    if len(members) > MAX_MEMBERS:
        raise TableError(f"archive has {len(members)} members, cap is {MAX_MEMBERS}")

    total = 0

    for info in members:
        if info.file_size > MAX_MEMBER_BYTES:
            raise TableError(f"{info.filename}: declared size above cap")

        if info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_RATIO:
            raise TableError(f"{info.filename}: compression ratio above {MAX_RATIO}, refused")

        total += info.file_size

    if total > MAX_TOTAL_UNCOMPRESSED:
        raise TableError("archive declared uncompressed size above cap")

    budget.add_declared(total)


def _read_member(archive: zipfile.ZipFile, name: str) -> bytes:
    with archive.open(name) as handle:
        data = handle.read(MAX_MEMBER_BYTES + 1)

    if len(data) > MAX_MEMBER_BYTES:
        raise TableError(f"{name}: actual size above cap")

    return data


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue

        if encoding == "utf-16" and data[:2] not in (b"\xff\xfe", b"\xfe\xff"):
            continue

        return text

    return data.decode("utf-8", errors="replace")


def read_csv_text(text: str, name: str = "table") -> Table:
    """Parse CSV text, delimiter sniffed among , ; and tab; the first non-empty row is the header.

    Raises TableError on NUL bytes or unreadable CSV; caps as in _fill.
    """
    if "\x00" in text:
        raise TableError(f"{name}: binary content (NUL bytes), not a CSV export")

    sample = text[:8192]

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    table = Table(name=name, headers=[])

    try:
        _fill(reader, table)
    except csv.Error as error:
        raise TableError(f"{name}: not a readable CSV ({error})") from error

    return table


def _fill(reader, table: Table) -> None:
    """Rows of a CSV reader, capped like a workbook: MAX_COLUMNS per row, MAX_ROWS rows and
    MAX_CELLS cells, so a file of separators alone cannot fill memory. A short row counts
    as wide as the header, since records() pads it to that width."""
    headers: Optional[List[str]] = None
    cells = 0

    for row in reader:
        if len(row) > MAX_COLUMNS:
            raise TableError(f"{table.name}: more than {MAX_COLUMNS} columns in a row")

        if headers is None:
            if not any(cell.strip() for cell in row):
                continue

            headers = [cell.strip() for cell in row]
            table.headers = headers
            continue

        if not any(cell.strip() for cell in row):
            continue

        width = max(len(row), len(headers))

        if len(table.rows) >= MAX_ROWS or cells + width > MAX_CELLS:
            table.truncated = True
            break

        cells += width
        table.rows.append([cell.strip() for cell in row])


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "")
    name = letters.group(0) if letters else "A"
    index = 0

    if len(name) > 3:
        raise TableError(f"cell reference {ref[:20]} beyond the XLSX column limit")

    for char in name:
        index = index * 26 + (ord(char) - 64)

    if index > MAX_COLUMNS:
        raise TableError(f"cell reference {ref[:20]} beyond the XLSX column limit")

    return index - 1


def _read_xlsx(archive: zipfile.ZipFile, prefix: str, budget: _Budget) -> List[Table]:
    """One Table per non-empty sheet, named prefix + sheet name; short rows padded to the header."""
    names = set(archive.namelist())
    shared = _shared_strings(archive, names)
    sheets = _sheet_paths(archive, names)

    if len(sheets) > MAX_SHEETS:
        raise TableError(f"workbook lists {len(sheets)} sheets, cap is {MAX_SHEETS}")

    tables = []

    for sheet_name, path in sheets:
        grid, truncated = _read_sheet(parse_xml_bytes(_read_member(archive, path)), shared, budget)
        grid = [r for r in grid if any(r)]

        if not grid:
            continue

        headers = grid[0]
        budget.add_cells(sum(len(headers) - len(r) for r in grid[1:] if len(r) < len(headers)))
        rows = [r + [""] * (len(headers) - len(r)) for r in grid[1:]]
        tables.append(Table(name=f"{prefix}{sheet_name}", headers=headers, rows=rows, truncated=truncated))

    return tables


def _shared_strings(archive: zipfile.ZipFile, names: Set[str]) -> List[str]:
    if "xl/sharedStrings.xml" not in names:
        return []

    root = parse_xml_bytes(_read_member(archive, "xl/sharedStrings.xml"))

    return ["".join(node.text or "" for node in item.iter(f"{NS_MAIN}t")) for item in root.iter(f"{NS_MAIN}si")]


def _sheet_paths(archive: zipfile.ZipFile, names: Set[str]) -> List[Tuple[str, str]]:
    """(name, member path) of each sheet listed by the workbook, in order, each path once.

    Falls back to the xl/worksheets/sheetN.xml members when the workbook lists none.
    """
    sheets: List[Tuple[str, str]] = []

    if "xl/workbook.xml" in names:
        workbook = parse_xml_bytes(_read_member(archive, "xl/workbook.xml"))
        targets = _relationship_targets(archive, names)

        for sheet in workbook.iter(f"{NS_MAIN}sheet"):
            path = targets.get(sheet.get(f"{NS_REL}id", ""))

            if path is not None and path in names and path not in {known for _, known in sheets}:
                sheets.append((sheet.get("name", path), path))

    if not sheets:
        sheets = [(n, n) for n in sorted(names) if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]

    return sheets


def _relationship_targets(archive: zipfile.ZipFile, names: Set[str]) -> Dict[str, str]:
    targets: Dict[str, str] = {}

    if "xl/_rels/workbook.xml.rels" not in names:
        return targets

    rels = parse_xml_bytes(_read_member(archive, "xl/_rels/workbook.xml.rels"))

    for rel in rels.iter(f"{NS_PKG_REL}Relationship"):
        target = rel.get("Target", "").lstrip("/")
        targets[rel.get("Id", "")] = target if target.startswith("xl/") else f"xl/{target}"

    return targets


def _read_sheet(root: ET.Element, shared: List[str], budget: _Budget) -> Tuple[List[List[str]], bool]:
    """Rows of a worksheet as lists of cell text, and whether MAX_ROWS cut them short."""
    grid: List[List[str]] = []

    for row in root.iter(f"{NS_MAIN}row"):
        if len(grid) >= MAX_ROWS:
            return grid, True

        values: Dict[int, str] = {}

        for position, cell in enumerate(row.iter(f"{NS_MAIN}c")):
            ref = cell.get("r")
            index = _col_index(ref) if ref else position
            values[index] = _cell_text(cell, shared).strip()

        if values:
            width = max(values) + 1
            budget.add_cells(width)
            grid.append([values.get(i, "") for i in range(width)])

    return grid, False


def _cell_text(cell: ET.Element, shared: List[str]) -> str:
    kind = cell.get("t")
    value_node = cell.find(f"{NS_MAIN}v")
    value = value_node.text if value_node is not None and value_node.text else ""

    if kind == "s" and value.isascii() and value.isdigit() and int(value) < len(shared):
        return shared[int(value)]

    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{NS_MAIN}t"))

    return value


def read_tables(path: str) -> List[Table]:
    """Every table found in a CSV, an XLSX, or a ZIP holding CSV/XLSX files."""
    with open(path, "rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)

    if len(data) > MAX_FILE_BYTES:
        raise TableError(f"{path}: file above {MAX_FILE_BYTES} bytes")

    return read_tables_bytes(data, os.path.basename(path))


def read_tables_bytes(data: bytes, name: str) -> List[Table]:
    """Any failure to read the export, whatever the layer, is a TableError."""
    try:
        return _read_tables_bytes(data, name)
    except TableError:
        raise
    except (ET.ParseError, ValueError, KeyError, EOFError, zlib.error, zipfile.BadZipFile, csv.Error,
            NotImplementedError, RuntimeError) as error:
        raise TableError(f"{name}: not a readable export ({type(error).__name__}: {str(error)[:120]})") from error


def _read_tables_bytes(data: bytes, name: str) -> List[Table]:
    """CSV text, or every CSV and XLSX inside a ZIP (an XLSX is itself a ZIP), under one budget."""
    if data[:4] != b"PK\x03\x04":
        return [read_csv_text(_decode_text(data), name=os.path.splitext(name)[0])]

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise TableError(f"{name}: not a readable ZIP/XLSX ({error})") from error

    budget = _Budget()

    with archive:
        _check_zip(archive, budget)
        members = archive.namelist()

        if "xl/workbook.xml" in members or any(m.startswith("xl/worksheets/") for m in members):
            return _read_xlsx(archive, prefix="", budget=budget)

        tables: List[Table] = []

        for member in members:
            lower = member.lower()

            if member.endswith("/") or "__macosx" in lower:
                continue

            stem = os.path.splitext(os.path.basename(member))[0]

            if lower.endswith(".csv"):
                tables.append(read_csv_text(_decode_text(_read_member(archive, member)), name=stem))
            elif lower.endswith(".xlsx"):
                inner = _read_member(archive, member)

                with zipfile.ZipFile(io.BytesIO(inner)) as nested:
                    _check_zip(nested, budget)
                    tables.extend(_read_xlsx(nested, prefix=f"{stem}:", budget=budget))

        return tables


_NUMBER_CLEAN = re.compile(r"[\s  ']")


def parse_number(value: str) -> Optional[float]:
    """Parse '1,234', '1 234', '12,5 %', '0.034', '3.4%'. Percentages return a 0–1 ratio."""
    if value is None:
        return None

    text = _NUMBER_CLEAN.sub("", str(value))
    percent = text.endswith("%")
    text = text.rstrip("%")

    if not text or text in ("-", "—"):
        return None

    if "," in text and "." in text:
        text = (text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".")
                else text.replace(",", ""))
    elif "," in text:
        is_thousands = re.fullmatch(r"-?\d{1,3}(,\d{3})+", text) is not None
        text = text.replace(",", "") if is_thousands else text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return None

    return number / 100 if percent else number
