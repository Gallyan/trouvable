import contextlib
import io
import json
import os
import tempfile
import unittest

from tests.support import LocalSite, html, use_skill_scripts

use_skill_scripts("seo-local")

import nap_check  # noqa: E402

CARD = {
    "name": "Boulangerie Dupré",
    "street": "12 boulevard Gambetta",
    "postal_code": "69003",
    "city": "Lyon",
    "phone": "04 72 00 00 01",
}

JSONLD = """<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
{"@type":"Bakery","name":"Boulangerie Dupre","telephone":"+33 4 72 00 00 02",
"address":{"@type":"PostalAddress","streetAddress":"12 bd Gambetta","postalCode":"69003","addressLocality":"Lyon"}}]}
</script>"""


def routes():
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, b""),
        "/": html('<h1>Boulangerie Dupré</h1><a href="/contact">Nous contacter</a><a href="/blog">Blog</a>',
                  JSONLD, "fr"),
        "/contact": html('<p>Boulangerie Dupré, 12 Bd Gambetta, 69003 LYON</p>'
                         '<a href="tel:+33472000001">Appeler</a><p>Fax : 04.72.00.00.09</p>', lang="fr"),
        "/blog": html("<p>Nos recettes</p>", lang="fr"),
    }


def write(data, suffix):
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as handle:
        handle.write(data)

    return handle.name


def run(args):
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = nap_check.main(args + ["--delay", "0", "--allow-private"])

    return code, json.loads(stdout.getvalue()) if stdout.getvalue().strip() else None


class NormaliseTest(unittest.TestCase):
    def test_phone_formats_share_one_key(self):
        keys = {nap_check.phone_key(value) for value in
                ("04 72 00 00 01", "+33 4 72 00 00 01", "0033 (0)4 72 00 00 01", "04.72.00.00.01", "+33472000001")}

        self.assertEqual(keys, {"33472000001"})

    def test_addresses_ignore_accents_case_and_abbreviations(self):
        self.assertEqual(nap_check.fold("12, Bd Gambetta"), nap_check.fold("12 boulevard GAMBETTA"))
        self.assertEqual(nap_check.fold("Saint-Étienne"), nap_check.fold("St Etienne"))

    def test_phone_pattern_finds_french_numbers_only(self):
        found = nap_check.PHONE.findall("Tél. 04 72 00 00 01, SIRET 123 456 789 00012, +33 6 12 34 56 78")

        self.assertEqual(len(found), 2)


class PageTest(unittest.TestCase):
    def test_site_pages_and_jsonld(self):
        card = write(json.dumps(CARD), ".json")

        with LocalSite(routes()) as site:
            code, data = run(["--card", card, "--site", site.url("/")])

        self.assertEqual(code, 0)
        pages = {source["url"].rsplit("/", 1)[-1]: source for source in data["sources"]}
        contact = pages["contact"]

        self.assertEqual({key: value["status"] for key, value in contact["fields"].items()},
                         {"name": "match", "street": "match", "postal_code": "match", "city": "match",
                          "phone": "match"})
        self.assertEqual(contact["other_phones"], ["04.72.00.00.09"])
        self.assertNotIn("blog", pages)

        entity = pages[""]["jsonld"][0]["fields"]

        self.assertEqual(entity["street"]["status"], "match")
        self.assertEqual(entity["name"]["status"], "match")
        self.assertEqual(entity["phone"]["status"], "differs")
        self.assertIn({"where": f"{pages['']['url']} JSON-LD Bakery", "field": "phone",
                       "found_quote": "+33 4 72 00 00 02"}, data["summary"]["differs"])

    def test_listings_are_compared_field_by_field(self):
        card = write(json.dumps(CARD), ".json")
        listings = write("source,url,name,street,postal_code,city,phone\n"
                         "PagesJaunes,https://example.test/pj,Boulangerie Dupré,12 bd Gambetta,69003,Lyon,0472000001\n"
                         "Apple Plans,,Dupré,12 rue Gambetta,69003,Lyon,\n", ".csv")
        code, data = run(["--card", card, "--listings", listings])
        first, second = data["sources"]

        self.assertEqual(code, 0)
        self.assertTrue(all(value["status"] == "match" for value in first["fields"].values()))
        self.assertEqual(second["fields"]["name"]["status"], "differs")
        self.assertEqual(second["fields"]["street"]["status"], "differs")
        self.assertEqual(second["fields"]["phone"]["status"], "absent")

    def test_incomplete_card_is_refused(self):
        card = write(json.dumps({"name": "X"}), ".json")
        code, _ = run(["--card", card, "--listings", card])

        self.assertEqual(code, 2)

    def test_blocked_site_stops(self):
        card = write(json.dumps(CARD), ".json")

        with LocalSite({"/robots.txt": (200, {}, b""), "/": (403, {}, b"no")}) as site:
            code, data = run(["--card", card, "--site", site.url("/")])

        self.assertEqual(code, 3)
        self.assertEqual(data["sources"], [])

    def test_local_file(self):
        card = write(json.dumps(CARD), ".json")
        page = write(html("<p>Boulangerie Dupré — 69003 Lyon</p>")[2].decode(), ".html")
        code, data = run(["--card", card, "--file", page])
        fields = data["sources"][0]["fields"]

        self.assertEqual(code, 0)
        self.assertEqual(fields["street"]["status"], "absent")
        self.assertEqual(fields["city"]["status"], "match")
        os.unlink(page)


class HostileInputTest(unittest.TestCase):
    def test_deep_jsonld_does_not_crash_the_run(self):
        card = write(json.dumps(CARD), ".json")
        deep = "[" * 900 + '"x"' + "]" * 900
        page = write(html(f'<script type="application/ld+json">{{"telephone":"x","name":{deep}}}</script>'
                          "<p>Boulangerie Dupré</p>")[2].decode(), ".html")
        out = os.path.join(tempfile.mkdtemp(), "nap.json")

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = nap_check.main(["--card", card, "--file", page, "--out", out])

        with open(out, encoding="utf-8") as handle:
            data = json.load(handle)

        self.assertEqual(code, 0)
        self.assertEqual(data["sources"][0]["fields"]["name"]["status"], "match")

    def test_site_urls_are_quoted(self):
        card = write(json.dumps(CARD), ".json")
        routes = {
            "/robots.txt": (200, {"Content-Type": "text/plain"}, b""),
            "/": html('<a href="/contact\u202eevil">Contact</a>', lang="fr"),
        }

        with LocalSite(routes) as site:
            _, data = run(["--card", card, "--site", site.url("/")])

        self.assertNotIn("\u202e", json.dumps(data, ensure_ascii=False))

    def test_contact_pages_stay_on_the_site_the_user_named(self):
        found = nap_check.candidate_pages("https://shop.example/", "https://other.example/",
                                          '<a href="https://other.example/contact">Contact</a>')

        self.assertEqual(found, [])

    def test_local_file_above_the_cap_is_refused(self):
        card = write(json.dumps(CARD), ".json")
        page = write("<p>" + "x" * 2000 + "</p>", ".html")
        code, _ = run(["--card", card, "--file", page, "--max-bytes", "1000"])

        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
