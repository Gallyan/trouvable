# The five verdicts

Every checked claim gets exactly one. The set is a design choice of this skill. The
three failure cases (contradicted, no support, unreadable) are deliberately kept apart.

| Verdict | Definition | Requires | Patch? |
|---|---|---|---|
| `confirmed` | The primary source, read today, contains the literal string or the same value in the same unit and scope | source URL, quoted string, date read | no |
| `wrong` | The primary source, read today, states a different value, label or version | source URL, quoted string that contradicts, date | yes: corrected sentence |
| `unsupported` | The primary source was read but holds no string supporting the claim, and no other primary source was found | URLs searched, strings tried, date | yes: remove, soften, or ask the author |
| `unreadable` | The source could not be read as a raw page (JavaScript-only, bot challenge, login, regional variant, timeout) | URL, reason, what was tried | no patch; manual route: user pastes the paragraph or a screenshot |
| `outdated` | The claim was true at a past date (changelog, archived page, dated announcement) but the current source states otherwise | both strings, both dates | yes: update, or date the statement explicitly |

Not verdicts, but ledger states:
- `unchecked` — low-risk claim left out of this run, listed as such.
- `author` — the claim can only be answered by the author (own figures, experience);
  goes to the questions list.

Partial matches (right amount, wrong currency or period; right label in another
language) are `wrong`, with the difference stated.
