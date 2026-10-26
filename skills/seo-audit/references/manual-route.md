# Manual route (no code execution or no web access from Python)

Use when `scripts/site_crawl.py` is missing, code execution is off, or Python has no
outbound web access. Say in the report that the manual route was used and on how many pages.

## Choose 10 to 15 pages by template

One or two pages per template, not the first 15 links: home, a main category or hub, two
articles or product pages (one old, one recent), a tag or archive page, a paginated page,
the contact or about page, a page from each language if the site has several, and any page
the user named. List them in the report.

## What to check by hand

| Area | How |
|---|---|
| Hosts and redirects | Fetch `http://host/`, `http://www.host/`, `https://host/`, `https://www.host/` and note each status and `Location`. A fetch tool that follows redirects silently cannot measure HOST-PERM: mark it `not-measured` |
| Crawl access | Read `/robots.txt` and the sitemap(s) it declares; open 10 sitemap URLs and note statuses |
| Status codes | Status of each sampled page and of every internal link on two hub pages |
| Directives | In each page's HTML: `<meta name="robots">`, `<link rel="canonical">`. Headers (`X-Robots-Tag`) only if the fetch tool shows headers; otherwise `not-measured` |
| On-page | `<title>`, meta description, `<h1>` count, heading sequence, `<html lang>` |
| Sharing | `og:*` and `twitter:*` meta tags |
| Images | `alt` attributes on content images |
| Architecture | Depth: count clicks from the home page to each sampled page. Orphans: compare 20 sitemap URLs with the links found on hub pages; result is `estimated` |

## What the manual route cannot measure

- Site-wide counts (duplicate titles across the whole site, all broken links, true orphans):
  report them as `estimated` from the sample, never as site totals.
- Anything written by JavaScript, unless the user checks it in a browser and reports it
  (`reported`).

Apply the same rubric; the coverage figure will be lower, and that is the honest result.
