# Page indexing statuses → cause classes

**Verify against Google's current Page indexing report documentation before use.** The
English labels below were checked against https://support.google.com/webmasters/answer/7440203
on 2026-10-24 (copied character for character: ASCII hyphens, curly quotes in
`URL marked ‘noindex’`); Google renames, merges and adds statuses. At run time, open the official Search Console Help page
for the Page indexing report, compare its list with this table, note the date of the
reading and any difference in the report. Exports in other interface languages carry
translated labels: map them from the export file itself (and from real export fixtures in
the script), never from a translation made from memory.

The cause classes and the confidence rules are a **heuristic, design choice of this skill,
to calibrate**.

## Cause classes

| Class | Meaning | What can be tested from outside | Usual owner of the fix |
|---|---|---|---|
| `ACCESS` | The crawler could not fetch the page (server error, robots.txt, authentication, forbidden) | Status code, robots.txt line, auth wall | Hosting, robots.txt |
| `DIRECTIVE` | The site asked not to index (noindex, removal request) | Meta robots, `X-Robots-Tag` header | Template, CMS setting, SEO plugin |
| `STATUS` | The URL does not return a usable 200 page (404, soft 404, redirect error) | Status chain, page body | Routes, redirects, templates |
| `CANONICAL` | Another URL was chosen or declared as the canonical | Canonical href, duplicates, parameters | Templates, URL parameters, internal links |
| `EXPECTED` | Exclusion that is normally fine (a redirect source, an alternate with a proper canonical) | Confirm it is intended and not in the sitemap | Usually none; clean the sitemap |
| `DISCOVERY` | Known URL, not crawled yet: crawl demand or discovery is weak | Inlinks, sitemap membership, site age, server speed | Internal links, sitemap, third-party mentions |
| `SELECTION` | Crawled, not indexed: no technical block found | Technical causes can be **ruled out**, never confirmed as the reason | Content value, duplication, internal links |
| `TOO-EARLY` | Page younger than the age gate (21 days, heuristic) | Publication date | None yet: re-measure later |

## Status → class (English labels, read on Google's Help page on 2026-10-24)

| Status label (EN, as written on the Help page) | Class | Evidence indexing_causes.py records |
|---|---|---|
| Server error (5xx) | `ACCESS` | Status code now; note that it may have been transient |
| Blocked due to unauthorized request (401) | `ACCESS` | Status, `WWW-Authenticate` header |
| Blocked due to access forbidden (403) | `ACCESS` | Status, server or WAF signature in headers |
| URL blocked by robots.txt | `ACCESS` | The literal `Disallow` line and its user-agent group |
| URL marked ‘noindex’ | `DIRECTIVE` | Literal meta tag or header |
| Excluded by 'noindex' tag | `DIRECTIVE` | Older name of the row above, still found in older exports |
| Blocked by page removal tool | `DIRECTIVE` | Older label, no longer on the Help page (2026-10-24); not testable from outside, ask the user to check Removals |
| Not found (404) | `STATUS` | Status; whether the URL is linked or in the sitemap |
| URL blocked due to other 4xx issue | `STATUS` | Status code |
| Soft 404 | `STATUS` | Body length, literal error text |
| Redirect error | `STATUS` | Hop list (loop, too long, bad target) |
| Page with redirect | `EXPECTED` | Hop list; flag only if the URL is in the sitemap or linked internally |
| Alternate page with proper canonical tag | `EXPECTED` | Canonical href; flag only if the user wants this URL indexed |
| Duplicate without user-selected canonical | `CANONICAL` | Absence of canonical, near-duplicate URLs |
| Duplicate, Google chose different canonical than user | `CANONICAL` | Declared canonical vs the one shown by URL Inspection (`reported`) |
| Discovered - currently not indexed | `DISCOVERY` | Inlinks, sitemap membership, response time |
| Crawled - currently not indexed | `SELECTION` | Word count, duplicate title or content, inlinks |
| Indexed, though blocked by robots.txt | `ACCESS` (warning) | The `Disallow` line |
| Page indexed without content | `ACCESS` / `STATUS` | Raw HTML body size, JavaScript dependence |

## Status → class (French labels, read on real exports)

Labels copied from two real French-interface Page indexing exports (XLSX, downloaded
2026-10-21). The English equivalent is matched by meaning; re-check both against Google's
documentation like the English table.

| Status label (FR, as read in the export) | Class | English equivalent |
|---|---|---|
| Bloquée par le fichier robots.txt | `ACCESS` | URL blocked by robots.txt |
| Exclue par la balise "noindex" | `DIRECTIVE` | Excluded by 'noindex' tag |
| Introuvable (404) | `STATUS` | Not found (404) |
| Erreur liée à des redirections | `STATUS` | Redirect error |
| Page avec redirection | `EXPECTED` | Page with redirect |
| Autre page avec balise canonique correcte | `EXPECTED` | Alternate page with proper canonical tag |
| Page en double sans URL canonique sélectionnée par l'utilisateur | `CANONICAL` | Duplicate without user-selected canonical |
| Détectée, actuellement non indexée | `DISCOVERY` | Discovered - currently not indexed |
| Explorée, actuellement non indexée | `SELECTION` | Crawled - currently not indexed |

The chart sheet of the same French exports names its columns `Non indexées` and
`Dans l'index`.

Any label in the export that is not in this table: keep it as `UNMAPPED`, quote it, and
classify it by reading Google's documentation for it (dated).

## Confidence

| Level | When |
|---|---|
| `high` | A literal piece of evidence explains the status on most sampled URLs (e.g. the noindex tag is there) |
| `medium` | Evidence on some sampled URLs, or the cause fits but could have changed since Google's crawl |
| `low` | No technical evidence; the class comes from the label alone (`DISCOVERY`, `SELECTION`) |

## Age gate

- Rule: URLs first published fewer than 21 days before the reading are `TOO-EARLY`
  (heuristic, design choice of this skill, to calibrate).
- Age sources, in order of trust: user-provided publication dates (`reported`), dates visible
  on the page or in its structured data (`measured`), first appearance in a previous export
  (`reported`). Sitemap `lastmod` is used only as an `assumed` age, and never when all values
  are identical or when most share one date.
