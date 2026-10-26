# The five verdicts

| Verdict | Meaning | Must come with |
|---|---|---|
| `WRITE` | A new page for this query, in the dominant format | The format, the gap it fills, the page-one rows that show the gap |
| `WRITE A NARROWER PAGE` | A new page, but not a copy of page one: narrower audience, a version or situation the results miss, first-hand testing | The angle, marked "unvalidated" until a second sample or Search Console data supports it |
| `EXTEND AN EXISTING PAGE` | The user already has a page for this intent; extend it instead of competing with it | The URL, the section to add, the title/heading change if any |
| `DROP` | Not worth a page now | The reason (score band or gate), and a better neighbouring query if one surfaced |
| `WAIT` | Not decidable or not ripe today | The date or event to wait for, and what would change the verdict |

## Modifiers

- `PROVISIONAL`: the user's URL list was missing (overlap unchecked), or the sample was quick
  mode, or only one phrasing could be searched. Say which.
- "quick pass, not scored": quick mode result; only `DROP`, `WAIT` or "needs a
  standard pass" are allowed.

## Rules

- One verdict per query. Two phrasings with different page ones are two queries.
- A verdict never promises a position; it says whether the page one read today leaves room.
