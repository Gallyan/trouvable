# From audit to scope

How an audit made with this plugin becomes the scope of a proposal.

## Pick what to propose

- Start from the failed checks only (`status = fail` in the audit's `issues.csv`, or the top
  fixes of a geo-audit report). Dropped false positives and `not-measured` checks are never
  sold as problems; `not-measured` ones go into the "What we did not measure" section.
- Keep three to five. A prospect reads the first screen; a list of 30 problems reads as a
  scare tactic and hides the ones that matter.
- Order: severity, then how many pages are affected, then how much the prospect's business
  depends on those pages (product pages before the legal notice).
- Open the example URL of each kept item before writing about it. An audit can be weeks
  old; if the page has changed, say so or drop the item.

## Translate into the prospect's terms

One sentence per item, in this shape: *what we saw* (literal string or count, with the
URL), then *what it means for them* (a consequence they recognise), with no figure that the
audit did not measure.

| Audit wording | Prospect's terms (example) |
|---|---|
| NOINDEX on 12 of 40 product pages | 12 of your 40 products cannot appear in Google results today |
| Canonical points to another host | Google may credit a different address than yours for these pages |
| No Organization markup, no sameAs | Search engines and AI assistants get no machine-readable card saying who the company is |
| robots.txt blocks GPTBot | ChatGPT's crawler is told not to read the site; whether that matters is the client's choice |
| Titles missing on 30 % of pages | One page in three shows no title of its own in search results |

The second column states a mechanism, never an outcome in money or visits. "Cannot appear"
is fine when the evidence proves it; "you are losing 400 visits a month" is not, because no
one measured it.

## Turn each item into work

1. The work: the exact change (template, setting, file, page) as the audit's `fix` column
   describes it, made concrete for this site.
2. The deliverable: what the client holds at the end (changed pages, a configured setting, a
   change list for their developer, a written page).
3. The done-when check: copied from the audit's `done_when` column, so the client can verify
   the result with the same evidence.
4. The effort in weeks, as a range. Sizing comes from the user's own experience; when they
   give none, mark it `assumed` and ask.
5. Who does what: what the user does, what the client must provide (access, approvals,
   content), what depends on a third party.

Always end the scope with a re-check step: re-crawl, compare with the original evidence, and
report each fix as confirmed or not.

## Prices and packages

- Prices, packages, units, payment terms and validity come only from the user's offer file
  (`templates/offers.csv` is the empty model). Copy them as written, labelled `reported`.
- Without an offer file, leave `{price}` visible in the draft and ask the user for their
  rates in the same message as the other missing inputs. Never suggest a "market rate".
- Match the scope to a package only when the package's `includes` column covers the work;
  otherwise list the gap and let the user decide.

## Expected effects

- Write what the fix changes for certain (the page can be indexed, the markup is valid, the
  crawler is allowed) and what stays out of anyone's hands (whether engines rank or cite it).
- Any range of effect starts at zero and is tied to an item: "from no change to these 12
  pages becoming eligible", not "+30 % traffic".
- No ROI, revenue, traffic, ranking, conversion or AI-citation projection, even when the
  prospect asks. Offer instead to measure a baseline now and compare after the work.
