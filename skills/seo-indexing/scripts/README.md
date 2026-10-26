# Scripts

## indexing_causes.py

Page indexing export reader and live evidence collector. Python 3.9+ standard library.

```
python3 scripts/indexing_causes.py --export <file> [--export <file> ...] --sitemap <url|file> --sample 50 --out <dir>
    [--urls <file>] [--published <url,date csv>] [--today YYYY-MM-DD]
    [--age-days 21] [--lastmod-uniform-share 0.5] [--classes <cause-classes.md>]
    [--user-agent .. --delay 0.5 --timeout 15 --max-bytes 5000000]
```

- **Export reading** (`seokit.tables`, CSV/XLSX/ZIP with caps): tables are recognised by content
  (URL column, status column, counts, dated chart). Status labels are matched only against the
  English table of `references/cause-classes.md`, read at run time. Any other label is reported as
  `UNMAPPED` with its literal text, never translated. A URL table with no recognisable status is
  reported in `url_tables_without_status`. Repeat `--export` for per-status example exports.
- **Ratio**: from a chart table with `Indexed` / `Not indexed` (English, unverified) or `Dans l'index` / `Non indexées` (French, read on real exports) columns, `reported`;
  otherwise "not measurable".
- **Age gate**: 21 days (heuristic). Age from `--published` (reported), then `datePublished` on the
  page (measured), then sitemap `lastmod` (assumed) — ignored with a warning when more than half of
  the values share one date. Too-early URLs are not sampled nor diagnosed.
- **Network**: GET only through `seokit.fetch`, on the user's host, robots.txt respected (a
  disallowed URL is not fetched; the matching `Disallow` line is recorded as evidence), ~2 req/s.
  Stops with exit 3 on a 429, on a blocked sitemap, or on 3 consecutive 401/403 for URLs whose status
  is not an ACCESS class (401/403 on ACCESS statuses is recorded as evidence).
- **Output**: `<out>/url-evidence.csv` (one row per URL: status chain, final URL, `X-Robots-Tag`, meta
  robots literal, canonical href, robots.txt line and group, sitemap membership, lastmod, age, title,
  word count, first HTML comment quoted as data, signals, evidence verdict) and a JSON summary on
  stdout: ratio, per status (class, counts, sampled, evidence, confidence), unmapped labels, counts
  per cause class, too-early count, lastmod warning, sitemap URLs not clean 200, stop reason,
  `not_measured`.
- Exit codes: 0 ok, 2 bad input, 3 site blocks.

## indexnow_ping.py

The only script in this skill that sends anything other than a GET.

```
python3 scripts/indexnow_ping.py --key <key> --urls <file>                          # dry run, no network
python3 scripts/indexnow_ping.py --key <key> --urls <file> --send --confirm <code>  # only after the user agreed
    [--key-file <path>] [--key-location <url>] [--host <host>] [--endpoint <url>] [--timeout 15]
```

- **Default endpoint**: `https://api.indexnow.org/indexnow`, the "global endpoint" of the
  indexnow.org FAQ, re-read on 2026-10-24 with the 10,000 URLs per POST limit, the key rule
  (8–128 characters, `a-z`, `A-Z`, `0-9`, `-`; the documentation page also says "hexadecimal",
  the FAQ does not) and the response codes. Participating engines listed that day: Amazon,
  Bing, Naver, Seznam.cz, Yandex, Yep. Google was not listed. **Re-check before sending and
  date the reading.**
- **Dry run** (default): prints host, key file URL, URL count, first URLs, the exact POST body
  and a `confirmation` code (hash of that body). No network call at all.
- **Bound to the dry run**: `--send` is refused unless `--confirm` repeats that code, so what is
  sent is exactly what the user approved. The endpoint must be `https`.
- **Refuses** (exit 2, nothing sent): key not 8–128 of `[A-Za-z0-9-]`, a URL holding control or
  bidi characters, URLs on several hosts or off
  `--host`, URLs outside the key file's directory, more than 10,000 URLs, a key file that is not
  served with the key as content.
- **With `--send`**: GET of the key file, then one POST (`application/json; charset=utf-8`, no
  redirect followed). Prints status and body quoted as data. Exit 0 on 200/202, 2 on 400/422,
  3 on 403/429 (or a blocked key file), 1 otherwise.
- Never generates or stores a key.
