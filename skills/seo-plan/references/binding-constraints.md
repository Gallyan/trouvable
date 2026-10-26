# Binding constraints

Name **one** binding constraint per layer: the one that, if lifted, unblocks the most. Others are
noted but do not drive the order.

## Layer 1 — resources (the user)

| Constraint | Signs | Effect on the plan |
|---|---|---|
| Time | fewer than ~3 h/week, or irregular | Fewer, smaller rows; only one workstream at a time; templates and checklists over custom work |
| Money | no budget for tools, writers or developers | Free tools and manual routes only; no row depends on a paid service |
| Skills | cannot edit templates, code, or write in the target language | Rows that need the skill become "ask someone" rows with a precise brief, or are deferred |

## Layer 2 — site

Check in this order; the first that fails is usually the binding one.

| Constraint | Typical evidence | First rows |
|---|---|---|
| Access | robots.txt blocks, `noindex`, broken HTTPS, pages need JavaScript to show text | seo-audit |
| Indexing | few pages indexed vs submitted, orphan pages | seo-indexing, seo-internal-links |
| Demand fit | pages target queries nobody searches or that are unwinnable | seo-keyword-verdict |
| Content | pages exist for good queries but answer worse than page one | seo-content-brief, seo-fact-check |
| Authority | good pages indexed, little visibility, nobody mentions the site | seo-offsite, geo-mentions |

The "Effect" and order above are a design choice of this skill, not a rule published by a search
engine. Each identification is labelled `measured` (light checks), `reported` (user figures) or
`assumed` (user's words such as "nobody finds us").
