# Business models

The model decides what a "result" is, which pages matter most and which metrics go on the sheet.

| Model | Result that counts | Pages that matter first | Typical early rows |
|---|---|---|---|
| SaaS / app | sign-ups, trials | product, use-case, comparison, alternatives pages | seo-keyword-verdict on problem queries, seo-comparison-page, seo-offsite (directories, launch sites) |
| E-commerce | orders | category pages, top product pages | seo-audit (facets, duplicates), seo-internal-links, seo-schema (product data on the page) |
| Local service | calls, bookings, visits | homepage, service × area pages, contact | business profile and reviews (seo-offsite local variant), consistent name/address/phone |
| Lead generation (B2B, agency, consultant) | qualified enquiries | service pages, case studies | seo-content-brief for decision queries, seo-fact-check |
| Publisher / ads / affiliate | engaged sessions, revenue per page | evergreen guides, hubs | seo-fact-check (site mode for freshness); affiliate links disclosed |
| Open source / community | users, contributors, mentions | docs, README, landing page | seo-offsite (awesome lists, communities), geo-mentions |
| Not sure / mixed | ask once; otherwise `assumed` from the site | | |

Metric suggestions for each model go into `templates/metrics-sheet.md`. Conversions are only
measured if the user has tracking; otherwise mark them "not measured" and add a setup row.
