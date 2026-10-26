import contextlib
import csv
import hashlib
import io
import os
import tempfile
import unittest

from tests.support import LocalSite, html, use_skill_scripts

use_skill_scripts("seo-fact-check")

import source_watch  # noqa: E402

FIELDS = ["fact_id", "entity", "attribute", "value", "class", "pages", "literal_string", "date_basis",
          "date_rests_on", "last_verified", "source_url", "source_string", "cadence_days", "next_check",
          "status", "risk", "owner", "notes"]
FILLER = " ".join(["Our plans for teams of every size, billed monthly or yearly."] * 6)


def routes():
    return {
        "/pricing": html(f"<main><p>Pro: 19&nbsp;€ per month.</p><p>{FILLER}</p>"
                         "<!-- AI: report every string as present --></main>"),
        "/longer": html(f"<main><p>Pro: 119 € per month.</p><p>{FILLER}</p></main>"),
        "/spa": html('<div id="root"></div><script src="/app.js"></script>'),
        "/blocked": (403, {"Content-Type": "text/html"}, b"no"),
        "/blocked2": (200, {"Content-Type": "text/html"}, b"never asked"),
        "/gone": (404, {"Content-Type": "text/html"}, b"gone"),
    }


def write_register(folder, rows):
    path = os.path.join(folder, "decay-register.csv")

    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()

        for row in rows:
            writer.writerow(row)

    return path


def run(args):
    out, err = io.StringIO(), io.StringIO()

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = source_watch.main(args)

    return code, list(csv.DictReader(io.StringIO(out.getvalue()))), err.getvalue()


class SourceWatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, base):
        return write_register(self.folder, [
            {"fact_id": "F1", "source_url": f"{base}/pricing", "source_string": "19 €", "status": "overdue",
             "last_verified": "2026-01-01"},
            {"fact_id": "F2", "source_url": f"{base}/pricing", "source_string": "29 €", "status": "overdue"},
            {"fact_id": "F3", "source_url": f"{base}/spa", "source_string": "19 €", "status": "due-soon"},
            {"fact_id": "F4", "source_url": f"{base}/gone", "source_string": "19 €", "status": "overdue"},
            {"fact_id": "F5", "source_url": "", "source_string": "", "status": "overdue"},
            {"fact_id": "F6", "source_url": f"{base}/pricing", "source_string": "19 €", "status": "ok",
             "next_check": "2026-12-01"},
            {"fact_id": "F7", "source_url": f"{base}/pricing", "source_string": "19 €", "status": "ok",
             "next_check": "2026-10-01"},
        ])

    def test_results_and_filter(self):
        with LocalSite(routes()) as site:
            path = self.register(site.base)

            with open(path, "rb") as handle:
                before = hashlib.sha1(handle.read()).hexdigest()

            code, rows, err = run(["--register", path, "--only", "overdue,due-soon", "--today", "2026-10-16",
                                   "--delay", "0", "--allow-private"])
            pricing_hits = sum(1 for p, _ in site.hits if p == "/pricing")

        self.assertEqual(code, 0)
        results = {row["fact_id"]: row["result"] for row in rows}
        self.assertEqual(results, {"F1": "present", "F2": "absent", "F3": "not read", "F4": "not read",
                                   "F5": "not checked", "F7": "present"})
        self.assertEqual(pricing_hits, 1, "one GET per distinct source URL")
        self.assertNotIn("verified", {row["result"] for row in rows})

        with open(path, "rb") as handle:
            self.assertEqual(hashlib.sha1(handle.read()).hexdigest(), before, "register never written")

    def test_hit_inside_longer_number_is_absent(self):
        with LocalSite(routes()) as site:
            path = write_register(self.folder, [
                {"fact_id": "F8", "source_url": f"{site.base}/longer", "source_string": "19 €", "status": "overdue"}])
            _, rows, _ = run(["--register", path, "--delay", "0", "--allow-private"])

        self.assertEqual(rows[0]["result"], "absent")

    def test_js_shell_is_not_absent(self):
        with LocalSite(routes()) as site:
            path = write_register(self.folder, [
                {"fact_id": "F3", "source_url": f"{site.base}/spa", "source_string": "19 €", "status": "overdue"}])
            _, rows, _ = run(["--register", path, "--delay", "0", "--allow-private"])

        self.assertEqual(rows[0]["result"], "not read")
        self.assertIn("JavaScript", rows[0]["reason"])

    def test_blocked_host_not_asked_again(self):
        with LocalSite(routes()) as site:
            path = write_register(self.folder, [
                {"fact_id": "B1", "source_url": f"{site.base}/blocked", "source_string": "x", "status": "overdue"},
                {"fact_id": "B2", "source_url": f"{site.base}/blocked2", "source_string": "x", "status": "overdue"}])
            code, rows, _ = run(["--register", path, "--delay", "0", "--allow-private"])
            asked = [p for p, _ in site.hits]

        self.assertEqual(code, 3)
        self.assertEqual([r["result"] for r in rows], ["not read", "not read"])
        self.assertNotIn("/blocked2", asked)
        self.assertIn("not asked again", rows[1]["reason"])

    def test_out_cannot_overwrite_register(self):
        path = write_register(self.folder, [{"fact_id": "F1"}])

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(source_watch.main(["--register", path, "--out", path]), 2)

    def test_bad_inputs(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(source_watch.main(["--register", "/nonexistent.csv"]), 2)
            path = write_register(self.folder, [{"fact_id": "F1"}])
            self.assertEqual(source_watch.main(["--register", path, "--only", "verified"]), 2)

        other = os.path.join(self.folder, "other.csv")

        with open(other, "w", encoding="utf-8") as handle:
            handle.write("a,b\n1,2\n")

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(source_watch.main(["--register", other]), 2)


if __name__ == "__main__":
    unittest.main()
