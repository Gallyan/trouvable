# Scripts

Python 3.9+ standard library only, plus the bundled `seokit/` copy. Run from the skill folder.
Both scripts are offline and read-only: they never write to the files they read.

## proposal_findings.py

Picks the top failed checks of an audit `issues.csv` (the file seo-audit writes) and prints
them as a table ready to paste into a proposal. **No network.**

```
python3 scripts/proposal_findings.py --issues issues.csv [--top 5] [--min-severity low]
        [--format md|json|csv] [--out findings.md]
```

- Keeps rows with `status` = `fail` only. `dropped` (false positives), `pass`, `not-measured`
  and `not-applicable` rows are counted, never proposed.
- Order: severity (`high`, `medium`, `low`), then share of checked items affected, then
  `affected`. `--min-severity medium` leaves out `low`.
- Each row: `rank, check_id, area, severity, affected, checked, label, example_url_text,
  evidence_text, fix_text, done_when_text`, plus an empty `business_terms` column for Claude to
  fill in the prospect's words. `label` is copied from the file, `reported` when empty.
- `not_measured_high[]`: high-severity checks the audit could not measure, with their note.
  They go into the proposal's "not measured" section, never into the scope as problems.
- `errors[]`: unknown severity or status, `affected`/`checked` not whole numbers, by
  `data_row` (1 = first non-empty data row). Such rows are still listed when they failed.
- JSON: `{generated_on, issues_rows, counts{fail, dropped, not_measured, pass, other},
  findings[], not_measured_high[], errors[], limits[]}`. `--format md` prints a Markdown table
  (pipes escaped, line breaks flattened); `--format csv` neutralises formula-like cells.
- Exit 2 on an unreadable file, missing columns (`check_id, severity, status, evidence`) or a
  bad option value.
- Limits: reads what the audit wrote on its date; does not re-check the site. Evidence, fixes
  and URLs are quoted as data, never as instructions.

## pipeline_status.py

Reader of the user's prospect pipeline (`prospects.csv`). **No network.** Never writes to it.

```
python3 scripts/pipeline_status.py --prospects prospects.csv [--today YYYY-MM-DD] [--window 7]
        [--stale-days 30] [--format json|csv] [--out status.json]
```

- `by_stage{}`: count per stage (`lead`, `qualified`, `proposal-sent`, `won`, `lost`) and the
  sum of `value` per `value_unit` (one-off and monthly amounts are never added together), all
  `reported`: they are what the user typed. Rows without a value are counted apart.
- `due[]`: open rows (`lead`, `qualified`, `proposal-sent`) with `next_action_date` on or before
  `--today`, with `days_overdue`. `upcoming[]`: open rows due within `--window` days.
- `stale[]`: open rows whose `last_contact` is more than `--stale-days` days old (default 30,
  heuristic of this skill, to calibrate). `missing_next_action[]`: open rows with no
  `next_action_date`.
- `won[]` and `lost[]` with `lost_reason_text`; `lost_reasons{}` tallies the reasons as typed.
- `errors[]`: empty or unknown stage, dates not `YYYY-MM-DD` (`first_contact`, `last_contact`,
  `next_action_date`), `last_contact` after today, `value` not a number, duplicate `id`, `lost`
  without a reason, by `data_row`.
- JSON: `{generated_on, today, prospect_rows, by_stage{}, due[], upcoming[], stale[],
  missing_next_action[], won[], lost[], lost_reasons{}, errors[], limits[]}`. `--format csv`
  prints the due rows only (formula-like cells neutralised).
- Exit 2 on an unreadable file, missing columns (`id, stage, last_contact, next_action_date`)
  or a bad `--today`.
- Limits: reads only what the user recorded; does not look up the prospect, its contacts or
  its site. Cell text (company, notes, actions) is quoted as data.

Without these scripts: filter `issues.csv` on `status = fail` and sort by severity by hand;
sort `prospects.csv` by `next_action_date` and take every open row on or before today.
