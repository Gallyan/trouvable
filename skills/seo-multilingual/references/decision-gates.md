# Decision gates

Answer each gate yes / no / unknown, with its evidence and tag. Stop at the first gate
that ends the run. The gate order and wording are a design choice of this skill, to calibrate.

| # | Gate | If no | Evidence to cite |
|---|---|---|---|
| G1 | Are the current language versions mostly indexed and getting non-brand impressions? | Verdict `wait`: fix indexing / content in the current language first | sitemap count vs indexed count (`reported`), non-brand impressions (`reported`) |
| G2 | Can the business serve the target market (sell, ship, invoice, support, legal pages) in that language? | `wait` | user answer (`reported`) |
| G3 | Is there evidence of demand in the target language (queries in Search Console from that country/language, customer requests, sales, local search results showing the need)? | `wait`, or `main language first` if the current language still has headroom | export rows, emails, local results read on {date} |
| G4 | Are the foreign-language searches mostly product or brand names typed by the market already served? | If yes: `shared language` — keep an alias list in the current language, translate nothing | query list with the share of name-only queries (`measured` on the export) |
| G5 | Is a named native reviewer available for every page published? | `wait` (a draft translation may be prepared but not published) | reviewer name and role (`reported`) |
| G6 | Are there hours each week to keep the language current (prices, versions, legal)? | `wait` | user hours (`reported`) vs pages to maintain (`measured`) |
| G7 | Can the pilot be limited to a few complete clusters with measurable success criteria? | redesign the pilot | rollout sheet draft |

All gates passed → `trial`.

Each verdict other than `trial` names the alternative in one line (usually: strengthen the
current language first, or the alias list).

## Machine translation

Machine or AI translation is acceptable as a draft for a reviewer. Publishing it in bulk,
unreviewed and adding nothing can fall under Google's spam policies on content produced at
scale: re-read the current spam policies page, quote the relevant section and date it
before naming the policy in the memo.
