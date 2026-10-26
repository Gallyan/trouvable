# Scripts

Python 3.9+ standard library only, **no network**. Both scripts only read the files they are
given; nothing is fetched, re-measured or re-estimated.

## audit_delta.py

```
python3 scripts/audit_delta.py --before old/issues.csv --after new/issues.csv \
    --before-date 2026-09-01 --after-date 2026-10-01 \
    [--before-summary old/summary.json --after-summary new/summary.json] \
    [--key check_id] [--domain-column area] [--checked-ratio 0.2] [--csv delta.csv] [--out delta.json]
python3 scripts/audit_delta.py --before old/result.json --after new/result.json [--out delta.json]
```

- **CSV runs** (two `issues.csv` from seo-audit, or any findings CSV with a key column and a
  `status` column): rows are matched on `--key` (comma-separated columns for a per-URL CSV).
  Read with `seokit.tables`. Rows marked as dropped false positives (`status` = dropped, as seo-audit writes them, or a `dropped` column set to yes) are left out and counted.
  Each key gets one change: `fixed` (fail, then pass), `new` (not failing, then fail),
  `still-open` (fail twice), `no-longer-measured` (fail, then not-measured or not-applicable:
  **not** fixed), `missing-from-after` (fail, then absent: **not** fixed), `lost-coverage`,
  `newly-measured`, `unchanged`. Counts by change, by `severity` and by `--domain-column`.
  Issues CSV files carry no date, so `--before-date` and `--after-date` are required.
- **JSON runs** (two summaries from the same script, e.g. `summary.json` of seo-audit or the
  JSON of seo-search-console): every numeric value is matched on its path; output gives both
  values, the change, both dates (from `generated_on` unless the date flags are given) and
  the sibling `label` when the summary has one. Summaries from different `tool` values are refused.
- **Comparability**: `comparable` is false, with one reason per line, when keys exist in one
  run only, a check's severity or label changed, a check's `checked` base moved by more than
  `--checked-ratio`, or a scope value differs (start URL, mode, page cap, stop reason, date
  range, export type, market, engines…; read from `--before-summary`/`--after-summary` for CSV runs).
- **Output**: JSON on stdout or `--out` (`generated_on`, both files and dates, `comparable`,
  `comparability_reasons`, `by_change`, `by_severity`, `by_domain`, open counts, rows or
  figures, limits). `--csv` writes the changed rows (or the figures) through `write_csv`,
  so spreadsheet-formula cells are neutralised. Site text is passed through `untrusted()`.
- Exit codes: 0 ok, 2 bad input (missing file or column, duplicate key, dates missing or not
  in order, mixed CSV and JSON, no shared key: not two runs of the same audit).

## report_to_html.py

```
python3 scripts/report_to_html.py --in report.md --out report.html [--title "..."] [--lang fr]
```

- Converts a Markdown subset: headings, paragraphs, bold, italic, inline and fenced code,
  bullet and numbered lists (nested by indentation), block quotes, rules, pipe tables
  (`\|` for a pipe inside a cell; short rows padded).
- Every piece of text is HTML-escaped; raw HTML in the Markdown is shown as text. Links and
  images become text followed by the URL in brackets: no live link, no loaded image.
- One standalone file: inline stylesheet, no JavaScript, no external resource, a
  Content-Security-Policy that blocks everything but the inline style. Print stylesheet: A4,
  a page break before each H2 except the first, table headers repeated, rows kept whole.
  PDF: open the file in a browser and print to PDF.
- Exit codes: 0 ok, 2 bad input (missing, larger than 5 MB, not UTF-8, bad `--lang`).
