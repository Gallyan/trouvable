# Exit and archive criteria per language

Write these before launch. Thresholds are filled with the user and labelled as a design
choice of the site, not as norms. Defaults proposed below are a heuristic, design choice
of this skill, to calibrate.

## Exit criteria (decided at launch)

| Language | Review date | Keep if | Rework if | Exit if |
|---|---|---|---|---|
| {xx} | launch + 6 months (default) | non-brand clicks ≥ {n}/month on the pilot clusters, or ≥ {n} leads/sales | indexed but few clicks: hand to seo-keyword-verdict for the queries | under {n} indexed pilot pages, or no reviewer, or upkeep hours not available for 2 months |

A language also exits when its content can no longer be kept true (prices, legal pages)
with the hours available.

## Archive procedure (when exiting)

1. List all URLs of the language (sitemap + crawl), with clicks and links received.
2. Map each URL: 301 to the equivalent page in a kept language, or 410 when no equivalent
   exists. Do not redirect everything to a home page.
3. Remove the language from every hreflang cluster (HTML, header, sitemap) at the same
   time as the redirects; remove its sitemap.
4. Remove it from the language selector and internal links.
5. Keep the redirects in place for the long term (verify current guidance on how long).
6. Recheck at +2 and +8 weeks: redirects return the mapped status, no hreflang points to
   removed URLs, Search Console shows the old URLs dropping.

Record the decision, date and who approved it.
