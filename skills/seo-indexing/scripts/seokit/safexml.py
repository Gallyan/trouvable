"""XML parsing for untrusted input (sitemaps, XLSX parts).

Documents carrying a DOCTYPE are refused outright: sitemaps and XLSX parts never need
one, and refusing it removes entity-expansion attacks whatever the expat version. The check
reads raw bytes, so only ASCII-compatible encodings are accepted: in UTF-16 or UTF-32 a
DOCTYPE would not appear as ASCII bytes, while expat would still decode and expand it.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 100_000_000
_DOCTYPE = re.compile(rb"<!DOCTYPE|<!ENTITY", re.I)
_WIDE_BOMS = (b"\x00\x00\xfe\xff", b"\xff\xfe", b"\xfe\xff")
_DECLARED = re.compile(rb"""^\s*<\?xml[^>]*\bencoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")
ASCII_COMPATIBLE = {"utf-8", "utf8", "us-ascii", "ascii", "iso-8859-1", "latin-1", "latin1",
                    "iso-8859-15", "windows-1252", "cp1252"}


class UnsafeXmlError(ValueError):
    """An XML document refused before parsing: too large, DOCTYPE/ENTITY, or a non-ASCII-compatible encoding."""


def parse_xml_bytes(data: bytes) -> ET.Element:
    """Parse XML with ElementTree after refusing what could expand or hide entities.

    Raises UnsafeXmlError above MAX_XML_BYTES, on DOCTYPE or ENTITY declarations, and on
    encodings that are not ASCII-compatible (the DOCTYPE check reads raw bytes).
    """
    if len(data) > MAX_XML_BYTES:
        raise UnsafeXmlError("XML document above size cap")

    head = data[:1024]
    declared = _DECLARED.match(head.lstrip(b"\xef\xbb\xbf"))

    if head.startswith(_WIDE_BOMS) or b"\x00" in head:
        raise UnsafeXmlError("XML not in an ASCII-compatible encoding refused")

    if declared and declared.group(1).decode("ascii").lower() not in ASCII_COMPATIBLE:
        name = declared.group(1).decode("ascii")

        raise UnsafeXmlError(f"XML declared as {name} refused: ASCII-compatible encodings only")

    if _DOCTYPE.search(data):
        raise UnsafeXmlError("XML with DOCTYPE or ENTITY declarations refused")

    return ET.fromstring(data)
