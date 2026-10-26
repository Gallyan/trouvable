# When two runs can be compared

Progress is only shown between two runs of the **same** audit, made the same way. Check
each rule below; every rule that fails becomes one line under "Limits of this comparison"
and, if it changes the counts, a sentence in "In short".

| Rule | Check | If it fails |
|---|---|---|
| Same audit | Same skill and script, same key column (`check_id` for seo-audit) | Not comparable: say so, report each run on its own |
| Same site | Same start URL or property; same host variant | Not comparable |
| Same scope | Same mode (full, sample, sections, light), same page cap, same sections | Counts of affected pages are not compared; check status can still be compared, with the caveat |
| Same depth of reading | Neither run stopped early (401, 403, 429, cap hit in one run only) | Checks the stopped run could not measure are left out of the delta |
| Same rubric | Same set of check IDs; same severity per check | Checks present in one run only are listed apart, never counted as fixed or new |
| Same base | A check's `checked` count within the ratio given to the script (default 20 %) | Its affected counts are not compared |
| Same period length (Search Console) | Same number of days, same search type, same filters | Figures not compared; describe each period separately |
| Same panel (AI mentions) | Same questions, engines, markets and number of runs | Presence counts not compared |

## Counting rules

- **Fixed** means failing in the first run and passing in the second. A check that became
  "not measured", "not applicable" or disappeared is not fixed: it is listed as such.
- **New** means not failing in the first run and failing in the second. A check that did not
  exist in the first run is new only for the rubric, and the report says so.
- A change in a figure is shown with both values and both dates, and the label of each.
- A change in a figure is not explained by the work done unless an input shows the link
  (for example a page that was not indexed and now is). Seasonality, algorithm updates and
  sampling are not ruled out by two readings.

## Partly comparable

When some rules fail, keep what still holds (check statuses on a same rubric, for example)
and drop the rest. Write "partly comparable" in the header with the reasons.
