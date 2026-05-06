# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Chapter sidecar loader + prev/next navigation helpers.

Chapter data lives in `<video_stem>.chapters.json` next to the video
file. The forgegen handoff path (loading from `<stem>.analysis.json` →
`structural.chapter_proposals`) is a future addition; this loader
targets the hand-authored / canonical sidecar shape only.

Sidecar JSON shape (forward-compatible — extra fields tolerated):

    {
      "version": "1.0",
      "chapters": [
        {"at_ms": 0,     "name": "Intro"},
        {"at_ms": 30000, "name": "Setup"},
        {"at_ms": 90000, "name": "Action"}
      ]
    }

Malformed files (bad JSON, missing fields, negative timestamps) yield
an empty chapter list rather than raising — chapters are an optional
nicety, not a precondition for playback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Within this many ms of a chapter's start, "previous" goes to the
# chapter before. Past this window, "previous" restarts the current
# chapter — same convention music players use, so users can always
# rewind a chapter by tapping prev once.
_PREV_GRACE_MS = 2000


@dataclass(frozen=True)
class Chapter:
    at_ms: int
    name: str


def load_chapters(video_path: Path | str) -> list[Chapter]:
    """Load chapters from `<stem>.chapters.json` next to the video file.

    Returns chapters sorted by at_ms ascending. Empty list when the
    sidecar is missing, unreadable, malformed, or contains no valid
    chapter entries.
    """
    sidecar = Path(video_path).with_suffix(".chapters.json")
    if not sidecar.exists():
        return []
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    raw = data.get("chapters") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[Chapter] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            at_ms = int(entry["at_ms"])
            name = str(entry["name"])
        except (KeyError, TypeError, ValueError):
            continue
        if at_ms < 0:
            continue
        out.append(Chapter(at_ms=at_ms, name=name))
    out.sort(key=lambda ch: ch.at_ms)
    return out


def prev_chapter(chapters: list[Chapter], position_ms: int) -> Chapter | None:
    """Return the chapter to seek to when the user clicks Prev.

    If the playhead is more than 2s into the current chapter, returns
    that chapter (restart it). Otherwise returns the previous chapter,
    or None if already at the first chapter or before all chapters.
    """
    if not chapters:
        return None
    current_idx = -1
    for i, ch in enumerate(chapters):
        if ch.at_ms <= position_ms:
            current_idx = i
        else:
            break
    if current_idx < 0:
        return None
    current = chapters[current_idx]
    if position_ms - current.at_ms > _PREV_GRACE_MS:
        return current
    if current_idx == 0:
        return None
    return chapters[current_idx - 1]


def next_chapter(chapters: list[Chapter], position_ms: int) -> Chapter | None:
    """Return the first chapter strictly after position_ms, or None."""
    for ch in chapters:
        if ch.at_ms > position_ms:
            return ch
    return None
