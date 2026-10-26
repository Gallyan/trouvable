#!/usr/bin/env python3
"""Turn a Markdown client report into one standalone, printable HTML file (A4, a page break
before each H2 but the first, tables kept readable). Print it to PDF from a browser.

Usage: python3 scripts/report_to_html.py --in report.md [--out report.html] [--title "..."] [--lang fr]

Supported Markdown: headings, paragraphs, bold, italic, inline code, fenced code, bullet and
numbered lists (nested by indentation), block quotes, horizontal rules, pipe tables.
Links and images are shown as text followed by their URL, never as live links or loaded images.
Every piece of text is HTML-escaped; raw HTML in the Markdown is shown as text. The page has
no JavaScript and loads nothing from outside.

Network: none.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from typing import List, Optional, Tuple

MAX_INPUT_BYTES = 5_000_000
_CONTROL = dict.fromkeys(c for c in range(32) if c not in (9, 10))
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
BULLET = re.compile(r"^(\s*)([-*+])\s+(.*)$")
NUMBERED = re.compile(r"^(\s*)(\d{1,9})[.)]\s+(.*)$")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*<?((?:[^()\s<>]|\([^()\s<>]*\))*)>?(?:\s+\"[^\"]*\")?\s*\)")
ESCAPABLE = {"\\*": "&#42;", "\\_": "&#95;", "\\`": "&#96;", "\\#": "&#35;", "\\[": "&#91;",
             "\\]": "&#93;", "\\|": "&#124;", "\\\\": "&#92;"}
LANG = re.compile(r"[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8}){0,3}")

STYLE = """
:root { color-scheme: light; }
body { font-family: Georgia, "Times New Roman", serif; font-size: 11pt; line-height: 1.5;
  color: #1a1a1a; background: #ffffff; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; }
h1, h2, h3, h4, h5, h6 { font-family: "Helvetica Neue", Arial, sans-serif; line-height: 1.25;
  break-after: avoid; page-break-after: avoid; }
h1 { font-size: 20pt; margin-top: 0; }
h2 { font-size: 15pt; border-bottom: 1px solid #999; padding-bottom: .2rem; margin-top: 2rem; }
h3 { font-size: 12.5pt; }
p, li { overflow-wrap: anywhere; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 9.5pt; }
th, td { border: 1px solid #888; padding: .3rem .4rem; text-align: left; vertical-align: top;
  overflow-wrap: anywhere; }
th { background: #eeeeee; }
tr { break-inside: avoid; page-break-inside: avoid; }
thead { display: table-header-group; }
code { font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 9.5pt;
  background: #f3f3f3; padding: 0 .15rem; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f3f3f3; padding: .5rem;
  font-size: 9pt; break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid #999; margin-left: 0; padding-left: .8rem; color: #333; }
.url { font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 8.5pt; color: #444; }
hr { border: 0; border-top: 1px solid #999; }
@page { size: A4; margin: 18mm 16mm; }
@media print {
  body { margin: 0; max-width: none; padding: 0; }
  h2 { break-before: page; page-break-before: always; }
  h2.first { break-before: auto; page-break-before: auto; }
}
"""


class InputError(ValueError):
    pass


def clean(text: str) -> str:
    return text.translate(_CONTROL)


def emphasis(escaped: str) -> str:
    for raw, entity in ESCAPABLE.items():
        escaped = escaped.replace(raw, entity)

    escaped = re.sub(r"\*\*(?!\s)(.+?)(?<!\s)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\w)__(?!\s)(.+?)(?<!\s)__(?!\w)", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])", r"<em>\1</em>", escaped)

    return re.sub(r"(?<![\w_])_(?![\s_])(.+?)(?<![\s_])_(?![\w_])", r"<em>\1</em>", escaped)


def links(text: str) -> str:
    """Escape a stretch without code spans, showing links and images as text plus URL."""
    out: List[str] = []
    last = 0

    for match in LINK.finditer(text):
        out.append(emphasis(html.escape(text[last:match.start()], quote=True)))
        label = emphasis(html.escape(match.group(2), quote=True))
        url = html.escape(match.group(3), quote=True)

        if match.group(1):
            label = f"[image: {label}]" if label else "[image]"

        if url and url != label:
            out.append(f"{label} <span class=\"url\">({url})</span>")
        else:
            out.append(label)

        last = match.end()

    out.append(emphasis(html.escape(text[last:], quote=True)))

    return "".join(out)


def inline(text: str) -> str:
    out: List[str] = []
    last = 0

    for match in CODE_SPAN.finditer(text):
        out.append(links(text[last:match.start()]))
        out.append(f"<code>{html.escape(match.group(2).strip(), quote=True)}</code>")
        last = match.end()

    out.append(links(text[last:]))

    return "".join(out)


def split_row(line: str) -> List[str]:
    """The cells of a pipe table row, outer pipes dropped; an escaped \\| stays inside its cell."""
    line = line.strip()

    if line.startswith("|"):
        line = line[1:]

    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]

    cells, current, index = [], "", 0

    while index < len(line):
        if line[index] == "\\" and index + 1 < len(line) and line[index + 1] == "|":
            current += "\\|"
            index += 2
            continue

        if line[index] == "|":
            cells.append(current.strip())
            current = ""
        else:
            current += line[index]

        index += 1

    cells.append(current.strip())

    return cells


def is_table_start(lines: List[str], index: int) -> bool:
    return ("|" in lines[index] and index + 1 < len(lines)
            and TABLE_SEPARATOR.match(lines[index + 1]) is not None and "-" in lines[index + 1])


def render_table(lines: List[str], index: int) -> Tuple[str, int]:
    """A pipe table starting at index (header, separator, rows), padded to its widest row; returns the next index."""
    header = split_row(lines[index])
    index += 2
    body: List[List[str]] = []

    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        body.append(split_row(lines[index]))
        index += 1

    width = max([len(header)] + [len(r) for r in body])
    out = ["<table>", "<thead><tr>"]
    out.extend(f"<th>{inline(c)}</th>" for c in header + [""] * (width - len(header)))
    out.append("</tr></thead>")

    if body:
        out.append("<tbody>")

        for row in body:
            cells = row + [""] * (width - len(row))
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")

        out.append("</tbody>")

    out.append("</table>")

    return "\n".join(out), index


def list_item(line: str) -> Optional[Tuple[int, str, str]]:
    """Indent width, list kind (ul or ol) and text of a list item line; None for any other line."""
    for pattern, kind in ((BULLET, "ul"), (NUMBERED, "ol")):
        match = pattern.match(line)

        if match and not RULE.match(line):
            return len(match.group(1).expandtabs(4)), kind, match.group(3)

    return None


def render_list(lines: List[str], index: int) -> Tuple[str, int]:
    """A list starting at index, nested by indentation, indented lines continuing the item above.

    Returns the HTML and the index of the first line after the list.
    """
    out: List[str] = []
    stack: List[Tuple[int, str]] = []

    def close() -> None:
        out.append(f"</{stack.pop()[1]}>")

        if stack:
            out.append("</li>")

    while index < len(lines):
        item = list_item(lines[index])

        if item is None:
            stripped = lines[index].strip()

            if stripped and lines[index][:1].isspace() and out[-1].endswith("</li>"):
                out[-1] = out[-1][: -len("</li>")] + " " + inline(stripped) + "</li>"
                index += 1
                continue

            break

        indent, kind, text = item

        while len(stack) > 1 and indent < stack[-1][0]:
            close()

        if stack and indent > stack[-1][0] and out[-1].endswith("</li>"):
            out[-1] = out[-1][: -len("</li>")]
            stack.append((indent, kind))
            out.append(f"<{kind}>")
        elif not stack:
            stack.append((indent, kind))
            out.append(f"<{kind}>")
        elif stack[-1][1] != kind and indent <= stack[-1][0]:
            out.append(f"</{stack.pop()[1]}>")
            stack.append((indent, kind))
            out.append(f"<{kind}>")

        out.append(f"<li>{inline(text)}</li>")
        index += 1

    while stack:
        close()

    return "\n".join(out), index


MAX_QUOTE_DEPTH = 5


def render_fence(lines: List[str], index: int, fence: re.Match) -> Tuple[str, int]:
    """A fenced code block opening at index; an unclosed fence runs to the end of the text."""
    marker = fence.group(1)[0] * 3
    index += 1
    code: List[str] = []

    while index < len(lines) and not lines[index].strip().startswith(marker):
        code.append(lines[index])
        index += 1

    return "<pre><code>" + html.escape("\n".join(code), quote=True) + "</code></pre>", index + 1


def render_quote(lines: List[str], index: int, depth: int) -> Tuple[str, int]:
    """A block quote, rendered as Markdown itself; past MAX_QUOTE_DEPTH its lines stay flat text."""
    quoted: List[str] = []

    while index < len(lines) and lines[index].strip().startswith(">"):
        quoted.append(lines[index].strip()[1:].strip())
        index += 1

    if depth >= MAX_QUOTE_DEPTH:
        return "<blockquote><p>" + "<br>".join(inline(q) for q in quoted) + "</p></blockquote>", index

    inner, _ = render_body("\n".join(quoted), depth + 1)

    return f"<blockquote>{inner}</blockquote>", index


def ends_paragraph(lines: List[str], index: int, started: bool) -> bool:
    """Whether the line at index closes the paragraph being built (a list item only once it has text)."""
    current = lines[index]

    if not current.strip() or HEADING.match(current.strip()) or FENCE.match(current):
        return True

    if RULE.match(current) or is_table_start(lines, index) or current.strip().startswith(">"):
        return True

    return started and list_item(current) is not None


def render_paragraph(lines: List[str], index: int) -> Tuple[str, int]:
    """A paragraph starting at index; a line ending in two spaces or a backslash becomes a line break."""
    paragraph: List[str] = []

    while index < len(lines) and not ends_paragraph(lines, index, bool(paragraph)):
        current = lines[index]
        breaks = current.endswith(("  ", "\\"))
        text = inline(current.strip().rstrip("\\"))
        paragraph.append(text + ("<br>" if breaks else ""))
        index += 1

    return "<p>" + "\n".join(paragraph) + "</p>", index


def render_body(markdown: str, depth: int = 0) -> Tuple[str, Optional[str]]:
    """The HTML body of a Markdown text and its first H1 text (None when it has none).

    The first H2 gets class "first": printing adds no page break before it.
    """
    lines = clean(markdown).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: List[str] = []
    title: Optional[str] = None
    seen_h2 = False
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        fence = FENCE.match(line)

        if fence:
            block, index = render_fence(lines, index, fence)
            out.append(block)
            continue

        heading = HEADING.match(stripped)

        if heading:
            level = len(heading.group(1))
            css = ""

            if level == 1 and title is None:
                title = heading.group(2)

            if level == 2 and not seen_h2:
                css = " class=\"first\""
                seen_h2 = True

            out.append(f"<h{level}{css}>{inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if RULE.match(line):
            out.append("<hr>")
            index += 1
            continue

        if is_table_start(lines, index):
            block, index = render_table(lines, index)
        elif list_item(line):
            block, index = render_list(lines, index)
        elif stripped.startswith(">"):
            block, index = render_quote(lines, index, depth)
        else:
            block, index = render_paragraph(lines, index)

        out.append(block)

    return "\n".join(out), title


def plain(text: str) -> str:
    text = CODE_SPAN.sub(lambda m: m.group(2), text)
    text = LINK.sub(lambda m: m.group(2), text)

    return re.sub(r"[*_`]", "", text).strip()


def render_document(markdown: str, title: Optional[str] = None, lang: str = "en") -> str:
    body, first_heading = render_body(markdown)
    page_title = title or (plain(first_heading) if first_heading else "Report")

    return "\n".join([
        "<!DOCTYPE html>",
        f"<html lang=\"{html.escape(lang, quote=True)}\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>{html.escape(clean(page_title), quote=True)}</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body>",
        body,
        "</body>",
        "</html>",
        "",
    ])


def read_markdown(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_INPUT_BYTES + 1)
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error

    if len(data) > MAX_INPUT_BYTES:
        raise InputError(f"{path}: larger than {MAX_INPUT_BYTES} bytes")

    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputError(f"{path}: not UTF-8 text ({error})") from error


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Markdown report to one printable, standalone HTML file.")
    parser.add_argument("--in", dest="source", required=True, help="Markdown report to convert")
    parser.add_argument("--out", help="HTML file to write (stdout when omitted)")
    parser.add_argument("--title", help="page title; default the first H1")
    parser.add_argument("--lang", default="en", help="language code of the report, e.g. fr (default en)")

    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    if not LANG.fullmatch(args.lang):
        print(f"error: --lang {args.lang!r} is not a language code", file=sys.stderr)
        return 2

    try:
        markdown = read_markdown(args.source)
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    document = render_document(markdown, args.title, args.lang)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(document)
    else:
        sys.stdout.write(document)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
