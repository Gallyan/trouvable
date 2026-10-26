# Sample verdict

Judged on **non-brand** rows only, for the export's date range.

| Verdict | Rule (heuristic, to calibrate on real exports) | What the report does |
|---|---|---|
| `insufficient` | fewer than 300 non-brand impressions, or fewer than 20 non-brand queries with impressions | No ranked queries. Explain the data cannot show yet whether SEO works, list what to watch, give the date of the next look |
| `limited` | fewer than 3,000 non-brand impressions, or fewer than 30 non-brand clicks | Analyses run, every action is marked provisional, no CTR curve unless at least 5 positions buckets have 50+ impressions each |
| `usable` | above both thresholds | Full analysis |

These thresholds are a design choice of this skill, not a Google rule. State the
numbers that produced the verdict (`measured` from the export).

Also mention, without changing the verdict:
- the date range (a range shorter than 28 days is noisy for a small site);
- the share of anonymised queries if the Pages total is much larger than the Queries total
  (Search Console omits rare queries from query-level tables).
