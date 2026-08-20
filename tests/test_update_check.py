# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for app.update_check — version-tag parsing and the newer-version
comparison. The QRunnable/Signal plumbing (UpdateCheckJob) just hands off to
these functions, so it isn't retested here; what's worth locking down is the
logic that decides whether to nag the user."""

from __future__ import annotations

import json
import urllib.error

import pytest

from app.update_check import UpdateCheckResult, _parse_version, check_for_update


# ── _parse_version ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "tag, expected",
    [
        ("v0.0.15", (0, 0, 15)),
        ("0.0.15", (0, 0, 15)),
        ("V0.0.15", (0, 0, 15)),
        ("v0.0.15-alpha", (0, 0, 15)),
        ("v0.0.15+build3", (0, 0, 15)),
        ("v1.2.3-beta+build7", (1, 2, 3)),
        ("v2.0", (2, 0)),
    ],
)
def test_parse_version_valid(tag, expected):
    assert _parse_version(tag) == expected


@pytest.mark.parametrize("tag", ["", "v", "garbage", "v.", "1.2.x", "vX.Y.Z"])
def test_parse_version_unparseable_returns_none(tag):
    # Never raises — an unrecognized tag just means "can't judge newer/older".
    assert _parse_version(tag) is None


# ── check_for_update ─────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, payload: dict | None, *, raises: Exception | None = None):
    def fake_urlopen(req, timeout=None):
        if raises is not None:
            raise raises
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def test_check_for_update_reports_newer(monkeypatch):
    _patch_urlopen(monkeypatch, {"tag": "v0.0.16", "name": "ForgePlayer 0.0.16"})
    result = check_for_update("0.0.15")
    assert result == UpdateCheckResult(
        ok=True, latest_tag="v0.0.16", latest_name="ForgePlayer 0.0.16", is_newer=True,
    )


def test_check_for_update_reports_up_to_date(monkeypatch):
    _patch_urlopen(monkeypatch, {"tag": "v0.0.15", "name": "ForgePlayer 0.0.15"})
    result = check_for_update("0.0.15")
    assert result.ok is True
    assert result.is_newer is False


def test_check_for_update_current_ahead_of_published(monkeypatch):
    # A dev build running ahead of the last published tag must not nag.
    _patch_urlopen(monkeypatch, {"tag": "v0.0.14", "name": "ForgePlayer 0.0.14"})
    result = check_for_update("0.0.15")
    assert result.is_newer is False


def test_check_for_update_name_defaults_to_tag(monkeypatch):
    _patch_urlopen(monkeypatch, {"tag": "v0.0.16"})
    result = check_for_update("0.0.15")
    assert result.latest_name == "v0.0.16"


def test_check_for_update_missing_tag_is_not_ok(monkeypatch):
    _patch_urlopen(monkeypatch, {"name": "ForgePlayer (no tag)"})
    result = check_for_update("0.0.15")
    assert result.ok is False
    assert result.is_newer is False


def test_check_for_update_network_failure_is_not_ok(monkeypatch):
    _patch_urlopen(monkeypatch, None, raises=urllib.error.URLError("offline"))
    result = check_for_update("0.0.15")
    assert result == UpdateCheckResult(ok=False)


def test_check_for_update_malformed_json_is_not_ok(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(b"not json")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = check_for_update("0.0.15")
    assert result.ok is False


def test_check_for_update_unparseable_current_version_never_nags(monkeypatch):
    # A malformed local __version__ must fail closed (no dialog), not crash.
    _patch_urlopen(monkeypatch, {"tag": "v0.0.16"})
    result = check_for_update("not-a-version")
    assert result.ok is True
    assert result.is_newer is False
