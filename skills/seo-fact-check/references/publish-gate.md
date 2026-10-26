# Publish gate

Gate rules are a heuristic, design choice of this skill, to calibrate with the user.

## BLOCKED if any of

- a `high` risk claim is `wrong`, `unsupported` or `outdated` and not yet patched;
- a `high` risk claim is `unreadable` or `unchecked` and the user has not supplied the
  source text;
- a `legal` claim has no named qualified reviewer;
- the page contradicts itself on a price, label or version;
- an `author` question on a high-risk claim is unanswered.

## PASS when

- every `high` risk claim is `confirmed` (or patched and the patch re-checked);
- remaining issues are medium/low and listed with their patch.

PASS means "no known blocking error on {date}", not "error-free". The report never adds a
"fact-checked" badge to the page.

## Re-check date

Default: the earliest of
- 90 days after the check (heuristic, to calibrate);
- the next known price or version change from the sources (release schedule, announced
  pricing change);
- any date stated in the page itself (deadline, event).

Dated claims go into `templates/decay-register.csv` for scheduled re-checks (site mode).
