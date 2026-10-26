# Own-product rules

Applies when the user makes, sells, resells or earns a commission on any product in the panel.
These rules are a design choice of this skill. Legal requirements on disclosure and
comparative advertising vary by country: point the user to the official sources for their
market (consumer protection authority, advertising standards body) and to counsel; do not
state them as settled.

## Facts

- Facts about the user's product come from the user, with the page that states them publicly.
  Claude may read that page to copy the literal string, but the row stays `pending-owner`
  until the user confirms it.
- A fact the user cannot point to on a public page is not used in the comparison table.
- A missing own-product fact leaves gate 3 `PENDING`: publication is blocked.
- The same attributes, the same proof standard and the same recheck cadence as competitors.

## Placement

- The user's product appears **last** in lists, tables and the verdict.
- Its section opens with its **limits** (who should not choose it), then its strengths.
- The verdict may recommend a competitor for some situations; if the decision table never
  does, gate 7 should be re-examined.

## Disclosure

- A visible line before the first product mention, in plain words, for example:
  "We make {product}. This page compares it with alternatives; it is not an independent
  review." Adapt to the user's language.
- Affiliate links: disclosed near the links and in the opening line; the page does not hide
  that a commission exists.
- No disclosure in a tooltip, footer-only or image-only.

## Requests to refuse, with the legitimate route

| Request | Answer |
|---|---|
| "Say we are the fastest / cheapest / best" | Only if checked on that attribute for every product; otherwise state the measured difference with its source |
| "Add some reviews / a rating" | No invented reviews; quote real public reviews with source and date, or none |
| "Make it look independent" | Disclosure stays; the page can still be useful by being checkable |
| "Leave out competitor X" | Explain the exclusion criterion on the page, or include X |
