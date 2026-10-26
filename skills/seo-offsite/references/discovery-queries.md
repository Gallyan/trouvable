# Target discovery queries (free)

Run with the web search tool available; note tool, region and date for each batch. Adapt the
wording to the market's language. `{cat}` = category in buyer words, `{comp}` = a competitor,
`{city}` = service area.

## Query patterns

| Target type | Patterns |
|---|---|
| Niche directories | `{cat} directory`, `submit {cat}`, `list your {cat}`, `{cat} "submit your"` |
| Awesome lists | `awesome {cat} github`, `awesome-{cat}`, `curated list {cat}` |
| Roundups | `best {cat} {year}`, `{cat} alternatives`, `{comp} alternatives`, `tools like {comp}` |
| Communities | `{cat} forum`, `{cat} community`, `{cat} subreddit`, `{cat} discord`, `{cat} slack group` |
| Newsletters | `{cat} newsletter`, `{cat} weekly`, `submit to {cat} newsletter` |
| Launch sites | `launch {cat} product`, `where to launch a {cat}` |
| Competitor mentions | `"{comp}" -site:{comp-domain}`, `"{comp}" review`, `"{comp}" vs` |
| Local (business) | `{trade} {city}`, `{trade} near {city} directory`, chamber of commerce, trade association member list, local press |
| Podcasts / interviews | `{cat} podcast guest`, `{cat} interview founders` |
| Resource pages | `{cat} "useful resources"`, `{cat} "recommended tools"` |

## Sources cited by AI assistants

If geo-mentions has run, import its cited-domain list. A domain cited by assistants where the
brand is absent is a priority candidate (still read for rules and red flags).

## Logging

Log every candidate in the tracker with `status=candidate` and the query that found it, even if it
is excluded later. The report gives "N candidates examined, K kept, M left out" (`measured`).

## Honest limits

- Free searches find what search engines show, not a full backlink graph. Do not estimate a
  competitor's link count.
- Search operators (`-site:`, quotes) behave differently between engines and change; if one seems
  ignored, say so and fall back to plain queries.
