"""Shared by source_find.py and source_watch.py: can a fetched body stand for the page a
reader sees, and is a number hit cut out of a longer number."""

from __future__ import annotations

import re
from typing import Optional

from seokit.fetch import BLOCKING_STATUSES, Response
from seokit.text import normalize

# Readability heuristics (design choice of this skill, to calibrate).
MIN_WORDS_READABLE = 20
JS_SHELL_MAX_WORDS = 60
LOGIN_WALL_MAX_WORDS = 150

CHALLENGE_MARKERS = (
    "cf-browser-verification",
    "challenge-platform",
    "cf_chl_",
    "just a moment...",
    "attention required! | cloudflare",
    "_incapsula_resource",
    "px-captcha",
    "captcha-delivery.com",
    "datadome",
    "g-recaptcha",
    "h-captcha",
    "please verify you are a human",
    "enable javascript and cookies to continue",
)
JS_SHELL_MARKERS = (
    'id="root"',
    'id="app"',
    'id="__next"',
    'id="__nuxt"',
    "ng-version",
    "you need to enable javascript",
    "please enable javascript",
    "requires javascript",
)
TEXT_TYPES = ("text/plain", "application/json", "application/xml", "text/xml", "text/csv", "text/markdown")


def unreadable_reason(response: Response, raw_lower: str, words: Optional[int]) -> Optional[str]:
    """Why the body cannot stand for the page a reader sees, or None when it is readable.

    words is the static word count of the parsed HTML, or None for a non-HTML text body.
    """
    if response.status is None:
        return f"not fetched: {response.error}"

    if response.status in BLOCKING_STATUSES:
        return f"site answered HTTP {response.status}: blocked, no workaround attempted"

    if not response.ok:
        return f"HTTP {response.status}"

    if not response.is_html and response.content_type not in TEXT_TYPES:
        return f"content type '{response.content_type or 'unknown'}' not searched (PDF, image or binary)"

    if words is None:
        return None if len(raw_lower.split()) >= MIN_WORDS_READABLE else "nearly empty body"

    for marker in CHALLENGE_MARKERS:
        if marker in raw_lower:
            return f"bot challenge or captcha page (marker '{marker}')"

    if 'type="password"' in raw_lower and words < LOGIN_WALL_MAX_WORDS:
        return "login wall: password form and little text"

    if words < JS_SHELL_MAX_WORDS:
        for marker in JS_SHELL_MARKERS:
            if marker in raw_lower:
                return f"JavaScript shell: {words} words of static text (marker '{marker}')"

    if words < MIN_WORDS_READABLE:
        return f"nearly empty: {words} words of static text"

    return None


def inside_longer_number(haystack: str, needle: str, start: int) -> bool:
    """True when a hit is cut out of a longer number ('19 €' inside '119 €' or '19,99 €')."""
    hay = normalize(haystack)
    pin = normalize(needle)
    before = hay[start - 1] if start > 0 else ""
    after = hay[start + len(pin): start + len(pin) + 2]

    if pin[:1].isdigit() and before and (before.isdigit() or before in ".,"):
        return True

    return bool(pin[-1:].isdigit() and re.match(r"[.,]?\d", after))
