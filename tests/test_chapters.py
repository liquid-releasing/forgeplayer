# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for chapter sidecar loading + prev/next navigation helpers.

Covers the lossy-input contract: any malformed sidecar yields an empty
list rather than raising. Chapters are an optional nicety; bad data
should never block playback.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.chapters import Chapter, load_chapters, next_chapter, prev_chapter


def _write_sidecar(video: Path, payload: object) -> Path:
    sidecar = video.with_suffix(".chapters.json")
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    return sidecar


def test_load_missing_sidecar_returns_empty(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.touch()
    assert load_chapters(video) == []


def test_load_basic_sidecar_sorted_by_time(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.touch()
    _write_sidecar(video, {
        "version": "1.0",
        "chapters": [
            {"at_ms": 30000, "name": "Setup"},
            {"at_ms": 0, "name": "Intro"},
            {"at_ms": 90000, "name": "Action"},
        ],
    })
    chs = load_chapters(video)
    assert chs == [
        Chapter(at_ms=0, name="Intro"),
        Chapter(at_ms=30000, name="Setup"),
        Chapter(at_ms=90000, name="Action"),
    ]


def test_load_malformed_json_returns_empty(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.touch()
    sidecar = video.with_suffix(".chapters.json")
    sidecar.write_text("not json {{{", encoding="utf-8")
    assert load_chapters(video) == []


def test_load_top_level_not_object_returns_empty(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.touch()
    _write_sidecar(video, [{"at_ms": 0, "name": "Intro"}])
    assert load_chapters(video) == []


def test_load_chapters_field_not_a_list_returns_empty(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.touch()
    _write_sidecar(video, {"chapters": "not a list"})
    assert load_chapters(video) == []


def test_load_skips_invalid_entries(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.touch()
    _write_sidecar(video, {
        "chapters": [
            {"at_ms": 0, "name": "Good"},
            {"at_ms": "not-a-number", "name": "Bad type"},
            {"name": "No timestamp"},
            {"at_ms": 5000},
            "not a dict",
            {"at_ms": 10000, "name": "Also good"},
        ],
    })
    chs = load_chapters(video)
    assert [ch.name for ch in chs] == ["Good", "Also good"]


def test_load_skips_negative_timestamps(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.touch()
    _write_sidecar(video, {
        "chapters": [
            {"at_ms": -100, "name": "Negative"},
            {"at_ms": 0, "name": "Good"},
        ],
    })
    chs = load_chapters(video)
    assert [ch.name for ch in chs] == ["Good"]


def test_load_tolerates_extra_fields(tmp_path: Path) -> None:
    """Forward-compat: future schemas may add content_type, end_ms,
    build_state, etc. Loader keeps at_ms+name and ignores the rest."""
    video = tmp_path / "scene.mp4"
    video.touch()
    _write_sidecar(video, {
        "version": "1.5",
        "chapters": [
            {"at_ms": 0, "name": "Intro", "content_type": "music",
             "end_ms": 30000, "build_state": "built"},
        ],
    })
    chs = load_chapters(video)
    assert chs == [Chapter(at_ms=0, name="Intro")]


def test_load_accepts_string_path(tmp_path: Path) -> None:
    video = tmp_path / "scene.mp4"
    video.touch()
    _write_sidecar(video, {"chapters": [{"at_ms": 0, "name": "Intro"}]})
    chs = load_chapters(str(video))
    assert chs == [Chapter(at_ms=0, name="Intro")]


def test_next_chapter_strict_after() -> None:
    chs = [
        Chapter(at_ms=0, name="A"),
        Chapter(at_ms=30000, name="B"),
        Chapter(at_ms=60000, name="C"),
    ]
    assert next_chapter(chs, 0) == Chapter(at_ms=30000, name="B")
    assert next_chapter(chs, 29999) == Chapter(at_ms=30000, name="B")
    # Strict — exactly at a chapter goes to the *next* one.
    assert next_chapter(chs, 30000) == Chapter(at_ms=60000, name="C")
    assert next_chapter(chs, 60000) is None
    assert next_chapter(chs, 999_999) is None


def test_prev_chapter_within_grace_returns_previous() -> None:
    chs = [
        Chapter(at_ms=0, name="A"),
        Chapter(at_ms=30000, name="B"),
        Chapter(at_ms=60000, name="C"),
    ]
    # 500 ms past B's start → still within grace → prev = A.
    assert prev_chapter(chs, 30500) == Chapter(at_ms=0, name="A")
    # Exactly at B → within grace → prev = A.
    assert prev_chapter(chs, 30000) == Chapter(at_ms=0, name="A")


def test_prev_chapter_past_grace_restarts_current() -> None:
    chs = [
        Chapter(at_ms=0, name="A"),
        Chapter(at_ms=30000, name="B"),
    ]
    # 5 seconds past B → past grace → seek back to B's start.
    assert prev_chapter(chs, 35000) == Chapter(at_ms=30000, name="B")


def test_prev_chapter_at_first_chapter_within_grace_returns_none() -> None:
    chs = [
        Chapter(at_ms=0, name="A"),
        Chapter(at_ms=30000, name="B"),
    ]
    assert prev_chapter(chs, 0) is None
    assert prev_chapter(chs, 1500) is None


def test_prev_chapter_at_first_chapter_past_grace_restarts() -> None:
    chs = [
        Chapter(at_ms=0, name="A"),
        Chapter(at_ms=30000, name="B"),
    ]
    assert prev_chapter(chs, 5000) == Chapter(at_ms=0, name="A")


def test_prev_chapter_before_first_chapter_returns_none() -> None:
    """If for some reason at_ms is non-zero on the first chapter and
    the playhead is before it, there is no previous chapter."""
    chs = [Chapter(at_ms=10_000, name="Late start")]
    assert prev_chapter(chs, 5000) is None


def test_prev_next_empty_chapters_returns_none() -> None:
    assert prev_chapter([], 5000) is None
    assert next_chapter([], 5000) is None
