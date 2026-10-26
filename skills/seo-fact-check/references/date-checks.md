# Date-consistency checks

For each scanned page, collect up to three dates and compare them.

| Source | Where to read it |
|---|---|
| Visible date | The "published" / "updated" text a reader sees (byline, footer, top of article) |
| Structured data | JSON-LD date properties on the page (for example `datePublished`, `dateModified`) |
| Sitemap | The `<lastmod>` of the URL in the XML sitemap |

Property names and how search engines use them: **verify against the official documentation
(schema.org and the search engine's structured data guide) at run time, and date the reading**.
Do not tell the user how an engine weighs these dates unless that reading says so.

## Findings

| Finding | Condition (heuristic thresholds, design choice of this skill, to calibrate) | Severity |
|---|---|---|
| Visible vs structured data disagree | The two "updated" dates differ by more than 2 days | medium |
| Visible vs `lastmod` disagree | `lastmod` differs from the visible updated date by more than 7 days | low |
| Unreliable `lastmod` | More than 80 % of sitemap URLs share the same `lastmod` day, or `lastmod` equals the scan day for most URLs | medium: fall back on visible dates |
| Date moved, content unchanged | On a re-scan, a date changed while the page's fact sentences are identical (needs a previous scan) | high |
| Future date | Any of the three dates is later than the scan date | medium |
| Event passed | An event date in the text is past while the wording presents it as upcoming ("ends on", "until", "join us on") | high |
| Year in title behind | The year in title/H1/slug is earlier than the current year and the page is not explicitly about that year | medium |
| Year in title ahead of content | The title carries the current year but every dated fact on the page is older | high |

## Rules

- Report the three dates side by side with their source, `measured`.
- Never fix a disagreement by moving the newest date onto the others. Fix the date that is
  wrong, and only move a date forward when the content changed on that day.
