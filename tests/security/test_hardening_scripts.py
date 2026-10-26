"""Hardening of script inputs left open by the security audits of 2026-10-25 and 2026-10-26:
symbolic links in a local folder, drafts and pages built to make regexes backtrack, raw text
on stderr, control characters in an IndexNow list, crawl planning on a huge sitemap."""

import contextlib
import io
import os
import tempfile
import time
import unittest

from tests.support import use_skill_scripts

use_skill_scripts("seo-schema")
import structured_data  # noqa: E402

use_skill_scripts("seo-fact-check")
import claim_scan  # noqa: E402
import perishable_facts  # noqa: E402

use_skill_scripts("geo-mentions")
import parse_answers  # noqa: E402

use_skill_scripts("seo-content-brief")
import competitor_outline  # noqa: E402

use_skill_scripts("geo-llmstxt")
import llmstxt_review  # noqa: E402

use_skill_scripts("seo-indexing")
import indexnow_ping  # noqa: E402

use_skill_scripts("seo-audit")
from seokit import crawl  # noqa: E402


class SymlinkTest(unittest.TestCase):
    def test_structured_data_skips_links_out_of_the_folder(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as site:
            secret = os.path.join(outside, "secret.html")

            with open(secret, "w", encoding="utf-8") as handle:
                handle.write("<p>secret</p>")

            with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as handle:
                handle.write("<p>home</p>")

            os.symlink(secret, os.path.join(site, "leak.html"))
            found = structured_data.local_files(site)

        self.assertEqual([os.path.basename(path) for path in found], ["index.html"])

    def test_parse_answers_skips_linked_files(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as folder:
            secret = os.path.join(outside, "secret.txt")

            with open(secret, "w", encoding="utf-8") as handle:
                handle.write("### q1 | ChatGPT | 1 | 2026-10-25 | FR\nsecret\n")

            os.symlink(secret, os.path.join(folder, "leak.txt"))
            blocks = parse_answers.load_blocks(folder, parse_answers.ParseNotes())

        self.assertEqual(blocks, [])


class MarkdownDraftTest(unittest.TestCase):
    def quick(self, call, *args):
        started = time.process_time()
        result = call(*args)
        self.assertLess(time.process_time() - started, 2.0)

        return result

    def test_claim_scan_is_linear_on_hostile_drafts(self):
        for text in ("<!--" * 50000, "# a" + " " * 50000 + "x", "![" * 50000, "[a](" * 50000):
            self.quick(claim_scan.markdown_segments, text)

        segments, _ = claim_scan.markdown_segments("# Title ##\n\ntext <!-- hidden --> [more](https://x.test)")

        for text in ("<!--" * 50000, "# a" + " " * 50000 + "x", "![" * 50000):
            self.quick(perishable_facts.markdown_page, "draft.md", text)

        self.assertEqual([(s.location, s.text) for s in segments][:2], [("h1", "Title"), ("p1", "text more")])


    def test_claim_scan_sentence_checks_are_linear(self):
        self.quick(claim_scan.PATH_LABEL_RE.search, "A" * 200000)
        self.quick(claim_scan.markdown_segments, "# T\n\n" + "A" * 200000)
        document = claim_scan.Document("markdown", claim_scan.markdown_segments("# T\n\n" + "1;" * 100000)[0])
        claims = self.quick(claim_scan.extract, document, "en")

        self.assertTrue(claims)
        self.assertTrue(any("checked on their first" in note for note in document.notes))
        self.assertEqual(claim_scan.PATH_LABEL_RE.search("Open Menu > Settings > Privacy").group(0),
                         "Open Menu > Settings > Privacy")

    def test_competitor_outline_time_tag_is_bounded(self):
        self.quick(competitor_outline.TIME_TAG.findall, "<time " * 50000)

        self.assertEqual(competitor_outline.TIME_TAG.findall('<time class="a" datetime="2024-05-01">'), ["2024-05-01"])


class OutputTest(unittest.TestCase):
    def test_llmstxt_review_quotes_urls_on_stderr(self):
        path = os.path.join(tempfile.mkdtemp(), "llms.txt")

        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# Site\n\n> Summary\n\n## Docs\n\n- [Home](http://127.0.0.1/a\x1b[2J\u202eTXT): page\n")

        err = io.StringIO()

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            llmstxt_review.main(["--file", path, "--max-links", "1"])

        self.assertNotIn("\x1b", err.getvalue())
        self.assertNotIn("\u202e", err.getvalue())

    def test_indexnow_refuses_urls_with_control_characters(self):
        path = os.path.join(tempfile.mkdtemp(), "urls.txt")

        with open(path, "w", encoding="utf-8") as handle:
            handle.write("https://example.test/a\u202e\n")

        with self.assertRaises(indexnow_ping.InputError):
            indexnow_ping.read_urls(path)


class CrawlPlanningTest(unittest.TestCase):
    def test_sample_planning_is_linear_in_sitemap_size(self):
        start = "https://example.test/"
        sitemap = {f"https://example.test/blog/{i}": None for i in range(50000)}

        class NoFetch:
            user_agent = "test"

            def get(self, url):
                raise AssertionError("no fetch expected with a cap of 0")

            def robots_text(self, url):
                return ""

        started = time.process_time()

        with tempfile.TemporaryDirectory() as out:
            crawl.crawl_listed(start, NoFetch(), out, 0, True, ["/blog/"], sitemap)

        self.assertLess(time.process_time() - started, 2.0)


if __name__ == "__main__":
    unittest.main()
