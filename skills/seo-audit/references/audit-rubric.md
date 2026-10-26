# Audit rubric

Everything in this file (areas, check list, severities, weights, thresholds, score formula)
is a **heuristic, design choice of this skill, to calibrate** on real crawls. It is not a
Google rule. Where a check depends on an external standard, the source is named: re-read it
and date the reading before quoting it as a requirement.

## Check statuses

Each check ends a run in exactly one status:

| Status | Meaning | Counts in score |
|---|---|---|
| `pass` | Measured, no affected page | yes |
| `fail` | Measured, at least one affected page (after false positives are removed) | yes |
| `not-measured` | Could not be measured (no sitemap to compare, page not read, JS-rendered, crawl stopped…) | no, listed with the reason |
| `not-applicable` | Does not apply (e.g. no `www` host exists) | no, not counted in coverage either |

## Areas and checks

Severity: `high` (can keep pages out of search or break them for users), `medium`
(degrades how pages are read or shown), `low` (polish).

### A. Hosts and redirects

| ID | Check | Severity | Evidence to record |
|---|---|---|---|
| HOST-HTTPS | `http://` versions redirect to `https://` | high | Request URL, status, `Location` header |
| HOST-CANON | Only one host answers 200 (`www` or apex); the other redirects | high | Both hosts, statuses, `Location` |
| HOST-PERM | Host and protocol redirects are permanent (301 or 308), not temporary (302 or 307) | high | Status code of each hop |
| HOST-CHAIN | No redirect chain longer than one hop on host/protocol normalisation | medium | Full hop list |

Status-code meanings: RFC 9110 (HTTP Semantics), sections on 3xx codes.

### B. Crawl access

| ID | Check | Severity | Evidence to record |
|---|---|---|---|
| ROBOTS-FETCH | `/robots.txt` answers 200 with text, or 404 (no restrictions) — not 5xx or an HTML page | high | Status, content type, first lines |
| ROBOTS-BLOCK | No important section disallowed for all crawlers by accident | high | The literal `Disallow` line and the user-agent group it sits in |
| SITEMAP-FOUND | A sitemap is declared in robots.txt or answers at `/sitemap.xml` | low | URLs tried and their statuses |
| SITEMAP-VALID | Sitemap parses as XML and lists absolute URLs on the audited host | medium | Parse error or offending entries |
| SITEMAP-CLEAN | Sitemap URLs answer 200, are not noindex and are their own canonical | medium | Offending URLs with status / directive / canonical |

Format reference: sitemaps.org protocol; robots.txt: RFC 9309. Verify before quoting limits.

### C. Status codes

| ID | Check | Severity | Evidence to record |
|---|---|---|---|
| STATUS-5XX | No crawled URL answers 5xx | high | URL, status |
| STATUS-4XX | No internally linked URL answers 4xx | high | URL, status, one linking page |
| STATUS-SOFT404 | No 200 page that reads as an error page ("not found" text, near-empty body); noindex pages are not checked (they cannot be indexed) | medium | URL + literal error string |

### D. Indexability directives

| ID | Check | Severity | Evidence to record |
|---|---|---|---|
| NOINDEX-UNEXPECTED | No page meant for search carries `noindex` (meta robots or `X-Robots-Tag` header). "Meant for search" = listed in the sitemap, or the start URL; noindex pages outside the sitemap are listed for review, not failed. No sitemap read: every noindex page fails | high | The literal tag or header |
| CANON-PRESENT | Indexable pages declare a canonical | low | Pages without one |
| CANON-VALID | Canonical is absolute, answers 200, is not noindex, not redirected | high | Canonical href + its status |
| CANON-CONSISTENT | Canonical points to itself unless the page is a deliberate duplicate | medium | Page URL vs canonical href |

### E. On-page basics

| ID | Check | Severity | Evidence to record |
|---|---|---|---|
| TITLE-PRESENT | Each indexable page has one non-empty `<title>` | high | URL |
| TITLE-UNIQUE | No two indexable pages share a title | medium | Title string + URLs |
| TITLE-LENGTH | Title between 10 and 70 characters (heuristic). A suffix shared by half the titles (" - Brand") is named, with the pages too long only because of it | low | Title + length |
| META-DESC | Meta description present and unique | low | URL or duplicated string |
| H1-ONE | Exactly one non-empty `<h1>` | medium | Count found |
| HN-ORDER | No heading level skipped downwards (h2 → h4) in the main content | low | The heading sequence |
| LANG-ATTR | `<html lang>` present | low | URL |

### F. Sharing metadata

| ID | Check | Severity | Evidence to record |
|---|---|---|---|
| OG-BASIC | `og:title`, `og:description`, `og:image` present | low | Missing properties per page |
| OG-IMAGE-OK | `og:image` is absolute and answers 200 | low | Image URL + status |
| TWITTER-CARD | `twitter:card` present | low | URL |

References: ogp.me; X developer documentation for cards. Verify the property list before use.

### G. Images

| ID | Check | Severity | Evidence to record |
|---|---|---|---|
| IMG-ALT | Content images have an `alt` attribute (empty `alt=""` is valid for decorative images) | medium | `src` + page URL |
| IMG-BROKEN | Images on crawled pages answer 200 (sampled, max 50 requests, heuristic) | medium | `src`, status |

### H. Links and architecture

| ID | Check | Severity | Evidence to record |
|---|---|---|---|
| LINK-BROKEN | No internal link to a 4xx/5xx URL | high | From URL, to URL, anchor, status |
| LINK-REDIRECT | Internal links point to final URLs, not to redirects. The note counts distinct targets and names one linked from most pages (a template link) | low | From, to, final URL |
| DEPTH | Indexable pages reachable within 3 clicks of the home page (heuristic) | medium | URL + depth |
| ORPHAN | Every sitemap URL receives at least one internal link from crawled pages | medium | URL (needs a sitemap; else `not-measured`) |

Depth and orphan counts are limited to the crawled set: on a capped or sampled crawl, say
that a page may be linked from a page that was not crawled.

## Score

Weights: `high` = 3, `medium` = 2, `low` = 1.

1. **Check score** (0 to 1):
   - site-level checks (HOST-*, ROBOTS-*, SITEMAP-FOUND, SITEMAP-VALID): 1 if `pass`, 0 if `fail`;
   - page-level checks: `1 − affected / checked`, where `checked` is the number of pages the
     check could be run on.
2. **Area score** (0 to 100) = `100 × Σ(weight × check score) / Σ(weight)` over the area's
   `pass` and `fail` checks only.
3. **Overall score** = the same weighted mean over all measured checks of all areas.
4. **Cap**: if any check is `fail`, the displayed score is at most 99, even when rounding would
   give 100. A score of 100 is only possible when every measured check passed.
5. Round to one decimal. Always print it as `score (estimated, method: this rubric)`.

## Share of the rubric measured (coverage)

- **Coverage** = `Σ(weight of measured checks) / Σ(weight of applicable checks)`, as a percentage,
  overall and per area. `not-applicable` checks are removed from both sides.
- Print it next to every score: "84.0/100 — 72 % of the rubric measured".
- Below 60 % coverage (heuristic), the summary says the score is partial and lists the
  biggest unmeasured checks first.

## Merging and false positives

- Findings with the same cause (one template, one server rule, one plugin) become one fix;
  the CSV keeps one row per check with a shared `cause_group`.
- A finding is dropped as a false positive only after opening at least one example and
  writing why (e.g. "noindex is on /cart, intended"). Dropped findings stay in `issues.csv`
  with `status = dropped` and do not count as `fail`.
