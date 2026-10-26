# hreflang check list

IDs and severities are a design choice of this skill, to calibrate. The underlying rules
(value syntax, reciprocity, x-default, where annotations may be declared) must be verified
against Google Search Central's current page on localized versions before use; re-read it,
date it, and quote it for any finding the user disputes.

| ID | Check | Severity |
|---|---|---|
| H01 | Each page in a cluster lists itself (self-reference) | warning |
| H02 | Return links: if A lists B, B lists A (reciprocity) | error |
| H03 | Language codes valid (ISO 639-1), optional script (ISO 15924, `zh-Hant`), optional region (ISO 3166-1 alpha-2); no `en-UK`-style errors, no numeric regions (`es-419`); a region alone is read as a language (Google, read 2026-10-24) | error |
| H04 | Only one URL per language-region value inside a cluster | error |
| H05 | Annotated URLs return 200, are not redirected, not noindex | error |
| H06 | Annotated URL equals the page's canonical (no hreflang to non-canonical URLs; no canonical pointing to another language) | error |
| H07 | HTML, HTTP header and sitemap annotations agree when more than one method is used | error |
| H08 | Absolute URLs with the correct protocol and host | error |
| H09 | x-default set when the site has a language chooser or a fallback page (optional otherwise) | info |
| H10 | Declared language matches the page's actual language (`lang` attribute, text sample) | warning |
| H11 | Every page of the language sitemap belongs to a cluster, or is knowingly single-language | info |
| H12 | Cluster completeness: pages missing in one language are listed, not linked to the home page of that language | warning |

## Priority in the report

1. Errors that break whole clusters (H02, H06, H07) across a template.
2. Errors on single pages (H03, H04, H05, H08).
3. Warnings, then info.

Fixes are given where annotations are generated (CMS plugin, template, sitemap generator),
not page by page, unless the site is hand-written.

## Manual route sample

Without the script, check at least 3 clusters: the home page, one high-traffic page, one
recent page. For each, record the annotations from the three sources side by side.
