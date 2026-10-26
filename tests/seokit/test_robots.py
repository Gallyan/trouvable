import unittest

from tests.support import LocalSite, html

from seokit import robots
from seokit.fetch import Fetcher

# Shape of a real robots.txt read on 2026-10-21: a broad Allow written before the Disallow lines.
ALLOW_FIRST = ("User-agent: *\nAllow: /\nDisallow: /contact-mail\nDisallow: /formulaire.php\n\n"
               "Sitemap: https://site.test/sitemap.xml\n")


class MatchingTest(unittest.TestCase):
    def test_longest_rule_wins_whatever_the_order(self):
        groups = robots.parse(ALLOW_FIRST)

        self.assertFalse(robots.allowed(groups, "seokit-audit", "https://site.test/contact-mail"))
        self.assertFalse(robots.allowed(groups, "seokit-audit", "https://site.test/formulaire.php?x=1"))
        self.assertTrue(robots.allowed(groups, "seokit-audit", "https://site.test/"))
        self.assertTrue(robots.allowed(groups, "seokit-audit", "https://site.test/contact"))

    def test_allow_wins_a_tie(self):
        groups = robots.parse("User-agent: *\nDisallow: /page\nAllow: /page\n")

        self.assertTrue(robots.allowed(groups, "bot", "https://x.test/page"))

    def test_groups_for_one_agent_are_merged(self):
        groups = robots.parse("User-agent: bot\nDisallow: /a\n\nUser-agent: *\nDisallow: /\n\n"
                              "User-agent: BOT\nDisallow: /b\n")

        self.assertFalse(robots.allowed(groups, "bot", "https://x.test/a/1"))
        self.assertFalse(robots.allowed(groups, "bot", "https://x.test/b/1"))
        self.assertTrue(robots.allowed(groups, "bot", "https://x.test/c"))
        self.assertFalse(robots.allowed(groups, "other", "https://x.test/c"))

    def test_wildcards_and_end_anchor(self):
        groups = robots.parse("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/x\n")

        self.assertFalse(robots.allowed(groups, "bot", "https://x.test/doc/a.pdf"))
        self.assertTrue(robots.allowed(groups, "bot", "https://x.test/doc/a.pdf?download=1"))
        self.assertFalse(robots.allowed(groups, "bot", "https://x.test/tmp-1/x"))

    def test_wildcard_matching_agrees_with_a_reference_regex(self):
        import re

        patterns = ["/a*b", "/a*b$", "/*", "/*$", "/a**b", "*.pdf$", "/x*y*z", "/x*y*z$", "/a", "/a$", "/$"]
        paths = ["/", "/ab", "/axb", "/axbx", "/a/b/c.pdf", "/c.pdf?x", "/xyz", "/xyyz", "/xzy", "/a", "/aa"]

        for pattern in patterns:
            anchored = pattern.endswith("$")
            body = pattern[:-1] if anchored else pattern
            regex = "".join(".*" if c == "*" else re.escape(c) for c in body) + ("$" if anchored else "")

            for path in paths:
                self.assertEqual(robots.rule_matches(pattern, path), re.match(regex, path) is not None,
                                 f"{pattern} on {path}")

    def test_hostile_pattern_is_fast(self):
        import time

        pattern = "/" + "*a" * 60 + "*b"
        path = "/" + "a" * 5000
        started = time.monotonic()

        self.assertFalse(robots.rule_matches(pattern, path))
        self.assertLess(time.monotonic() - started, 0.5)

    def test_robots_txt_itself_is_always_allowed(self):
        self.assertTrue(robots.allowed(robots.parse("User-agent: *\nDisallow: /\n"), "bot",
                                       "https://x.test/robots.txt"))

    def test_product_token(self):
        self.assertEqual(robots.product_token("seokit-audit/0.1 (+manual SEO review)"), "seokit-audit")
        self.assertEqual(robots.product_token(""), "*")


class FetcherRobotsTest(unittest.TestCase):
    def test_allow_first_file_still_blocks_the_disallowed_path(self):
        routes = {
            "/robots.txt": (200, {"Content-Type": "text/plain"}, ALLOW_FIRST.encode()),
            "/contact-mail": html("<p>should not be fetched</p>"),
            "/": html("<p>home</p>"),
        }

        with LocalSite(routes) as site:
            fetcher = Fetcher(delay=0)
            blocked = fetcher.get(site.url("/contact-mail"))
            home = fetcher.get(site.url("/"))

        self.assertIsNone(blocked.status)
        self.assertEqual(blocked.error, "blocked by robots.txt")
        self.assertNotIn("/contact-mail", [path for path, _ in site.hits])
        self.assertEqual(home.status, 200)

    def test_server_error_on_robots_txt_means_full_disallow(self):
        routes = {
            "/robots.txt": (503, {"Content-Type": "text/plain"}, b"down"),
            "/": html("<p>home</p>"),
        }

        with LocalSite(routes) as site:
            response = Fetcher(delay=0).get(site.url("/"))

        self.assertIsNone(response.status)
        self.assertIn("RFC 9309", response.error)

    def test_missing_robots_txt_allows_everything(self):
        with LocalSite({"/": html("<p>home</p>")}) as site:
            response = Fetcher(delay=0).get(site.url("/"))

        self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
