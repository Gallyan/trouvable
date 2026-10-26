# Status of each part

The four parts measure different things, so each keeps its own status. Thresholds below are
design choices of this skill (heuristic, to calibrate).

| Part | `blocking` | `to improve` | `in good shape` | `not measured` |
|---|---|---|---|---|
| Access | a search agent disallowed on a key page, or `noindex` / `nosnippet` on a key page, or robots.txt answering 5xx | `max-snippet` very low, `data-nosnippet` around main text, key pages with little static text, a user-triggered fetcher disallowed | search agents allowed on all key pages, no snippet limit on them | robots.txt not read, crawl stopped on 401/403/429 |
| Content | no key page has a `quotable` passage | some key pages have `fixable` passages, or trust signals missing on key pages | most key passages `quotable` and trust signals present | key pages not read, or JavaScript-only |
| llms.txt | never blocking | present with broken links, wrong facts or wording aimed at models | absent and not needed, or present and sound | file not reachable for another reason than 404/410 |
| Mentions | never blocking | the brand absent from most answers where competitors appear, or confused with another entity | cited in a fair share of relevant answers | no pasted answers and no web search run |

Rules:
- A part is `not measured` rather than guessed when its input is missing.
- The plan follows the statuses: every `blocking` item comes before any `to improve` item.
- Effects of the plan are not forecast; each item has a check to run after the change.
