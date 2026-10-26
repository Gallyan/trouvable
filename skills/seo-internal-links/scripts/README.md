# Scripts

## internal_links.py

Polite crawl and internal link graph, zones per `references/link-zones.md` (via
`seokit.html` `Link.zone` / `Link.subtype`). Python 3.9+ standard library only.

```
python3 scripts/internal_links.py --url https://example.com --sitemap https://example.com/sitemap.xml \
    --max-pages 300 --out links/
python3 scripts/internal_links.py --url https://example.com --sample --section /blog --out links/
python3 scripts/internal_links.py --from-crawl links/crawl --offline --target https://example.com/new-post \
    --mentions "internal linking,maillage interne" --out links-new/
python3 scripts/internal_links.py --url https://example.com --compare links/ --target https://example.com/new-post \
    --out links-after/
```

- **Options**: `--sitemap` (URL, local XML file or text file of URLs; default robots.txt
  `Sitemap:` lines, else `/sitemap.xml`; needed for orphans), `--max-pages` (default 300),
  `--rate` (default 2, capped at 2), `--sample` (spread the cap across sitemap sections),
  `--section PREFIX` (repeatable: crawl that path in full), `--target URL` (repeatable:
  inlinks by zone, editorial sources and rank of that page), `--mentions "a,b"` (needs
  `--target`: pages whose paragraph/list text contains a term as whole words and that do
  not link to the target yet, sorted by internal rank), `--compare <previous out dir>`
  (before/after metrics), `--from-crawl <dir>`, `--offline`, thresholds `--max-depth 3`,
  `--hub-max-links 150`, `--hub-max-editorial 50`, `--unknown-max 0.10` (heuristics, to
  calibrate), `--user-agent --timeout --max-bytes`, `--allow-private` (local or staging site only).
- **Network**: GET only via `seokit.fetch`, same site, robots.txt honoured, timeouts, size
  cap. Stops on 401/403/429 (outputs written, exit 3), no workaround.
- **Output** in `--out`: `crawl/`, `edges.csv` (from, to, zone, subtype, anchor_text,
  anchor_from_image_alt, position, paragraph, rel, hreflang, target_status = first answer,
  3xx for a redirect, target_final_url, target_final_status), `pages.csv` (url, status, depth,
  title_text, h1_text, lang, in_sitemap, inlinks and outlinks per zone, totals,
  internal_rank), `summary.json` (also on stdout): share by zone, unknown share, orphans,
  navigation-only, language-switch-only, weakly linked, overloaded hubs, broken and
  redirected links, deep pages, internal rank (top 20, 1.0 = average page), three
  `self_check_pages` (home + two other templates, counts and examples per zone, agreement
  to record), `targets`, `mentions`, `metrics`, `not_read`, `warnings`, limits; with
  `--compare`, `before_after` in the summary and `before_after.csv`.
- **Limits**: raw HTML only (JavaScript links absent); inlinks count distinct linking
  pages; orphans "not measurable" without a sitemap or URL list; orphans and weak links
  labelled `estimated` on a capped or sampled crawl; click depth unknown on sampled or
  section crawls; mentions search all paragraph/list blocks except bare menu/footer items,
  so check a match is in the body; the rank weight of `unknown` links (0.3) is this
  script's choice, not in the reference.
- Anchors, titles and quotes go through `untrusted()` and CSV cells are formula-neutralised.
  Exit codes: 0 ok, 2 bad input (bad URL, unreadable sitemap file, malformed `--compare`
  summary), 3 site blocked.
