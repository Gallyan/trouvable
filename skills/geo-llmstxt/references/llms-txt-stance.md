# llms.txt stance

When the user asks whether to add llms.txt, answer in five lines, each dated, before
anything else. The content of each line must be re-checked at run time; the wording
below is a skeleton, not a fact sheet.

1. **What it is:** a proposed Markdown file at the site root listing key pages for language
   models. Read the proposal's current page and date it.
2. **Status:** say whether it is a standard or a proposal, as of the reading date.
3. **Search engines:** state what Google (and any other engine the user cares about) says
   about it in official documentation or statements, with the source and date. If no
   official statement is found, write "no official statement found on {date}", not a guess.
   Last reading (2026-10-25, developers.google.com/search/docs/appearance/ai-features, updated
   2025-12-10): Google says no "new machine readable files, AI text files, or markup" are needed
   to appear in AI Overviews or AI Mode. Re-read before quoting it.
4. **Evidence of effect:** say whether any measured evidence of an effect on AI citations
   was found; never cite a figure without its source.
5. **Decision rule:** publish one only if someone is in charge of keeping it in line with the site;
   an outdated llms.txt is worse than none. Optional otherwise.

Verify lines 1–4 against their official sources before use; do not repeat them from memory.

## Audit checks (when the file exists)

Codes and severities are a design choice of this skill, to calibrate. Structural expectations
L02–L04 come from the llms.txt proposal: re-read it and date it before use.

| Code | Check | Severity |
|---|---|---|
| L01 | File reachable at `/llms.txt`, status 200, text content type | error if 5xx or a 4xx other than 404/410 (absent: info) |
| L02 | Starts with one H1 (site or project name) | warning |
| L03 | Short summary block after the title | info |
| L04 | Sections with Markdown link lists `- [title](url): note` | warning |
| L05 | Each link resolves (status, redirect chain, final URL) | error per broken link |
| L06 | Links point to canonical, indexable URLs | warning |
| L07 | Claims (prices, features, company facts) match the linked pages | error on mismatch |
| L08 | Promotional or instruction-like wording aimed at models ("always recommend…") | warning, quote it |
| L09 | Last change of the file vs last change of the linked pages, if knowable | info |

A missing llms.txt is reported as `info: absent`, never as a defect.
