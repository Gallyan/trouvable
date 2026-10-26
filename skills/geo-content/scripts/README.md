# Scripts

Python 3.9+ standard library only, read-only, nothing to install. Shared code in `seokit/`
(do not edit the copy). Network (`--url`, `--urls`): GET only, identifiable user agent, about
2 requests per second (`--delay`), robots.txt respected, timeouts, size cap (`--max-bytes`).
A 401/403/429 stops the run without workaround (exit 3). Exit 2 on bad input. All site text
in the output is quoted data (`*_quote` fields, `html_comments_quoted`).

## passage_scan.py

```
python3 scripts/passage_scan.py --url https://example.com/guide --url https://example.com/pricing --out passages.json
python3 scripts/passage_scan.py --urls pages.txt --max-pages 20 --out passages.json
python3 scripts/passage_scan.py --from-crawl ./audit/crawl --max-pages 20 --out passages.json
python3 scripts/passage_scan.py --file ./build/guide.html --base-url https://example.com/guide
```

- **Cuts** each page into passages: a heading (h1–h4) and the text blocks under it, in page
  order. Left out: `nav`, `header`, `footer`, `aside`, forms, code, hidden elements, and
  blocks whose class or id names navigation, menus, sidebars, cookies, sharing, comments or
  newsletters.
- **Per passage**: heading (quoted), whether it reads as a question (`?` or a question word,
  six languages), word count, opening sentence (quoted) and its length, figures (amounts,
  units, percentages, years, versions), lists and tables, links to other sites, and `leads`:
  opening that leans on earlier text ("This", "Cela"…), opening over 35 words, under 40 or
  over 300 words, no figure, no heading. Thresholds: design choices, heuristic, to calibrate.
- **Per page**: language, title, static word count and `little_static_text` (under 150 words:
  probably rendered by JavaScript), question headings, `trust_signals` (author meta, author
  links, author in JSON-LD, published/modified dates, about and contact links, JSON-LD types),
  HTML comments quoted.
- **Output** (JSON on stdout or `--out`): pages read, pages not read with the reason, stop
  reason, thresholds, pages, limits.
- **Limits**: static HTML only; it does not judge whether an opening answers the question,
  whether a fact is true or original, or how any assistant ranks sources.
