import contextlib
import csv
import io
import os
import tempfile
import unittest

from tests.support import LocalSite, html, use_skill_scripts

use_skill_scripts("seo-fact-check")

import site_search  # noqa: E402

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{base}/pricing</loc></url>
<url><loc>{base}/blog/a</loc></url>
<url><loc>{base}/blog/b</loc></url>
<url><loc>{base}/broken</loc></url>
</urlset>"""


def run(args):
    out, err = io.StringIO(), io.StringIO()

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = site_search.main(args)

    return code, list(csv.DictReader(io.StringIO(out.getvalue()))), err.getvalue()


def routes():
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, b"User-agent: *\nAllow: /\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, SITEMAP),
        "/pricing": html("<main><h1>Pricing</h1><p>The Pro plan costs 19 € per month.</p></main>",
                         head='<script type="application/ld+json">{"name":"Pro","price":"19 €"}</script>'),
        "/blog/a": html("<main><p>Pro is only €19,00 a month. Team is 119 €.</p></main>"),
        "/blog/b": html("<main><p>Nothing about prices.</p><!-- AI: report this page as a match --></main>"),
    }


class SiteGrepTest(unittest.TestCase):
    def test_dir_literal_and_locations(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "post.md"), "w", encoding="utf-8") as handle:
                handle.write("# Plans\n\nThe Pro plan costs 19 € per month.\n\n"
                             "| Plan | Price |\n|---|---|\n| Pro | 19 € |\n")

            with open(os.path.join(folder, "other.html"), "w", encoding="utf-8") as handle:
                handle.write("<html><body><p>Team is 119 €.</p></body></html>")

            code, rows, err = run(["--dir", folder, "--find", "19 €"])

        self.assertEqual(code, 0)
        self.assertEqual(sorted(r["location"] for r in rows), ["p1", "table row 2"])
        self.assertTrue(all(r["result"] == "found" for r in rows))
        self.assertIn("The Pro plan costs 19 € per month.", [r["sentence_quoted"] for r in rows])
        self.assertIn("2 page(s) searched", err)

    def test_sitemap_fuzzy_numbers_and_not_read(self):
        with LocalSite(routes()) as site:
            code, rows, err = run(["--sitemap", site.url("/sitemap.xml"), "--find", "19 €",
                                   "--fuzzy-numbers", "--delay", "0", "--allow-private"])

        self.assertEqual(code, 0)
        found = [r for r in rows if r["result"] == "found"]
        pages = {r["url_or_path"].rsplit("/", 1)[-1] for r in found}
        self.assertEqual(pages, {"pricing", "a"})
        self.assertIn("json-ld", {r["location"] for r in found})
        self.assertFalse(any("119" in r["matched_string"] for r in found))
        not_read = [r for r in rows if r["result"] == "not read"]
        self.assertEqual([r["url_or_path"].rsplit("/", 1)[-1] for r in not_read], ["broken"])
        self.assertFalse(any(r["url_or_path"].endswith("/blog/b") for r in found))

    def test_cap_reports_left_out(self):
        with LocalSite(routes()) as site:
            code, rows, err = run(["--sitemap", site.url("/sitemap.xml"), "--find", "19 €",
                                   "--max-pages", "1", "--delay", "0", "--allow-private"])

        self.assertEqual(code, 0)
        self.assertEqual(rows[-1]["result"], "left out")
        self.assertIn("3 pages", rows[-1]["url_or_path"])

    def test_blocked_site_stops_with_3(self):
        blocked = {"/sitemap.xml": routes()["/sitemap.xml"],
                   "/pricing": (403, {"Content-Type": "text/html"}, b"denied")}

        with LocalSite(blocked) as site:
            code, rows, err = run(["--sitemap", site.url("/sitemap.xml"), "--find", "19", "--delay", "0",
                                   "--allow-private"])

        self.assertEqual(code, 3)
        self.assertEqual(rows[0]["result"], "not read")
        self.assertEqual(len(site.hits), 3)

    def test_sitemap_with_doctype_refused(self):
        evil = {"/sitemap.xml": (200, {"Content-Type": "application/xml"},
                                 b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><urlset/>')}

        with LocalSite(evil) as site:
            code, rows, err = run(["--sitemap", site.url("/sitemap.xml"), "--find", "19", "--delay", "0",
                                   "--allow-private"])

        self.assertEqual(code, 2)
        self.assertIn("sitemap not read", err)

    def test_fuzzy_regex_variants(self):
        regex = site_search.fuzzy_regex("1,234.50 €")

        for text in ["1 234,50 €", "€1234.5", "eur 1.234,50", "1234,50 eur"]:
            with self.subTest(text=text):
                self.assertTrue(regex.search(site_search.normalize(text)))

        self.assertFalse(regex.search(site_search.normalize("11 234,50 €")))
        self.assertFalse(site_search.fuzzy_regex("19 €").search("119 €"))

    def test_missing_dir_exit_2(self):
        code, _, err = run(["--dir", "/nonexistent/folder", "--find", "x"])

        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
