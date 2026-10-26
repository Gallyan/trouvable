# Link zones: classification heuristic and self-check

Everything here (zone rules, priority order, thresholds) is a **heuristic, design choice of
this skill, to calibrate** on real sites. HTML structure varies by theme; the rules can
misread a template, which is why the self-check below is mandatory.

## Zones

| Zone | Meaning |
|---|---|
| `header` | Site header: logo, top bar, account links |
| `nav` | Main or secondary navigation menus |
| `footer` | Site footer |
| `widget` | Sidebars, related posts, tag clouds, breadcrumbs, pagination, language switchers, author boxes |
| `editorial` | Links inside the main written content of the page |
| `unknown` | None of the rules matched |

`widget` carries a `subtype` when it can be told: `breadcrumb`, `pagination`, `related`,
`lang-switch`, `sidebar`, `tags`, `author`.

## Rules, in priority order (first match wins)

1. **Nearest landmark ancestor**: `<header>`, `<nav>`, `<footer>`, `<aside>` → header, nav,
   footer, widget. A `<header>` or `<footer>` inside an `<article>` is part of the article,
   not the site header or footer: skip it and keep climbing.
2. **ARIA roles** on ancestors: `banner` → header, `navigation` → nav, `contentinfo` →
   footer, `complementary` → widget.
3. **Class and id tokens** on ancestors (case-insensitive, whole tokens or hyphen parts):
   `header`, `masthead`, `topbar` → header; `nav`, `menu`, `navbar` → nav; `footer` → footer;
   `sidebar`, `widget`, `related`, `breadcrumb`, `pagination`, `pager`, `tags`, `share`,
   `lang`, `language` → widget (with subtype).
4. **Link attributes**: `hreflang` on the link, or a list of links to the same path in other
   languages → widget / `lang-switch`; `rel="prev"`/`"next"` → widget / `pagination`.
5. **Main content**: inside `<main>`, `<article>`, `role="main"`, or tokens `content`,
   `entry`, `post-body`, `prose` with none of the above → editorial.
6. Otherwise → `unknown`. More than 10 % of links in `unknown` (heuristic) means the rules
   do not fit this theme: report it.

**Position** is recorded as the link's order in the document and, for editorial links, the
index of the paragraph or list item that contains it.

## Self-check before trusting any count

1. Pick three pages of different templates (e.g. home, an article, a category page).
2. For each, list the script's counts per zone.
3. Compare with the page as seen in a browser (the user describes or confirms it) or with
   your own reading of the raw HTML: which links are in the menu, the footer, the body.
4. Record agreement per page: links classified the same way / links on the page.
5. If agreement is below 90 % on a template (heuristic), either fix the rule for that theme
   and rerun, or label every count from that template `estimated` and say why.
6. Put the result in the summary: "Zone sorting checked on 3 pages: 41/43, 18/18, 60/66".

## Thresholds for findings

| Finding | Rule |
|---|---|
| Orphan | In the sitemap (or URL list), zero inlinks from crawled pages |
| Navigation-only | All inlinks come from `header`, `nav` or `footer` |
| Weakly linked | At most 1 editorial inlink (home excluded) |
| Overloaded hub | More than 150 unique internal outlinks on one page, or editorial outlinks above 50 |
| Deep | More than 3 clicks from the home page |
| Broken | Internal target answers 4xx or 5xx |
| Redirected | Internal target answers 3xx |

On a capped or sampled crawl, a page may have inlinks from pages not crawled: label orphan
and weak-link counts `estimated` in that case.

## Internal rank

- Iterative rank over the crawled graph (damping 0.85, 50 iterations or convergence),
  with link weights by zone: editorial 1.0, widget 0.5, nav/header/footer 0.3 (heuristic).
- It models how the site's own links distribute attention. It is not Google's PageRank and
  does not predict rankings. Use it only to pick source pages for briefs.
