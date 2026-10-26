# Passage checks

A passage is a heading and the text under it, up to the next heading. Read it as if it were
the only thing an assistant kept from the page. Statuses and criteria below are design
choices of this skill (heuristic, to calibrate), not a documented rule of any engine.

## Statuses

| Status | When | What the report says |
|---|---|---|
| `quotable` | All five checks hold | Nothing to change; name the question it answers |
| `fixable` | The topic is right, one or more checks fail | Which checks fail, quoted, and the rewrite |
| `not a candidate` | Navigation-like text, legal boilerplate, promotional copy without facts, a teaser that sends the reader elsewhere | Why; leave it alone |

## The five checks

1. **Answer first.** The first one or two sentences answer the question the heading asks (or
   the question the user gave). A passage that starts with background, a story or a
   rhetorical question fails.
2. **Stands alone.** No opener that points back ("This", "As we saw", "Cela", "Comme vu
   plus haut"); the subject is named; abbreviations are spelt out once.
3. **Specific.** At least one concrete fact a reader could check: an amount, a date, a
   version, a named method, a limit or a condition. A figure without its source or date is a
   question for the author, not a pass.
4. **Sized to be lifted.** Long enough to make sense alone, short enough to be quoted: the
   script flags under 40 and over 300 words; read the passage before trusting either flag.
5. **Shaped for its content.** Steps as a numbered list, options compared in a table or list,
   a definition in one sentence. Prose is fine when the content is an argument.

## Script leads and what they mean

| Lead | Check it points to |
|---|---|
| `opening leans on earlier text` | 2 |
| `long opening sentence` | 1 |
| `short: may not stand alone` / `long: consider splitting` | 4 |
| `no figure, date or version` | 3 |
| `no heading` | 1 (no question to answer; often an intro) |

A lead is a reason to read the passage, never a status on its own.
