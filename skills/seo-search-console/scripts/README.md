# Scripts

## query_opportunities.py

Offline analyser of Search Console Performance exports. Python 3.9+ standard library, no network.

```
python3 scripts/query_opportunities.py --queries <file> --pages <file> --brand "<term1>,<term2>"
    [--compare <previous-period file>] [--query-pages <file>] [--out result.json] [--top 20]
    [--min-impressions 300 --min-queries 20 --usable-impressions 3000 --usable-clicks 30]
    [--near-min-position 8 --near-max-position 20 --near-min-impressions 0]
    [--curve-min-bucket 50 --curve-min-buckets 5 --gap-ratio 0.5 --gap-min-impressions 50]
    [--competing-min-share 0.2]
```

- **Input**: CSV, XLSX or the export ZIP (read with `seokit.tables`, size and row caps). `--queries`
  and `--pages` may be the same ZIP. Tables are recognised by `seokit.gsc`: English headers, then
  content. No translated header is added from memory; unmapped columns are listed per table.
- **Output** (JSON on stdout, or `--out`): `generated_on`, tables read, date range (from a dates
  table, else "not measurable"), `export_type` (`web-search` or `discover-or-news` when there is no
  queries table with positions), brand split (case- and accent-insensitive), anonymised-query share
  (Pages vs Queries totals), `sample_verdict` (`insufficient|limited|usable` per `references/sample-verdict.md`,
  with its numbers), trend vs `--compare`, then unless `insufficient`: near-page-one queries, the site's own
  CTR curve or `not computable yet`, CTR gaps against that curve, competing pages (only when a
  query+page table exists, else `not measurable with these exports`), `not_measured`.
- **Limits**: thresholds are heuristics to calibrate; the gap ratio, gap minimum and competing share
  are script choices not set by the references. No generic CTR curve is ever used. Queries and URLs
  are printed through `untrusted()` in `query_text` / `page_url` fields, never interpreted.
- Exit codes: 0 ok, 2 bad input (missing or unreadable file, no recognised table).
