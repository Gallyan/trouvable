# Scripts

Python 3.9+ standard library only, read-only, no installation. Shared code in `seokit/`
(do not edit the copy). Network: GET only, identifiable user agent, about 2 requests per
second (`--delay`), robots.txt respected, timeouts, response size cap (`--max-bytes`).
A 401/403/429 stops the run without workaround (exit code 3); pages left are "not read".
Exit 2 on bad input. All site text in the output is quoted data (`*_quote`, `*_text` fields).

## structured_data.py

```
python3 scripts/structured_data.py --urls urls.txt --out findings.json
python3 scripts/structured_data.py --sitemap https://example.com/sitemap.xml --max 25 --out findings.json
python3 scripts/structured_data.py --dir ./build --base-url https://example.com/ --out findings.json
```

- **Input**: `--urls` (file, one URL per line, or comma-separated), `--sitemap` (fills the
  sample after the given URLs, evenly spread), `--dir` (an HTML file or a build folder, no
  network; `--base-url` maps files to public URLs for the URL checks), `--max` (default 25).
  Tuning: `--min-overlap` (0.6) and `--ngram` (3) for the FAQ phrase-overlap pointer,
  heuristic, to calibrate.
- **Reads**: every `<script type="application/ld+json">` (seokit.html), `@graph`, top-level
  lists and nested typed nodes flattened. Visible text = static body text minus script,
  style, template, svg and elements hidden by `hidden`, inline `display:none` /
  `visibility:hidden` or `noscript` (that text is kept apart as "hidden").
- **Output** (JSON): `sample` (candidates, selected, left out), `summary`, then per page:
  status (`read` / `not read` + reason), blocks (parsed or error), types, entities with
  `properties_present`, findings (code, severity, property, `markup_value_quote`,
  `visible_quote`, note, overlap score), `html_comments_quoted`.
- **Codes computed**: M01–M10, P01, P05; P03 partly (visible `<time datetime>` newer than
  `dateModified`); P04 partly (template = first path segment in the sample). P02 not computed.
  Listed in `codes_computed` / `codes_partial` / `codes_not_computed`.
- **Limits**: no required-property check (that comes from the dated policy table, not from
  this script); no Google eligibility decision; no review authenticity judgement; dates
  searched in ISO/numeric forms and `<time datetime>` only; currency symbols from a partial
  table. Every finding is a lead to confirm on the page.
