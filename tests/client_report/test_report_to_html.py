import contextlib
import io
import os
import re
import tempfile
import unittest

from tests.support import use_skill_scripts

use_skill_scripts("client-report")

import report_to_html  # noqa: E402


def render(markdown, **kwargs):
    return report_to_html.render_document(markdown, **kwargs)


class RenderTest(unittest.TestCase):
    def test_structure(self):
        doc = render("# Monthly report\n\nIntro **bold**, *it* and `code`.\n\n## Summary\n\n- a\n  - b\n- c\n\n"
                     "1. one\n2. two\n\n## Next\n\n> quoted\n\n---\n\n```\nx < y\n```\n")

        self.assertIn("<title>Monthly report</title>", doc)
        self.assertIn("<strong>bold</strong>", doc)
        self.assertIn("<em>it</em>", doc)
        self.assertIn("<code>code</code>", doc)
        self.assertIn('<h2 class="first">Summary</h2>', doc)
        self.assertIn("<h2>Next</h2>", doc)
        self.assertRegex(doc, r"<li>a\n<ul>\n<li>b</li>\n</ul>\n</li>")
        self.assertIn("<ol>", doc)
        self.assertIn("<blockquote>", doc)
        self.assertIn("<hr>", doc)
        self.assertIn("<pre><code>x &lt; y</code></pre>", doc)

    def test_table(self):
        doc = render("| Check | Status |\n|---|:---:|\n| TITLE | fixed |\n| a \\| b |\n")

        self.assertIn("<th>Check</th>", doc)
        self.assertIn("<td>TITLE</td><td>fixed</td>", doc)
        self.assertIn("<td>a &#124; b</td><td></td>", doc)
        self.assertIn("<thead>", doc)

    def test_print_stylesheet_and_no_external_resource(self):
        doc = render("# T\n\n## A\n\ntext\n")

        self.assertIn("size: A4", doc)
        self.assertIn("break-before: page", doc)
        self.assertIn("default-src 'none'", doc)
        self.assertNotIn("<script", doc)
        self.assertNotIn("<link", doc)
        self.assertNotIn("<img", doc)
        self.assertNotRegex(doc, r"(src|href)=")
        self.assertNotRegex(doc, r"url\(")

    def test_title_and_lang_override(self):
        doc = render("# Ignored\n", title="Rapport <b>", lang="fr")

        self.assertIn("<title>Rapport &lt;b&gt;</title>", doc)
        self.assertIn('<html lang="fr">', doc)


class HostileInputTest(unittest.TestCase):
    def test_raw_html_is_text(self):
        doc = render("# Site <script>alert(1)</script>\n\nSee <img src=x onerror=alert(1)> & \"quote\"\n")
        body = doc.split("<body>")[1]

        self.assertNotIn("<script", body)
        self.assertNotIn("<img", body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertIn("&amp;", body)
        self.assertIn("&quot;quote&quot;", body)

    def test_script_in_table_cell(self):
        doc = render("| a | b |\n|---|---|\n| <script>x()</script> | \"><svg onload=1> |\n")
        body = doc.split("<body>")[1]

        self.assertNotIn("<script", body)
        self.assertNotIn("<svg", body)

    def test_links_and_images_are_text(self):
        doc = render("[click](javascript:alert(1)) and ![logo](https://cdn.example/l.png) and "
                     "[x\"](https://e.example/?a=\"><b>)\n")
        body = doc.split("<body>")[1]

        self.assertNotIn("<a ", body)
        self.assertNotIn("href", body)
        self.assertNotIn("<img", body)
        self.assertIn("click <span class=\"url\">(javascript:alert(1))</span>", body)
        self.assertIn("[image: logo]", body)
        self.assertNotIn("<b>", body)

    def test_markers_inside_code_stay_literal(self):
        doc = render("`**not bold** <i>`\n")

        self.assertIn("<code>**not bold** &lt;i&gt;</code>", doc)

    def test_control_characters_and_long_line(self):
        doc = render("a\x00b\x1bc " + "x" * 10000 + "\n")

        self.assertNotIn("\x00", doc)
        self.assertNotIn("\x1b", doc)
        self.assertIn("x" * 10000, doc)

    def test_unclosed_fence_and_emphasis(self):
        doc = render("**open bold\n\n```\n<code never closed>\n")

        self.assertIn("**open bold", doc)
        self.assertIn("&lt;code never closed&gt;", doc)

    def test_every_tag_is_from_the_allowed_set(self):
        hostile = ("# <h1>x</h1>\n\n<div onclick=1>*<em>*</div>\n\n| <tr> | `</td>` |\n|---|---|\n"
                   "| [a](<javascript:x>) | <style>body{}</style> |\n\n- <li>\n")
        body = render(hostile).split("<body>")[1]
        tags = set(re.findall(r"</?([a-z0-9]+)", body))

        self.assertTrue(tags <= {"h1", "h2", "h3", "p", "em", "strong", "code", "pre", "ul", "ol", "li", "table",
                                 "thead", "tbody", "tr", "th", "td", "span", "blockquote", "hr", "br", "body",
                                 "html"}, tags)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, args):
        out, err = io.StringIO(), io.StringIO()

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = report_to_html.main(args)

        return code, out.getvalue(), err.getvalue()

    def test_writes_file(self):
        source = os.path.join(self.tmp.name, "r.md")
        target = os.path.join(self.tmp.name, "r.html")

        with open(source, "w", encoding="utf-8") as handle:
            handle.write("# Rapport\n\nTexte é.\n")

        code, out, _ = self.run_main(["--in", source, "--out", target, "--lang", "fr"])

        with open(target, encoding="utf-8") as handle:
            self.assertIn("Texte é.", handle.read())

        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_bad_inputs(self):
        binary = os.path.join(self.tmp.name, "b.md")

        with open(binary, "wb") as handle:
            handle.write(b"\xff\xfe\xfa\x00bad")

        self.assertEqual(self.run_main(["--in", os.path.join(self.tmp.name, "none.md")])[0], 2)
        self.assertEqual(self.run_main(["--in", binary])[0], 2)
        self.assertEqual(self.run_main(["--in", binary, "--lang", "fr\"><script>"])[0], 2)


if __name__ == "__main__":
    unittest.main()


class DeepNestingTest(unittest.TestCase):
    def test_deep_blockquote(self):
        doc = render(">" * 3000 + " <b>deep</b>\n")

        self.assertLessEqual(doc.count("<blockquote>"), 6)
        self.assertIn("&lt;b&gt;deep", doc)
