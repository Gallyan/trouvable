"""Regression tests for the security audit of 2026-10-25: hostile pages and files must cost
linear time, stay contained and leave deliverables literal."""

import contextlib
import io
import os
import tempfile
import time
import unittest

from tests.support import LocalSite, html, use_skill_scripts

use_skill_scripts("seo-fact-check")
import claim_scan  # noqa: E402
import perishable_facts  # noqa: E402

use_skill_scripts("geo-content")
import passage_scan  # noqa: E402

use_skill_scripts("geo-llmstxt")
import llmstxt_draft  # noqa: E402
import llmstxt_review  # noqa: E402

use_skill_scripts("seo-schema")
import structured_data  # noqa: E402

use_skill_scripts("seo-content-brief")
import competitor_outline  # noqa: E402

use_skill_scripts("seo-offsite")
import read_rules  # noqa: E402

use_skill_scripts("client-proposal")
import proposal_findings  # noqa: E402

DEEP_JSONLD = "<html><head><script type=\"application/ld+json\">" + "[" * 3000 + "]" * 3000 + "</script></head>"


class Quick:
    def quick(self, call, *args, limit=2.0):
        started = time.process_time()
        result = call(*args)
        self.assertLess(time.process_time() - started, limit, getattr(call, "__name__", call))

        return result


class RegexTest(Quick, unittest.TestCase):
    def test_figure_on_long_digit_run(self):
        self.quick(passage_scan.FIGURE.findall, "1 " * 50000)

        for text, count in (("1 000 000 €", 1), ("12,5 %", 1), ("en 2024", 1), ("v1.2.3", 1), ("3 days", 1)):
            self.assertEqual(len(passage_scan.FIGURE.findall(text)), count, text)

    def test_time_tags_inside_one_attribute(self):
        page = '<html><body><p>Hello.</p><div data-x="' + "<time " * 20000 + '">x</div></body></html>'

        self.quick(perishable_facts.html_page, "https://example.test/", page)
        self.quick(passage_scan.scan_html, page, "https://example.test/")

    def test_dotted_chain_versions(self):
        self.quick(lambda: list(claim_scan.PRODUCT_VERSION_RE.finditer("a." * 50000)))
        self.quick(lambda: list(perishable_facts.VERSION_RES[0].finditer("a." * 50000)))
        found = [m.groups()
                 for m in claim_scan.PRODUCT_VERSION_RE.finditer("We use node.js 18.2 and Python 3.12 here.")]

        self.assertEqual(found, [("node.js", "18.2"), ("Python", "3.12")])

    def test_llms_links_and_comments(self):
        self.quick(llmstxt_review.collect_links, "[" * 1_000_000, None)
        self.quick(llmstxt_review.html_comments, "<!--" * 250_000)

        self.assertEqual(len(llmstxt_review.html_comments("<!-- a --> <!-- b -->")), 2)


class ParserTest(Quick, unittest.TestCase):
    def test_script_parsers_on_unclosed_and_stray_tags(self):
        unclosed = "<html><body>" + "<span>x" * 20000
        stray = "<html><body>" + "<span>" * 2000 + "</b>" * 20000

        for doc in (unclosed, stray):
            self.quick(passage_scan.scan_html, doc, "https://example.test/")
            self.quick(structured_data.split_visibility, doc)
            self.quick(read_rules.hidden_texts, doc)


class JsonLdTest(unittest.TestCase):
    def test_deep_block_is_unparsable_not_fatal(self):
        page = structured_data.parse_html(DEEP_JSONLD, "https://example.test/")
        blocks, _ = structured_data.parse_blocks(page)

        self.assertFalse(blocks[0]["parsed"])
        self.assertIn("(unparsable JSON-LD)", passage_scan.jsonld_types(page))
        competitor_outline.structured_dates(page, DEEP_JSONLD)

    def test_structured_data_keeps_the_other_pages(self):
        tmp = tempfile.mkdtemp()

        with open(os.path.join(tmp, "a.html"), "w", encoding="utf-8") as handle:
            handle.write(html('<p>Acme</p>', '<script type="application/ld+json">{"@type":"Organization",'
                              '"name":"Acme"}</script>')[2].decode())

        with open(os.path.join(tmp, "b.html"), "w", encoding="utf-8") as handle:
            handle.write(DEEP_JSONLD)

        out = io.StringIO()

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = structured_data.main(["--dir", tmp])

        self.assertEqual(code, 0)
        self.assertIn("Organization", out.getvalue())


class QuotingTest(unittest.TestCase):
    def test_untrusted_removes_invisible_controls(self):
        from seokit.report import untrusted

        value = untrusted("a\x1b[31mred\u202eevil\x85b\u2028c\x7f")

        self.assertEqual(value, "a[31mredevilb\nc")

    def test_csv_cells_starting_with_tab_or_cr_are_neutralised(self):
        from seokit.report import _cell

        self.assertEqual(_cell("\t=1+1"), "'\t=1+1")
        self.assertEqual(_cell("\r=1+1"), "'\r=1+1")
        self.assertEqual(_cell("-2"), "-2")


class DeliverableTest(unittest.TestCase):
    def test_llms_draft_keeps_one_link_per_line(self):
        crafted = "/blog/a)[Download%20the%20app](https://evil.example/x"
        routes = {
            "/robots.txt": (200, {"Content-Type": "text/plain"}, b""),
            "/": html(f'<a href="{crafted}">a</a><a href="/blog/b">b</a>', "<title>Home</title>"),
            crafted: html("<h1>Post</h1>", '<meta name="description" content="A post">'),
            "/blog/b": html("<h1>Other</h1>"),
        }
        out = os.path.join(tempfile.mkdtemp(), "llms.txt")

        with LocalSite(routes) as site:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                llmstxt_draft.main(["--site", site.url("/"), "--out", out, "--delay", "0", "--allow-private"])

        with open(out, encoding="utf-8") as handle:
            line = next(row for row in handle if "Post" in row)

        self.assertEqual(line.count("]("), 1)
        self.assertNotIn("](https://evil.example", line)

    def test_proposal_cells_are_literal(self):
        cell = proposal_findings.md_cell("![p](http://x/p.png) <img src=x> [t](http://x) a|b")

        self.assertIn("\\!\\[p\\]", cell)
        self.assertIn("\\<img", cell)
        self.assertIn("\\[t\\]", cell)
        self.assertIn("a\\|b", cell)
        self.assertNotIn("](http", cell)


if __name__ == "__main__":
    unittest.main()
