# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Canonicalize one filename into a title identity.

This is the foundation of the media recognizer: given a filename, split it into
the parts that identify a WORK (the title name + any volume/part ordinal) from
the parts that only describe a *rendering* of that work (resolution, upscaler,
aspect, codec, channel suffix, edit tags). Two files are the "same title" iff
their :pyattr:`RecognizedFile.cluster_key` matches — they differ only by
rendering. A different ordinal (Vol 1 vs Vol 2) is a DIFFERENT title.

Token classification, not a lookup of known titles — so a brand-new work needs
zero code. An *unknown* token is kept in the name (the safe direction: files
stay apart rather than wrongly merging different content). The quality/format
vocabulary it strips is single-sourced in ``vocabulary/variant_tokens.json`` so
the JS scanner (forgemoment) and the Python recognizer share one copy.

Design: name proposes, content adjudicates. This module is the pure NAME half —
no I/O, no ffprobe. The duration/funscript-span probe that breaks genuine ties
lives separately (``probe.py``) and is only consulted when names are ambiguous.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from app.library.channels import ChannelInfo, classify_funscript_channel

# ── File-type extensions (recognizer-local: single source once extracted) ─────

VIDEO_EXTS = frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv"})
AUDIO_EXTS = frozenset({".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus"})
SUBTITLE_EXTS = frozenset({".srt", ".ass", ".ssa", ".vtt"})
ARCHIVE_EXTS = frozenset({".zip", ".7z", ".rar"})
FUNSCRIPT_EXT = ".funscript"
# `.forge` / `.forgeplay` ZIP files are self-contained bundles. (A `.output`
# FOLDER is a bundle too, but that's a directory the walker handles — not a
# filename this function classifies.)
BUNDLE_EXTS = frozenset({".forge", ".forgeplay"})
_PRESET_SUFFIX = ".forgeplayer.json"


_VOCAB_PATH = Path(__file__).parent / "vocabulary" / "variant_tokens.json"


@lru_cache(maxsize=1)
def _vocab() -> dict:
    return json.loads(_VOCAB_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _token_sets() -> tuple[dict[str, str], frozenset[str], frozenset[str], frozenset[str], frozenset[str]]:
    """(resolution_token→bucket, upscalers, aspects, codecs, misc) from vocab."""
    v = _vocab()
    res_map: dict[str, str] = {}
    for bucket, toks in v["resolution"].items():
        for t in toks:
            res_map[t.lower()] = bucket
    return (
        res_map,
        frozenset(t.lower() for t in v["upscaler"]),
        frozenset(t.lower() for t in v["aspect"]),
        frozenset(t.lower() for t in v["codec_format"]),
        frozenset(t.lower() for t in v.get("misc_noise", [])),
    )


def resolution_rank(bucket: str | None) -> int:
    """Lower is higher-quality. Unknown/None sorts last."""
    if not bucket:
        return 99
    return _vocab()["resolution_rank"].get(bucket, 99)


# ── Roles ─────────────────────────────────────────────────────────────────────

class Role(str, Enum):
    VIDEO = "video"
    FUNSCRIPT = "funscript"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
    BUNDLE = "bundle"
    ARCHIVE = "archive"
    PRESET = "preset"
    OTHER = "other"


# ── Ordinal (volume / part / episode …) ───────────────────────────────────────

# Normalize marker synonyms to a class so `Vol 1` and `Volume 1` collapse but
# `Vol 1` and `Part 1` stay distinct (safe: prefer splitting). Single-letter
# markers (v/e/s/p) are deliberately EXCLUDED — too many false hits inside real
# names ("v2" version tags, etc.).
_MARKER_CLASS: dict[str, str] = {
    "vol": "volume", "volume": "volume",
    "part": "part", "pt": "part",
    "ep": "episode", "episode": "episode", "eps": "episode",
    "scene": "scene",
    "disc": "disc", "disk": "disc", "cd": "disc",
    "chapter": "chapter",
}

_ORDINAL_MARKER_RE = re.compile(
    r"(?i)(?<![a-z])(?P<marker>vol|volume|part|pt|ep|episode|eps|scene|disc|disk|cd|chapter)"
    r"[\s._-]*(?P<num>\d{1,3})(?![a-z0-9])"
)
# A bare trailing number after a name (e.g. "Magik 1") — only WITH a separator
# and a name in front, so we never eat digits that are glued to a word or a
# pure-number filename.
_TRAILING_NUM_RE = re.compile(r"(?<=\S)[\s._-]+(?P<num>\d{1,3})\s*$")

_BRACKET_RE = re.compile(r"[\[\(\{][^\]\)\}]*[\]\)\}]")
_SPLIT_RE = re.compile(r"[\s._\-]+")
_WORD_NUM_RE = re.compile(r"^([a-z]+)(\d*)$")


@dataclass(frozen=True)
class Ordinal:
    """An identity-bearing ordinal pulled out of a filename."""
    cls: str
    """Normalized class: 'volume' | 'part' | 'episode' | 'scene' | 'disc' |
    'chapter' | '' for a bare trailing number."""
    number: int
    raw: str
    """As found, for display (e.g. 'Vol 2')."""

    @property
    def signature(self) -> str:
        return f"{self.cls}:{self.number}"

    @property
    def label(self) -> str:
        if self.cls:
            return f"{self.cls.capitalize()} {self.number}"
        return str(self.number)


# ── The recognized file ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class RecognizedFile:
    path: str
    role: Role
    canonical_key: str
    """Title name only — lower-cased, ordinal + quality/channel tokens removed,
    separators normalized to single spaces. Never empty (falls back to the raw
    stem when stripping would empty it)."""
    ordinal: Ordinal | None = None
    resolution: str | None = None
    """Best (highest-quality) resolution bucket found, or None."""
    variant_tags: frozenset[str] = frozenset()
    """Normalized quality/format tokens found: resolution bucket, upscaler base
    words ('iris', 'topaz'), aspect ('vr', 'cropped'), codec, misc."""
    channel: str = ""
    """Funscript channel as it appears ('alpha', 'alpha-prostate'); '' for the
    main funscript or any non-funscript role."""
    channel_info: ChannelInfo | None = None

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def cluster_key(self) -> str:
        """Title identity for clustering. Same cluster_key ⇒ same work (differs
        only by rendering). Different ordinal ⇒ different work (sequel/volume)."""
        if self.ordinal is not None:
            return f"{self.canonical_key}#{self.ordinal.signature}"
        return self.canonical_key

    @property
    def is_upscaled(self) -> bool:
        return bool(self.variant_tags & _token_sets()[1])


# ── Classification pipeline ────────────────────────────────────────────────────

def _role_and_stem(path: Path) -> tuple[Role, str, ChannelInfo | None, str]:
    """Return (role, channel, channel_info, stem_for_key)."""
    name = path.name
    ext = path.suffix.lower()
    low = name.lower()

    if ext == FUNSCRIPT_EXT:
        info = classify_funscript_channel(name)
        return Role.FUNSCRIPT, info.channel, info, info.base_stem
    if ext in BUNDLE_EXTS:
        return Role.BUNDLE, "", None, path.stem
    if low.endswith(_PRESET_SUFFIX):
        return Role.PRESET, "", None, name[: -len(_PRESET_SUFFIX)]
    if ext in VIDEO_EXTS:
        return Role.VIDEO, "", None, path.stem
    if ext in AUDIO_EXTS:
        return Role.AUDIO, "", None, path.stem
    if ext in SUBTITLE_EXTS:
        return Role.SUBTITLE, "", None, path.stem
    if ext in ARCHIVE_EXTS:
        return Role.ARCHIVE, "", None, path.stem
    return Role.OTHER, "", None, path.stem


def _extract_ordinal(s: str) -> tuple[str, Ordinal | None]:
    """Pull an ordinal out of ``s`` (lower-cased), returning (remainder, ordinal).

    Explicit markers (vol/part/ep…) win; otherwise a bare trailing number.
    """
    m = _ORDINAL_MARKER_RE.search(s)
    if m:
        marker = m.group("marker").lower()
        ordinal = Ordinal(
            cls=_MARKER_CLASS.get(marker, ""),
            number=int(m.group("num")),
            raw=m.group(0).strip(),
        )
        remainder = (s[: m.start()] + " " + s[m.end():])
        return remainder, ordinal

    m = _TRAILING_NUM_RE.search(s)
    if m:
        ordinal = Ordinal(cls="", number=int(m.group("num")), raw=m.group("num"))
        return s[: m.start()], ordinal

    return s, None


def _classify_token(tok: str) -> str | None:
    """Return a normalized quality tag if ``tok`` is a rendering token, else None.

    Recognizes resolution buckets, upscalers (with optional trailing digits like
    'iris3'), aspect markers, codecs, and misc release noise.
    """
    res_map, upscalers, aspects, codecs, misc = _token_sets()
    if tok in res_map:
        return res_map[tok]
    wm = _WORD_NUM_RE.match(tok)
    base = wm.group(1) if wm else tok
    if base in upscalers:
        return base
    if tok in aspects or base in aspects:
        return base if base in aspects else tok
    if tok in codecs:
        return tok
    if tok in misc:
        return tok
    return None


def canonicalize(path: str | Path) -> RecognizedFile:
    """Classify one filename into its role and title identity.

    Pure and fast — no filesystem access beyond reading the path string.
    """
    p = Path(path)
    role, channel, channel_info, stem = _role_and_stem(p)

    # 1. Drop bracketed edit tags: [E-Stim Edit], (final), {v2}.
    work = _BRACKET_RE.sub(" ", stem).lower()

    # 2. Pull the ordinal out (before token stripping so "Pt 1" is seen whole).
    work, ordinal = _extract_ordinal(work)

    # 3. Split into words; drop rendering tokens, keep the name.
    name_tokens: list[str] = []
    tags: set[str] = set()
    best_res: str | None = None
    res_map = _token_sets()[0]
    for tok in _SPLIT_RE.split(work):
        if not tok:
            continue
        tag = _classify_token(tok)
        if tag is None:
            name_tokens.append(tok)
            continue
        tags.add(tag)
        if tok in res_map or tag in res_map.values():
            # Track the best (lowest-rank) resolution bucket seen.
            if best_res is None or resolution_rank(tag) < resolution_rank(best_res):
                best_res = tag

    canonical_key = " ".join(name_tokens).strip()
    if not canonical_key:
        # Stripping emptied it (e.g. "4k.mp4") — fall back to the raw stem so a
        # title identity always exists.
        canonical_key = re.sub(r"\s+", " ", stem.lower()).strip()

    return RecognizedFile(
        path=str(p),
        role=role,
        canonical_key=canonical_key,
        ordinal=ordinal,
        resolution=best_res,
        variant_tags=frozenset(tags),
        channel=channel,
        channel_info=channel_info,
    )
