import contextlib
import io
import json
import unittest

from tests.support import LocalSite, html, use_skill_scripts

use_skill_scripts("seo-local")

import city_pages  # noqa: E402

TEMPLATE = ("<main><h1>Plombier à {city}</h1><p>Votre plombier à {city} intervient rapidement pour toute fuite, "
            "panne de chauffe-eau ou débouchage. Nos artisans qualifiés se déplacent à {city} et alentours "
            "sept jours sur sept, avec un devis gratuit et un tarif clair annoncé avant chaque intervention."
            "</p></main>")

REAL = ("<main><h1>Plombier à Bron</h1><p>Notre atelier est au 4 rue du Marché à Bron, à côté de la mairie. "
        "Les maisons du quartier Terraillon datent souvent des années soixante, avec des colonnes en fonte "
        "que nous remplaçons par du PVC. Le parking de la place Curial permet de déposer un ballon.</p></main>")


def routes():
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, b""),
        "/lyon": html(TEMPLATE.format(city="Lyon"), "<title>Plombier Lyon</title>", "fr"),
        "/villeurbanne": html(TEMPLATE.format(city="Villeurbanne"), "<title>Plombier Villeurbanne</title>", "fr"),
        "/bron": html(REAL, "<title>Plombier Bron</title>", "fr"),
    }


def run(args):
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = city_pages.main(args + ["--delay", "0", "--allow-private"])

    return code, json.loads(stdout.getvalue()) if stdout.getvalue().strip() else None


class CityPagesTest(unittest.TestCase):
    def test_swapped_place_pages_are_near_duplicates(self):
        with LocalSite(routes()) as site:
            urls = [site.url(path) for path in ("/lyon", "/villeurbanne", "/bron")]
            code, data = run(sum((["--url", url] for url in urls), []) + ["--places", "Lyon,Villeurbanne,Bron"])

        self.assertEqual(code, 0)
        self.assertEqual(len(data["pairs"]), 1)
        self.assertEqual(data["pairs"][0]["similarity"], 1.0)
        self.assertTrue(data["pairs"][0]["near_duplicate"])

        pages = {page["url"].rsplit("/", 1)[-1]: page for page in data["pages"]}

        self.assertIn("near-duplicate", pages["lyon"]["leads"])
        self.assertNotIn("near-duplicate", pages["bron"]["leads"])
        self.assertEqual(pages["bron"]["unique_share"], 1.0)
        self.assertEqual(pages["villeurbanne"]["places_named"], ["Villeurbanne"])
        self.assertIn("thin", pages["bron"]["leads"])
        self.assertNotIn("_text", pages["lyon"])

    def test_without_places_the_names_lower_similarity(self):
        with LocalSite(routes()) as site:
            code, data = run(["--url", site.url("/lyon"), "--url", site.url("/villeurbanne")])

        self.assertLess(data["pairs"][0]["similarity"], 1.0)

    def test_long_pages_are_compared_on_their_first_words(self):
        original = city_pages.MAX_WORDS
        city_pages.MAX_WORDS = 30

        try:
            record = city_pages.page_record(html("<main><p>" + "mot " * 100 + "</p></main>")[2].decode(), "a.html")
        finally:
            city_pages.MAX_WORDS = original

        self.assertTrue(record["_truncated"])
        self.assertEqual(len(record["_text"].split()), 30)

    def test_needs_two_pages(self):
        code, _ = run(["--url", "https://example.test/a"])

        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
