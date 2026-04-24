#!/usr/bin/env python3
"""Sync the vendored `stim_math/` tree from restim (diglet48/restim).

ForgePlayer vendors restim's pure-math layer rather than taking a library or
subprocess dependency. This keeps us immune to churn in the parts of restim
we don't use (Qt UI, device drivers, sensors, network) and lets us upgrade
on our schedule.

Usage:
    # Show what's pinned and what would change against upstream:
    python scripts/sync_restim_stim_math.py --check

    # Copy upstream tree (at the commit in VERSION or --commit) and rewrite
    # internal imports to relative form:
    python scripts/sync_restim_stim_math.py --update [--commit <sha>]

Assumptions:
    - Upstream clone lives at ../restim (sibling directory).
    - Target lives at app/vendor/restim_stim_math/.
    - Commit hash pinned in app/vendor/restim_stim_math/VERSION.
    - sensors/ is dropped (not used by ForgePlayer's audio synthesis path).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_CLONE = REPO_ROOT.parent / "restim"
VENDOR_DIR = REPO_ROOT / "app" / "vendor" / "restim_stim_math"
VERSION_FILE = VENDOR_DIR / "VERSION"
SOURCE_SUBTREE = "stim_math"
DROP_SUBDIRS = {"sensors"}


def _read_pinned_commit() -> str:
    if not VERSION_FILE.is_file():
        return ""
    for line in VERSION_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line.split()[0]
    return ""


def _git(*args: str, cwd: Path = UPSTREAM_CLONE) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _ensure_upstream_clean() -> None:
    if not UPSTREAM_CLONE.is_dir():
        sys.exit(f"ERROR: upstream clone not found at {UPSTREAM_CLONE}. "
                 "Clone diglet48/restim there first.")
    status = _git("status", "--porcelain")
    if status:
        sys.exit(f"ERROR: upstream clone at {UPSTREAM_CLONE} has local "
                 "changes. Stash or commit them before syncing.")


def _rewrite_imports(path: Path, at_top_level: bool) -> None:
    """Rewrite `from stim_math...` / `import stim_math...` to relative form.

    at_top_level: True for files directly under the vendor root; False for
    files under a sub-package (e.g. audio_gen/).
    """
    text = path.read_text(encoding="utf-8")
    new = text

    if at_top_level:
        # from stim_math import X -> from . import X
        new = re.sub(
            r"^from stim_math import ", "from . import ", new, flags=re.M,
        )
        # from stim_math.X import Y -> from .X import Y
        new = re.sub(
            r"^from stim_math\.", "from .", new, flags=re.M,
        )
    else:
        # from stim_math.audio_gen.X import Y -> from .X import Y
        new = re.sub(
            r"^from stim_math\.audio_gen\.", "from .", new, flags=re.M,
        )
        # from stim_math import X -> from .. import X
        new = re.sub(
            r"^from stim_math import ", "from .. import ", new, flags=re.M,
        )
        # from stim_math.X import Y -> from ..X import Y  (X is a top-level
        # sibling of audio_gen, not audio_gen itself — order matters; the
        # audio_gen case above is matched first)
        new = re.sub(
            r"^from stim_math\.", "from ..", new, flags=re.M,
        )
        # import stim_math.X -> from .. import X  (X = top-level module)
        new = re.sub(
            r"^import stim_math\.(\w+)\s*$",
            r"from .. import \1", new, flags=re.M,
        )
        # After the above, the body may still reference `stim_math.X.Y`;
        # strip the `stim_math.` prefix so `stim_math.pulse.foo()` becomes
        # `pulse.foo()`.
        new = re.sub(r"\bstim_math\.", "", new)

    if new != text:
        path.write_text(new, encoding="utf-8")


def _rewrite_tree() -> None:
    for py in VENDOR_DIR.rglob("*.py"):
        rel = py.relative_to(VENDOR_DIR)
        at_top = len(rel.parts) == 1
        _rewrite_imports(py, at_top_level=at_top)


def _copy_from_upstream(commit: str) -> None:
    _ensure_upstream_clean()
    current_head = _git("rev-parse", "HEAD")
    try:
        _git("checkout", "--quiet", commit)
        src = UPSTREAM_CLONE / SOURCE_SUBTREE
        if not src.is_dir():
            sys.exit(f"ERROR: {src} not found at {commit}")
        # Preserve VERSION + ATTRIBUTION if the target already exists.
        stash_files = {}
        for name in ("VERSION", "ATTRIBUTION.md"):
            p = VENDOR_DIR / name
            if p.is_file():
                stash_files[name] = p.read_text(encoding="utf-8")
        if VENDOR_DIR.is_dir():
            shutil.rmtree(VENDOR_DIR)
        shutil.copytree(src, VENDOR_DIR)
        # LICENSE is at the repo root upstream, so it needs a separate copy.
        upstream_license = UPSTREAM_CLONE / "LICENSE"
        if upstream_license.is_file():
            shutil.copy2(upstream_license, VENDOR_DIR / "LICENSE")
        for name, content in stash_files.items():
            (VENDOR_DIR / name).write_text(content, encoding="utf-8")
        for name in DROP_SUBDIRS:
            d = VENDOR_DIR / name
            if d.is_dir():
                shutil.rmtree(d)
        for pycache in VENDOR_DIR.rglob("__pycache__"):
            shutil.rmtree(pycache, ignore_errors=True)
    finally:
        _git("checkout", "--quiet", current_head)


def cmd_check() -> int:
    pinned = _read_pinned_commit()
    if not pinned:
        print("No pinned commit yet (VENDOR VERSION file missing).")
        return 0
    print(f"Pinned: {pinned}")
    if not UPSTREAM_CLONE.is_dir():
        print(f"(Upstream clone not found at {UPSTREAM_CLONE}; cannot diff.)")
        return 0
    _git("fetch", "--quiet", "upstream")
    upstream_head = _git("rev-parse", "upstream/master")
    print(f"Upstream master: {upstream_head}")
    if pinned == upstream_head:
        print("Up to date.")
        return 0
    ahead = _git("log", "--oneline", f"{pinned}..{upstream_head}",
                 f"--", SOURCE_SUBTREE)
    if not ahead:
        print("Upstream has moved, but stim_math/ is unchanged. No sync needed.")
        return 0
    print("stim_math/ commits since pin:\n" + ahead)
    return 0


def cmd_update(commit: str | None) -> int:
    target = commit or _read_pinned_commit()
    if not target:
        sys.exit("ERROR: no commit specified and no VERSION file to read from.")
    _copy_from_upstream(target)
    _rewrite_tree()
    (VENDOR_DIR / "VERSION").write_text(f"{target}\n", encoding="utf-8")
    print(f"Vendored restim stim_math at {target} into {VENDOR_DIR}.")
    print("Run `python -m pytest tests/` to validate.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="Show pinned + diff vs upstream master")
    up = sub.add_parser("update", help="Copy upstream stim_math/ + rewrite imports")
    up.add_argument("--commit", help="Upstream commit to pin. Defaults to VERSION file.")
    args = ap.parse_args()
    if args.cmd == "check":
        return cmd_check()
    if args.cmd == "update":
        return cmd_update(args.commit)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
