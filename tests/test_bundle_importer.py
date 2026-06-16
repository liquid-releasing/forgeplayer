# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for the FunscriptForge .forge bundle importer.

Synthetic bundles built from zero-byte files in tmp_path — the scanner
classifies funscripts by FILENAME, so no real content (or ffprobe) is needed.
Covers both shapes load_bundle accepts: a loose <stem>.output/ folder and a
zipped .forge archive, plus the lean-bundle video relink.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.bundle_importer import load_bundle


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _make_bundle_tree(root: Path, stem: str = "Scene", *, media_filename: str | None = "Scene.mp4") -> Path:
    """Build a FunscriptForge-shaped bundle folder (device-organized)."""
    _touch(root / "motion.funscript")
    for ch in ("alpha", "beta", "pulse_frequency", "alpha-prostate", "beta-prostate"):
        _touch(root / "stations" / "estim3p" / f"{stem}.{ch}.funscript")
    _touch(root / "stations" / "tcode" / f"{stem}.roll.funscript")
    _touch(root / "stations" / "handy" / f"{stem}.funscript")
    # Pre-rendered control signals — must NOT become scene audio tracks.
    _touch(root / "audio" / "stim.mp3")
    _touch(root / "audio" / "beat.mp3")
    manifest = {
        "version": 1, "schema": "ffmeta/v1", "stem": stem,
        "created_with": "FunscriptForge",
        "media": {"filename": media_filename, "bundled": False} if media_filename else {},
    }
    (root / "manifest.ffmeta").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _assert_estim_set(entry, stem="Scene"):
    assert entry is not None
    assert entry.name == stem
    # One funscript SET keyed on the stem, with the e-stim channels grouped in.
    sets_by_stem = {s.base_stem: s for s in entry.funscript_sets}
    assert stem in sets_by_stem, f"no set for {stem}: {list(sets_by_stem)}"
    fset = sets_by_stem[stem]
    assert fset.main_path is not None  # motion.funscript → <stem>.funscript
    for ch in ("alpha", "beta", "pulse_frequency", "alpha-prostate", "beta-prostate", "roll"):
        assert ch in fset.channels, f"missing channel {ch}: {list(fset.channels)}"


def test_loads_loose_output_folder(tmp_path):
    bundle = _make_bundle_tree(tmp_path / "Scene.output")
    # A sibling video next to the bundle → relinked into the scene.
    _touch(tmp_path / "Scene.mp4")
    entry = load_bundle(bundle, cache_root=tmp_path / "cache")
    _assert_estim_set(entry)
    # Lean bundle (media not bundled) relinks the sibling video.
    assert any(Path(v.path).name == "Scene.mp4" for v in entry.videos)
    # Control-signal audio is never surfaced as a scene track.
    assert entry.audio_tracks == []


def test_loads_zipped_forge_bundle(tmp_path):
    tree = _make_bundle_tree(tmp_path / "build", media_filename=None)
    archive = tmp_path / "Scene.forge"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for fp in sorted(tree.rglob("*")):
            if fp.is_file():
                z.write(fp, fp.relative_to(tree).as_posix())
    entry = load_bundle(archive, cache_root=tmp_path / "cache")
    _assert_estim_set(entry)


def test_missing_path_returns_none(tmp_path):
    assert load_bundle(tmp_path / "nope.forge", cache_root=tmp_path / "cache") is None


def test_non_bundle_file_returns_none(tmp_path):
    stray = tmp_path / "notes.txt"
    stray.write_text("hello", encoding="utf-8")
    assert load_bundle(stray, cache_root=tmp_path / "cache") is None
