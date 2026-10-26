# Claim types and risk ranking

Types and risk levels are a heuristic, design choice of this skill, to calibrate.
A claim can carry several types (e.g. `statistic,absolute`).

## Types

| Type | What it looks like | Typical primary source |
|---|---|---|
| `price` | amount + currency, plan names, "free", tax wording | vendor pricing or checkout page |
| `label` | menu names, button text, setting names, step-by-step paths ("Settings > Billing") | the interface itself, official help in the page's language |
| `version` | version numbers, "since v3", release names, compatibility | changelog, release notes, official docs |
| `date` | launch dates, deadlines, "in 2025", "last updated" | official announcement, changelog |
| `statistic` | percentages, counts, rankings, survey figures | the original study or dataset |
| `quote` | words attributed to a person or organisation | the original statement (recording, transcript, post) |
| `absolute` | "always", "never", "only", "zero", "all", "first", "the best" | needs proof over the whole set, or rewording |
| `comparison` | "faster than", "cheaper than", "more than X" | both sources, same date |
| `legal` | legal, medical, financial, safety statements | law text, regulator, official guidance; plus a qualified reviewer |
| `own` | the author's own figures or experience | only the author (question, not a verdict) |

## Risk levels

| Risk | Rule |
|---|---|
| `high` | the reader pays for it (price, plan limits), follows it step by step (labels, settings, commands), or it is `legal`; any claim in a title, heading or first paragraph |
| `medium` | versions, dates, statistics and comparisons in the body |
| `low` | context and background facts that change nothing for the reader if slightly off |

Ordering: high first, then by position on the page (top first). The ledger keeps
low-risk claims, marked `unchecked` if not checked.

## Six-language vocabulary for extraction

The extractor looks for cue words in English, French, Spanish, German, Italian and
Portuguese (currency words, "version", "since", "per month", superlatives, absolute words).
The lists are written and tested from real pages in each language as fixtures; numbers,
prices and versions are found by pattern in any language.
