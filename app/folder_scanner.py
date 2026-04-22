# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""FolderScanner — scan a folder for media and auto-assign to monitor slots."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".ogg"}


@dataclass
class MediaFile:
    path: str
    width: int = 0
    height: int = 0
    is_video: bool = False
    is_audio: bool = False


def probe_video_size(path: str) -> tuple[int, int]:
    """Return (width, height) via ffprobe; (0, 0) on error or timeout."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                w = stream.get("width", 0)
                h = stream.get("height", 0)
                return int(w), int(h)
    except Exception:
        pass
    return 0, 0


def scan_folder(folder: str) -> list[MediaFile]:
    """Return all media files directly inside *folder* (non-recursive)."""
    files: list[MediaFile] = []
    try:
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in VIDEO_EXTS:
                w, h = probe_video_size(path)
                files.append(MediaFile(path=path, width=w, height=h, is_video=True))
            elif ext in AUDIO_EXTS:
                files.append(MediaFile(path=path, is_audio=True))
    except Exception:
        pass
    return files


def _aspect_ratio(w: int, h: int) -> float:
    return w / h if h else 0.0


def _ar_similarity(video_ar: float, screen_ar: float) -> float:
    """Score 0–1; higher = better match."""
    if video_ar == 0 or screen_ar == 0:
        return 0.0
    denom = max(video_ar, screen_ar)
    return 1.0 - abs(video_ar - screen_ar) / denom


def auto_assign(
    folder: str,
    screen_sizes: list[tuple[int, int]],   # [(width, height), ...]
    max_slots: int = 3,
) -> list[dict]:
    """
    Scan *folder* and return up to *max_slots* slot config dicts:
      {"video_path": str, "audio_path": str, "monitor_index": int}

    Matching strategy
    -----------------
    * Each video is scored against every screen by aspect-ratio similarity.
    * A greedy pass assigns each screen the best unassigned video.
    * Audio files are paired by matching filename stem (case-insensitive).
    * If there are more videos than screens, remaining videos fill remaining
      slot positions using the last screen index.
    """
    media = scan_folder(folder)
    videos = [m for m in media if m.is_video]
    audio_map: dict[str, str] = {
        os.path.splitext(os.path.basename(m.path))[0].lower(): m.path
        for m in media if m.is_audio
    }

    screen_ars = [_aspect_ratio(w, h) for w, h in screen_sizes]

    assigned: list[dict] = []
    used: set[str] = set()

    # Greedy: for each screen, pick the best matching video
    for screen_idx, s_ar in enumerate(screen_ars):
        if len(assigned) >= max_slots:
            break
        best: MediaFile | None = None
        best_score = -1.0
        for v in videos:
            if v.path in used:
                continue
            score = _ar_similarity(_aspect_ratio(v.width, v.height), s_ar)
            if score > best_score:
                best_score, best = score, v
        if best is None:
            continue
        used.add(best.path)
        stem = os.path.splitext(os.path.basename(best.path))[0].lower()
        assigned.append({
            "video_path": best.path,
            "audio_path": audio_map.get(stem, ""),
            "monitor_index": screen_idx,
        })

    # Any leftover videos (more videos than screens) go to the last screen
    fallback_screen = len(screen_sizes) - 1 if screen_sizes else 0
    for v in videos:
        if len(assigned) >= max_slots:
            break
        if v.path in used:
            continue
        used.add(v.path)
        stem = os.path.splitext(os.path.basename(v.path))[0].lower()
        assigned.append({
            "video_path": v.path,
            "audio_path": audio_map.get(stem, ""),
            "monitor_index": fallback_screen,
        })

    return assigned[:max_slots]
