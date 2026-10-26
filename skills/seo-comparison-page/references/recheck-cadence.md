# Recheck cadence by fact volatility

Each fact in `vendor-facts.csv` gets a volatility class and a `recheck_by` date = read date + cadence.
**Cadences are heuristic, design choices of this skill, to calibrate** on the category (some
SaaS categories change prices monthly, hardware rarely).

| Volatility | Typical facts | Cadence |
|---|---|---|
| `very-high` | Promotions, launch prices, counts that grow daily (stars, installs, users), "new" features in beta | 14 days, and always shown with "as of {date}" |
| `high` | Prices, plan limits, free-tier limits | 30 days |
| `medium` | Feature availability, integrations, platforms supported, versions | 90 days |
| `low` | Company facts (founding year, headquarters), licence type, data location statements | 180 days |
| `event` | Anything with an end date ("until", "ends on") | the end date itself |

## `vendor-facts.csv` status values

`verified` (literal string read at the source on `read_on`), `changed` (source now differs;
old and new kept), `pending-owner` (own-product fact awaiting the user's confirmation),
`contradicted` (sources disagree; see `contradicts`), `not-read` (source unreadable on the
last attempt). The `label` column carries `measured` or `reported` (ground rule 3).

## Rules

- On recheck, re-read the source and compare the literal string. Same string → update
  `read_on` and `recheck_by`. Different → status `changed`, patch the page, log old and new.
- The page's visible "checked on" date changes only when the facts it covers were re-read.
- A source that cannot be read on recheck is `not-read`; the old value stays, flagged, and
  gate 12 goes `PENDING`.
- `compare_facts.py` (or the manual sort) lists facts past `recheck_by`; `publish-checks.md` gives the
  next three recheck dates.
