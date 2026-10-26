"""End to end: one local site with planted defects, crawled once, read by several skills.

Each script runs as a real process (python3 scripts/x.py), the way Claude runs it.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.support import ROOT, LocalSite, html

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
<url><loc>{base}/</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>{base}/blog/post</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>{base}/fr/</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>{base}/orphan</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>{base}/hidden</loc><lastmod>2026-10-01</lastmod></url>
</urlset>"""

NAV = '<header><a href="/">Home</a></header><nav><a href="/blog/post">Blog</a> <a href="/fr/">FR</a></nav>'
FOOT = '<footer><a href="/legal">Legal</a></footer>'
FAQ = ('<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage",'
       '"mainEntity":[{"@type":"Question","name":"Is it free?","acceptedAnswer":{"@type":"Answer",'
       '"text":"Yes, the basic plan is free forever for everyone."}}]}</script>')


def routes():
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, b"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, SITEMAP),
        "/": html(NAV + '<main><h1>Home</h1><p>Read <a href="/blog/post">our post</a> and '
                  '<a href="/gone">this old page</a> and <a href="/moved">that one</a>.</p>'
                  '<h3>Is it free?</h3><p>No, it costs 25 euros per month.</p></main>' + FOOT,
                  head='<title>Home</title><meta name="description" content="Home page">'
                       '<link rel="alternate" hreflang="en" href="{base}/">'
                       '<link rel="alternate" hreflang="fr" href="{base}/fr/">' + FAQ),
        "/blog/post": html(NAV + "<main><h1>Post</h1><p>Some text.</p></main>" + FOOT,
                           head='<title>Post</title><link rel="canonical" href="{base}/other">'
                                '<script type="application/ld+json">{"@type": "Article",</script>'),
        "/fr/": html(NAV + "<main><h1>Home</h1><p>Read our post and this old page.</p></main>" + FOOT,
                     head="<title>Home</title>", lang="fr"),
        "/orphan": html("<main><h1>Orphan</h1></main>", head="<title>Orphan</title>"),
        "/hidden": html("<main><h1>Hidden</h1></main>",
                        head='<title>Hidden</title><meta name="robots" content="noindex">'),
        "/legal": html(NAV + "<main><h1>Legal</h1></main>" + FOOT, head="<title>Legal</title>"),
        "/moved": (307, {"Location": "/legal"}, b""),
    }


def run(script, *args):
    path = os.path.join(ROOT, "skills", script)
    result = subprocess.run([sys.executable, path, *args, "--allow-private"], capture_output=True, text=True,
                            timeout=300, check=False)

    return result.returncode, result.stdout, result.stderr


class FixtureSiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = LocalSite(routes()).__enter__()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.audit = os.path.join(cls.tmp.name, "audit")
        code, _, err = run("seo-audit/scripts/site_crawl.py", "--url", cls.site.url("/"),
                           "--out", cls.audit, "--max-pages", "30")
        cls.audit_code, cls.audit_err = code, err
        cls.crawl = os.path.join(cls.audit, "crawl")

    @classmethod
    def tearDownClass(cls):
        cls.site.__exit__(None, None, None)
        cls.tmp.cleanup()

    def test_audit_flags_planted_defects(self):
        self.assertEqual(self.audit_code, 0, self.audit_err)

        with open(os.path.join(self.audit, "issues.csv"), encoding="utf-8") as handle:
            text = handle.read()

        for planted in ("307", "/gone", "/orphan"):
            self.assertIn(planted, text, f"{planted} not reported")

    def test_link_graph_reuses_the_crawl(self):
        out = os.path.join(self.tmp.name, "links")
        code, _, err = run("seo-internal-links/scripts/internal_links.py", "--from-crawl", self.crawl, "--out", out)
        self.assertEqual(code, 0, err)

        with open(os.path.join(out, "summary.json"), encoding="utf-8") as handle:
            summary = json.dumps(json.load(handle))

        self.assertIn("orphan", summary)

    def test_hreflang_finds_missing_return_link(self):
        code, stdout, err = run("seo-multilingual/scripts/lang_alternates.py", "--from-crawl", self.crawl, "--offline")
        self.assertIn(code, (0, 1), err)
        report = json.loads(stdout)
        self.assertTrue(report.get("findings") or report.get("errors"), stdout[:500])

    def test_jsonld_mismatch_and_parse_error(self):
        urls = f"{self.site.url('/')},{self.site.url('/blog/post')}"
        code, stdout, err = run("seo-schema/scripts/structured_data.py", "--urls", urls)
        self.assertIn(code, (0, 1), err)
        self.assertIn("FAQ", stdout)
        self.assertRegex(stdout, r"(?i)parse|invalid|J0")


if __name__ == "__main__":
    unittest.main()
