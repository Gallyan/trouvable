# Scripts

Python 3.9+ standard library only, plus the bundled `seokit` copy. Site and file text is
printed as quoted data (`*_text`, `*_quote` fields), never interpreted.

## compare_facts.py

```
python3 scripts/compare_facts.py --facts vendor-facts.csv --today 2026-10-16
python3 scripts/compare_facts.py --facts vendor-facts.csv --today 2026-10-16 --draft page.md --fetch --out audit.json
```

Flags: `--facts` (required, CSV as in `templates/vendor-facts.csv`), `--today` (default: system date),
`--due-days` (default 14), `--draft` (Markdown/text), `--fetch` (alias `--live`), `--out`,
plus `--user-agent --delay --timeout --max-bytes`.

**Output** (JSON): `overdue` (effective `recheck_by` < today; computed as `read_on` +
cadence of `references/recheck-cadence.md` when `recheck_by` is empty), `due_soon`, `undated`,
`cadence_notes` (recheck_by later than the cadence allows), `pending_owner` (status
`pending-owner`, or own-product fact not `verified`), `contradictions` (same product +
attribute, different `value_on_page`, or status `contradicted`), `unknown_status`,
`draft_values_without_row` (prices, versions, percentages, numbers with units),
`source_checks` with `--fetch` (`present` + `evidence_quote` / `absent` / `not read` + reason),
`blocked_hosts`, `blocking`, `limits`, `generated_on`.

**Exit codes**: 0 nothing blocking, 1 blocking items (overdue, pending owner, contradiction,
string absent or not read), 2 bad input (missing columns, bad date, unreadable file), 3 a
source answered 401/403/429.

**Limits**: never writes to `vendor-facts.csv` (no status, `read_on` or `recheck_by` change). String
presence is not verification: a present string may sit in an outdated section, an absent one
may be a rewording or JavaScript-rendered. Cadences are heuristic, to calibrate. The draft
check misses facts written in words.

**Network**: none by default. With `--fetch`: one GET per distinct source URL, robots.txt
respected, ~2 req/s, size cap, timeouts; a host answering 401/403/429 is not asked again.
