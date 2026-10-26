# Fact classes and check cadences

Each perishable fact gets one class. The cadence is how long a verified value is trusted
before it must be checked again. **All cadences below are heuristic, design choices of this
skill, to calibrate** on the user's market and history. The user can override any of them;
record the override in the register's `notes` column.

| Class | What it catches | Examples of signals | Default cadence | Default risk |
|---|---|---|---|---|
| `price` | Prices, fees, discounts, currency amounts | currency symbol or code next to a number, "per month", "/yr" | 30 days | high |
| `plan-limit` | Quotas, seats, storage, free-tier limits | number + unit near a plan name | 60 days | high |
| `version` | Software, API, model or standard versions | `v2.3`, "version 14", "iOS 18" | 60 days | medium |
| `terms` | Legal and commercial terms: refunds, trials, warranties, shipping, eligibility | "days", "refund", "trial", "within" | 90 days | high |
| `count` | Counts that grow or shrink: users, stars, integrations, team size | number + "users", "customers", "+", "over" | 90 days | medium |
| `stat` | Third-party statistics and survey figures | "%", "according to", a cited study | 180 days | medium |
| `year-in-title` | A year in `<title>`, H1 or URL slug | four-digit year in title/H1/slug | at the year change, then 365 days | medium |
| `event` | Dated events, deadlines, offers ending | "until", "ends", "on {date}", a full date | the event date itself | high once passed |
| `person-role` | Named people with a role or employer | name + title | 180 days | low |
| `other` | Anything perishable not above | — | 90 days | low |

## Rules

- A fact belongs to one class; when two fit, take the shorter cadence.
- The **date it rests on** is, in order of preference: the date the fact was last verified at
  its source (from the register), the page's visible "updated" date, the structured data
  `dateModified`, the sitemap `lastmod`. Record which one was used (`date_basis` column).
  Without any of these, the fact has no date (`no-date`).
- Risk is raised one level when the fact appears on a page that sells, collects leads or gives
  instructions the reader follows step by step.
- Detection by pattern is a first pass. Claude reads each flagged sentence and drops false
  positives (a phone number, a postcode, a product name containing digits) before the register.

## Dedupe key

`entity + attribute + value`, normalised: lower case, spaces collapsed, currency and units
kept. "Pro plan / monthly price / 19 €" on the pricing page and in three blog posts is **one**
row listing four pages. The same entity and attribute with two different values on two pages
is a contradiction: keep both rows and re-check both values at the source (page mode, steps 3 to 5).
