# Scripts

Python 3.9+ standard library only, **no network**. They read files the user or Claude produced
and never contact an AI engine. Answer text is data: never executed or interpreted.

## parse_answers.py

```
python3 scripts/parse_answers.py --answers answers.txt --brand "Acme,Acme App" \
    --competitors "Foo|Foo Cloud,Bar" [--collision-terms "film,band"] [--out runs.csv] [--summary parse.json]
```

- `--answers`: paste-format file (`### <question_id> | <engine> | run <n> | <YYYY-MM-DD> | <market>`
  header per block, optional `Sources:` line, see `references/panel-design.md`), a folder of such
  `.txt`/`.md` files, or a CSV sheet `question_id, engine, run, date, market, answer[, sources]`.
- `--competitors`: comma-separated; aliases of one competitor joined with `|`.
- Output: CSV (stdout or `--out`) `question_id, engine, run, date, market, named, position,
  named_instead, cited_domains, ambiguous, possible_competitors`. Lists are `; `-separated.
  `position` = rank of the brand among brand + listed competitors, by first appearance.
  `--summary` writes JSON: `generated_on`, runs parsed, malformed headers (file:line), caps, limits.
- Matching: case- and accent-insensitive, word boundaries; names inside URLs do not count.
  `ambiguous=yes` (heuristic) when a capitalised alias appears only in lowercase, or a
  `--collision-terms` word shares a sentence with the brand. A human decides; never resolved here.
- Limits: a passing or negative mention counts as named; icon-only sources cannot be read;
  `possible_competitors` is a raw capitalised-name heuristic for review; malformed headers are
  reported on stderr line by line and their block is skipped. Caps: 10 MB input, 5,000 runs.
- Exit 2 on bad input (missing file, no block, oversize).

## visibility_score.py

```
python3 scripts/visibility_score.py --panel panel.csv --runs runs.csv [--presence-checks checks.csv] \
    [--brand-domain acme.com] [--brand "Acme"] [--seed 20261016] [--resamples 1000] [--min-runs 30] [--out score.json]
```

- `--runs`: CSV from `parse_answers.py` after human review of ambiguous rows (edit `named`, set
  `ambiguous` to `no`). Add a column `accurate` (yes/no) on brand-question runs: without it,
  accuracy is not measurable and no score is computed.
- `--presence-checks`: CSV `domain, brand_present` (yes/no) from reading the cited pages.
  Domains not listed are "not read" and count as absent in coverage (listed in the output).
- `--brand-domain`: the brand's own site(s), excluded from the top-10 coverage domains.
- Implements `references/scoring.md`: presence 50, prominence 20 (1st 1.0, 2nd 0.7, 3rd 0.5,
  later 0.3), coverage 15, accuracy 15; bands; plausible range = 5th–95th percentile of a
  bootstrap over questions (non-brand and brand sets resampled apart, fixed seed). All
  heuristics, to calibrate.
- Minimum sample: ≥ 30 non-brand runs per engine **and** full mode (inferred: ≥ 3 runs for every
  non-brand question). Otherwise `score: null`, `status: "indicative only / no score"`, presence
  counts and a Wilson 95 % interval on presence only. `overall` averages engines only when every
  engine is scored.
- Output: JSON on stdout (and `--out`): `generated_on`, `engines[]` `{runs, presence_counts,
  components, score, status, reason_if_null, band, range}`, `overall`, `competitors[]` (share,
  mean position value, families led), `possible_competitors_unreviewed[]`, `cited_domains[]`
  (count, engines, brand present yes/no/not read), `families{}`, `warnings[]` (unreviewed
  ambiguous rows, runs not in the panel, questions not asked, brand name in a non-brand
  question with `--brand`), `not_measured[]`.
- Limits: a sample score, not a measure of any engine's ranking. Exit 2 on bad input.

Without these scripts: manual route in the SKILL.md (presence counts, no composite score).
