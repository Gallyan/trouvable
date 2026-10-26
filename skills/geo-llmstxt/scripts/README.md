# Scripts

Python 3.9+ standard library only, read-only, no installation. Shared code in `seokit/`
(do not edit the copy). Network: GET only, identifiable user agent, about 2 requests per
second (`--delay`), robots.txt respected, timeouts, response size cap (`--max-bytes`).
A 401/403/429 stops the run without workaround (exit code 3); pages left are "not read".
Exit 2 on bad input. All site text in the output is quoted data (`*_quote`, `*_text` fields).

## llmstxt_review.py

```
python3 scripts/llmstxt_review.py --site https://example.com/ --out llms.json
python3 scripts/llmstxt_review.py --file ./public/llms.txt --site https://example.com/ --max-links 100
python3 scripts/llmstxt_review.py --file ./llms.txt --no-check-links
```

- **Input**: `--site` (fetches `/llms.txt`, base for relative links) and/or `--file` (local
  file instead of the fetch); `--check-links` on by default (`--no-check-links`),
  `--max-links` (default 100).
- **Checks**: L01 status and content type (a missing file, 404/410, is `present: false`
  with an info line, never a defect), L02 one H1 first, L03 summary after the title, L04
  `## ` sections with `- [title](url): note` lists, L05 each link by GET (status, redirects,
  final URL), L06 redirect, noindex, canonical elsewhere, L08 instruction-like or promotional
  wording (pattern list, heuristic) quoted as `wording_quote`, L09 when Last-Modified headers
  exist. L07 (claims vs pages) is left to reading.
- **Output** (JSON): `present`, `structure`, `links` (status, redirects, result),
  `findings`, `html_comments_quoted`, `summary`, `limits`.

## llmstxt_draft.py

```
python3 scripts/llmstxt_draft.py --site https://example.com/ --out llms.txt
python3 scripts/llmstxt_draft.py --from-crawl ./audit/crawl --out llms.txt --report draft.json
```

- **Input**: `--site` (crawls it, `--max-pages` default 200, heuristic) or `--from-crawl` (a
  seokit crawl directory, such as the one seo-audit writes; offline).
- **Keeps**: HTML pages answering 200, without `noindex` (meta or `X-Robots-Tag`), whose
  canonical is themselves, without a query string, on the same site. Everything else is
  counted in `pages_left_out` by reason.
- **Writes** (`--out`): H1 = `og:site_name` of the home page, else a title suffix shared by
  most pages, else `{site name}`; summary = the home page meta description, else a
  placeholder; one `## ` section per first path segment holding at least 2 pages (heuristic),
  the rest under `## Pages`; one line per page, `- [H1 or title](url): meta description`,
  `{description}` when the page has none. Site text is put on one line, stripped of `[ ] < >`
  and cut at 90 / 200 characters.
- **Output** (JSON on stdout or `--report`): pages read, listed and left out, site name and
  its basis, sections, placeholder count, `wording_leads` (L08 patterns found in the draft,
  quoted), limits. Exit 3 when the crawl stopped on 401/403/429.
- **Limits**: static HTML only; sections follow URLs, not the site's menu; titles and
  descriptions are the pages' own and may need rewriting; nothing is invented.
