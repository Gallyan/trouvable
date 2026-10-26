# Status definitions

One status per register row, computed on the day of the scan. `age` = scan date minus the
date the fact rests on. `cadence` comes from `fact-classes.md`. The 80 % threshold for
`due-soon` is heuristic, design choice of this skill, to calibrate.

| Status | Condition | What the report does |
|---|---|---|
| `overdue` | The fact was verified at its source once, and `age` > `cadence` | Lists it first if risk is high; source to re-read is named |
| `due-soon` | Verified at its source, `age` between 80 % and 100 % of `cadence` | Lists it with its due date |
| `ok` | Verified at its source, `age` < 80 % of `cadence` | Counted, not listed |
| `page-dated` | Never verified at its source; the only date is the page's own (visible date, `dateModified` or `lastmod`) | Counted; ranked by risk; the page date says when the page changed, not when the fact was checked |
| `no-date` | Never verified, and the page carries no date of any kind | Counted; ranked by risk; treated as unknown age, never as fresh |
| `future-date` | The date it rests on is later than the scan date (a typo, a scheduled post, a wrong timezone or a faked date) | Listed as a date finding |
| `event-passed` | Class `event` and the event date is before the scan date while the page still presents it as upcoming or current | Listed among the riskiest findings |

## Notes

- `overdue`, `due-soon` and `ok` need a recorded source verification. On a first scan most
  facts are `page-dated` or `no-date`: that is the honest result, not a failure.
- A page-dated fact is never promoted to `ok` because the page was edited recently: an edit
  may not have touched the fact.
- Counts by status are `measured` from the scan. Statuses that depend on a user-given
  verification date are `reported`.
