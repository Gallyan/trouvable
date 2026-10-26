# Manual route (no code execution or no web access from Python)

Use when `scripts/internal_links.py` is missing or code execution is off. Say in the report
that the manual route was used and on how many pages.

1. **Sample**: the home page, every section landing page, and 2 to 3 pages per template;
   15 to 30 pages in total. List them.
2. **Read each page's HTML** and note every internal link with its zone, using the rules in
   `references/link-zones.md` (header, nav, footer, widget, editorial), and its anchor.
3. **Search Console Links report** (verify the menu path in the live interface): export the
   "Top linked pages" internal table. Its counts are Google's view, `reported`, and include
   pages not in the sample; they do not split by zone.
4. **Orphans**: compare sitemap URLs with the union of link targets in the sample and in the
   Links report. Result is `estimated`.
5. Continue with the relation table and briefs as in the main workflow.
