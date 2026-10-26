# seokit API (frozen for script authors)

Python 3.9+, standard library only. Every module starts with `from __future__ import annotations`.
Scripts import it as `from seokit import ...`: `python3 scripts/x.py` puts `scripts/` on `sys.path`,
and `tools/sync_lib.py` copies this package to `skills/<slug>/scripts/seokit/`.

## seokit.fetch
- `Fetcher(user_agent=DEFAULT_USER_AGENT, delay=0.5, timeout=15, max_bytes=5_000_000, respect_robots=True, allow_private=None)`
  - `allow_private=None`: decided by the first URL requested; a public first URL makes every later
    private/local address (links, hreflang, sitemap entries, redirects) refused.
  - `.get(url, follow=True, check_robots=True) -> Response` — GET only, never raises; records every
    redirect hop; refuses URLs disallowed by robots.txt (`status=None`, `error="blocked by robots.txt"`).
    Only http/https, on every hop; a public start URL may not redirect to a private/local address.
  - `.allowed(url) -> bool`, `.robots_for(url) -> RobotFileParser | None`, `.robots_text(url) -> str`
- `Response`: `url, final_url, status (int|None), headers (lowercase keys), body (bytes, capped), truncated,
  chain (list[Hop(url, status, location)]), error, elapsed`; `.ok`, `.content_type`, `.is_html`, `.text()`, `.to_dict()`
- `BLOCKING_STATUSES = (401, 403, 429)` — stop, never work around.
- `normalize_url(url)` (drops fragment, lowercases scheme/host), `same_site(a, b)` (ignores `www.`),
  `decode_body(bytes, content_type)`
- `add_fetch_arguments(argparse_parser)` adds `--user-agent --delay --timeout --max-bytes`;
  `fetcher_from_args(args) -> Fetcher`

## seokit.html
- `parse_html(html, base_url) -> Page` — static HTML only, never raises.
- `Page`: `lang, title, titles (all <title>), meta {name|property|http-equiv lowercased: [values]}, canonicals,
  alternates [(hreflang, url)], headings [(tag, text)], links [Link], images [Image(src, alt|None)],
  jsonld [raw strings], blocks [text of p/li/td… blocks], text (visible text), html_comments,
  content_blocks, content_text` (same without code blocks — `<pre>`, or `<code>` outside a p/li/td block — and
  without header/nav/footer/widget zones; inline code in a paragraph stays), content_loose` (content text
  outside headings and blocks, cut at div/section/list/table/br… boundaries: one run per bare <div> text),
  main_content_text` (content text inside <main>/<article>/role=main, empty when the page has none),
  `content_headings` (headings outside header/nav/footer/widget zones);
  properties `description, robots (meta robots + googlebot, lowercased), canonical, word_count`; `meta_first(name)`.
- `Link`: `href (raw), url (absolute), text, rel, hreflang, zone, subtype, order, block, nofollow`.
  `zone` ∈ header | nav | footer | widget | editorial | unknown (rules: seo-internal-links/references/link-zones.md);
  `subtype` for widgets: breadcrumb, pagination, related, lang-switch, tags, author, sidebar.
  `block` = index in `Page.blocks` for editorial links inside a block, else None.

## seokit.sitemap
- `discover(fetcher, site_url) -> [sitemap urls]` (robots.txt `Sitemap:` lines, else `/sitemap.xml`)
- `load(fetcher, sitemap_urls, max_urls=50000) -> SitemapResult(urls [SitemapUrl(loc, lastmod, alternates, source)], files, errors, truncated, left_out)`
- `parse_sitemap_bytes(bytes, source="") -> (kind, urls, child_sitemaps)`; gzip handled; DOCTYPE refused.

## seokit.crawl
- `crawl(start_url, fetcher, out_dir, max_pages=300, use_sitemap=True, extra_urls=None, progress=None) -> CrawlResult`
  BFS over same-site links first (so `depth` = click depth from start), then sitemap/extra URLs (`depth=None`
  unless a link reaches them). Stops on 401/403/429 on the first page or 3 in a row.
- Crawl directory: `crawl.json` (start_url, started, user_agent, max_pages, pages_fetched, queued_not_fetched,
  stop_reason, sitemap {declared, files, errors, url_count}, sitemap_urls, robots_txt),
  `pages.jsonl` (one object per fetched URL: `Response.to_dict()` + `id, depth, referrer, in_sitemap,
  sitemap_lastmod, content_type, html_path`), `html/<id>.html`.
- `crawl_listed(start, fetcher, out_dir, cap, sample, sections, sitemap_urls, sitemap_info=None, progress=None) -> meta`:
  sampled (`spread_sample` round-robin over first path segments) or section (`path_matches` prefixes) crawl
  from a `{url: lastmod}` sitemap map, same directory layout plus `mode` and `sections` in `crawl.json`.
- `crawlable(url, root)`: http(s), same site, not a static asset.
- `load_crawl(dir) -> (meta, records)`, `read_html(dir, record) -> str|None`, `iter_pages(dir)` yields `(record, html|None)`.
- Analyser scripts accept `--from-crawl <dir>` to reuse a crawl, or crawl themselves.

## seokit.tables
- `read_tables(path)` / `read_tables_bytes(bytes, name) -> [Table(name, headers, rows, truncated)]` — CSV (sniffed
  `, ; tab`, UTF-8/UTF-16/cp1252), XLSX (zipfile + XML), ZIP of CSV/XLSX. Caps on sizes, ratio, rows. Raises `TableError`.
- `parse_number(str) -> float|None` — thousands separators, decimal comma, `%` → ratio 0–1.

## seokit.gsc
- `detect(Table) -> GscTable(name, kind (query|page|date|query-or-other|unknown), key, columns {clicks, impressions, ctr, position}, rows [{key, clicks, impressions, ctr, position}], notes)`.
  English headers first, then content-based detection. Never add translated headers from memory.

## seokit.text
- `normalize(text, casefold=True)`, `find_literal(haystack, needle, context=80) -> [Match(start, context)]`,
  `sentences(text)`, `shingles(text, size=8) -> set`.

## seokit.report
- `untrusted(text, limit=300)` — use for every piece of site text put in output; `emit_json(obj)`;
  `write_csv(rows, fields, path=None)` (stdout when None or "-", spreadsheet-formula cells neutralised); `today()`.

## seokit.safexml
- `parse_xml_bytes(bytes)` — refuses DOCTYPE/ENTITY and oversize documents (`UnsafeXmlError`).

## seokit.robots

RFC 9309 matching (not `urllib.robotparser`, which applies the first matching rule in file order).

- `parse(text) -> [Group]`, a group being `(lowercased agents, [(allow|disallow, pattern, literal line)])`
- `product_token(user_agent) -> str`; `rules_for(groups, agent) -> (agents, rules)` (groups naming the agent merged, else `*`)
- `deciding_rule(groups, agent, url)` (longest pattern, Allow on ties), `disallowing_rule(groups, agent, url) -> (agents, literal) | None`,
  `allowed(groups, agent, url) -> bool`, `rule_matches(pattern, path)` (`*` and `$`), `path_of(url)`
