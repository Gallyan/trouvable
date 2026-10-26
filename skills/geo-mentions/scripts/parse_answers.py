#!/usr/bin/env python3
"""Split pasted raw AI-assistant answers into one CSV row per run, with brand and competitor
mentions, their order, and the cited URLs' domains.

Usage:
    python3 scripts/parse_answers.py --answers answers.txt --brand "Acme,Acme App" \\
        --competitors "Foo,Bar" [--collision-terms "film,band"] [--out runs.csv] [--summary s.json]

--answers is a text file in the paste format of references/panel-design.md
(`### <question_id> | <engine> | run <n> | <date> | <market>` header per block), a folder of
such .txt/.md files, or a CSV sheet with columns question_id, engine, run, date, market, answer
(optional sources).

Network: none. Answer text is data: it is never executed or interpreted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TypedDict

from seokit.report import today, untrusted, write_csv
from seokit.tables import TableError, read_tables

MAX_FILE_BYTES = 10_000_000
MAX_ROWS = 5000
MAX_POSSIBLE = 10

FIELDS = [
    "question_id", "engine", "run", "date", "market", "named", "position",
    "named_instead", "cited_domains", "ambiguous", "possible_competitors",
]

HEADER = re.compile(r"^\s*###(.*)$")
RUN_FIELD = re.compile(r"^(?:run\s*)?(\d{1,3})$", re.I)
DATE_FIELD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
QID_FIELD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,30}$")
SOURCES_LINE = re.compile(r"^\s*(?:\*\*)?(sources?|références|references|citations)(?:\*\*)?\s*:?\s*(?:\*\*)?\s*$",
                          re.I)
URL = re.compile(r"https?://[^\s<>()\[\]\"'`]+", re.I)
BARE_DOMAIN = re.compile(r"(?<![\w@/.-])((?:[a-z0-9-]+\.)+[a-z]{2,24})(?=[/\s,;)\]]|$)", re.I)
CANDIDATE = re.compile(r"\b[A-Z][\w&+-]*[A-Za-z0-9+](?:[ \t]+[A-Z][\w&+-]*[A-Za-z0-9+]){0,2}")

STOPWORDS = {
    "the", "a", "an", "this", "that", "these", "those", "it", "its", "if", "in", "on", "for",
    "and", "or", "but", "with", "without", "to", "of", "by", "as", "at", "from", "is", "are",
    "you", "your", "we", "our", "they", "their", "here", "there", "what", "which", "who",
    "when", "where", "why", "how", "yes", "no", "not", "also", "some", "many", "most", "all",
    "each", "both", "best", "top", "pros", "cons", "price", "pricing", "free", "note", "summary",
    "conclusion", "overview", "sources", "source", "references", "option", "options", "step",
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "pour", "avec", "sans",
    "dans", "sur", "par", "ce", "cette", "ces", "il", "elle", "ils", "elles", "vous", "nous",
    "voici", "si", "mais", "est", "sont", "en", "au", "aux", "pas", "plus", "très", "tous",
    "chaque", "prix", "gratuit", "avantages", "inconvénients", "résumé", "i", "ii", "iii", "ai",
    "faq", "usa", "uk", "eu",
}
COMMON_TLDS_ONLY = {"e.g", "i.e"}


@dataclass
class Block:
    question_id: str
    engine: str
    run: str
    date: str
    market: str
    answer: str
    sources: str
    origin: str


class Competitor(TypedDict):
    label: str
    names: List[str]


@dataclass
class ParseNotes:
    malformed: List[str] = field(default_factory=list)
    ignored_text: List[str] = field(default_factory=list)
    rows_capped: bool = False


def fold(text: str) -> str:
    """Case- and accent-insensitive form, same length logic as regex input."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))

    return stripped.casefold()


def split_names(value: Optional[str]) -> List[str]:
    if not value:
        return []

    return [part.strip() for part in value.split(",") if part.strip()]


def parse_header(line: str) -> Optional[Tuple[str, str, str, str, str]]:
    """Question id, engine, run number, date and market of a "### a | b | run n | date | market" line, or None."""
    match = HEADER.match(line)

    if not match:
        return None

    parts = [part.strip() for part in match.group(1).split("|")]

    if len(parts) != 5:
        return None

    qid, engine, run, date, market = parts
    run_match = RUN_FIELD.match(run)

    if not QID_FIELD.match(qid) or not engine or not run_match:
        return None

    if not DATE_FIELD.match(date) or not market:
        return None

    return qid, engine, run_match.group(1), date, market


def split_answer(text: str) -> Tuple[str, str]:
    """Answer body and sources list, split on the first 'Sources:' line."""
    lines = text.splitlines()

    for index, line in enumerate(lines):
        if SOURCES_LINE.match(line):
            return "\n".join(lines[:index]), "\n".join(lines[index + 1:])

    return text, ""


def parse_paste(text: str, origin: str, notes: ParseNotes) -> List[Block]:
    """The answer blocks of a pasted text, one per valid header; malformed headers and stray text go to notes."""
    blocks: List[Block] = []
    current: Optional[Tuple[str, str, str, str, str]] = None
    buffer: List[str] = []
    skipping = False

    def flush() -> None:
        if current is None:
            return

        answer, sources = split_answer("\n".join(buffer))
        blocks.append(Block(*current, answer=answer, sources=sources, origin=origin))

    for number, line in enumerate(text.splitlines(), start=1):
        if HEADER.match(line):
            flush()
            buffer = []
            current = parse_header(line)
            skipping = current is None

            if skipping:
                notes.malformed.append(f"{origin}:{number}: header not in the form "
                                       f"'### <question_id> | <engine> | run <n> | <YYYY-MM-DD> | <market>'; "
                                       f"block skipped")
            continue

        if current is None:
            if line.strip() and not skipping and notes.ignored_text[-1:] != [origin]:
                notes.ignored_text.append(origin)
            continue

        buffer.append(line)

    flush()

    return blocks


def parse_sheet(path: str, notes: ParseNotes) -> List[Block]:
    """The answer blocks of a CSV, TSV or XLSX sheet with one row per run; invalid rows go to notes."""
    tables = read_tables(path)

    if not tables:
        raise TableError(f"{path}: no table found")

    table = tables[0]
    headers = [h.strip().lower() for h in table.headers]
    required = ["question_id", "engine", "run", "date", "market", "answer"]
    missing = [name for name in required if name not in headers]

    if missing:
        raise TableError(f"{path}: missing columns {', '.join(missing)}")

    blocks: List[Block] = []

    for number, row in enumerate(table.rows, start=2):
        record = dict(zip(headers, row + [""] * (len(headers) - len(row))))
        header = f"### {record['question_id']} | {record['engine']} | {record['run']} | " \
                 f"{record['date']} | {record['market']}"
        parsed = parse_header(header)

        if parsed is None:
            notes.malformed.append(f"{os.path.basename(path)}:{number}: question_id/engine/run/date/market "
                                   f"not valid; row skipped")
            continue

        answer, sources = split_answer(record["answer"])
        sources = "\n".join(part for part in (sources, record.get("sources", "")) if part)
        blocks.append(Block(*parsed, answer=answer, sources=sources, origin=os.path.basename(path)))

    if table.truncated:
        notes.rows_capped = True

    return blocks


def read_text_file(path: str) -> str:
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise TableError(f"{path}: file above {MAX_FILE_BYTES} bytes")

    with open(path, "rb") as handle:
        data = handle.read()

    return data.decode("utf-8", errors="replace")


def load_blocks(path: str, notes: ParseNotes) -> List[Block]:
    """Answer blocks from a folder of .txt/.md pastes, a sheet, or one pasted file; bounded by MAX_FILE_BYTES."""
    if os.path.isdir(path):
        blocks: List[Block] = []
        total = 0

        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)

            if os.path.islink(full) or not os.path.isfile(full) or not name.lower().endswith((".txt", ".md")):
                continue

            total += os.path.getsize(full)

            if total > MAX_FILE_BYTES:
                raise TableError(f"{path}: folder above {MAX_FILE_BYTES} bytes of answers")

            blocks.extend(parse_paste(read_text_file(full), name, notes))

        return blocks

    if path.lower().endswith((".csv", ".tsv", ".xlsx")):
        if os.path.getsize(path) > MAX_FILE_BYTES:
            raise TableError(f"{path}: file above {MAX_FILE_BYTES} bytes")

        return parse_sheet(path, notes)

    return parse_paste(read_text_file(path), os.path.basename(path), notes)


def name_pattern(name: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(fold(name)) + r"(?!\w)")


def first_match(text: str, folded: str, names: List[str]) -> Optional[Tuple[int, str]]:
    """Earliest match among a name and its aliases: (position, original matched text)."""
    best: Optional[Tuple[int, str]] = None

    for name in names:
        match = name_pattern(name).search(folded)

        if match and (best is None or match.start() < best[0]):
            best = (match.start(), name)

    return best


def strip_urls(text: str) -> str:
    """URLs replaced by spaces of the same length, so a name only in a link does not count."""
    return URL.sub(lambda m: " " * len(m.group(0)), text)


def folded_view(text: str) -> str:
    """Folded text with one folded char per original char where possible, for offsets."""
    return "".join(fold(c)[:1] or " " for c in text)


def domains_in(text: str) -> List[str]:
    """Hosts of the URLs and bare domains in a text, without www., in order of first appearance."""
    found: List[str] = []

    for url in URL.findall(text):
        host = (urllib.parse.urlsplit(url.rstrip(".,;:")).hostname or "").lower()
        found.append(host)

    without_urls = strip_urls(text)

    for match in BARE_DOMAIN.finditer(without_urls):
        host = match.group(1).lower().rstrip(".")

        if host in COMMON_TLDS_ONLY or "." not in host:
            continue

        found.append(host)

    result: List[str] = []

    for name in found:
        host = name[4:] if name.startswith("www.") else name

        if host and host not in result:
            result.append(host)

    return result


def is_ambiguous(answer: str, folded: str, brand: List[str], collisions: List[str]) -> bool:
    """Heuristic: a brand alias written with capitals appears only in lowercase, or a
    collision term shares a sentence with the brand. A human decides; never resolved here."""
    for name in brand:
        pattern = name_pattern(name)
        matches = list(pattern.finditer(folded))

        if not matches:
            continue

        if name != name.lower():
            originals = [answer[m.start():m.end()] for m in matches]

            if all(original == original.lower() for original in originals):
                return True

    if not collisions:
        return False

    for sentence in re.split(r"(?<=[.!?\n])\s+", folded):
        has_brand = any(name_pattern(name).search(sentence) for name in brand)
        has_collision = any(name_pattern(term).search(sentence) for term in collisions)

        if has_brand and has_collision:
            return True

    return False


def possible_competitors(answer: str, known: List[str]) -> List[str]:
    """Capitalised names in an answer that are not known names or stopwords; at most MAX_POSSIBLE."""
    known_folded = {fold(name) for name in known}
    lower_words = {w for w in re.findall(r"\b[a-zà-ÿ][\w-]*", answer)}
    found: List[str] = []

    for match in CANDIDATE.finditer(answer):
        words = match.group(0).split()

        while words and fold(words[0]) in STOPWORDS:
            words = words[1:]

        if not words:
            continue

        phrase = " ".join(words)
        folded = fold(phrase)

        if folded in known_folded or folded in STOPWORDS:
            continue

        if any(fold(word) in known_folded for word in words):
            continue

        if len(words) == 1 and words[0].lower() in lower_words:
            continue

        if len(phrase) < 2 or phrase in found:
            continue

        found.append(phrase)

        if len(found) >= MAX_POSSIBLE:
            break

    return found


def analyse(block: Block, brand: List[str], competitors: List[Competitor],
            collisions: List[str]) -> Dict[str, str]:
    """One CSV row for an answer: brand named or not, its rank among named entities, domains, ambiguity."""
    body = strip_urls(block.answer)
    folded = folded_view(body)
    entities: List[Tuple[int, str, bool]] = []
    brand_hit = first_match(body, folded, brand)

    if brand_hit:
        entities.append((brand_hit[0], brand[0], True))

    for competitor in competitors:
        hit = first_match(body, folded, competitor["names"])

        if hit:
            entities.append((hit[0], competitor["label"], False))

    entities.sort(key=lambda item: item[0])
    position = ""
    others: List[str] = []

    for rank, (_, label, is_brand) in enumerate(entities, start=1):
        if is_brand:
            position = str(rank)
        else:
            others.append(label)

    known = brand + [name for c in competitors for name in c["names"]]
    domains = domains_in(block.answer + "\n" + block.sources)
    ambiguous = brand_hit is not None and is_ambiguous(body, folded, brand, collisions)
    possible = possible_competitors(body, known)

    return {
        "question_id": untrusted(block.question_id),
        "engine": untrusted(block.engine),
        "run": block.run,
        "date": block.date,
        "market": untrusted(block.market),
        "named": "yes" if brand_hit else "no",
        "position": position,
        "named_instead": untrusted("; ".join(others)),
        "cited_domains": untrusted("; ".join(domains), limit=2000),
        "ambiguous": "yes" if ambiguous else "no",
        "possible_competitors": untrusted("; ".join(possible)),
    }


def parse_competitors(value: Optional[str]) -> List[Competitor]:
    """'Foo|Foo App,Bar' -> Foo with alias Foo App, and Bar."""
    result: List[Competitor] = []

    for item in split_names(value):
        names = [name.strip() for name in item.split("|") if name.strip()]

        if names:
            result.append({"label": names[0], "names": names})

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split pasted raw AI answers into one CSV row per run (no network). "
                    "Mention detection is case- and accent-insensitive with word boundaries; "
                    "it cannot tell a recommendation from a passing or negative mention.",
    )
    parser.add_argument("--answers", required=True,
                        help="paste-format text file, folder of .txt/.md files, or CSV sheet "
                             "(question_id, engine, run, date, market, answer[, sources])")
    parser.add_argument("--brand", required=True, help="comma-separated brand name and aliases")
    parser.add_argument("--competitors", default="",
                        help="comma-separated competitors; aliases with '|', e.g. 'Foo|Foo App,Bar'")
    parser.add_argument("--collision-terms", default="",
                        help="comma-separated words that signal a same-name entity (e.g. 'film,band'); "
                             "a brand mention in the same sentence is flagged ambiguous")
    parser.add_argument("--out", help="CSV path (stdout when omitted)")
    parser.add_argument("--summary", help="optional JSON path for counts, malformed headers and limits")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the answers, write the runs CSV and the optional summary; returns 2 on bad input."""
    args = build_parser().parse_args(argv)
    brand = split_names(args.brand)

    if not brand:
        print("error: --brand needs at least one name", file=sys.stderr)
        return 2

    if not os.path.exists(args.answers):
        print(f"error: {args.answers} not found", file=sys.stderr)
        return 2

    notes = ParseNotes()

    try:
        blocks = load_blocks(args.answers, notes)
    except (TableError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    for line in notes.malformed:
        print(f"malformed: {untrusted(line, 200)}", file=sys.stderr)

    if not blocks:
        print("error: no answer block found; expected headers like "
              "'### Q07 | perplexity | run 2 | 2026-10-16 | FR'", file=sys.stderr)
        return 2

    if len(blocks) > MAX_ROWS:
        blocks = blocks[:MAX_ROWS]
        notes.rows_capped = True
        print(f"warning: capped at {MAX_ROWS} runs", file=sys.stderr)

    competitors = parse_competitors(args.competitors)
    collisions = split_names(args.collision_terms)
    rows = [analyse(block, brand, competitors, collisions) for block in blocks]
    write_csv(rows, FIELDS, args.out)
    print(f"{len(rows)} runs parsed, {sum(r['ambiguous'] == 'yes' for r in rows)} flagged ambiguous, "
          f"{len(notes.malformed)} malformed headers", file=sys.stderr)

    if args.summary:
        summary = {
            "generated_on": today(),
            "runs_parsed": len(rows),
            "ambiguous_runs": sum(r["ambiguous"] == "yes" for r in rows),
            "malformed_headers": [untrusted(line) for line in notes.malformed],
            "files_with_text_before_first_header": [untrusted(name) for name in notes.ignored_text],
            "rows_capped": notes.rows_capped,
            "limits": [
                "a mention is not a recommendation: passing or negative mentions also count as named",
                "names only inside a URL do not count; sources shown only as icons cannot be read",
                "ambiguous=yes rows need a human decision before visibility_score.py",
                "possible_competitors is a raw capitalised-name heuristic for human review",
            ],
        }

        with open(args.summary, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
