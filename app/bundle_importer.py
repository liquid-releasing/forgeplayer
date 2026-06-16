# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Import a FunscriptForge ``.forge`` bundle into a playable scene.

A ``.forge`` bundle (or its loose ``<stem>.output/`` folder) is *device-
organized* — produced by FunscriptForge's exporter:

    motion.funscript                                  (L0 stroke, top level)
    stations/estim3p/<stem>.alpha.funscript           (e-stim channels…)
                     <stem>.beta.funscript
                     <stem>.pulse_frequency.funscript
                     <stem>.alpha-prostate.funscript   (prostate side-chain)
    stations/tcode/  <stem>.roll.funscript …           (multi-axis)
    stations/<dev>/  …                                 (handy / lovense / …)
    audio/stim.mp3 · stim-prostate.mp3 · beat.mp3
    thumbnails/… · events.yml · <name>.json sidecars
    media/<file>                                       (only when --include-media)
    manifest.ffmeta                                    (stem + media relink key)

forgeplayer's scanner (`scan_scene_folder`) reads a FLAT scene folder — the
top-level files plus a single ``.forge/`` subfolder whose contents it flattens —
and groups funscripts into channel SETS by filename (``<stem>.<channel>.funscript``
→ ``classify_funscript_channel``). The per-channel files in a bundle are ALREADY
stem-named the way the scanner expects; they're just nested under ``stations/``.

So importing is a *normalize* step, not a parse: extract the archive, then lay
the channel funscripts (and ``motion.funscript`` → ``<stem>.funscript``) into a
``.forge/`` subfolder of a fresh scene dir, relink the source video from the
manifest when it wasn't bundled, and hand the folder to ``scan_scene_folder``.
The returned :class:`SceneCatalogEntry` feeds straight into
``ControlWindow._on_scene_activated`` — the same path the library panel uses.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from app.library.catalog import SceneCatalogEntry, VideoVariant, FunscriptSet
from app.library.channels import classify_funscript_channel
from app.library.scanner import VIDEO_EXTS

# Where extracted zip bundles live between launches. Stem-keyed so re-opening
# the same bundle refreshes one folder rather than piling up temps.
_CACHE_DIRNAME = "bundle_cache"


def _default_cache_root() -> Path:
    return Path.home() / ".forgeplayer" / _CACHE_DIRNAME


def _read_manifest(bundle_dir: Path) -> dict:
    mf = bundle_dir / "manifest.ffmeta"
    if not mf.is_file():
        return {}
    try:
        return json.loads(mf.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _relink_video(bundle_dir: Path, manifest: dict, search_dirs) -> str | None:
    """Resolve the source video for a bundle that didn't ship the media bytes.

    Priority: bundled ``media/<file>`` → the manifest's recorded absolute path
    (if it still exists) → a sibling of the bundle with the recorded filename.
    Returns an absolute path to a usable video, or None (the scene still loads —
    the user attaches a video via forgeplayer's picker).
    """
    media = manifest.get("media") or {}
    filename = media.get("filename")

    # 1. Bundled bytes (--include-media): manifest path is bundle-relative.
    rel = media.get("path")
    if media.get("bundled") and rel:
        bundled = bundle_dir / rel
        if bundled.is_file():
            return str(bundled)

    # 2. The original absolute source path, if it still resolves.
    for key in ("source_path", "original_path", "abspath", "path"):
        p = media.get(key)
        if p and not str(p).startswith(("media/", "media\\")):
            cand = Path(p)
            if cand.is_file():
                return str(cand)

    # 3. A sibling (of the bundle / its source) with the recorded filename —
    #    common when a lean bundle is shared next to its video.
    if filename:
        for d in search_dirs:
            cand = Path(d) / filename
            if cand.is_file():
                return str(cand)
    return None


def _collect_funscript_sets(bundle_dir: Path, stem: str) -> list[FunscriptSet]:
    """Group the bundle's funscripts into channel SETS, exactly as the library
    scanner would. ``motion.funscript`` is the set's main (classified as
    ``<stem>.funscript``); every ``stations/*/*.funscript`` is already
    ``<stem>.<channel>.funscript`` and rides on its real filename. Files are
    referenced in place (in the extracted bundle) — never copied."""
    # (classify_name, real_path). Stations first, motion LAST so the canonical
    # motion track wins the main slot over any station's plain L0 duplicate.
    items: list[tuple[str, Path]] = []
    stations = bundle_dir / "stations"
    if stations.is_dir():
        for fp in sorted(stations.rglob("*.funscript")):
            items.append((fp.name, fp))
    motion = bundle_dir / "motion.funscript"
    if motion.is_file():
        items.append((f"{stem}.funscript", motion))

    sets_by_stem: dict[str, FunscriptSet] = {}
    for classify_name, fp in items:
        info = classify_funscript_channel(classify_name)
        fset = sets_by_stem.get(info.base_stem)
        if fset is None:
            fset = FunscriptSet(base_stem=info.base_stem)
            sets_by_stem[info.base_stem] = fset
        if info.channel == "":
            fset.main_path = str(fp)
        else:
            fset.channels[info.channel] = str(fp)
    return list(sets_by_stem.values())


def load_bundle(path, *, cache_root=None) -> SceneCatalogEntry | None:
    """Extract a FunscriptForge ``.forge`` bundle (zip OR loose ``<stem>.output/``
    folder) into a playable scene entry, or None if it isn't a readable bundle /
    has nothing to play.

    Built directly from the known bundle structure + manifest (not via the
    folder scanner) so a lean bundle's relinked external video is honored —
    forgeplayer only requires a video OR audio to consider a scene playable, and
    the channel funscripts ride on top. The entry feeds straight into
    ``ControlWindow._on_scene_activated``.
    """
    src = Path(path)
    if not src.exists():
        return None

    cache_root = Path(cache_root) if cache_root else _default_cache_root()

    if src.is_file() and zipfile.is_zipfile(src):
        bundle_dir = cache_root / f"{src.stem}__extracted"
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir, ignore_errors=True)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            z.extractall(bundle_dir)
        scene_name = src.stem
    elif src.is_dir():
        bundle_dir = src
        scene_name = src.name
    else:
        return None  # a file that isn't a zip — not a bundle

    manifest = _read_manifest(bundle_dir)
    stem = manifest.get("stem") or scene_name

    funscript_sets = _collect_funscript_sets(bundle_dir, stem)

    videos: list[VideoVariant] = []
    video = _relink_video(bundle_dir, manifest, [src.parent, bundle_dir.parent])
    if video and Path(video).suffix.lower() in VIDEO_EXTS:
        videos.append(VideoVariant(path=video, tags=frozenset()))

    # Nothing to play AND no haptics → not a usable bundle.
    if not videos and not funscript_sets:
        return None

    return SceneCatalogEntry(
        folder_path=str(bundle_dir),
        name=stem,
        videos=videos,
        funscript_sets=funscript_sets,
    )
