# Page-one reading checklist

## Before reading

- [ ] Note the tool (search tool name, or "pasted by user"), the region if known, the day.
- [ ] Note each phrasing searched. Two or three phrasings in standard mode, one in quick mode.
- [ ] If the tool's region or engine is unknown, write "engine unknown" rather than naming one.

## For each result (standard mode: open it)

| Field | How to fill it |
|---|---|
| Position | Order in the results as returned; mark ads and non-organic blocks separately if the tool shows them |
| URL | Full URL |
| Site type | One of: brand/vendor, large publisher, niche blog, forum/Q&A, video, directory/aggregator, marketplace, official doc, government/education, tool/app, other |
| Date | Published or updated date visible on the page; "none shown" if absent. Do not take the date from the snippet alone if the page shows another |
| Version covered | Product version, year or edition the page is about, when relevant |
| Answers the query? | `yes` / `partly` / `no`, judged against the query's intent, not its words |
| Evidence | One short quoted string from the page (or the snippet in quick mode, marked as snippet) supporting the two fields above |
| Read status | `read`, or `not read` (blocked, JavaScript-only, paywall, error) |

## Page-level observations

- [ ] Dominant intent: informational, commercial investigation, transactional, navigational, local. Mixed is a valid answer.
- [ ] Dominant format: guide, list, comparison, tool, product page, video, forum thread.
- [ ] Freshness: how many results are dated in the last 12 months, how many cover an outdated version.
- [ ] Weak spots: forums, thin pages, outdated pages, pages that do not answer.
- [ ] Results-page features the tool shows (direct answers, videos, questions). Do not infer features a text-only search tool cannot show; write "not visible with this tool".

## Demand signals (none of them is a volume)

- Autocomplete suggestions seen today, if a tool can show them.
- Forum and Q&A threads asking the question, with dates.
- Questions repeated across results.
- Search Console impressions for the query or close variants (`reported`).

Record each signal with its URL or its source and the day.

## Overlap with the user's site

- Search the URL list for pages whose title or slug covers the query.
- If a search tool supports a site filter, run it and date it.
- An existing page that already covers the intent triggers the overlap gate in `scoring.md`.
