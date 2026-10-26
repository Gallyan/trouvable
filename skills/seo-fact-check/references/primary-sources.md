# Primary-source rules

1. **Whoever creates the fact.** The vendor for its prices and labels, the maintainer for
   versions, the authors of a study for its figures, the speaker for a quote, the official
   text for law. Blogs, aggregators, AI answers and search snippets are pointers to find the
   source, never the source.
2. **Raw page, literal string.** Search the exact string in the raw fetched page. A summary,
   a rendered screenshot description or a model's paraphrase is not a match. Record the
   string found between quotes, with its URL and date.
3. **Same language.** Check a French page's labels on the French source (French interface,
   French help centre). Never carry an English label into a translation. If no source exists
   in that language, say so and record which language was used.
4. **Same scope.** Region, currency, plan, tax inclusion, platform and version must match
   the claim. Regional prices: note the location the fetch came from; one fetch is one
   location.
5. **Date everything.** The "checked on" date is the day the string was read in this run.
   Never reuse an earlier date, never back-date.
6. **Variants.** Try formatting variants before `unsupported`: thousands separators, decimal
   comma, currency before/after, non-breaking spaces, typographic quotes, case.
7. **Statistics.** Find the original publication; note sample, date and population. A
   figure quoted second-hand with no reachable original is `unsupported`.
8. **Quotes.** Exact words from the original; a translated quote is marked as a translation.
9. **Unreadable sources.** JavaScript-only, bot protection, login or region walls:
   `unreadable`. Manual route: ask the user to paste the paragraph or a screenshot, then
   check the string in what they gave (`reported`).
10. **Archived versions** (e.g. a web archive) may establish `outdated`, never `confirmed`
    for a current claim.
