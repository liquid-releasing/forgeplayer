# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Group recognized files into distinct TITLES.

This is the NAME-proposes half of clustering, kept deliberately simple and
bulletproof: files are grouped by exact :pyattr:`RecognizedFile.cluster_key`.
A video and its channel funscripts share a cluster_key (same title name, no
ordinal), so they land together; ``Vol 1`` and ``Vol 2`` have different
cluster_keys, so they split into separate titles.

All the fuzzy / repair heuristics — attaching an orphan funscript whose name
drifted from the video, the one-video-one-script singleton pairing, pulling
funscripts in from a sibling folder, and the duration/funscript-span probe that
adjudicates genuine ties — live in ``match.py``. Keeping them out of here means
this core is trivially correct: same name ⇒ same title, full stop.

The input is a flat list of :class:`RecognizedFile` — the walker is free to
gather it from one folder OR from a folder plus its funscript subfolder, since
grouping is by name, not by directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.recognizer.canonicalize import Ordinal, RecognizedFile, Role, resolution_rank


@dataclass
class TitleCluster:
    """One distinct work, with every file that belongs to it."""
    canonical_key: str
    ordinal: Ordinal | None = None
    files: list[RecognizedFile] = field(default_factory=list)

    @property
    def cluster_key(self) -> str:
        if self.ordinal is not None:
            return f"{self.canonical_key}#{self.ordinal.signature}"
        return self.canonical_key

    # ── role-bucketed views ────────────────────────────────────────────────
    def _by_role(self, role: Role) -> list[RecognizedFile]:
        return [f for f in self.files if f.role is role]

    @property
    def videos(self) -> list[RecognizedFile]:
        """Video variants, best default first (non-aspect, non-upscaled,
        highest resolution, then name for determinism)."""
        return sorted(self._by_role(Role.VIDEO), key=_video_sort_key)

    @property
    def funscripts(self) -> list[RecognizedFile]:
        return self._by_role(Role.FUNSCRIPT)

    @property
    def audio(self) -> list[RecognizedFile]:
        return self._by_role(Role.AUDIO)

    @property
    def subtitles(self) -> list[RecognizedFile]:
        return self._by_role(Role.SUBTITLE)

    @property
    def bundles(self) -> list[RecognizedFile]:
        return self._by_role(Role.BUNDLE)

    @property
    def presets(self) -> list[RecognizedFile]:
        return self._by_role(Role.PRESET)

    @property
    def archives(self) -> list[RecognizedFile]:
        return self._by_role(Role.ARCHIVE)

    # ── predicates ─────────────────────────────────────────────────────────
    @property
    def has_video(self) -> bool:
        return any(f.role is Role.VIDEO for f in self.files)

    @property
    def has_haptics(self) -> bool:
        return any(f.role in (Role.FUNSCRIPT, Role.BUNDLE) for f in self.files)

    @property
    def is_playable(self) -> bool:
        """A title is playable if it has a video, audio, or a bundle."""
        return any(
            f.role in (Role.VIDEO, Role.AUDIO, Role.BUNDLE) for f in self.files
        )

    @property
    def display_name(self) -> str:
        """Human title — the primary video's original stem when available (keeps
        real casing), otherwise the normalized key, plus the ordinal label."""
        base = None
        vids = self.videos
        if vids:
            base = _display_stem(vids[0])
        if not base:
            base = self.canonical_key.title()
        if self.ordinal is not None:
            return f"{base} · {self.ordinal.label}"
        return base


def cluster_files(files: list[RecognizedFile]) -> list[TitleCluster]:
    """Group recognized files into titles by exact cluster_key.

    ``Role.OTHER`` files (unrecognized junk) are dropped — they neither define
    nor attach to a title. Order is deterministic: by name, then ordinal number.
    """
    groups: dict[str, TitleCluster] = {}
    for rf in files:
        if rf.role is Role.OTHER:
            continue
        ck = rf.cluster_key
        tc = groups.get(ck)
        if tc is None:
            tc = TitleCluster(canonical_key=rf.canonical_key, ordinal=rf.ordinal)
            groups[ck] = tc
        tc.files.append(rf)
    return sorted(
        groups.values(),
        key=lambda t: (t.canonical_key, t.ordinal.number if t.ordinal else -1),
    )


# ── helpers ────────────────────────────────────────────────────────────────

def _video_sort_key(v: RecognizedFile) -> tuple:
    """Lower is a better default: non-aspect, non-upscaled, highest res, name."""
    is_aspect = int(bool(v.variant_tags & {"vr", "cropped", "ultrawide", "sbs", "fisheye"}))
    return (is_aspect, int(v.is_upscaled), resolution_rank(v.resolution), v.filename.lower())


def _display_stem(rf: RecognizedFile) -> str:
    """The video's filename stem, quality + ordinal tokens trimmed but original
    casing kept — 'Magik Vol 2.4k' → 'Magik'. The ordinal is re-appended as a
    clean label by :pyattr:`TitleCluster.display_name`. Display-only, best-effort;
    reuses the canonicalizer's single-source token classifier so it never drifts.
    """
    from pathlib import Path

    from app.recognizer.canonicalize import (
        _BRACKET_RE, _ORDINAL_MARKER_RE, _SPLIT_RE, _TRAILING_NUM_RE,
        _classify_token,
    )

    stem = _BRACKET_RE.sub(" ", Path(rf.path).stem)
    if rf.ordinal is not None:
        stripped = _ORDINAL_MARKER_RE.sub(" ", stem)
        stem = stripped if stripped != stem else _TRAILING_NUM_RE.sub("", stem)
    kept = [t for t in _SPLIT_RE.split(stem) if t and _classify_token(t.lower()) is None]
    return " ".join(kept).strip()
