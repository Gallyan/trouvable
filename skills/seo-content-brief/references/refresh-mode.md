# Refresh mode

For an existing page that used to perform and dropped.

## Inputs

- The URL.
- Search Console Queries and Pages exports for a period before the drop and one after (same
  length). Optional, but without them the report lists the differences and leaves the cause of the drop unmeasured.

## Steps

1. **Read the page as it is today** (date it). Extract its headings, dates, versions, prices,
   figures, as in workflow step 2.
2. **Re-check each claim at its source.** Same facts table as a new brief; mark each
   `still true`, `changed` (old → new value), `cannot confirm`, `not read`.
3. **Read today's page one** for the main query (and the top two or three queries from the
   export, if given). Build the coverage matrix with the user's page as a column.
4. **Compare.**
   - Topics the top results now cover that the page does not.
   - Format or intent shift (for example, lists replaced by tools or forum threads on page one).
   - Freshness: versions or prices on the page older than on page one or at the source.
5. **With Search Console data**: which queries lost clicks or impressions, and on which
   positions; label `reported`. Without it: write "cause of the drop not measurable without
   Search Console data".
6. **Recommend a level** (heuristic, design choice of this skill):
   - patch facts only (claims changed, page one stable);
   - rework sections (gaps in the matrix);
   - rewrite on the same URL (intent shifted, page still on topic);
   - hand over to seo-fact-check (site mode) for merge/redirect/retire decisions.
7. **Do not move the visible date** unless the content is changed.

## Output additions

- A "what differs" table: topic or fact, page today, page one / source today, change needed.
- The query-level loss table when data is given.
