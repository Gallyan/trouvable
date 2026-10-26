# Market ranking

Score each candidate market on the criteria below, 0–5 each. Weights and scale are a
heuristic, design choice of this skill, to calibrate. Every cell carries its tag:
`measured`, `reported`, `estimated` (method stated) or `assumed`.

| Criterion | Weight | What counts as evidence |
|---|---|---|
| Existing demand signals | 3 | impressions/clicks from that country or language in Search Console; customer requests; sales |
| Ability to serve | 3 | shipping, payment, support, legal pages in that language |
| Reviewer and upkeep capacity | 2 | named native reviewer, hours per week |
| Competitive difficulty of the local results | 2 | local results read on {date} for 3–5 core queries in that language (lower difficulty scores higher) |
| Language reuse | 1 | another market shares the language (one version, several countries) |

Total = Σ(score × weight), max 55. Report the total **and** the per-criterion cells; a high
total built mostly on `assumed` cells is flagged as weak.

## Rules

- Search volume is not a criterion unless a measured source is available. Otherwise the
  cell says "not measurable here — cheapest measurement: {e.g. a 4-week pilot page, a
  keyword tool trial, Search Console data from an existing page in that language}".
- Results reading: tool, region, language and date noted for each query.
- A market where Ability to serve = 0 is excluded regardless of total.

## Table

| Rank | Market (language-country) | Demand | Serve | Reviewer | Difficulty | Reuse | Total | Weakest evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | | 4 (`reported`) | | | | | | |
