# Scripts — not written yet

No script is planned for this skill. Every step is a web search or the reading of a page, which
Claude does with its own tools; the score is simple arithmetic on judgements written in the
report.

## Considered and not planned: serp_table.py

A formatter that would turn pasted search results (title, URL, snippet) into the page-one table
skeleton and sort an idea list by verdict and score.

- **Would take**: pasted results as text, or a CSV of ideas with verdict and score columns.
- **Would output**: Markdown table on stdout.
- **Why not now**: it saves typing only; it cannot fill the judgement columns (site type,
  answers or not, evidence). Write it only if long idea lists turn out to be slow to sort by
  hand.
- **If written**: Python 3.9+ standard library only, offline (no network), prints site text
  as quoted data.
