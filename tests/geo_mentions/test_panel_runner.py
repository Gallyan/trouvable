import os
import re
import unittest

from tests.support import ROOT

SKILL = os.path.join(ROOT, "skills", "geo-mentions")
FORBIDDEN_WORDS = ["brand", "marque", "competitor", "concurrent", "alias", "audit", "visibility",
                   "score", "panel", "mention", "recommend"]


def read(*parts):
    with open(os.path.join(SKILL, *parts), encoding="utf-8") as handle:
        return handle.read()


def sub_agent_prompt():
    blocks = re.findall(r"```text\n(.*?)```", read("references", "panel-runner.md"), re.S)
    assert len(blocks) == 1, f"expected one ```text block, found {len(blocks)}"

    return blocks[0]


class PanelRunnerTest(unittest.TestCase):
    def test_prompt_has_only_question_language_country_placeholders(self):
        placeholders = set(re.findall(r"\{(\w+)\}", sub_agent_prompt()))

        self.assertEqual(placeholders, {"question", "language", "country"})

    def test_prompt_says_nothing_about_the_measure(self):
        prompt = sub_agent_prompt().lower()

        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, prompt, word)

    def test_launch_settings_rule_out_fork_and_fix_the_model(self):
        text = read("references", "panel-runner.md")

        self.assertIn("Never `fork`", text)
        self.assertIn("`model`: `sonnet`", text)
        self.assertIn("`description`: `Answer a user question`", text)

    def test_skill_links_the_runner_and_keeps_a_fallback(self):
        text = read("SKILL.md")

        self.assertIn("references/panel-runner.md", text)
        self.assertIn("Main-conversation route otherwise", text)
        self.assertIn("Answering the panel while knowing the brand", text)


if __name__ == "__main__":
    unittest.main()
