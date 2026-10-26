# City and area pages: the doorway gate

Google's spam policies (developers.google.com/search/docs/essentials/spam-policies, updated
2026-08-28, read on 2026-10-25): "Doorway abuse is when sites or pages are created to rank for
specific, similar search queries", with the example "Having multiple domain names or pages
targeted at specific regions or cities that funnel users to one page".

A page per town or per town × service is legitimate when it gives the visitor from that place
something the other pages do not. Every page passes all four questions, or it is not written
(new) or is merged into a broader page (existing).

| Question | Pass | Fail |
|---|---|---|
| Real presence | An address there, or proven work there (jobs done, customers, trips) | The town is only in the service area list |
| Own facts | At least one fact true only of that place: address and access, team on site, local prices or delays, jobs done there with photos, local rules | Only the town name changes |
| Distinct need | Someone searching from there needs something the main service page does not give | The main service page already answers |
| Lead to action | Contact, booking or quote for that place on the page | A link that funnels to one generic page |

`city_pages.py` gives leads: pairs `near_duplicate` once the place names are removed, and
`thin` pages. A lead is read, never a verdict: say which question fails, quoted from the page.

## Decisions

| Situation | Decision |
|---|---|
| Passes all four | Keep; add what is missing |
| Real presence but no own facts yet | Enrich with facts the business supplies, or wait |
| No presence, no own facts | Merge into the service page (301 to it), list the towns served in plain text there |
| Dozens of near-identical pages | Stop generating; keep the few that pass, merge the rest |

Never fill a page with invented local facts, made-up jobs, fake testimonials or stock photos
presented as local work.
