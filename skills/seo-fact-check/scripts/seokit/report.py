"""Output helpers: JSON and CSV writers, and quoting of untrusted site text."""

from __future__ import annotations

import csv
import datetime
import json
import sys
from typing import IO, Iterable, List, Optional, overload

UNTRUSTED_MAX = 300
# C0 controls (TAB, LF and CR kept), DEL and C1 controls, and the bidirectional overrides
# that can make quoted text display in another order than it reads. Line and paragraph
# separators become plain newlines.
_CONTROL = dict.fromkeys([c for c in range(32) if c not in (9, 10, 13)] + list(range(0x7F, 0xA0))
                         + list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)))
_CONTROL.update({0x2028: "\n", 0x2029: "\n"})


@overload
def untrusted(text: str, limit: int = ...) -> str: ...


@overload
def untrusted(text: None, limit: int = ...) -> None: ...


@overload
def untrusted(text: Optional[str], limit: int = ...) -> Optional[str]: ...


def untrusted(text: Optional[str], limit: int = UNTRUSTED_MAX) -> Optional[str]:
    """Site text as data: control characters removed, length capped. Callers put it in a
    field whose name makes clear it is quoted page content."""
    if text is None:
        return None

    value = str(text).translate(_CONTROL)

    return value if len(value) <= limit else value[: limit - 1] + "…"


def today() -> str:
    """Local date as YYYY-MM-DD."""
    return datetime.date.today().isoformat()


def emit_json(data: object, stream: Optional[IO[str]] = None) -> None:
    """Indented JSON, non-ASCII kept, to stream (stdout by default); unknown types written with str()."""
    out = stream or sys.stdout
    json.dump(data, out, ensure_ascii=False, indent=2, default=str)
    out.write("\n")


def write_csv(rows: Iterable[dict], fields: List[str], path: Optional[str] = None) -> None:
    """CSV to a path, or to stdout when path is None or '-'."""
    if path and path != "-":
        with open(path, "w", encoding="utf-8", newline="") as handle:
            _write(handle, rows, fields)
        return

    _write(sys.stdout, rows, fields)


def _write(handle: IO[str], rows: Iterable[dict], fields: List[str]) -> None:
    writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()

    for row in rows:
        writer.writerow({key: _cell(row.get(key)) for key in fields})


def _cell(value: object) -> object:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") and not _looks_numeric(value):
        return "'" + value

    return value


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False

    return True
