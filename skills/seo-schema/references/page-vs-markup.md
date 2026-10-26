# Page vs markup comparison

Compare in both directions, on the **static HTML** (raw fetch or view-source), page by page.
Finding codes and severities below are a design choice of this skill, to calibrate.
Whether a given mismatch breaks a Google rule is decided by the dated policy table, not here.

## Direction 1: markup → page (the markup claims something the page does not show)

| Code | Check | Default severity |
|---|---|---|
| M01 | JSON-LD block does not parse | error |
| M02 | FAQ question in markup absent from the visible text | error |
| M03 | FAQ answer in markup differs from the visible answer (compare phrase overlap, then read) | warning |
| M04 | FAQ answer present only in hidden or JS-loaded content (not in static HTML) | warning |
| M05 | Price or currency in markup not visible, or different from the visible one | error |
| M06 | `aggregateRating` / `review` values not visible on the page | error |
| M07 | Rating count or value differs from the visible figure | error |
| M08 | Author, publisher, dates in markup differ from the visible byline or dates | warning |
| M09 | Organization name, logo, contact or `sameAs` differ from the site footer / about page | warning |
| M10 | Markup describes another entity than the page (e.g. product markup on a category page) | warning |

## Direction 2: page → markup (the page shows something the markup gets wrong or omits)

| Code | Check | Default severity |
|---|---|---|
| P01 | Visible FAQ has more or different questions than the markup | info |
| P02 | Visible price, availability or currency changed, markup still old | error |
| P03 | Visible updated date newer than `dateModified` (or the reverse) | info |
| P04 | Main entity of the page has no markup while siblings of the same template do | info |
| P05 | Same entity marked up twice with conflicting values (plugin + theme) | warning |

## How to compare

1. Normalise both texts: decode entities, collapse whitespace, lowercase, strip tags.
2. For prices: compare amount and currency separately; note tax wording if visible.
3. For FAQ answers: compute word n-gram overlap as a pointer only, then read both texts.
   A low overlap is a lead, not a finding, until read.
4. Record the literal evidence: the markup value in quotes and the visible string in quotes,
   or "absent from static HTML".
5. A page that fails to fetch, needs JavaScript, or returns a challenge page is "not read".

## Ratings and reviews

The skill can only check that figures are visible and consistent. It always asks where the
ratings come from (own collection, third-party widget, imported) and records the answer as
`reported`. It never proposes a rating value.
