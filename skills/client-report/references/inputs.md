# Inputs this report can use

Only files the user gives or that a skill of this plugin wrote. Each input keeps its own
date and labels; the report copies them.

| Input | Written by | Feeds | Keep from it |
|---|---|---|---|
| `issues.csv`, `summary.json`, `report.md` | seo-audit | What we found, annex, progress | status, severity, area, affected/checked, evidence, label; mode and caps from the summary |
| `fix-tracker.csv` | seo-audit (filled by the user) | What was done | fix, where, status, `verified_on`, `verified_how`; a fix without `verified_on` is "done, not yet checked" |
| Search Console JSON and report | seo-search-console | In short, figures | sample verdict first; brand and non-brand split; date range; actions with their effect ranges |
| GEO report, one section per part | geo-audit | What we found, next | each part's status and evidence, kept apart (no merged score) |
| Visibility score JSON, runs CSV | geo-mentions | Figures | presence counts, score only when the skill computed one, its range and sample |
| Claims ledger, decay register, freshness report | seo-fact-check | What we found, next | gate verdict, claims and their check dates, pages to refresh |
| Indexing, schema, llms.txt, internal links, multilingual reports | the matching seo- or geo- skill | What we found | each report's findings with evidence and dates |
| A previous client report | this skill | Progress | the dates and figures it showed, as labelled then |

Anything else the user pastes (a dashboard screenshot, a figure from another tool) is
`reported`: name the tool and the date the user gave, or write "date not given".

A number that no input contains does not go in the report. When the user asks for one,
say which skill or export would produce it.
