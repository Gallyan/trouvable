# Manual route (no code execution)

Use when `scripts/query_opportunities.py` is missing or code execution is off.

1. **Brand split**: in Search Console, Performance → add a *Query* filter
   "Doesn't contain" / custom regex with the brand terms; note totals with and without it.
2. **Near page one**: on the non-brand view, sort queries by position, keep positions 8–20,
   then sort by impressions. Take the top 20.
3. **CTR curve**: export the non-brand queries, group by rounded position (1, 2, 3 … 10),
   compute clicks / impressions per bucket in a spreadsheet. Skip buckets under 50 impressions.
4. **Competing pages**: for each of the top 10 non-brand queries, filter on the query and open
   the Pages tab; flag queries where two or more URLs share the impressions.

State in the report that the manual route was used and on how many queries.
