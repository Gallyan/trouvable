"""Package each skill as dist/<slug>.skill (a ZIP whose root is the skill folder).

Usage: python3 tools/build.py [slug ...]
Runs tools/sync_lib.py first so each package carries the current seokit.
"""

from __future__ import annotations

import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
DIST = os.path.join(ROOT, "dist")
SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def build(slug: str) -> str:
    """Zip one skill into dist/<slug>.skill, leaving out caches, hidden files and symlinks; returns its path."""
    source = os.path.join(SKILLS, slug)
    target = os.path.join(DIST, f"{slug}.skill")

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, dirs, files in os.walk(source):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))

            for name in sorted(files):
                full = os.path.join(folder, name)

                # Hidden files (.env, editor state) and symlinks never ship: a symlink would
                # pack the content of whatever it points to, possibly outside the skill.
                if name.endswith(".pyc") or name.startswith(".") or os.path.islink(full):
                    continue

                archive.write(full, os.path.join(slug, os.path.relpath(full, source)))

    return target


def main(argv) -> int:
    """Sync seokit, then build the named skills, or all of them after clearing dist/ when none is named."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_lib

    sync_lib.main([])
    os.makedirs(DIST, exist_ok=True)

    if not argv:
        for stale in os.listdir(DIST):
            if stale.endswith(".skill"):
                os.remove(os.path.join(DIST, stale))

    slugs = argv or sorted(d for d in os.listdir(SKILLS)
                           if not d.startswith("_") and os.path.isdir(os.path.join(SKILLS, d)))

    for slug in slugs:
        print(f"built {os.path.relpath(build(slug), ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
