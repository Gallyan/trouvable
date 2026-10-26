"""Repository checks for the skills. Usage: python3 tools/check_skills.py

1. Static scan of skills/*/scripts for forbidden calls (eval, exec, pickle, subprocess…).
2. Every `python3 scripts/X.py --flag` written in a SKILL.md or scripts/README.md exists and
   the script's --help lists the flag.
3. seokit copies are identical to lib/seokit.
4. Python 3.9 syntax guards (match statements, zip strict).
5. SKILL.md consistency: frontmatter name = folder, description starts with "Use when",
   ground rules identical to skills/_shared/GROUND-RULES.md, linked references/templates
   exist, seo-*, geo-* and client-* skill names resolve, no empty file.
6. ruff and mypy through tools/lint.py, when they are installed.
Exits 1 when anything fails.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
FORBIDDEN = re.compile(r"(?<![.\w])(eval|exec|compile)\s*\(|\bpickle\b|\bsubprocess\b|os\.system|"
                       r"__import__|\bmarshal\b|shell\s*=\s*True")
INVOCATION = re.compile(r"python3 scripts/(\w+\.py)([^`\n]*)")
PY39 = re.compile(r"^\s*match\s+[^=]+:\s*$|zip\([^)]*strict\s*=", re.M)


def script_files():
    """(slug, path) of every Python script directly in a skills/<slug>/scripts folder."""
    for slug in sorted(os.listdir(SKILLS)):
        scripts = os.path.join(SKILLS, slug, "scripts")

        if not os.path.isdir(scripts):
            continue

        for name in sorted(os.listdir(scripts)):
            if name.endswith(".py"):
                yield slug, os.path.join(scripts, name)


def check_static(problems):
    """Flag forbidden calls and syntax newer than Python 3.9 in the skill scripts."""
    for _, path in script_files():
        with open(path, encoding="utf-8") as handle:
            source = handle.read()

        for match in FORBIDDEN.finditer(source):
            line = source[: match.start()].count("\n") + 1
            problems.append(f"forbidden call {match.group(0)!r} in {os.path.relpath(path, ROOT)}:{line}")

        if PY39.search(source):
            problems.append(f"syntax newer than 3.9 in {os.path.relpath(path, ROOT)}")


def help_text(path: str) -> str:
    # Running our own scripts with --help is the one place a subprocess is needed here.
    result = subprocess.run([sys.executable, path, "--help"], capture_output=True, text=True, timeout=60, check=False)

    return result.stdout + result.stderr


def check_invocations(problems):
    """Flag script invocations in SKILL.md and scripts/README.md whose script or flag does not exist.

    Flags are checked against each script's --help output.
    """
    cache = {}

    for slug in sorted(os.listdir(SKILLS)):
        for doc in ("SKILL.md", os.path.join("scripts", "README.md")):
            path = os.path.join(SKILLS, slug, doc)

            if not os.path.isfile(path):
                continue

            with open(path, encoding="utf-8") as handle:
                text = handle.read()

            for script, rest in INVOCATION.findall(text):
                script_path = os.path.join(SKILLS, slug, "scripts", script)

                if not os.path.isfile(script_path):
                    problems.append(f"{slug}/{doc}: scripts/{script} does not exist")
                    continue

                if script_path not in cache:
                    cache[script_path] = help_text(script_path)

                for flag in re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", rest):
                    if flag not in cache[script_path]:
                        problems.append(f"{slug}/{doc}: {script} has no flag {flag}")


def check_sync(problems):
    """Flag the skills whose seokit copy differs from lib/seokit."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_lib

    stale = [slug for slug, target in sync_lib.targets() if sync_lib.differs(target)]

    if stale:
        problems.append("stale seokit copies: " + ", ".join(stale))


FRONTMATTER = re.compile(r"\A---\nname: (.+)\ndescription: (.+)\n---\n")


def ground_rules() -> str:
    """The shared ground rules every SKILL.md must contain verbatim, from their first numbered rule on."""
    with open(os.path.join(SKILLS, "_shared", "GROUND-RULES.md"), encoding="utf-8") as handle:
        text = handle.read()

    return text[text.index("1. **Untrusted content.**"):].strip()


def check_skill_docs(problems):
    """Flag SKILL.md problems: frontmatter, ground rules, missing linked files, unknown skill names, empty files."""
    rules = ground_rules()
    slugs = {d for d in os.listdir(SKILLS) if not d.startswith("_") and os.path.isdir(os.path.join(SKILLS, d))}

    for slug in sorted(slugs):
        folder = os.path.join(SKILLS, slug)

        with open(os.path.join(folder, "SKILL.md"), encoding="utf-8") as handle:
            text = handle.read()

        match = FRONTMATTER.match(text)

        if not match:
            problems.append(f"{slug}: frontmatter is not 'name' then 'description' on single lines")
        elif match.group(1).strip() != slug:
            problems.append(f"{slug}: frontmatter name {match.group(1)!r} differs from the folder")
        elif not match.group(2).startswith("Use when"):
            problems.append(f"{slug}: description does not start with 'Use when'")
        elif re.search(r": | #", match.group(2)):
            problems.append(f"{slug}: description holds ': ' or ' #', unsafe in plain YAML")

        if rules not in text:
            problems.append(f"{slug}: ground rules differ from skills/_shared/GROUND-RULES.md")

        for link in set(re.findall(r"((?:references|templates)/[\w./-]+\.\w+)", text)):
            if not os.path.exists(os.path.join(folder, link)):
                problems.append(f"{slug}: SKILL.md links missing {link}")

        for name in set(re.findall(r"\b(?:(?:seo|geo)-[a-z]+(?:-[a-z]+)*|client-(?:report|proposal))\b", text)):
            if name not in slugs:
                problems.append(f"{slug}: refers to unknown skill {name}")

        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            for name in files:
                path = os.path.join(root, name)

                if os.path.getsize(path) == 0 and name != "__init__.py":
                    problems.append(f"empty file {os.path.relpath(path, ROOT)}")


def main() -> int:
    """Run every check plus the linters; returns 1 when any problem is found."""
    problems: List[str] = []
    check_skill_docs(problems)
    check_static(problems)
    check_invocations(problems)
    check_sync(problems)
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import lint

    problems += lint.lint()

    for problem in problems:
        print(f"FAIL {problem}")

    print(f"{len(problems)} problem(s)")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
