# Where a French local business is listed

Read on 2026-10-25 on each service's own pages. Listings are created and edited by the owner;
Claude prepares the content (one card for all, see `templates/card.json`).

| Platform | What it is (official) | Cost | Note |
|---|---|---|---|
| Google Business Profile | business.google.com | free | See `gbp-rules.md`; feeds Search and Maps |
| Apple Business (formerly Apple Business Connect) | business.apple.com: "Claim your location on Maps so millions of customers can connect with your business." Apple's newsroom (24 March 2026): "Apple Business Connect will no longer be available once Apple Business launches"; data migrated | basic service free | Feeds Apple Plans, Siri; say "Apple Business", not "Business Connect" |
| Bing Places for Business | bing.com/forbusiness (bingplaces.com redirects there); Bing blog, 3 Oct 2025: "a free online platform". Google sync help page (bing.com/forbusiness/help/syncGoogleBusinessProfile, pasted by the user on 2026-10-25): import of name, address, phone, hours and photos, sync weekly, every two weeks or monthly; a profile verified on Google « Bing vérifie automatiquement »; publication « généralement 7 à 12 jours » | free | Synced listings cannot be edited in Bing: « Mettez à jour la fiche dans Google, puis synchronisez-la ». The sync « peut créer des référencements en double » and categories may not match: check after import. So fix the Google profile first |
| PagesJaunes (Solocal) | pagesjaunes.fr/plusdeservices/gerer-ma-fiche-pagesjaunes: managing the listing is « facile et gratuit »; requires « Un numéro SIRET actif », listing « sous réserve d'accord de Solocal » | free basic listing, paid options | Free tools: update, news, reply to reviews |
| Waze | Waze Ads ended on 31 August 2023 (support.google.com/wazeads). A place can be added from the app; "The place will be reviewed by our community of volunteer map editors." | free | No business tool; check the place once, from the app |

Beyond these, trade directories (professional bodies, chambers of commerce, local business
networks) and niche platforms are found and scored with seo-offsite. A listing site that asks
for payment to "boost" rankings or sells reviews is a red flag (seo-offsite
`references/red-flags.md`).

## The legal notice page is a NAP source

Site publisher obligations, article 1-1 of loi n° 2004-575 (LCEN), in force since 23 May 2024
(Légifrance; the former article 6 III now deals with internet access providers: do not cite it
for legal notices), as summarised by entreprendre.service-public.gouv.fr/vosdroits/F37351
(checked by the page on 13 October 2026): identity (company name, legal form and capital, or name and « EI »),
head office address, email and phone, RCS and/or RNE number, VAT number where applicable, and
the host's name, address and phone. These may sit in the CGV or on a dedicated page. The
address and phone stated there are compared like any other source by `nap_check.py`; a legal
notice that disagrees with the shop sign is a finding. This plugin checks consistency only; it
gives no legal advice.
