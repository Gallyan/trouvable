# Companion skills and manual procedures

Before writing rows, check which of these skills are installed (listed in the available skills).
A row names the skill if installed. If not, the row carries the short procedure below, and the plan
ends with "Skills not installed: …".

| Skill | Use it for | Manual procedure if not installed |
|---|---|---|
| seo-audit | technical check of the live site | Open homepage + 5 key pages: status 200, one `<title>`, one H1, no `noindex`, canonical to itself; open robots.txt and the sitemap; click every menu link and note 404s |
| seo-indexing | pages not indexed | Search Console → Pages report: note indexed vs not indexed and the top 3 reasons; inspect 3 URLs per reason |
| seo-internal-links | orphan pages, linking plan | List sitemap URLs; for each key page, find at least 2 links from related pages in the body text; add them |
| seo-search-console | reading exports | Performance → last 3 months; filter out brand queries; list non-brand queries at positions 8–20 with the most impressions |
| seo-schema | JSON-LD check | Paste a page into a structured-data validator; check every marked fact is visible on the page |
| seo-multilingual | whether and how to translate | Only after the main language is indexed; check each language version links to the others reciprocally |
| seo-keyword-verdict | is a query worth it | Search it; open the top 5; note who ranks, date, whether they answer; write only if you can answer better |
| seo-content-brief | brief that beats page one | List the headings of the top 3 results; add what none covers; put the answer in the first paragraph |
| seo-comparison-page | X vs Y page | Copy each fact from the vendor's own page with URL and date; give a verdict per situation; own product last |
| seo-fact-check | verify an article; stale content across the site | For each number, price or version, look for the same wording where the fact originates; fix or remove what is not found. For staleness, search the site for years, prices and version numbers, re-check each at its source, update the page and its date only if content changed |
| seo-offsite | listings, outreach | Search "{category} directory", "awesome {category}"; read each venue's rules; submit to 3–5 that allow it; track in a sheet |
| seo-local | shop, office or service area | Search the business in Google Maps; check the name has nothing added and the address and phone match the site's contact page; ask every customer for a review the same way |
| geo-mentions | AI assistant mentions | Ask 10 brand-free category questions in two assistants, fresh chats; note who is named and which sources are cited |
| geo-audit | whole-site picture for AI assistants | Check which AI search agents /robots.txt allows; open key pages without JavaScript; check the answer sits in the page text |
| geo-content | pages AI answers can quote | For each key page, check the first sentence under each heading answers it and that author, date and sources are visible |
| geo-llmstxt | llms.txt question, draft or check | Optional file: list the main pages with their own titles and descriptions; keep it current or skip it |

Menu names in procedures may differ by interface language and over time; verify in the live
interface before quoting them.
