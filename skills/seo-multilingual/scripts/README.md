# Scripts

Python 3.9+ standard library only, read-only, no installation. Shared code in `seokit/`
(do not edit the copy). Network: GET only, identifiable user agent, about 2 requests per
second (`--delay`), robots.txt respected, timeouts, response size cap (`--max-bytes`).
A 401/403/429 stops the run without workaround (exit code 3); pages left are "not read".
Exit 2 on bad input. No JavaScript. Site text in the output is quoted data.

## lang_alternates.py

```
python3 scripts/lang_alternates.py --sitemap https://example.com/sitemap.xml --max 200 --out hreflang.json
python3 scripts/lang_alternates.py --urls urls.txt --region-codes iso3166.txt --out hreflang.json
python3 scripts/lang_alternates.py --from-crawl ./crawl --sitemap https://example.com/sitemap.xml
python3 scripts/lang_alternates.py --from-crawl ./crawl --offline
```

- **Input**: `--sitemap` (index and gzip handled; `xhtml:link` read), `--urls` (file or
  comma-separated), `--from-crawl <dir>` (reuse a seokit crawl; `--offline` fetches nothing),
  `--max` (pages fetched, annotated targets included; default 200, heuristic).
- **Reads**: `<link rel="alternate" hreflang>`, `Link:` headers (alternate and canonical),
  sitemap `xhtml:link`; `<html lang>`, canonical, meta robots, `X-Robots-Tag`, status and
  redirects of every annotated URL it could fetch. A crawl keeps no sitemap alternates: add
  `--sitemap` to compare them.
- **Checks**: H01–H12 of `references/hreflang-checks.md`. H03 checks the format only
  (`ll` or `ll-RR`, `x-default`; script subtags reported as info); membership in ISO 639-1 /
  ISO 3166-1 is checked only with user-supplied lists `--language-codes <file>` /
  `--region-codes <file>` (one code per line): no list is bundled. H02 only when the target
  was read (others in `reciprocity_not_checked`). H10 against `<html lang>` only. H12: deep
  pages pointing to a language home (warning) and `missing_languages_by_cluster` (data).
- **Output** (JSON): `summary` (pages, clusters, errors, warnings, info), `findings` (ID,
  severity, URL, literal annotations per source), `clusters`, `code_inventory_text`,
  `not_read`, `notes`, `limits`.
- **Cannot**: know whether a search engine used an annotation.

## untranslated_text.py

```
python3 scripts/untranslated_text.py --pairs pairs.csv --out overlap.json
python3 scripts/untranslated_text.py --from-hreflang hreflang.json --max-pairs 100 --format csv --out overlap.csv
python3 scripts/untranslated_text.py --from-crawl ./crawl --offline
```

- **Input**: `--pairs` (CSV/XLSX, first two columns `url_a,url_b`, header optional),
  `--from-hreflang` (JSON of lang_alternates.py: every pair inside each cluster), or
  `--from-crawl <dir>` (page text read from the crawl; without the two others, pairs come
  from the crawled pages' hreflang tags; `--offline` fetches nothing). `--max-pairs`
  (default 100).
- **Method**: main text = headings and text blocks of the static HTML, menu/footer link
  labels dropped; sentences under `--min-words` (5) ignored; identical sentence share in each
  direction and word `--shingle-size` (8) n-gram overlap (seokit.text). Flag at
  `--threshold` (0.5). All heuristic, to calibrate.
- **Output**: JSON (default) or `--format csv`: pair, declared language and `<html lang>`,
  shares (`measured`), verdict (`largely identical: likely untranslated`, `some identical
  sentences`, `text differs`, `not measurable: too little main text`, or `not read`), up to
  5 identical sentences quoted.
- **Does not**: rate translation quality; a low overlap only means the text differs.
  Regional variants of one language are expected to share text (noted on the pair).
