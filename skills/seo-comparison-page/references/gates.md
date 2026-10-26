# Gate 0 and the twelve gates

The gate list and the blocking rule are a **heuristic, design choice of this skill, to
calibrate**. They encode the skill's honesty rules; they are not a search engine requirement.

## Gate 0 — is the page worth writing?

Inputs: a seo-keyword-verdict result if one exists, otherwise about three searches for the
query and close forms (tool, region, day noted).

| seo-keyword-verdict result, or own reading | Gate 0 | Effect |
|---|---|---|
| `WRITE` | `GO` | Page type as page one suggests |
| `WRITE A NARROWER PAGE` | `NARROW SCOPE` | One page, narrower: a situation, a segment, two products instead of ten |
| `EXTEND AN EXISTING PAGE` | `NARROW SCOPE` | Add a comparison section to the named page instead of a new URL |
| `DROP` | `STOP` | No page; say why and what would change it |
| `WAIT` | `STOP` | Give the date or event to wait for |

Also `STOP` when the only way to win would be a page per product pair generated in bulk.

## The twelve gates

Each gate is `PASS`, `FAIL` or `PENDING` (cannot be decided yet: missing input, source not
read, user confirmation awaited). Each result cites its evidence (vendor-facts.csv ids, draft line).

| # | Gate | PASS when | Blocking |
|---|---|---|---|
| 1 | Sourced facts | Every price, limit, requirement and figure in the draft has a `vendor-facts.csv` row with literal string, URL and read date | yes |
| 2 | Primary sources | Each fact comes from the vendor's own page or official doc; third-party sources only for third-party facts (ratings, counts), with their date | yes |
| 3 | Own-product facts confirmed | Every fact about the user's product is confirmed by the user (`reported`); none filled by Claude | yes |
| 4 | Disclosure | Commercial ties ("I make this", affiliate links) disclosed before the first mention and near each affiliate link; a vendor's own page states plainly that it is written by an interested party | yes |
| 5 | No invented evidence | No made-up rating, review, testimonial, benchmark or quote; any benchmark states method, date, and versions | yes |
| 6 | Superlatives checked | Each "best/cheapest/fastest/only/most" is backed by that attribute read for each compared product, or removed | no |
| 7 | Conditional verdict | The verdict depends on situations; a decision table maps situations to products | no |
| 8 | Same standard | The same attributes are shown for every product; a value the vendor does not publish is written "not published by the vendor", not guessed | no |
| 9 | Contradictions shown | Where sources disagree, the values, sources and dates are listed and the one kept is justified | no |
| 10 | Own product placement | The user's product is last, limits first | no |
| 11 | Panel fairness | Inclusion criteria are stated; alternatives prominent on page one are included or their exclusion explained | no |
| 12 | Freshness | No fact is past its recheck date; the page shows when facts were checked; visible dates moved only after re-verification | no |

## Publication rule

- Any `FAIL` or `PENDING` on a blocking gate (1–5): do not publish.
- Non-blocking `FAIL`: fix before publication or state the reason in `publish-checks.md`.
- Non-blocking `PENDING`: allowed, listed with what would close it and by when.
