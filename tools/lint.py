"""Lint and type-check the repository with ruff and mypy, when they are installed.

Usage: python3 tools/lint.py
ruff runs once over the repository (settings in pyproject.toml). mypy runs on lib/seokit, then
on each skills/<slug>/scripts folder from inside it, so the bundled seokit copy resolves as it
does at run time; errors inside those copies are left to the lib/seokit pass.
Exits 1 when a tool reports a problem, 0 when everything passes or a tool is missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "pyproject.toml")


def run(command: List[str], cwd: str) -> List[str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=600, check=False)

    return [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]


def ruff_problems() -> List[str]:
    lines = run(["ruff", "check", "--no-cache", "--output-format", "concise", "."], ROOT)

    return [line for line in lines if ":" in line and not line.startswith(("Found", "All checks"))]


def mypy_problems() -> List[str]:
    """mypy errors in lib/seokit and in each skill's scripts, the bundled seokit copies left out."""
    cache = tempfile.mkdtemp(prefix="mypy-")
    base = ["mypy", "--config-file", CONFIG, "--cache-dir", cache, "--no-error-summary"]
    problems = [line for line in run(base + ["lib/seokit"], ROOT) if ": error:" in line]
    skills = os.path.join(ROOT, "skills")

    for slug in sorted(os.listdir(skills)):
        folder = os.path.join(skills, slug, "scripts")
        scripts = sorted(name for name in os.listdir(folder) if name.endswith(".py")) if os.path.isdir(folder) else []

        if not scripts:
            continue

        for line in run(base + ["--follow-imports", "silent"] + scripts, folder):
            if ": error:" in line and not line.startswith("seokit/"):
                problems.append(f"skills/{slug}/scripts/{line}")

    shutil.rmtree(cache, ignore_errors=True)

    return problems


def lint() -> List[str]:
    """Problems found by the installed tools; a missing tool is reported, not counted."""
    problems = []

    for tool, check in (("ruff", ruff_problems), ("mypy", mypy_problems)):
        if shutil.which(tool) is None:
            print(f"lint: {tool} not installed, skipped")
            continue

        problems += [f"{tool}: {line}" for line in check()]

    return problems


def main() -> int:
    problems = lint()

    for problem in problems:
        print(problem)

    print(f"{len(problems)} lint problem(s)")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
