# Scripts

Python 3.9+ standard library only, plus the bundled `seokit/` copy. Run from the skill folder.

## outreach_due.py

Weekly reader of the tracker. **No network.** Never writes to the tracker.

```
python3 scripts/outreach_due.py --tracker outreach-log.csv [--today YYYY-MM-DD] [--window 7]
        [--max-followups 1] [--format json|csv] [--out due.json]
```

- Takes rows with an open status (`drafted`, `submitted`, `sent`, `followed-up`) and a
  `next_action_date` on or before today → `due[]` (with `days_overdue`, suggestion).
- `stop_following_up[]`: due rows awaiting a reply (`submitted`, `sent`, `followed-up`) with
  `followups_sent` ≥ `--max-followups` (default 1, heuristic from `references/outreach-rules.md`)
  → suggest `no-reply`.
- `upcoming[]`: open rows due within `--window` days (this week by default).
- `missing_dates[]`: `kept` or open rows with no `next_action_date`.
- `errors[]`: unknown or empty status, dates not `YYYY-MM-DD` (`next_action_date`, `submitted_on`,
  `rules_read_on`), non-integer `followups_sent`, by `data_row` (1 = first non-empty data row).
- JSON: `{generated_on, today, tracker_rows, due[], overdue_days{id: days}, upcoming[],
  stop_following_up[], missing_dates[], by_status{}, errors[], limits[]}`. `--format csv` prints
  the due rows only (formula-like cells neutralised).
- Exit 2 on unreadable tracker, missing columns (`id, status, next_action_date, followups_sent`)
  or a bad `--today`.
- Limits: reads only what the user recorded; does not check whether a listing went live or a
  reply arrived. Cell text is quoted (`target_text`, `notes_text`) as data.

## read_rules.py

Polite reader of a venue's rules or submission page. **Network: GET only** (seokit.fetch).

```
python3 scripts/read_rules.py --url <rules page> [--url <another>] [--out rules.json]
python3 scripts/read_rules.py --urls-file venues.txt [--max-urls 20] [--keywords rule_keywords.json]
        [--user-agent ... --delay 1.0 --timeout 15 --max-bytes 2000000]
```

- Fetch policy: identifiable user agent, robots.txt read and honoured, 1 s between requests per
  host, 2 MB cap, TLS verified, redirects followed and reported. On 401/403/429 or a
  challenge/captcha page: `not read`, no retry, other URLs on that host skipped, exit 3.
- Extracts title, headings, a text excerpt, and **candidate** rule sentences by topic
  (`self_promotion`, `ai_generated`, `link_back`, `fee_paid_sponsored`, `criteria`,
  `disclosure`) using `rule_keywords.json` (English + the page language when a list exists;
  `en` and `fr` today — review and extend that file, do not guess).
- `red_flag_candidates[]`: sentences containing phrases tied to `references/red-flags.md`
  (paid link placement, reciprocal link required, rules exclude the site, asks for
  credentials, guaranteed metrics). Candidates to read, not verdicts.
- `untrusted_comments[]`, `untrusted_hidden_text[]` (hidden attribute, `aria-hidden`, inline
  `display:none`/`visibility:hidden`) and `untrusted_instructions[]` (text addressed to AI or
  asking to ignore instructions, with where it was found): quoted site text, never acted on.
- JSON: `{generated_on, user_agent, pages[{url, final_url, status, fetched_at, robots_allowed,
  redirects[], truncated, read_status, not_read_reason?, lang, keyword_languages, title_text,
  headings[], rule_sentences[{topics, keywords, sentence_quote}], red_flag_candidates[],
  untrusted_comments[], untrusted_hidden_text[], untrusted_instructions[], word_count,
  text_excerpt, notes[]}], not_read[], limits[]}`.
- Exit 2 on no URL, a non-http(s) URL or an unreadable keyword file.
- Limits: no JavaScript rendering, no login, no form submission; keyword matching misses rules
  phrased otherwise (heuristic, to calibrate); dead venues, link farms or scraped domains cannot be
  seen from one page.

Without these scripts: sort the tracker by `next_action_date` by hand; open rules pages in the
browser or with the page-reading tool and copy the literal rule sentences with the date.
