# Manual route (no code execution or no web access from Python)

Use when `scripts/indexing_causes.py` or `scripts/indexnow_ping.py` is missing or code execution
is off. Say in the report that the manual route was used and on how many URLs.

## What to ask the user to export

In Search Console, **Indexing → Pages** (verify the menu names in the live, localised
interface before quoting them):

1. Keep "All known pages", or filter on one submitted sitemap for the submitted ratio.
2. Use **Export** and send the CSV or ZIP as downloaded.
3. For each status worth examining, open it and export its example URLs.

A screenshot can show the totals but not the URLs: it gives a ratio (`reported`), not a
diagnosis.

## Sorting by hand, 5 URLs per status

For each URL:

1. Fetch it and note the status and any redirect hops.
2. In the HTML: `<meta name="robots">`, `<link rel="canonical">`, `<title>`, body length.
3. Headers if the fetch tool shows them (`X-Robots-Tag`); otherwise mark `not-measured`.
4. Find the `Disallow` line in robots.txt that matches the path, if any.
5. Check whether the URL is in the sitemap and whether a hub page links to it.

Ask the user to run **URL Inspection** on one or two URLs per group and to paste the
result (Google-selected canonical, last crawl date): `reported`.

## Acceleration by hand

- Resubmit the sitemap in Search Console after fixes.
- Request indexing for a handful of key URLs with URL Inspection (the user does it).
- IndexNow without the script: follow the official IndexNow documentation (read it, date
  it), host the key file, and send one test URL first. Explain each step; the user sends.

Bing (Bing Webmaster Guidelines, pasted by the user on 2026-10-25): notify IndexNow when URLs are
added, updated or removed; "Avoid batch submissions when possible. Streaming submissions provide
faster updates"; sitemaps list "only canonical URLs" with accurate `lastmod`; a removed page
returns 404; 302 "only for very short-term changes (less than 2 days)".
