import contextlib
import csv
import io
import json
import os
import tempfile
import unittest

from tests.support import use_skill_scripts

use_skill_scripts("geo-mentions")

import visibility_score  # noqa: E402

RUN_FIELDS = ["question_id", "engine", "run", "date", "market", "named", "position",
              "named_instead", "cited_domains", "ambiguous", "possible_competitors", "accurate"]
FAMILIES = ["discovery", "comparison", "problem", "decision"]


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def panel_rows():
    rows = []

    for index in range(1, 11):
        rows.append({"panel_version": "v1", "market": "FR", "language": "fr",
                     "question_id": f"Q{index:02d}", "family": FAMILIES[index % 4],
                     "question": f"neutral question {index}", "brand_question": "no"})

    for index in (1, 2):
        rows.append({"panel_version": "v1", "market": "FR", "language": "fr",
                     "question_id": f"B{index:02d}", "family": "brand",
                     "question": "What is Acme?", "brand_question": "yes"})

    return rows


def run_rows(engine="chatgpt", runs_per_question=3):
    rows = []

    for index in range(1, 11):
        for run in range(1, runs_per_question + 1):
            named = index <= 5
            rows.append({
                "question_id": f"Q{index:02d}", "engine": engine, "run": str(run),
                "date": "2026-10-16", "market": "FR",
                "named": "yes" if named else "no", "position": "1" if named else "",
                "named_instead": "" if named else "Foo; Bar",
                "cited_domains": "a.com; www.acme.com" if named else "a.com; b.org",
                "ambiguous": "no", "possible_competitors": "Mystery Tool",
            })

    rows.append({"question_id": "B01", "engine": engine, "run": "1", "named": "yes", "position": "1",
                 "cited_domains": "acme.com", "accurate": "yes"})
    rows.append({"question_id": "B02", "engine": engine, "run": "1", "named": "yes", "position": "1",
                 "cited_domains": "", "accurate": "no"})

    return rows


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.panel = os.path.join(self.tmp.name, "panel.csv")
        self.runs = os.path.join(self.tmp.name, "runs.csv")
        self.checks = os.path.join(self.tmp.name, "checks.csv")
        write_csv(self.panel, ["panel_version", "market", "language", "question_id", "family",
                               "question", "brand_question", "notes"], panel_rows())
        write_csv(self.checks, ["domain", "brand_present"],
                  [{"domain": "a.com", "brand_present": "yes"}, {"domain": "b.org", "brand_present": "no"}])

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, extra=None, runs=None):
        write_csv(self.runs, RUN_FIELDS, runs if runs is not None else run_rows())
        out = io.StringIO()
        err = io.StringIO()
        args = ["--panel", self.panel, "--runs", self.runs, "--resamples", "200"] + (extra or [])

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = visibility_score.main(args)

        return code, (json.loads(out.getvalue()) if code == 0 else err.getvalue())

    def test_full_score_matches_formula(self):
        code, data = self.run_main(["--presence-checks", self.checks, "--brand-domain", "acme.com"])

        self.assertEqual(code, 0)
        engine = data["engines"][0]
        # presence 0.5, prominence 0.5, coverage 1/2 (a.com yes, b.org no), accuracy 0.5
        self.assertEqual(engine["components"]["presence"], 0.5)
        self.assertEqual(engine["components"]["prominence"], 0.5)
        self.assertEqual(engine["components"]["coverage"], 0.5)
        self.assertEqual(engine["components"]["accuracy"], 0.5)
        self.assertEqual(engine["score"], 50)
        self.assertEqual(engine["mode_inferred"], "full")
        low, high = engine["range"]
        self.assertLessEqual(low, 50)
        self.assertGreaterEqual(high, 50)
        self.assertIn("generated_on", data)
        self.assertEqual(data["overall"]["score"], None)

    def test_range_is_reproducible_with_seed(self):
        _, first = self.run_main(["--presence-checks", self.checks, "--seed", "7"])
        _, second = self.run_main(["--presence-checks", self.checks, "--seed", "7"])

        self.assertEqual(first["engines"][0]["range"], second["engines"][0]["range"])

    def test_not_read_domain_counts_absent_and_listed(self):
        _, data = self.run_main(["--brand-domain", "acme.com"])
        engine = data["engines"][0]

        self.assertEqual(engine["components"]["coverage"], 0.0)
        self.assertEqual(sorted(engine["components"]["coverage_not_read_counted_absent"]), ["a.com", "b.org"])
        domains = {d["domain"]: d for d in data["cited_domains"]}
        self.assertEqual(domains["a.com"]["brand_present"], "not read")
        self.assertTrue(domains["acme.com"]["own_site"])

    def test_quick_mode_gives_counts_only(self):
        _, data = self.run_main(runs=run_rows(runs_per_question=1))
        engine = data["engines"][0]

        self.assertIsNone(engine["score"])
        self.assertEqual(engine["status"], "indicative only / no score")
        self.assertIn("sample too small", engine["reason_if_null"])
        self.assertIn("not full mode", engine["reason_if_null"])
        self.assertEqual(engine["presence_counts"]["text"], "named in 5 of 10 non-brand runs")
        self.assertIsNone(engine["components"])
        self.assertEqual(len(engine["presence_counts"]["wilson_95_presence_only"]), 2)

    def test_accuracy_not_reviewed_means_no_score(self):
        rows = run_rows()

        for row in rows:
            row["accurate"] = ""

        _, data = self.run_main(["--presence-checks", self.checks], runs=rows)

        self.assertIsNone(data["engines"][0]["score"])
        self.assertIn("accuracy not measurable", data["engines"][0]["reason_if_null"])

    def test_two_engines_overall_only_when_both_meet_minimum(self):
        rows = run_rows("chatgpt") + run_rows("perplexity", runs_per_question=1)
        _, data = self.run_main(["--presence-checks", self.checks], runs=rows)

        self.assertIsNone(data["overall"]["score"])
        self.assertIn("every engine", data["overall"]["reason_if_null"])

        rows = run_rows("chatgpt") + run_rows("perplexity")
        _, data = self.run_main(["--presence-checks", self.checks, "--brand-domain", "acme.com"], runs=rows)
        self.assertEqual(data["overall"]["score"], 50)

    def test_competitor_ranking_and_families(self):
        _, data = self.run_main(["--presence-checks", self.checks])
        foo = data["competitors"][0]

        self.assertEqual(foo["competitor_name"], "Foo")
        self.assertEqual(foo["share"], 0.5)
        self.assertEqual(foo["mean_position_value"], 0.5)
        bar = data["competitors"][1]
        self.assertEqual(bar["mean_position_value"], 0.35)
        self.assertEqual(sum(f["non_brand_runs"] for f in data["families"].values()), 30)
        self.assertEqual(data["possible_competitors_unreviewed"][0]["name_text"], "Mystery Tool")

    def test_warnings_ambiguous_unknown_and_panel_neutrality(self):
        rows = run_rows()
        rows[0]["ambiguous"] = "yes"
        rows.append({"question_id": "Q99", "engine": "chatgpt", "run": "1", "named": "no"})
        panel = panel_rows()
        panel[0]["question"] = "Is Acme better than Foo?"
        write_csv(self.panel, list(panel[0].keys()), panel)
        _, data = self.run_main(["--brand", "Acme"], runs=rows)
        text = " ".join(data["warnings"])

        self.assertIn("ambiguous=yes", text)
        self.assertIn("Q99", text)
        self.assertIn("panel not neutral", text)
        self.assertEqual(data["engines"][0]["unreviewed_ambiguous_runs"], 1)

    def test_bands(self):
        self.assertEqual(visibility_score.band_for(14), "Absent")
        self.assertEqual(visibility_score.band_for(15), "Marginal")
        self.assertEqual(visibility_score.band_for(59), "Present")
        self.assertEqual(visibility_score.band_for(80), "Leading")
        self.assertEqual(visibility_score.band_label(40, 30, 50), "Marginal to Present")
        self.assertEqual(visibility_score.position_value(True, 2), 0.7)
        self.assertEqual(visibility_score.position_value(True, 7), 0.3)

    def test_bad_input_exit_2(self):
        bad = os.path.join(self.tmp.name, "bad.csv")

        with open(bad, "w", encoding="utf-8") as handle:
            handle.write("foo,bar\n1,2\n")

        out = io.StringIO()

        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(visibility_score.main(["--panel", self.panel, "--runs", bad]), 2)
            self.assertEqual(visibility_score.main(["--panel", os.path.join(self.tmp.name, "x.csv"), "--runs", bad]), 2)


if __name__ == "__main__":
    unittest.main()
