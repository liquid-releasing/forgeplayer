# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Thumbnail cache-key behavior (the pure, mpv-free parts)."""

from __future__ import annotations

from pathlib import Path

from app import thumbnails


def test_cache_key_stable_for_same_file(tmp_path):
    f = tmp_path / "scene.mp4"
    f.write_bytes(b"x" * 100)
    assert thumbnails._cache_key(str(f)) == thumbnails._cache_key(str(f))


def test_cache_key_changes_when_file_changes(tmp_path):
    f = tmp_path / "scene.mp4"
    f.write_bytes(b"x" * 100)
    before = thumbnails._cache_key(str(f))
    # Different size → different signature → a stale frame won't be served.
    f.write_bytes(b"x" * 200)
    after = thumbnails._cache_key(str(f))
    assert before != after


def test_cache_key_distinct_paths_distinct_keys(tmp_path):
    a = tmp_path / "a.mp4"; a.write_bytes(b"x")
    b = tmp_path / "b.mp4"; b.write_bytes(b"x")
    assert thumbnails._cache_key(str(a)) != thumbnails._cache_key(str(b))


def test_cache_key_survives_missing_file():
    # A path that doesn't exist must not raise — it just yields a key.
    key = thumbnails._cache_key(r"C:\nope\missing.mp4")
    assert isinstance(key, str) and key


def test_cached_path_is_jpg_under_cache_dir(tmp_path):
    f = tmp_path / "scene.mp4"; f.write_bytes(b"x")
    p = thumbnails.cached_path(str(f))
    assert isinstance(p, Path)
    assert p.suffix == ".jpg"
    assert p.parent == thumbnails._CACHE_DIR
