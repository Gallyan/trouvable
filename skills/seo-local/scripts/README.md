# Scripts

Python 3.9+ standard library only, read-only, nothing to install. Shared code in `seokit/`
(do not edit the copy). Network: GET only, this tool's own identifiable user agent, about 2
requests per second (`--delay`), robots.txt respected, timeouts, size cap (`--max-bytes`). A
401/403/429 stops the run without workaround (exit 3). Exit 2 on bad input. Site text in the
output is quoted data (`*_quote` fields).

## nap_check.py

```
python3 scripts/nap_check.py --card card.json --site https://example.fr/ --out nap.json
python3 scripts/nap_check.py --card card.json --listings listings.csv --out nap.json
python3 scripts/nap_check.py --card card.json --file ./public/contact.html
```

- **Card** (`templates/card.json`): name, street, postal code, city and phone as the business
  really is. It is the reference every source is compared with.
- **Pages**: with `--site`, the home page plus up to `--max-pages` (default 8) same-site pages it
  links to whose path or link text looks like contact, legal notice, about, access or opening
  hours, on the site named by `--site` even when the home page redirects elsewhere; `--url` and
  `--file` add pages (a local file above `--max-bytes` is refused, like a fetched page).
- **Per page**: `match` or `absent` for name, street, postal code and city in the visible text
  (accents, case, punctuation and street abbreviations such as `bd`, `av`, `r` ignored); for the
  phone, `match`, `differs` (other French numbers found, quoted) or `absent`, from the text and
  `tel:` links. Every JSON-LD object that states an `address` or a `telephone` is compared field
  by field.
- **Listings** (`templates/listings.csv`): the rows the user copied from each directory,
  compared field by field. Directories are never fetched.
- **Summary**: counts per field and every `differs` with where it was found.
- **JSON-LD**: values nested deeper than 20 levels are ignored rather than crashing the run.
- **Limits**: static HTML only; an address in an image or loaded by JavaScript is `absent`;
  phone patterns are French numbers.

## city_pages.py

```
python3 scripts/city_pages.py --urls city-pages.txt --places "Lyon,Villeurbanne,Bron" --out city.json
python3 scripts/city_pages.py --file lyon.html --file bron.html --places-file places.txt
```

- **Text**: the main content of each page (static HTML), with every place of `--places` or
  `--places-file` replaced by one token.
- **Pairs**: Jaccard similarity of 5-word sequences (`--shingle`) for every pair at or above
  0.5; `near_duplicate` from 0.8 (heuristic, to calibrate).
- **Per page**: title and H1 quoted, places named, main word count, share of sequences found on
  no other page (`unique_share`), closest similarity, leads `near-duplicate` and `thin` (under
  250 words, heuristic).
- **Caps**: 200 pages in all (local files first, then URLs); the first 20,000 words of main
  text per page (`text_truncated` when cut); local files above `--max-bytes` refused.
  **Limits**: wording only, not usefulness; places not listed lower the similarity.
