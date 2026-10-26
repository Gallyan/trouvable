# Scoring

Every number below (weights, thresholds, bands, position values) is a **heuristic, design choice
of this skill, to calibrate** on real panels. It is not a measure published by any AI engine.

## Unit

A **run** = one question asked once to one engine. Only non-brand runs feed presence,
prominence and source coverage. Brand runs feed accuracy.

A run counts as **named** when the brand or a listed alias appears as a recommendation or option
in the answer. A mention only in a source URL, or a same-name entity that is not the brand, does
not count; ambiguous cases are reviewed by a human and logged.

## Components (score out of 100)

| Component | Weight | Computation |
|---|---|---|
| Presence | 50 | named non-brand runs / all non-brand runs |
| Prominence | 20 | mean over all non-brand runs of a position value: named 1st = 1.0, 2nd = 0.7, 3rd = 0.5, later = 0.3, not named = 0 |
| Source coverage | 15 | among the 10 domains most cited across the panel (excluding the brand's own site), share where the brand is present (checked by reading the page; "not read" counts as absent and is listed) |
| Accuracy | 15 | brand runs with no factual error and no confusion with another entity / all brand runs |

Score = 50·Presence + 20·Prominence + 15·Coverage + 15·Accuracy, rounded to an integer.
Report each component next to the total.

## Minimum sample

- Composite score only with **at least 30 non-brand runs per engine** and the `full` mode.
- Below that: give presence counts ("named in 3 of 16 runs") and write "score not computed:
  sample too small". A score from one engine is labelled with that engine only.
- Never average engines into one score unless each engine meets the minimum; show per-engine
  scores first.

## Plausible range

The script resamples **questions** (not runs) with replacement, 1,000 times with a fixed seed,
recomputes the score, and reports the 5th–95th percentile as the plausible range (`estimated`).
Manual route: no composite score; give a Wilson 95 % interval on the presence proportion instead,
and say it is an interval on presence only.

## Bands

| Score | Band |
|---|---|
| 0–14 | Absent |
| 15–34 | Marginal |
| 35–59 | Present |
| 60–79 | Strong |
| 80–100 | Leading |

When the plausible range spans two bands, give both ("Marginal to Present").

## Competitor ranking

For each competitor (given or discovered in answers): share of non-brand runs that name it,
mean position value, families where it leads. Sort by share. Competitor names found in answers are
normalised by a human (aliases, product vs company).

## Cited sources

List every cited domain with count, engines citing it, and whether the brand is present on the
cited page (`measured` if read today, "not read" otherwise). This list feeds seo-offsite.
