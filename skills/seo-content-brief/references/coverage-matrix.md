# Coverage matrix and information gain

## Building the matrix

Rows are topics (sub-questions, steps, criteria, objections) found in at least one page read or
in the questions people ask (forums, results-page questions if the tool shows them). Columns are
the pages read, then the user's page (planned or existing), then the gain column.

| Topic | Page A | Page B | Page C | Page D | Page E | User's page | Information gain |
|---|---|---|---|---|---|---|---|
| {sub-question} | ✓ / ~ / ✗ | | | | | planned / exists / ✗ | {what can be added, and with which material} |

Cell values: `✓` covered with substance, `~` mentioned without substance, `✗` absent,
`n/r` page not read. Each `✓` and `~` should be traceable to a heading or quoted sentence in
the extraction.

## Reading the matrix

- **Table stakes**: topics covered `✓` by most pages. The brief keeps them, shorter and answer
  first.
- **Gaps**: topics `✗` or `~` everywhere, but asked about in forums or questions. Strong
  candidates.
- **Stale cells**: covered, but on an old version, an old price or an undated figure.
- **Thin consensus**: every page repeats the same unsourced claim; check it at the source.

## Information-gain column

A gain is something the user's page can contain that no page read contains. Valid sources of
gain, strongest first (heuristic order, design choice of this skill, to calibrate):

1. First-hand material: a test the user ran, screenshots, measurements, own data.
2. The current version or price, read at the source today, where pages are stale.
3. A situation or audience no page addresses (by budget, size, country, skill level).
4. A decision aid: table by situation, checklist, calculator inputs.
5. A clearer structure of the same facts (weakest; rarely enough alone).

Each gain names the material that backs it. A gain with no material is removed, not kept as
"add expert insight".

## Limits to state

- The matrix holds for the pages read on the day, from one search sample.
- A "gap" may be absent because it is off-intent; check the query's intent before adding it.
