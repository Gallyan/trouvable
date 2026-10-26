# Scripts

Python 3.9+ standard library only, read-only, nothing to install. They use the bundled
`seokit/` package (fetching, HTML parsing, sitemaps, tables, text normalisation, output).
Site and file text is printed as quoted data (`*_quoted` fields, `claim_text`), never
interpreted; HTML comments are listed as data. Exit codes: 0 done, 2 bad input or
unreadable input, 3 the site answered 401/403/429 (no retry, no workaround).
Networked scripts accept `--user-agent --delay --timeout --max-bytes --allow-private` (the last one only for a local or staging site; private and local addresses are refused otherwise).

## claim_scan.py

```
python3 scripts/claim_scan.py --in <file|url> [--lang en|fr|es|de|it|pt] [--out claims.csv] [--format csv|json]
```

- **Input**: Markdown (front matter `title`/`lang` read), HTML, plain text, or one URL (one GET).
- **Finds** sentences with amounts + currency (and "free" wording), versions, dates and years,
  percentages and other numbers, quoted strings (short = `label`, long = `quote`), path-like
  labels (`"Settings" > "Billing"`), absolute/superlative words, comparison wording; `legal`
  is added when a candidate also carries legal/tax wording.
- **Output**: CSV with the columns of `templates/claims-ledger.csv` (id, claim_text, location
  such as `title`, `h1`, `p3`, `li2`, `table row 2`, `text`; type; risk; `string_searched`
  pre-filled with the matched literal; `source_language` = page language; verdict and
  checked_on left empty). Order: high risk first, then position. Summary on stderr: date,
  language and how it was obtained, rows per type, possible internal conflicts (same plan
  with two prices for the same period, same product with two versions, in different
  sentences), HTML comments quoted. `--format json` puts the summary, limits and ledger in one JSON.
- **Vocabulary**: one marked `VOCABULARY` block for EN/FR/ES/DE/IT/PT, small and conservative;
  each language has a fixture in `tests/fixtures/seo-fact-check/`. Language: `--lang`, else
  the page's declared language, else a labelled stopword guess, else all six lists.
- **Limits**: candidates only (Claude reads the full text); risk `low` is never assigned by
  the script; static HTML only; HTML order is rebuilt from text positions.

## site_search.py

```
python3 scripts/site_search.py --dir <content folder> --find "<old string>" [--find "<variant>"] [--fuzzy-numbers] [--out hits.csv]
python3 scripts/site_search.py --sitemap <url> --find "<string>" [--max-pages 200]
python3 scripts/site_search.py --urls <file with one URL per line> --find "<string>"
```

- **Method**: literal search after whitespace/quote/dash normalisation (`seokit.text.find_literal`),
  ignoring hits cut out of a longer number (`19 €` inside `119 €`). HTML is searched in title,
  meta description, headings, blocks, remaining text and JSON-LD. `--fuzzy-numbers` also matches
  separators, decimal comma, trailing zeros, currency symbol/code and its position.
- **Output**: CSV on stdout or `--out`: url_or_path, location, string_searched, matched_string,
  sentence_quoted, result (`found`, `not read` with the reason, `left out` for the cap), note,
  checked_on. Summary on stderr.
- **Limits**: page cap 200 by default (heuristic) with `--sitemap`/`--urls`; the run stops on
  401/403/429 on the first page or 3 in a row (exit 3); no JavaScript rendering. `--dir` is offline.

## source_find.py

```
python3 scripts/source_find.py --url <source> [--url <other>] --find "<string>" [--find "<variant>"] [--context 200] [--out result.json]
```

- **Method**: one raw GET per URL, each string searched in the raw HTML (entities decoded) and
  in the extracted text, after normalisation.
- **Output**: JSON per URL: final_url, redirect_chain, status, fetched_at (UTC), truncated,
  `readable` + `unreadable_reason` (non-200, blocked, challenge/captcha, login wall, JavaScript
  shell, nearly empty, PDF or binary), page_title_quoted, html_comments_quoted, and per string:
  result `found` / `not found` / `not found in the part read` (body above the size cap) /
  `not read`, where it was found (raw, text), matches with context quoted.
- **Limits**: "found" wins even on a page flagged unreadable (the string was read); "not found"
  only on a readable, complete body. One location, one user agent: regional prices may differ.
  Readability checks are heuristic. Exit 3 if any URL answered 401/403/429.

## perishable_facts.py

```
python3 scripts/perishable_facts.py --sitemap <url> [--max-pages 100] --out facts.json
python3 scripts/perishable_facts.py --dir <folder> [--csv decay-register.csv]
python3 scripts/perishable_facts.py --urls <file> [--register decay-register.csv] [--previous old-facts.json] [--today YYYY-MM-DD]
```

- **Reads**: `--dir` (HTML and Markdown, offline), `--sitemap` (index and gzip followed) or
  `--urls`; cap `--max-pages` (default 100, heuristic) on every mode, the rest listed as left out.
- **Extracts** per sentence the classes of `references/fact-classes.md`: price, plan-limit,
  version, terms, count, stat, year-in-title (title, H1, slug), event (full dates; "upcoming"
  wording noted), person-role, other (years). Overlaps keep the shorter cadence. Per page:
  visible updated/published date (cue words, `<time>`), JSON-LD `dateModified`/`datePublished`,
  Markdown front matter dates, sitemap `lastmod`.
- **Output** (JSON on stdout or `--out`): generated_on, scan_date, pages_scanned,
  pages_left_out (count + URLs), pages_not_read, stopped, sitemap_lastmod_check, status_counts,
  `facts` (one row per entity + attribute + value, with every page, date basis, status, risk,
  cadence, next check, sentences quoted), contradictions (same entity and attribute, other
  value, in different sentences), date_findings (`references/date-checks.md`), pages, fact_records,
  not_measured, limits. `--csv` writes the rows in `templates/decay-register.csv` columns
  (owner "to assign" unless the register names one).
- **Statuses**: `overdue`/`due-soon`/`ok` only with a `last_verified` from `--register`
  (label `reported`); otherwise `page-dated`, `no-date`, `future-date`, `event-passed` (`measured`).
  A register `cadence_days` overrides the class default.
- **Date checks**: visible vs dateModified (> 2 days, `--visible-structured-days`), visible vs
  lastmod (> 7 days, `--visible-lastmod-days`), unreliable lastmod (> 80 % on one day or > 50 %
  on the scan day, at least 5 URLs; lastmod then not used as a date basis), future date, event
  passed, year in title behind / ahead of content, date moved with unchanged facts (needs `--previous`).
- **Limits**: static HTML only; pattern detection has false positives and misses; entity and
  attribute names are best guesses; the risk raise for selling/lead/step pages reads a pricing
  URL or slug, two prices or more, a `<form>` or a "step 1" cue; it never says whether a fact is true.

## source_watch.py

```
python3 scripts/source_watch.py --register decay-register.csv [--only overdue,due-soon] [--today YYYY-MM-DD] --out watch.csv
```

- **Input**: register rows with `source_url` and `source_string`. `--only` filters on the
  register `status` (an `ok`/`due-soon` row whose `next_check` has passed counts as `overdue`).
- **Output**: CSV on stdout or `--out`: fact_id, source_url, http_status, result (`present` /
  `absent` / `not read` / `not checked` when the row has no source), reason,
  source_string_quoted, context_quoted, fetched_at, register_status.
- **Rules**: one GET per distinct URL; a blocked host (401/403/429) is not asked again and the
  exit code is 3; blocked, erroring, challenge, login or JavaScript-shell pages are `not read`,
  never `absent`. It never marks a fact verified and never writes the register (`--out` may not
  point at it). `present` only means the string is still there: re-read the source to verify.
