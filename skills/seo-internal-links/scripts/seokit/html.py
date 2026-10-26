"""Static HTML extraction with html.parser: links with zones, meta, headings, JSON-LD, text.

No JavaScript is run: what a script writes into the page is invisible here.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}
TEXT_SKIP_TAGS = {"script", "style", "template", "svg", "noscript"}
BLOCK_TAGS = {"p", "li", "td", "th", "dd", "dt", "blockquote", "figcaption", "pre"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
CODE_TAGS = {"pre", "code", "kbd", "samp"}
BOILERPLATE_ZONES = {"header", "nav", "footer", "widget"}
STRUCTURE_TAGS = BLOCK_TAGS | HEADING_TAGS | {
    "div", "section", "article", "header", "footer", "aside", "nav", "main", "ul", "ol", "dl",
    "table", "tr", "br", "hr", "form", "figure",
}

LANDMARK_ZONES = {"header": "header", "nav": "nav", "footer": "footer", "aside": "widget"}
ROLE_ZONES = {"banner": "header", "navigation": "nav", "contentinfo": "footer", "complementary": "widget"}
TOKEN_ZONES = [
    ({"header", "masthead", "topbar"}, "header", None),
    ({"nav", "menu", "navbar"}, "nav", None),
    ({"footer"}, "footer", None),
    ({"breadcrumb", "breadcrumbs"}, "widget", "breadcrumb"),
    ({"pagination", "pager"}, "widget", "pagination"),
    ({"related"}, "widget", "related"),
    ({"lang", "language", "languages"}, "widget", "lang-switch"),
    ({"tags", "tag"}, "widget", "tags"),
    ({"author"}, "widget", "author"),
    ({"sidebar", "widget", "share"}, "widget", "sidebar"),
]
CONTENT_TOKENS = {"content", "entry", "post-body", "prose", "article", "post"}


@dataclass
class Link:
    """An <a href> with its zone (header, nav, footer, widget, editorial, unknown) and position."""

    href: str
    url: str
    text: str
    rel: str
    hreflang: Optional[str]
    zone: str
    subtype: Optional[str]
    order: int
    block: Optional[int]
    nofollow: bool


@dataclass
class Image:
    """An <img>: absolute src ("" when missing) and alt (None when the attribute is absent)."""

    src: str
    alt: Optional[str]


@dataclass
class Page:
    """What parse_html extracts from one document (see API.md for each field)."""

    base_url: str
    lang: Optional[str] = None
    title: Optional[str] = None
    titles: List[str] = field(default_factory=list)
    meta: Dict[str, List[str]] = field(default_factory=dict)
    canonicals: List[str] = field(default_factory=list)
    alternates: List[Tuple[str, str]] = field(default_factory=list)
    headings: List[Tuple[str, str]] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    images: List[Image] = field(default_factory=list)
    jsonld: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)
    text: str = ""
    content_blocks: List[str] = field(default_factory=list)
    content_text: str = ""
    content_loose: List[str] = field(default_factory=list)
    main_content_text: str = ""
    content_headings: List[Tuple[str, str]] = field(default_factory=list)
    html_comments: List[str] = field(default_factory=list)

    def meta_first(self, name: str) -> Optional[str]:
        """Content of the first meta tag with this name, property or http-equiv."""
        values = self.meta.get(name.lower())

        return values[0] if values else None

    @property
    def description(self) -> Optional[str]:
        """Content of the first meta description."""
        return self.meta_first("description")

    @property
    def robots(self) -> str:
        """Meta robots and googlebot directives joined by commas, lowercased."""
        values = self.meta.get("robots", []) + self.meta.get("googlebot", [])

        return ", ".join(values).lower()

    @property
    def canonical(self) -> Optional[str]:
        """First rel=canonical URL, absolute."""
        return self.canonicals[0] if self.canonicals else None

    @property
    def word_count(self) -> int:
        """Whitespace-separated words of the visible text."""
        return len(self.text.split())


def _tokens(value: Optional[str]) -> set:
    if not value:
        return set()

    tokens = set()

    for token in re.split(r"\s+", value.lower()):
        if not token:
            continue

        tokens.add(token)
        tokens.update(part for part in re.split(r"[-_]", token) if part)

    return tokens


MAX_DEPTH = 1024


def _main_like(tag: str, attrs: Dict[str, str]) -> bool:
    return tag in ("main", "article") or attrs.get("role", "").lower() == "main"


class _Element:
    """An open element and the context it inherits from its parent, computed once when it is
    pushed. Text and link events then read the top of the stack instead of walking it, which
    keeps parsing linear even on pages made of thousands of unclosed tags."""

    __slots__ = ("tag", "attrs", "in_head", "in_svg", "in_pre", "in_code", "in_article", "in_main",
                 "landmark", "role_zone", "token_zone", "editorial")

    tag: str
    attrs: Dict[str, str]
    in_head: bool
    in_svg: bool
    in_pre: bool
    in_code: bool
    in_article: bool
    in_main: bool
    landmark: Optional[str]
    role_zone: Optional[str]
    token_zone: Optional[Tuple[str, Optional[str]]]
    editorial: bool

    def __init__(self, tag: str, attrs: Dict[str, str], parent: Optional["_Element"] = None) -> None:
        self.tag = tag
        self.attrs = attrs
        main_like = _main_like(tag, attrs)
        tokens = _tokens(attrs.get("class")) | _tokens(attrs.get("id"))
        self.in_head = tag == "head" or bool(parent and parent.in_head)
        self.in_svg = tag == "svg" or bool(parent and parent.in_svg)
        self.in_pre = tag == "pre" or bool(parent and parent.in_pre)
        self.in_code = tag in CODE_TAGS or bool(parent and parent.in_code)
        self.in_article = tag == "article" or bool(parent and parent.in_article)
        self.in_main = main_like or bool(parent and parent.in_main)
        # A header or footer inside an article belongs to the article, not to the page chrome.
        own = LANDMARK_ZONES.get(tag)

        if own and tag in ("header", "footer") and parent and parent.in_article:
            own = None

        self.landmark = own or (parent.landmark if parent else None)
        self.role_zone = ROLE_ZONES.get(attrs.get("role", "").lower()) or (parent.role_zone if parent else None)
        # Class tokens of <body>/<html> describe the layout ("nav-sidebar"), and the classes of
        # wrappers outside <main>/<article> ("page-navbar") do not make the content a menu.
        own_token = None

        if not main_like and tag not in ("body", "html"):
            own_token = next(((zone, subtype) for names, zone, subtype in TOKEN_ZONES if tokens & names), None)

        self.token_zone = None if main_like else (own_token or (parent.token_zone if parent else None))
        self.editorial = main_like or bool(tokens & CONTENT_TOKENS) or bool(parent and parent.editorial)


class _Parser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page = Page(base_url=base_url)
        self.base = base_url
        self.stack: List[_Element] = []
        self.order = 0
        self.block_index = -1
        self.block_open = 0
        self.current_block: List[str] = []
        self.text_parts: List[str] = []
        self.content_parts: List[str] = []
        self.current_content_block: List[str] = []
        self.loose_parts: List[str] = []
        self.main_parts: List[str] = []
        self.capture_content = False
        self.capture: Optional[List[str]] = None
        self.capture_kind: Optional[str] = None
        self.link_text: Optional[List[str]] = None
        self.link_attrs: Optional[Dict[str, str]] = None
        self.link_context: Optional[Tuple[str, Optional[str], Optional[int]]] = None
        self.in_title = False
        self.title_parts: List[str] = []
        self.in_jsonld = False
        self.jsonld_parts: List[str] = []
        self.skip_depth = 0
        self.open_count: Dict[str, int] = {}

    def _abs(self, href: str) -> str:
        return urllib.parse.urljoin(self.base, href.strip())

    def _top(self) -> Optional[_Element]:
        return self.stack[-1] if self.stack else None

    def _zone(self, link_attrs: Dict[str, str]) -> Tuple[str, Optional[str]]:
        top = self._top()

        if top and top.landmark:
            return top.landmark, ("sidebar" if top.landmark == "widget" else None)

        if top and top.role_zone:
            return top.role_zone, None

        if top and top.token_zone:
            return top.token_zone

        rel = link_attrs.get("rel", "").lower().split()

        if link_attrs.get("hreflang"):
            return "widget", "lang-switch"

        if "prev" in rel or "next" in rel:
            return "widget", "pagination"

        if top and top.editorial:
            return "editorial", None

        return "unknown", None

    def _in_main(self) -> bool:
        top = self._top()

        return bool(top and top.in_main)

    def _is_content(self) -> bool:
        """Text outside code blocks and outside header, nav, footer and widget zones. Inline code
        inside a paragraph stays: '<pre>' and a '<code>' outside any p/li/td block do not."""
        top = self._top()

        if top and (top.in_pre or (top.in_code and not self.block_open)):
            return False

        return self._zone({})[0] not in BOILERPLATE_ZONES

    def handle_starttag(self, tag, attrs):
        attributes = {key.lower(): (value or "") for key, value in attrs}
        self._start(tag, attributes)

        if tag not in VOID_TAGS and len(self.stack) < MAX_DEPTH:
            self.stack.append(_Element(tag, attributes, self._top()))
            self.open_count[tag] = self.open_count.get(tag, 0) + 1

    def handle_startendtag(self, tag, attrs):
        attributes = {key.lower(): (value or "") for key, value in attrs}
        self._start(tag, attributes)

    def _flush_loose(self) -> None:
        run = " ".join(" ".join(self.loose_parts).split())

        if run:
            self.page.content_loose.append(run)

        self.loose_parts = []

    def _start(self, tag: str, attrs: Dict[str, str]) -> None:
        if tag in STRUCTURE_TAGS:
            self._flush_loose()

        if tag in TEXT_SKIP_TAGS:
            self._start_skipped(tag, attrs)
            return

        if not self._start_head_tag(tag, attrs):
            self._start_body_tag(tag, attrs)

        if tag in BLOCK_TAGS:
            if not self.block_open:
                self.block_index += 1
                self.current_block = []
                self.current_content_block = []

            self.block_open += 1

    def _start_skipped(self, tag: str, attrs: Dict[str, str]) -> None:
        """Opening of script, style, template, svg or noscript: their text is not page text."""
        if tag == "script" and attrs.get("type", "").lower().strip() == "application/ld+json":
            self.in_jsonld = True
            self.jsonld_parts = []

        if tag != "noscript":
            self.skip_depth += 1

    def _start_head_tag(self, tag: str, attrs: Dict[str, str]) -> bool:
        """Record html lang, base, title, meta and link tags; False when the tag is none of them."""
        page = self.page

        if tag == "html" and attrs.get("lang"):
            page.lang = attrs["lang"].strip()
        elif tag == "base" and attrs.get("href"):
            self.base = self._abs(attrs["href"])
        elif tag == "title" and not self.skip_depth and not (self.stack and self.stack[-1].in_svg):
            self.in_title = True
            self.title_parts = []
        elif tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or attrs.get("http-equiv") or "").lower().strip()

            if key:
                page.meta.setdefault(key, []).append(attrs.get("content", "").strip())
        elif tag == "link":
            self._start_link_tag(attrs)
        else:
            return False

        return True

    def _start_link_tag(self, attrs: Dict[str, str]) -> None:
        rel = attrs.get("rel", "").lower().split()
        href = attrs.get("href")

        if href and "canonical" in rel:
            self.page.canonicals.append(self._abs(href))

        if href and "alternate" in rel and attrs.get("hreflang"):
            self.page.alternates.append((attrs["hreflang"].strip(), self._abs(href)))

    def _start_body_tag(self, tag: str, attrs: Dict[str, str]) -> None:
        """Record an image, or start capturing a heading or a link."""
        if tag == "img":
            self.page.images.append(Image(self._abs(attrs.get("src", "")) if attrs.get("src") else "",
                                          attrs.get("alt")))
        elif tag in HEADING_TAGS:
            self.capture = []
            self.capture_kind = tag
            self.capture_content = self._is_content()
        elif tag == "a" and attrs.get("href") is not None:
            self.link_text = []
            self.link_attrs = attrs
            zone, subtype = self._zone(attrs)
            block = self.block_index if (zone == "editorial" and self.block_open) else None
            self.link_context = (zone, subtype, block)

    def handle_endtag(self, tag):
        """Close what the tag ends (JSON-LD, title, heading, link, block), then pop it off the stack."""
        if tag in STRUCTURE_TAGS:
            self._flush_loose()

        if tag in TEXT_SKIP_TAGS:
            self._end_skipped(tag)

        if tag == "title" and self.in_title:
            self._end_title()
        elif tag in HEADING_TAGS and self.capture is not None and self.capture_kind == tag:
            self._end_heading(tag, self.capture)
        elif tag == "a" and self.link_attrs is not None:
            self._close_link()

        if tag in BLOCK_TAGS and self.block_open:
            self._end_block()

        self._pop(tag)

    def _end_skipped(self, tag: str) -> None:
        if tag == "script" and self.in_jsonld:
            self.page.jsonld.append("".join(self.jsonld_parts).strip())
            self.in_jsonld = False

        if tag != "noscript" and self.skip_depth:
            self.skip_depth -= 1

    def _end_title(self) -> None:
        title = " ".join("".join(self.title_parts).split())
        self.page.titles.append(title)

        if self.page.title is None:
            self.page.title = title

        self.in_title = False

    def _end_heading(self, tag: str, captured: List[str]) -> None:
        heading = (tag, " ".join("".join(captured).split()))
        self.page.headings.append(heading)

        if self.capture_content:
            self.page.content_headings.append(heading)

            # A heading ends a sentence: "Background" must not run into "Agents now use…".
            if heading[1] and heading[1][-1] not in ".!?:…" and self.content_parts:
                self.content_parts[-1] += "."

                if self.main_parts and self._in_main():
                    self.main_parts[-1] += "."

        self.capture = None
        self.capture_kind = None

    def _end_block(self) -> None:
        """Close one level of p/li/td… nesting; the outermost one stores the block's text."""
        self.block_open -= 1

        if self.block_open:
            return

        block = " ".join("".join(self.current_block).split())

        if block:
            self.page.blocks.append(block)
        else:
            self.block_index -= 1

        content = " ".join("".join(self.current_content_block).split())

        if content:
            self.page.content_blocks.append(content)

    def _pop(self, tag: str) -> None:
        """Pop the innermost open element with this tag and every element opened inside it."""
        if not self.open_count.get(tag):
            return

        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                for element in self.stack[index:]:
                    self.open_count[element.tag] -= 1

                del self.stack[index:]
                break

    def _close_link(self) -> None:
        attrs = self.link_attrs or {}
        href = attrs.get("href", "")
        zone, subtype, block = self.link_context or ("unknown", None, None)
        rel = attrs.get("rel", "").lower()
        self.page.links.append(Link(
            href=href,
            url=self._abs(href) if href else "",
            text=" ".join("".join(self.link_text or []).split()),
            rel=rel,
            hreflang=attrs.get("hreflang") or None,
            zone=zone,
            subtype=subtype,
            order=self.order,
            block=block,
            nofollow="nofollow" in rel.split(),
        ))
        self.order += 1
        self.link_attrs = None
        self.link_text = None
        self.link_context = None

    def handle_data(self, data):
        """Route text to the title, JSON-LD, heading, link, block, content and main buffers that are open."""
        if self.in_jsonld:
            self.jsonld_parts.append(data)
            return

        if self.skip_depth:
            return

        if self.in_title:
            self.title_parts.append(data)
            return

        if self.stack and self.stack[-1].in_head:
            return

        self.text_parts.append(data)

        if self.capture is not None:
            self.capture.append(data)

        if self.link_text is not None:
            self.link_text.append(data)

        if self.block_open:
            self.current_block.append(data)

        if self._is_content():
            self.content_parts.append(data)

            if self.block_open:
                self.current_content_block.append(data)
            elif self.capture is None:
                self.loose_parts.append(data)

            if self._in_main():
                self.main_parts.append(data)

    def handle_comment(self, data):
        text = data.strip()

        if text:
            self.page.html_comments.append(text)

    def close(self):
        """Finish parsing: close a dangling link, flush loose text and build the page texts."""
        super().close()

        if self.link_attrs is not None:
            self._close_link()

        self._flush_loose()

        self.page.text = " ".join(" ".join(self.text_parts).split())
        self.page.content_text = " ".join(" ".join(self.content_parts).split())
        self.page.main_content_text = " ".join(" ".join(self.main_parts).split())


def parse_html(html: str, base_url: str) -> Page:
    """Extract a Page from static HTML; never raises (on a parser failure, text gathered so far is kept)."""
    parser = _Parser(base_url)

    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, ValueError):
        parser.page.text = " ".join(" ".join(parser.text_parts).split())

    return parser.page
