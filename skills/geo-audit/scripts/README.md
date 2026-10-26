# Scripts

Python 3.9+ standard library only, read-only, nothing to install. Shared code in `seokit/`
(do not edit the copy). Network: GET only, this tool's own identifiable user agent (never a
vendor's), about 2 requests per second (`--delay`), robots.txt respected, timeouts, size cap
(`--max-bytes`). A 401/403/429 stops the run without workaround (exit 3). Exit 2 on bad
input. Site text in the output is quoted data (`*_quote` fields).

## ai_access.py

```
python3 scripts/ai_access.py --site https://example.com/ --out access.json
python3 scripts/ai_access.py --site https://example.com/ --urls key-pages.txt --sample 15 --out access.json
python3 scripts/ai_access.py --site https://example.com/ --robots-file ./public/robots.txt --no-pages
```

- **Sample**: the home page, the URLs of `--urls`, then sitemap URLs spread evenly, up to
  `--sample` (default 10, heuristic).
- **robots.txt per agent**: for each token of `references/ai-agents.md` (vendor, role), the
  RFC 9309 decision on every sampled URL: `allowed`, `partially disallowed`, `disallowed`,
  the group used (its own or `*`) and the deciding `Disallow` line quoted. `finding` is true
  only for a blocked **search** agent; training opt-outs are reported, not judged.
- **Per page**: status, `noindex`, `nosnippet`, `noarchive` and `nocache` (Bing: Copilot use), `max-snippet` (meta robots or `X-Robots-Tag`),
  count of `data-nosnippet` elements, static word count and `little_static_text` (under 150
  words), canonical.
- **Also**: status of `/llms.txt` (information; geo-llmstxt audits it).
- **Limits**: firewall or CDN blocking is invisible; nothing is fetched with a vendor's user
  agent; JavaScript rendering by each engine is unknown.
