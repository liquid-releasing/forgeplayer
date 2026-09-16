# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
r"""A slow scan must be distinguishable from a broken one in the log.

Dogfood 2026-09-16: the library was pointed at `G:\Telegram Desktop`, which
holds a non-media folder of ~13,900 files. The walk took minutes. The only UI
feedback was a small "Scanning…" label, and the debug stream went silent
between `library.root_changed` and the cards appearing, so the report — "root
folder does not seem to be updating" — could not be answered from a log at all.

Duration and entry count turn that into a one-line answer, and a failed or
superseded scan now says so instead of looking identical to an empty folder.
"""

from __future__ import annotations

import pytest

from app.debug_log import DebugLog
from app.library_panel import _ScanJob, _ScanSignals


@pytest.fixture(autouse=True)
def events():
    was = DebugLog.enabled
    DebugLog.set_enabled(False)          # no stream file
    DebugLog._events.clear()
    DebugLog.enabled = True              # capture in memory
    yield DebugLog._events
    DebugLog._events.clear()
    DebugLog.enabled = was


class _Sig:
    """Stands in for _ScanSignals — captures the emit instead of needing Qt."""

    def __init__(self):
        self.emitted = []
        self.done = self

    def emit(self, root, entries):
        self.emitted.append((root, entries))


# DebugLog is a process-wide singleton and the panel's scans run on a thread
# pool, so a scan started by ANOTHER test can land in the middle of this one.
# Every assertion here is therefore scoped to the root under test rather than
# to the event list as a whole.

def _for_root(events, root):
    return [e for e in events if e.get("root") == root]


def _kinds(events, root):
    return [e["kind"] for e in _for_root(events, root)]


def _one(events, kind, root):
    matching = [e for e in _for_root(events, root) if e["kind"] == kind]
    assert len(matching) == 1, (
        f"expected one {kind} for {root}, got {_kinds(events, root)}"
    )
    return matching[0]


def test_a_scan_reports_start_and_finish(tmp_path, events):
    scene = tmp_path / "Scene"
    scene.mkdir()
    (scene / "Scene.mp4").write_bytes(b"\x00")

    sig = _Sig()
    _ScanJob(str(tmp_path), sig).run()

    root = str(tmp_path)
    assert _one(events, "library.scan_started", root)["root"] == root
    done = _one(events, "library.scan_done", root)
    assert done["entries"] >= 1
    assert isinstance(done["seconds"], float)
    assert sig.emitted[0][0] == str(tmp_path)


def test_the_haptic_split_is_recorded(tmp_path, events):
    """`entries` alone doesn't say whether the user got what they came for —
    ForgePlayer is a launcher for haptic scenes, so how many carry funscripts
    is the number that matters in a report."""
    scene = tmp_path / "Scene"
    scene.mkdir()
    (scene / "Scene.mp4").write_bytes(b"\x00")
    (scene / "Scene.alpha.funscript").write_text('{"actions": []}', encoding="utf-8")

    _ScanJob(str(tmp_path), _Sig()).run()

    assert _one(events, "library.scan_done", str(tmp_path))["with_funscripts"] >= 1


def test_an_empty_root_still_reports_done(tmp_path, events):
    """Zero scenes is an ANSWER. It used to look the same as a scan that never
    ran, which is the ambiguity this whole file exists to remove."""
    _ScanJob(str(tmp_path), _Sig()).run()
    assert _one(events, "library.scan_done", str(tmp_path))["entries"] == 0


def test_a_failing_scan_is_logged_and_still_emits(monkeypatch, tmp_path, events):
    """A bad root must not kill the pool, and must not look like an empty
    folder either."""
    import app.library_panel as panel

    def boom(_root):
        raise OSError("drive went away")

    monkeypatch.setattr(panel, "scan_library_root", boom)
    sig = _Sig()
    _ScanJob(str(tmp_path), sig).run()

    root = str(tmp_path)
    assert "library.scan_done" not in _kinds(events, root)
    assert "drive went away" in _one(events, "library.scan_failed", root)["error"]
    # Still emits, so the buttons get re-enabled on the GUI thread.
    assert sig.emitted == [(str(tmp_path), [])]
