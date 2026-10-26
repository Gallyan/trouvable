#!/usr/bin/env python3
"""Copied-sentence detector between a draft and the pages read.

Splits the draft and the sources into sentences, compares word shingles (seokit.text) and
reports draft sentences above a similarity threshold, or sharing a long run of words, with
the closest source sentence. Catches near-verbatim reuse only, not paraphrase. Threshold and
shingle size are heuristic design choices, to calibrate.

Usage:
    python3 scripts/overlap_sentences.py --draft draft.md --sources outlines.json
    python3 scripts/overlap_sentences.py --draft draft.md --source-text a.txt b.txt

Network: none, fully offline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Dict, List, Optional, Tuple

from seokit.report import emit_json, today, untrusted
from seokit.text import normalize, sentences, shingles

DEFAULT_SHINGLE = 5
DEFAULT_THRESHOLD = 0.5
DEFAULT_MIN_RUN = 12
MAX_FILE_BYTES = 20_000_000

MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
MD_PREFIX = re.compile(r"^\s{0,3}(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)")
MD_MARKS = re.compile(r"[*_`]+")


def _close(chunk: str) -> str:
    return chunk if re.search(r"[.!?…:]$", chunk) else f"{chunk}."


def strip_markdown(text: str) -> str:
    """Plain text where headings, list items and paragraphs each end a sentence."""
    chunks: List[str] = []
    paragraph: List[str] = []

    for raw in text.splitlines():
        is_item = MD_PREFIX.match(raw) is not None
        line = MD_MARKS.sub("", MD_PREFIX.sub("", MD_LINK.sub(r"\1", raw))).strip()

        if (not line or is_item) and paragraph:
            chunks.append(_close(" ".join(paragraph)))
            paragraph = []

        if not line:
            continue

        if is_item:
            chunks.append(_close(line))
            continue

        paragraph.append(line)

    if paragraph:
        chunks.append(_close(" ".join(paragraph)))

    return "\n".join(chunks)


def words_of(text: str) -> List[str]:
    return re.findall(r"\w+", normalize(text))


def longest_run(left: List[str], right: List[str]) -> Tuple[int, int]:
    """Length and start (in left) of the longest common run of words."""
    best = 0
    best_start = 0
    previous = [0] * (len(right) + 1)

    for i in range(1, len(left) + 1):
        current = [0] * (len(right) + 1)

        for j in range(1, len(right) + 1):
            if left[i - 1] == right[j - 1]:
                current[j] = previous[j - 1] + 1

                if current[j] > best:
                    best = current[j]
                    best_start = i - best

        previous = current

    return best, best_start


class SourceIndex:
    """Source sentences indexed by shingle, to find the closest one to a draft sentence."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.sentences: List[Tuple[str, str]] = []
        self.by_shingle: Dict[str, set] = {}

    def add(self, url: str, text: str) -> None:
        for sentence in sentences(text):
            index = len(self.sentences)
            self.sentences.append((url, sentence))

            for shingle in shingles(sentence, self.size):
                self.by_shingle.setdefault(shingle, set()).add(index)

    def candidates(self, draft_shingles: set) -> Dict[int, int]:
        counts: Dict[int, int] = {}

        for shingle in draft_shingles:
            for index in self.by_shingle.get(shingle, ()):
                counts[index] = counts.get(index, 0) + 1

        return counts


def compare(draft_text: str, index: SourceIndex, threshold: float, min_run: int) -> Tuple[List[dict], int, int]:
    """Draft sentences close to a source sentence (by shingle share or shared word run).

    Returns the flagged sentences, the count compared and the count too short to compare.
    """
    flagged = []
    compared = 0
    too_short = 0

    for position, sentence in enumerate(sentences(draft_text), start=1):
        draft_shingles = shingles(sentence, index.size)

        if not draft_shingles:
            too_short += 1
            continue

        compared += 1
        counts = index.candidates(draft_shingles)

        if not counts:
            continue

        best = max(counts, key=lambda i: counts[i])
        similarity = counts[best] / len(draft_shingles)
        url, source_sentence = index.sentences[best]
        draft_words = words_of(sentence)
        run, start = longest_run(draft_words, words_of(source_sentence))

        if similarity < threshold and run < min_run:
            continue

        flagged.append({
            "draft_sentence_number": position,
            "draft_sentence_text": untrusted(sentence, 500),
            "closest_source_sentence_quote": untrusted(source_sentence, 500),
            "source_url": untrusted(url, 500),
            "similarity": round(similarity, 3),
            "longest_shared_run_words": run,
            "shared_run_text": untrusted(" ".join(draft_words[start:start + run]), 500),
        })

    return flagged, compared, too_short


def read_text(path: str) -> str:
    with open(path, "rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)

    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"{path} is above {MAX_FILE_BYTES} bytes")

    return data.decode("utf-8", errors="replace")


def load_outlines(path: str) -> Tuple[List[Tuple[str, str]], List[dict]]:
    """(URL, main text) of each page read in a competitor_outline.py output, and the pages left out with why."""
    data = json.loads(read_text(path))

    if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
        raise ValueError("not a competitor_outline.py output: no 'pages' list")

    usable: List[Tuple[str, str]] = []
    skipped: List[dict] = []

    for page in data["pages"]:
        if not isinstance(page, dict):
            continue

        url = str(page.get("final_url") or page.get("url") or "?")
        text = page.get("main_text_quoted")

        if not page.get("read") or not isinstance(text, str) or not text.strip():
            skipped.append({"url": untrusted(url, 500),
                            "reason": untrusted(str(page.get("reason") or "no main text"), 200)})
            continue

        if any(url == seen for seen, _ in usable):
            skipped.append({"url": untrusted(url, 500),
                            "reason": "same final URL as another source (redirect): compared once"})
            continue

        usable.append((url, text))

    return usable, skipped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Flag draft sentences copied (near-verbatim) from the pages read. "
                    "Threshold and shingle size are heuristic, to calibrate. Offline.",
    )
    parser.add_argument("--draft", required=True, help="draft in Markdown or plain text")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sources", help="outlines.json written by competitor_outline.py")
    source.add_argument("--source-text", nargs="+", metavar="FILE", help="plain-text source files")
    parser.add_argument("--shingle-size", type=int, default=DEFAULT_SHINGLE,
                        help=f"words per shingle (default {DEFAULT_SHINGLE}, heuristic)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"share of the draft sentence's shingles found in one source sentence "
                             f"(default {DEFAULT_THRESHOLD}, heuristic)")
    parser.add_argument("--min-run", type=int, default=DEFAULT_MIN_RUN,
                        help=f"flag any shared run of at least this many words (default {DEFAULT_MIN_RUN})")
    parser.add_argument("--out", help="write the JSON here instead of stdout")

    return parser


def load_sources(args) -> Tuple[List[Tuple[str, str]], List[dict]]:
    if args.sources:
        return load_outlines(args.sources)

    return [(path, read_text(path)) for path in args.source_text], []


def main(argv: Optional[List[str]] = None) -> int:
    """Compare the draft with the sources and print or write the flagged sentences as JSON."""
    args = build_parser().parse_args(argv)

    if args.shingle_size < 2 or not 0 < args.threshold <= 1 or args.min_run < 2:
        print("--shingle-size >= 2, 0 < --threshold <= 1, --min-run >= 2", file=sys.stderr)
        return 2

    try:
        draft = strip_markdown(read_text(args.draft))
        sources, skipped = load_sources(args)
    except (OSError, ValueError) as error:
        print(f"bad input: {error}", file=sys.stderr)
        return 2

    index = SourceIndex(args.shingle_size)

    for url, text in sources:
        index.add(url, text)

    flagged, compared, too_short = compare(draft, index, args.threshold, args.min_run)
    limits = [
        "catches near-verbatim reuse only, not paraphrase of structure or ideas",
        "common phrases and quotations are flagged too: review each one",
        "rewrite flagged sentences from the facts, do not tune the draft until it passes",
    ]

    if not sources:
        limits.append("no readable source: nothing compared")

    report = {
        "generated_on": today(),
        "tool": "overlap_sentences.py",
        "settings": {"shingle_size": args.shingle_size, "threshold": args.threshold,
                     "min_run": args.min_run, "note": "heuristic values, to calibrate"},
        "sources_compared": [untrusted(url, 500) for url, _ in sources],
        "sources_not_compared": skipped,
        "draft_sentences_compared": compared,
        "draft_sentences_too_short": too_short,
        "flagged_count": len(flagged),
        "flagged": flagged,
        "limits": limits,
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            emit_json(report, handle)
    else:
        emit_json(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
