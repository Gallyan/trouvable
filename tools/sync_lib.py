"""Copy lib/seokit into skills/<slug>/scripts/seokit/ for every skill that has scripts.

Usage: python3 tools/sync_lib.py [--check]
--check exits 1 if any copy differs from the source, without writing.
"""

from __future__ import annotations

import filecmp
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "lib", "seokit")
SKILLS = os.path.join(ROOT, "skills")


def source_files():
    """The Python files of lib/seokit, sorted."""
    return sorted(f for f in os.listdir(SOURCE) if f.endswith(".py"))


def _plans_scripts(readme: str) -> bool:
    """A skill gets a copy when its scripts/README.md has a '## <name>.py' section."""
    if not os.path.isfile(readme):
        return False

    with open(readme, encoding="utf-8") as handle:
        return any(re.match(r"^## \w+\.py\s*$", line) for line in handle)


def targets():
    """(slug, seokit copy folder) of each skill that ships scripts."""
    for slug in sorted(os.listdir(SKILLS)):
        scripts = os.path.join(SKILLS, slug, "scripts")

        if _plans_scripts(os.path.join(scripts, "README.md")):
            yield slug, os.path.join(scripts, "seokit")


def differs(target: str) -> bool:
    """True when a seokit copy is missing, has other files, or any file differs from lib/seokit."""
    if not os.path.isdir(target):
        return True

    present = sorted(f for f in os.listdir(target) if f.endswith(".py"))

    if present != source_files():
        return True

    return any(not filecmp.cmp(os.path.join(SOURCE, f), os.path.join(target, f), shallow=False) for f in present)


def main(argv) -> int:
    """Replace every stale seokit copy; with --check only list them and return 1 when one is stale."""
    check = "--check" in argv
    stale = []

    for slug, target in targets():
        if not differs(target):
            continue

        stale.append(slug)

        if check:
            continue

        if os.path.isdir(target):
            shutil.rmtree(target)

        os.makedirs(target)

        for name in source_files():
            shutil.copy2(os.path.join(SOURCE, name), os.path.join(target, name))

        print(f"synced {slug}")

    if check and stale:
        print("stale seokit copies: " + ", ".join(stale))
        return 1

    if not stale:
        print("all seokit copies up to date")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
