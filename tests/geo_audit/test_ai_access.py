import contextlib
import io
import json
import os
import tempfile
import unittest

from tests.support import LocalSite, html, use_skill_scripts

use_skill_scripts("geo-audit")

import ai_access  # noqa: E402

ROBOTS = b"""User-agent: *
Allow: /

User-agent: GPTBot
Disallow: /

User-agent: PerplexityBot
Disallow: /prices

Sitemap: {base}/sitemap.xml
"""

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{base}/guide</loc></url><url><loc>{base}/prices</loc></url><url><loc>{base}/app</loc></url>
</urlset>"""

LONG = "<p>" + "Kettles boil water fast and last for years. " * 30 + "</p>"


def routes():
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, ROBOTS),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, SITEMAP),
        "/": html(LONG),
        "/guide": html(LONG + '<div data-nosnippet>secret</div>',
                       '<meta name="robots" content="max-snippet:50, noarchive">'),
        "/prices": (200, {"Content-Type": "text/html", "X-Robots-Tag": "nosnippet"}, html(LONG)[2]),
        "/app": html('<div id="root"></div>'),
        "/llms.txt": (404, {"Content-Type": "text/plain"}, b"none"),
    }


def run(args):
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = ai_access.main(args + ["--delay", "0", "--allow-private"])

    return code, json.loads(stdout.getvalue()) if stdout.getvalue().strip() else None


class AccessTest(unittest.TestCase):
    def test_agents_and_page_controls(self):
        with LocalSite(routes()) as site:
            code, data = run(["--site", site.url("/")])

        agents = {row["token"]: row for row in data["agents"]}
        pages = {page["url"].rsplit("/", 1)[-1]: page for page in data["pages"]}

        self.assertEqual(code, 0)
        self.assertEqual(agents["GPTBot"]["status"], "disallowed")
        self.assertFalse(agents["GPTBot"]["finding"])
        self.assertEqual(agents["PerplexityBot"]["status"], "partially disallowed")
        self.assertTrue(agents["PerplexityBot"]["finding"])
        self.assertIn("Disallow: /prices", agents["PerplexityBot"]["blocked_urls"][0]["line_quote"])
        self.assertEqual(agents["OAI-SearchBot"]["status"], "allowed")
        self.assertEqual(agents["OAI-SearchBot"]["group_used"], "*")
        self.assertEqual(data["search_agents_blocked"], ["PerplexityBot"])
        self.assertEqual(pages["guide"]["max_snippet"], 50)
        self.assertEqual(pages["guide"]["data_nosnippet_elements"], 1)
        self.assertTrue(pages["prices"]["nosnippet"])
        self.assertTrue(pages["guide"]["noarchive"])
        self.assertFalse(pages["prices"]["nocache"])
        self.assertTrue(pages["app"]["little_static_text"])
        self.assertEqual(data["llms_txt_status"], 404)
        self.assertTrue(all(agent != "GPTBot" for _, agent in site.hits))

    def test_local_robots_file_without_pages(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "robots.txt")

        with open(path, "w", encoding="utf-8") as handle:
            handle.write("User-agent: OAI-SearchBot\nDisallow: /\n")

        code, data = run(["--site", "https://example.invalid/", "--robots-file", path, "--no-pages"])
        agents = {row["token"]: row for row in data["agents"]}

        self.assertEqual(code, 0)
        self.assertEqual(agents["OAI-SearchBot"]["status"], "disallowed")
        self.assertTrue(agents["OAI-SearchBot"]["finding"])
        self.assertEqual(data["pages"], [])

    def test_stops_on_403(self):
        site_routes = routes()
        site_routes["/"] = (403, {"Content-Type": "text/html"}, b"no")

        with LocalSite(site_routes) as site:
            code, data = run(["--site", site.url("/")])

        self.assertEqual(code, 3)
        self.assertEqual(data["pages_not_read"][0]["reason"], "HTTP 403")


if __name__ == "__main__":
    unittest.main()
