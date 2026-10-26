# Scripts

## site_crawl.py

Polite crawl, then every check of `references/audit-rubric.md` a crawl can measure, with the
per-area score and the share of the rubric measured computed as the rubric defines them.
Python 3.9+ standard library only, `seokit` for fetching, parsing and output.

```
python3 scripts/site_crawl.py --url https://example.com --max-pages 300 --out audit/
python3 scripts/site_crawl.py --url https://example.com --sample --max-pages 300 --out audit/
python3 scripts/site_crawl.py --url https://example.com --sections /blog /docs --out audit/
python3 scripts/site_crawl.py --url https://competitor.example --light --out comp/
python3 scripts/site_crawl.py --from-crawl audit/crawl --out audit2/ [--offline]
```

- **Options**: `--max-pages` (default 300), `--rate` (requests/s, default 2, capped at 2),
  `--sample` (spread the cap across sitemap sections; click depth then unknown),
  `--sections PREFIX...` (sitemap URLs and links under these paths, in full), `--light`
  (third-party site: cap 50, no image or og:image requests), `--from-crawl <dir>` (reuse a
  crawl, e.g. the one seo-internal-links made), `--offline` (with `--from-crawl`: no request,
  host and robots checks become `not-measured`), `--max-depth 3`, `--title-min 10`,
  `--title-max 70` (heuristics, to calibrate), `--user-agent --timeout --max-bytes`,
  `--allow-private` (local or staging site only; private and local addresses are refused otherwise).
- **Network**: GET only via `seokit.fetch` (robots.txt honoured, timeouts, size cap, TLS
  verified). Besides the crawl: the four http/https x www/apex home variants (redirects read
  hop by hop: 301/308 vs 302/307), `/robots.txt`, sitemaps, at most 30 canonical targets,
  20 og:image URLs and 50 images on the audited site (off-site assets are not requested).
  On 401/403/429 the crawl stops, outputs are written, exit code 3; no retry or workaround.
- **Output** in `--out`: `crawl/` (seokit crawl directory), `issues.csv` (one row per
  rubric check, columns of `templates/issues.csv`; `status` = pass, fail, not-measured,
  not-applicable; `cause_group` left for Claude; Claude sets `status` to `dropped` for a false positive after review),
  `pages.csv` (url, final_url, status, depth, in_sitemap, title_text, canonical_url,
  robots_directives_quote, x_robots_tag_quote, inlinks, js_suspect, error), and
  `summary.json`, also printed on stdout: mode, pages read, stop reason, caps, sitemap
  info, `not_read`, `js_suspect_pages`, per-check status/affected/checked/unit/label/reason
  with up to 10 examples, `scores` (overall and per area, coverage, `partial` below 60 %,
  biggest unmeasured checks), quoted HTML comments that look like instructions, limits.
- **Limits**: raw HTML only (pages looking script-rendered are `js-suspect`, left out of
  content checks: check in a browser); NOINDEX and CANON-CONSISTENT flag every case, intent is
  for Claude to judge; HN-ORDER reads the whole page; DEPTH and ORPHAN are `estimated` on a
  capped or sampled crawl; ORPHAN needs a sitemap; no Search Console, no index data.
- Site text (titles, anchors, robots lines, comments) is quoted through `untrusted()`, never
  interpreted. Exit codes: 0 ok, 2 bad input, 3 site blocked.
