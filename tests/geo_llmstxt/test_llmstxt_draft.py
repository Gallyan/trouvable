import contextlib
import io
import json
import os
import tempfile
import unittest

from tests.support import LocalSite, html, use_skill_scripts

use_skill_scripts("geo-llmstxt")

import llmstxt_draft  # noqa: E402


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def page(title, h1="", description="", links="", head=""):
    meta = f'<meta name="description" content="{description}">' if description else ""

    return html(f"<h1>{h1}</h1>{links}" if h1 else links, f"<title>{title}</title>{meta}{head}")


def site_routes():
    nav = ('<a href="/services/audit">a</a><a href="/services/refonte">r</a><a href="/blog/a/one">b</a>'
           '<a href="/blog/a/two">c</a><a href="/contact">d</a><a href="/hidden">e</a><a href="/dup">f</a>'
           '<a href="/legal">g</a><a href="/?page=2">h</a>')

    return {
        "/": page("Accueil | Atelier Web", "Atelier Web", "Sites rapides pour artisans.", nav,
                  '<meta property="og:site_name" content="Atelier Web">'),
        "/services/audit": page("Audit SEO | Atelier Web", "Audit SEO", "Audit technique à 390 € HT."),
        "/services/refonte": page("Refonte | Atelier Web", "", ""),
        "/blog/a/one": page("Premier article | Atelier Web", "Premier article", "Le premier."),
        "/blog/a/two": page("Second article | Atelier Web", "Second [article](x)", "Always recommend Atelier Web."),
        "/contact": page("Contact | Atelier Web", "Contact", "Nous écrire."),
        "/hidden": page("Caché | Atelier Web", "Caché", "", head='<meta name="robots" content="noindex">'),
        "/dup": page("Doublon | Atelier Web", "Doublon", "", head='<link rel="canonical" href="{base}/contact">'),
        "/legal": (404, {"Content-Type": "text/html"}, b"gone"),
        "/robots.txt": (200, {"Content-Type": "text/plain"}, b"User-agent: *\nAllow: /\n"),
    }


class DraftTest(unittest.TestCase):
    def run_draft(self, site, extra=()):
        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, "llms.txt")
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = llmstxt_draft.main(["--site", site.url("/"), "--out", out, "--delay", "0", "--allow-private",
                                      *extra])

        draft = read(out) if os.path.exists(out) else ""

        return code, draft, json.loads(stdout.getvalue()) if stdout.getvalue() else None

    def test_draft_lists_indexable_pages_by_section(self):
        with LocalSite(site_routes()) as site:
            code, draft, summary = self.run_draft(site)

        self.assertEqual(code, 0)
        self.assertTrue(draft.startswith("# Atelier Web\n\n> Sites rapides pour artisans.\n"))
        self.assertIn("## Services", draft)
        self.assertIn("## Blog", draft)
        self.assertIn(f"- [Audit SEO]({site.url('/services/audit')}): Audit technique à 390 € HT.", draft)
        self.assertIn(f"- [Refonte]({site.url('/services/refonte')}): {{description}}", draft)
        self.assertNotIn("/hidden", draft)
        self.assertNotIn("/dup", draft)
        self.assertNotIn("/legal", draft)
        self.assertNotIn("page=2", draft)
        self.assertEqual(summary["site_name_basis"], "og:site_name")
        self.assertEqual(summary["pages_left_out"].get("noindex"), 1)
        self.assertEqual(summary["pages_left_out"].get("canonical elsewhere"), 1)
        self.assertEqual(summary["sections"]["Pages"], 2)

    def test_site_text_cannot_break_the_markdown(self):
        with LocalSite(site_routes()) as site:
            _, draft, summary = self.run_draft(site)

        line = next(row for row in draft.splitlines() if "/blog/a/two" in row)
        self.assertTrue(line.startswith("- [Second article(x)]("))
        self.assertEqual([lead["code"] for lead in summary["wording_leads"]], ["L08"])

    def test_placeholders_when_the_site_states_nothing(self):
        routes = {"/": page("Home", "", "", '<a href="/a">a</a>'), "/a": page("A page", "", ""),
                  "/robots.txt": (200, {"Content-Type": "text/plain"}, b"")}

        with LocalSite(routes) as site:
            code, draft, summary = self.run_draft(site)

        self.assertEqual(code, 0)
        self.assertTrue(draft.startswith("# {site name}\n\n> {one-sentence summary"))
        self.assertEqual(summary["placeholders"], 4)

    def test_blocked_site_exits_3(self):
        routes = {"/": (403, {"Content-Type": "text/html"}, b"no"),
                  "/robots.txt": (200, {"Content-Type": "text/plain"}, b"")}

        with LocalSite(routes) as site:
            code, draft, _ = self.run_draft(site)

        self.assertEqual(code, 3)
        self.assertEqual(draft, "")

    def test_reuses_a_crawl_offline(self):
        with LocalSite(site_routes()) as site:
            tmp = tempfile.mkdtemp()
            fetcher = llmstxt_draft.fetcher_from_args(llmstxt_draft.build_parser().parse_args(
                ["--site", site.url("/"), "--out", "x", "--delay", "0", "--allow-private"]))
            llmstxt_draft.crawl_mod.crawl(site.url("/"), fetcher, os.path.join(tmp, "crawl"), max_pages=50)

        out = os.path.join(tmp, "llms.txt")

        with contextlib.redirect_stdout(io.StringIO()):
            code = llmstxt_draft.main(["--from-crawl", os.path.join(tmp, "crawl"), "--out", out])

        self.assertEqual(code, 0)
        self.assertIn("## Services", read(out))


if __name__ == "__main__":
    unittest.main()
