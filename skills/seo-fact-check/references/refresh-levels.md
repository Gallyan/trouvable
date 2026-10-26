# Ranking and refresh levels

## Ranking score

Heuristic, design choice of this skill, to calibrate. Each factor is scored 1 to 3; the page
score is their product (1 to 27). Ties are broken by the number of facts on the page.

| Factor | 1 | 2 | 3 |
|---|---|---|---|
| Importance | Supporting page | Ranks or gets traffic (`reported` from Search Console) or is linked from the main menu | Sells, collects leads, or the user named it |
| Staleness | All facts `ok` | Some `due-soon`, `page-dated` or `no-date` | Any `overdue`, `event-passed` or `future-date` |
| Risk | Only low-risk classes | Medium-risk classes | Any high-risk class (`price`, `plan-limit`, `terms`, passed `event`) |

When importance is `assumed` (no data), say so next to the score.

## Refresh levels

Assign one level per group of pages (same template, topic or fact).

| Level | When | What is done |
|---|---|---|
| 1. Verify only | Facts are probably still right; nothing in the register changed | Re-read sources, update `last_verified` in the register; no page edit, no date change |
| 2. Patch facts | One or more values changed at the source | Replace the value on every page carrying it; update the visible date on those pages only; log it |
| 3. Rework sections | Several facts changed, or the page explains a process that changed | Rewrite the affected sections; check the search results first (hand over to seo-content-brief, refresh mode, when the results moved) |
| 4. Rewrite | The page's premise is out of date (discontinued product, superseded version) | New brief, same URL if the topic still holds |
| 5. Merge, redirect or retire | The page duplicates another, or the topic is gone | **Only with page-level search data** (impressions, clicks, linking pages). Without it, write "not decidable without Search Console data" and stop at level 1–4 |

## Change log

Every refresh writes one line per fact: date, entity, attribute, old value, new value,
source URL, literal string read at the source, pages patched, who did it.
