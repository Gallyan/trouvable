"""Text normalisation and literal search, shared by every 'is this string on the page' check."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List

_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u200b": "", "\u2060": "", "\ufeff": "",
})


def normalize(text: str, casefold: bool = True) -> str:
    """NFKC, typographic quotes and dashes to ASCII, all spaces to one space, none around '/'
    ('20 € HT /mois', split by inline tags, reads as '20 € HT/mois')."""
    value = unicodedata.normalize("NFKC", text or "").translate(_TRANSLATE)
    value = " ".join(value.split()).replace(" /", "/").replace("/ ", "/")

    return value.casefold() if casefold else value


@dataclass
class Match:
    """An occurrence found by find_literal: its position and surrounding normalised text."""

    start: int
    context: str


def find_literal(haystack: str, needle: str, context: int = 80, casefold: bool = True) -> List[Match]:
    """Occurrences of needle in haystack after normalising both. Positions are in the
    normalised haystack."""
    hay = normalize(haystack, casefold)
    pin = normalize(needle, casefold)

    if not pin:
        return []

    matches = []
    start = hay.find(pin)

    while start != -1:
        left = max(0, start - context)
        right = min(len(hay), start + len(pin) + context)
        matches.append(Match(start, hay[left:right]))
        start = hay.find(pin, start + 1)

    return matches


def sentences(text: str) -> List[str]:
    """Split text on ., !, ? or … followed by a capital, a digit, a quote or a parenthesis."""
    parts = re.split(r"(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Þ0-9\"'«(])", " ".join(text.split()))

    return [p.strip() for p in parts if p.strip()]


def shingles(text: str, size: int = 8) -> set:
    """Set of normalised runs of `size` consecutive words, for near-duplicate comparison."""
    words = re.findall(r"\w+", normalize(text))

    return {" ".join(words[i:i + size]) for i in range(max(0, len(words) - size + 1))}
