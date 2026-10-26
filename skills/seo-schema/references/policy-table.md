# Policy table procedure

Build this table during the run, before any sentence about what Google does with a
markup type. Nothing in this file is a policy: it is the procedure to read the policy.

## Where to read

- Google Search Central, structured data section: the general guidelines page, the
  search gallery (list of supported features), and the feature page of each type found.
- schema.org type page, only for vocabulary (property names, expected types). schema.org
  does not decide what a search engine displays.
- Other engines (Bing…) only if the user asks, with their own official page.

Find the current URLs by search or navigation on the day of the run; do not reuse URLs
from memory without opening them. If a page cannot be opened, write "not read" in the row.

## One row per markup type

| Type | Feature in Google (as documented) | Required properties | Content rules that apply | Source URL | Read on |
|---|---|---|---|---|---|
| e.g. FAQPage | {what the page says, or "no feature listed"} | {from the page} | {e.g. marked-up content must be visible} | {url} | {YYYY-MM-DD} |

Rules:
- Quote or closely paraphrase the official page; never fill a cell from memory.
- If the documentation restricts a feature (to some site types, regions or devices),
  record the restriction literally.
- If the page shows a "last updated" date, record it next to the reading date.
- Types with no documented Google feature get the row anyway, with "no feature listed
  on {date}": the markup may still be valid and useful to other consumers.
- When the user's symptom is "stars or FAQ disappeared", check the feature page and the
  documentation change log for that period before suspecting the site.

## Use in the report

Every finding that depends on a policy cites the row by type. A finding that would need a
row you could not fill is downgraded to a question for the user.
