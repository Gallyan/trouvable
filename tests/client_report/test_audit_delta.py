import contextlib
import csv
import io
import json
import os
import tempfile
import unittest

from tests.support import use_skill_scripts

use_skill_scripts("client-report")

import audit_delta  # noqa: E402

HEADER = "check_id,area,severity,status,cause_group,affected,checked,example_url,evidence,fix,done_when,label,note"


def row(check, status, severity="high", area="E", affected="3", checked="100", label="measured",
        evidence="title missing", example="https://site.example/a"):
    return f"{check},{area},{severity},{status},,{affected},{checked},{example},{evidence},fix it,re-crawl,{label},"


class DeltaTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = os.path.join(self.tmp.name, name)

        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

        return path

    def issues(self, name, lines, header=HEADER):
        return self.write(name, "\n".join([header] + lines) + "\n")

    def run_main(self, args):
        out, err = io.StringIO(), io.StringIO()

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = audit_delta.main(args)

        return code, out.getvalue(), err.getvalue()

    def dated(self, before, after, *extra):
        return ["--before", before, "--after", after, "--before-date", "2026-09-01",
                "--after-date", "2026-10-01"] + list(extra)


class IssuesRunsTest(DeltaTestCase):
    def test_fixed_new_open_and_not_measured(self):
        before = self.issues("a.csv", [
            row("TITLE", "fail"),
            row("H1", "fail", severity="medium"),
            row("CANON", "pass", area="D"),
            row("OG", "fail", severity="low", area="F"),
            row("ALT", "pass", area="G"),
            row("DEPTH", "not-measured", area="H"),
        ])
        after = self.issues("b.csv", [
            row("TITLE", "pass"),
            row("H1", "fail", severity="medium", affected="1"),
            row("CANON", "fail", area="D"),
            row("OG", "not-measured", severity="low", area="F"),
            row("ALT", "pass", area="G"),
            row("DEPTH", "pass", area="H"),
        ])
        code, out, _ = self.run_main(self.dated(before, after))
        data = json.loads(out)
        changes = {r["key"]: r["change"] for r in data["rows"]}

        self.assertEqual(code, 0)
        self.assertEqual(changes, {"TITLE": "fixed", "H1": "still-open", "CANON": "new",
                                   "OG": "no-longer-measured", "DEPTH": "newly-measured"})
        self.assertEqual(data["by_change"]["fixed"], 1)
        self.assertEqual(data["by_change"]["unchanged"], 1)
        self.assertEqual(data["by_severity"]["high"], {"fixed": 1, "new": 1, "newly-measured": 1})
        self.assertEqual(data["by_domain"]["F"], {"no-longer-measured": 1})
        self.assertEqual(data["open_before"], 3)
        self.assertEqual(data["open_after"], 2)
        self.assertTrue(data["comparable"])
        h1 = next(r for r in data["rows"] if r["key"] == "H1")
        self.assertEqual((h1["affected_before"], h1["affected_after"]), ("3", "1"))
        self.assertEqual((h1["date_before"], h1["date_after"]), ("2026-09-01", "2026-10-01"))

    def test_missing_check_is_not_fixed_and_breaks_comparability(self):
        before = self.issues("a.csv", [row("TITLE", "fail"), row("H1", "pass")])
        after = self.issues("b.csv", [row("H1", "pass"), row("NEWCHECK", "fail")])
        code, out, _ = self.run_main(self.dated(before, after))
        data = json.loads(out)
        changes = {r["key"]: r["change"] for r in data["rows"]}

        self.assertEqual(code, 0)
        self.assertEqual(changes["TITLE"], "missing-from-after")
        self.assertEqual(changes["NEWCHECK"], "new")
        self.assertEqual(data["by_change"]["fixed"], 0)
        self.assertFalse(data["comparable"])
        self.assertIn("only in the first run", data["comparability_reasons"][0])

    def test_checked_base_severity_and_label_changes(self):
        before = self.issues("a.csv", [row("TITLE", "fail", checked="300"), row("H1", "fail")])
        after = self.issues("b.csv", [row("TITLE", "fail", checked="50"),
                                      row("H1", "fail", severity="low", label="estimated")])
        code, out, _ = self.run_main(self.dated(before, after))
        data = json.loads(out)
        reasons = " ".join(data["comparability_reasons"])

        self.assertFalse(data["comparable"])
        self.assertIn("checked base", reasons)
        self.assertIn("severity", reasons)
        self.assertIn("label", reasons)

    def test_scope_from_summaries(self):
        before = self.issues("a.csv", [row("TITLE", "fail")])
        after = self.issues("b.csv", [row("TITLE", "pass")])
        s1 = self.write("s1.json", json.dumps({"tool": "site_crawl", "mode": "links", "caps": {"max_pages": 300}}))
        s2 = self.write("s2.json", json.dumps({"tool": "site_crawl", "mode": "sample", "caps": {"max_pages": 50}}))
        code, out, _ = self.run_main(self.dated(before, after, "--before-summary", s1, "--after-summary", s2))
        data = json.loads(out)
        reasons = " ".join(data["comparability_reasons"])

        self.assertEqual(code, 0)
        self.assertFalse(data["comparable"])
        self.assertIn("max_pages", reasons)
        self.assertIn("mode", reasons)

    def test_one_summary_only_is_bad_input(self):
        before = self.issues("a.csv", [row("TITLE", "fail")])
        after = self.issues("b.csv", [row("TITLE", "pass")])
        s1 = self.write("s1.json", "{}")
        code, _, err = self.run_main(self.dated(before, after, "--before-summary", s1))

        self.assertEqual(code, 2)
        self.assertIn("both", err)

    def test_dropped_rows_are_left_out(self):
        header = HEADER + ",dropped"
        before = self.issues("a.csv", [row("TITLE", "fail") + ",yes", row("H1", "fail") + ","], header)
        after = self.issues("b.csv", [row("H1", "pass") + ","], header)
        code, out, _ = self.run_main(self.dated(before, after))
        data = json.loads(out)

        self.assertEqual(code, 0)
        self.assertEqual(data["before"]["dropped"], 1)
        self.assertEqual([r["key"] for r in data["rows"]], ["H1"])
        self.assertTrue(data["comparable"])

    def test_status_dropped_is_left_out(self):
        before = self.issues("a.csv", [row("TITLE", "dropped"), row("H1", "fail")])
        after = self.issues("b.csv", [row("H1", "pass")])
        code, out, _ = self.run_main(self.dated(before, after))
        data = json.loads(out)

        self.assertEqual(code, 0)
        self.assertEqual(data["before"]["dropped"], 1)
        self.assertEqual([r["key"] for r in data["rows"]], ["H1"])

    def test_composite_key_for_per_url_findings(self):
        header = "issue,url,severity,status"
        before = self.issues("a.csv", ["404,https://s.example/a,high,fail", "404,https://s.example/b,high,fail"],
                             header)
        after = self.issues("b.csv", ["404,https://s.example/a,high,pass", "404,https://s.example/b,high,fail"], header)
        code, out, _ = self.run_main(self.dated(before, after, "--key", "issue,url"))
        changes = {r["key"]: r["change"] for r in json.loads(out)["rows"]}

        self.assertEqual(code, 0)
        self.assertEqual(changes, {"404 | https://s.example/a": "fixed", "404 | https://s.example/b": "still-open"})

    def test_hostile_cells_are_neutralised_in_csv(self):
        before = self.issues("a.csv", [row("TITLE", "fail", example='=HYPERLINK("http://evil.example")',
                                           evidence="<script>alert(1)</script>")])
        after = self.issues("b.csv", [row("TITLE", "fail", example='=HYPERLINK("http://evil.example")')])
        delta = os.path.join(self.tmp.name, "delta.csv")
        report = os.path.join(self.tmp.name, "delta.json")
        code, out, _ = self.run_main(self.dated(before, after, "--csv", delta, "--out", report))

        with open(delta, encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertTrue(rows[0]["example_url_text"].startswith("'="))
        self.assertTrue(os.path.isfile(report))

    def test_unknown_status_is_reported(self):
        before = self.issues("a.csv", [row("TITLE", "maybe"), row("H1", "fail")])
        after = self.issues("b.csv", [row("TITLE", "pass"), row("H1", "fail")])
        _, out, _ = self.run_main(self.dated(before, after))

        self.assertEqual(len(json.loads(out)["unknown_statuses"]), 1)


class BadInputTest(DeltaTestCase):
    def assertBad(self, args, fragment):
        code, out, err = self.run_main(args)

        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(fragment, err)

    def test_missing_dates(self):
        a = self.issues("a.csv", [row("TITLE", "fail")])
        self.assertBad(["--before", a, "--after", a], "required")

    def test_dates_in_wrong_order_or_malformed(self):
        a = self.issues("a.csv", [row("TITLE", "fail")])
        self.assertBad(["--before", a, "--after", a, "--before-date", "2026-10-01", "--after-date", "2026-09-01"],
                       "not earlier")
        self.assertBad(["--before", a, "--after", a, "--before-date", "01/09/2026", "--after-date", "2026-10-01"],
                       "YYYY-MM-DD")

    def test_missing_column(self):
        a = self.issues("a.csv", ["TITLE,E,high"], header="check_id,area,severity")
        self.assertBad(self.dated(a, a), "missing column")

    def test_missing_file(self):
        self.assertBad(self.dated(os.path.join(self.tmp.name, "nope.csv"), os.path.join(self.tmp.name, "x.csv")),
                       "cannot read")

    def test_no_shared_key(self):
        a = self.issues("a.csv", [row("TITLE", "fail")])
        b = self.issues("b.csv", [row("OTHER", "fail")])
        self.assertBad(self.dated(a, b), "share no key")

    def test_duplicate_key(self):
        a = self.issues("a.csv", [row("TITLE", "fail"), row("TITLE", "pass")])
        self.assertBad(self.dated(a, a), "duplicate key")

    def test_mixed_formats(self):
        a = self.issues("a.csv", [row("TITLE", "fail")])
        b = self.write("b.json", "{}")
        self.assertBad(self.dated(a, b), "same format")


class SummaryRunsTest(DeltaTestCase):
    def summary(self, name, **values):
        data = {"tool": "query_opportunities", "generated_on": "2026-09-01",
                "date_range": {"start": "2026-06-01", "end": "2026-08-31"},
                "brand_split": {"non_brand": {"clicks": 120, "impressions": 9000, "label": "reported"}},
                "sample_verdict": {"verdict": "usable"}}
        data.update(values)

        return self.write(name, json.dumps(data))

    def test_figures_with_both_dates_and_labels(self):
        a = self.summary("a.json")
        b = self.summary("b.json", generated_on="2026-10-01",
                         brand_split={"non_brand": {"clicks": 150, "impressions": 9500, "label": "reported"}})
        code, out, _ = self.run_main(["--before", a, "--after", b])
        data = json.loads(out)
        clicks = next(f for f in data["figures"] if f["path"] == "brand_split.non_brand.clicks")

        self.assertEqual(code, 0)
        self.assertEqual((clicks["before"], clicks["after"], clicks["change"]), (120, 150, 30))
        self.assertEqual((clicks["date_before"], clicks["date_after"]), ("2026-09-01", "2026-10-01"))
        self.assertEqual(clicks["label_after"], "reported")
        self.assertTrue(data["comparable"])

    def test_different_date_ranges_are_not_comparable(self):
        a = self.summary("a.json")
        b = self.summary("b.json", generated_on="2026-10-01", date_range={"start": "2026-08-01", "end": "2026-09-30"})
        code, out, _ = self.run_main(["--before", a, "--after", b])
        data = json.loads(out)

        self.assertEqual(code, 0)
        self.assertFalse(data["comparable"])
        self.assertIn("date_range", " ".join(data["comparability_reasons"]))
        self.assertFalse(any(f["path"].startswith("date_range") for f in data["figures"]))

    def test_different_tools_refused(self):
        a = self.summary("a.json")
        b = self.summary("b.json", generated_on="2026-10-01", tool="site_crawl")
        code, _, err = self.run_main(["--before", a, "--after", b])

        self.assertEqual(code, 2)
        self.assertIn("different tools", err)

    def test_invalid_json(self):
        a = self.summary("a.json")
        b = self.write("b.json", "{not json")
        code, _, err = self.run_main(["--before", a, "--after", b])

        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)

    def test_deeply_nested_json(self):
        deep = '{"tool": "t", "generated_on": "2026-09-01", "x": ' + "[" * 5000 + "]" * 5000 + "}"
        a = self.write("a.json", deep)
        b = self.write("b.json", deep)
        code, _, err = self.run_main(["--before", a, "--after", b, "--after-date", "2026-10-01"])

        self.assertEqual(code, 2)
        self.assertIn("nested", err)

    def test_no_dates_anywhere(self):
        a = self.write("a.json", json.dumps({"tool": "t", "n": 1}))
        b = self.write("b.json", json.dumps({"tool": "t", "n": 2}))
        code, _, err = self.run_main(["--before", a, "--after", b])

        self.assertEqual(code, 2)
        self.assertIn("generated_on", err)


if __name__ == "__main__":
    unittest.main()
