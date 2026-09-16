# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Browse must survive its own instrumentation.

v0.1.22-alpha added logging to `_on_browse_stim` so a user could tell us why
Browse "did nothing". The logging call was:

    DebugLog.record("browse.stim_picked", path=..., kind=..., ...)

`DebugLog.record(cls, kind, **fields)` already had a parameter named `kind`, so
that raised `TypeError: got multiple values for argument 'kind'` — at bind
time, before a single line of either function ran. Every Browse pick aborted
out of the Qt slot, and nothing reached the log *because the logging call was
what failed*.

That produced a uniquely misleading report (2026-09-13, again 2026-09-16):

    "I can select a funscript file but it doesn't get loaded/accepted.
     I also don't see any entries in the debug*.json files when pressing
     the browse button and selecting a file."

The empty log read as evidence of an old build. It was evidence of this.

Nothing caught it because the tests stopped either side of the break: they
covered `_funscript_set_from_path` (before) and `_on_stim_folder_scanned`
(after), and never called the entry point that actually runs when a user
clicks Browse. These tests call it.
"""

from __future__ import annotations

import types

import pytest

from app.control_window import ControlWindow
from app.debug_log import DebugLog
from app.library.catalog import SceneCatalogEntry, VideoVariant
from app.select_picker import SelectionChoices


@pytest.fixture(autouse=True)
def capture_debug():
    was = DebugLog.enabled
    DebugLog.set_enabled(False)      # no stream file
    DebugLog._events.clear()
    DebugLog.enabled = True          # capture in memory only
    yield DebugLog._events
    DebugLog._events.clear()
    DebugLog.enabled = was


# ── The API that allowed it ──────────────────────────────────────────────────

@pytest.mark.parametrize("reserved", ["kind", "t", "wall"])
def test_record_survives_a_field_named_like_the_envelope(capture_debug, reserved):
    """A caller must never be able to break a feature by choosing an unlucky
    field name. `kind` is the one that actually shipped broken."""
    DebugLog.record("some.event", **{reserved: "value"})

    assert len(capture_debug) == 1
    event = capture_debug[0]
    assert event["kind"] == "some.event", "the event lost its own identity"
    assert event[f"field_{reserved}"] == "value"


def test_ordinary_fields_are_untouched(capture_debug):
    DebugLog.record("some.event", path="x", count=3)
    assert capture_debug[0]["path"] == "x"
    assert capture_debug[0]["count"] == 3


# ── The entry point itself ───────────────────────────────────────────────────

class _Btn:
    def __init__(self):
        self.enabled = True

    def setEnabled(self, on):
        self.enabled = on


class _Pool:
    """Stands in for the scan thread pool — records rather than threads, so the
    funscript branch is exercised synchronously and deterministically."""

    def __init__(self):
        self.started = []

    def start(self, job):
        self.started.append(job)


class _Window:
    """Only what `_on_browse_stim` touches."""

    def __init__(self, entry, picked):
        self._current_entry = entry
        self._current_choices = SelectionChoices(
            video=entry.videos[0] if entry.videos else None,
            audio=None, funscript_set=None, subtitle=None,
        )
        self._stim_browse_btn = _Btn()
        self._stim_scan_pool = _Pool()
        self._stim_scan_signals = types.SimpleNamespace()
        self._stim_scan_target_entry = None
        self._picked = picked
        self.reloads = 0
        self.persisted = []

    def _pick_source_file(self, *a, **k):
        return self._picked

    def _reload_current_scene(self):
        self.reloads += 1

    def _persist_current_pin(self, reason):
        self.persisted.append(reason)


def _scene(tmp_path):
    """A video-only scene, which is the case the user reproduced: a flat folder
    of videos with no funscripts anywhere near them."""
    folder = tmp_path / "New folder"
    folder.mkdir()
    video = folder / "Clip.mp4"
    video.write_bytes(b"\x00")
    entry = SceneCatalogEntry(folder_path=str(folder), name="Clip")
    entry.videos.append(VideoVariant(path=str(video)))
    return entry


def test_browsing_an_audio_file_does_not_raise(tmp_path, capture_debug):
    """THE bug. Before the fix this raised TypeError out of the Qt slot."""
    entry = _scene(tmp_path)
    mp3 = tmp_path / "estim audio" / "Drumming_ Pt. I.mp3"
    mp3.parent.mkdir()
    mp3.write_bytes(b"\x00")

    win = _Window(entry, str(mp3))
    ControlWindow._on_browse_stim(win)     # must not raise

    assert win._current_choices.audio is not None
    assert win._current_choices.audio.path == str(mp3)
    assert [a.path for a in entry.audio_tracks] == [str(mp3)]
    assert win.reloads == 1
    assert win.persisted == ["browse_stim_audio"]


def test_browsing_an_audio_file_is_logged(tmp_path, capture_debug):
    """The log entry whose absence was mistaken for an old build."""
    entry = _scene(tmp_path)
    mp3 = tmp_path / "s.mp3"
    mp3.write_bytes(b"\x00")

    ControlWindow._on_browse_stim(_Window(entry, str(mp3)))

    picked = [e for e in capture_debug if e["kind"] == "browse.stim_picked"]
    assert len(picked) == 1
    assert picked[0]["source_kind"] == "audio"
    assert picked[0]["outside_scene_folder"] is True


def test_browsing_a_funscript_does_not_raise(tmp_path, capture_debug):
    """Same crash, the other branch — this is the one the first reporter hit."""
    entry = _scene(tmp_path)
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    fs = scripts / "Whatever.funscript"
    fs.write_text('{"actions": []}', encoding="utf-8")

    win = _Window(entry, str(fs))
    ControlWindow._on_browse_stim(win)     # must not raise

    picked = [e for e in capture_debug if e["kind"] == "browse.stim_picked"]
    assert len(picked) == 1
    assert picked[0]["source_kind"] == "funscript"
    # The folder scan is handed off; the button stays disabled until it lands.
    assert len(win._stim_scan_pool.started) == 1
    assert win._stim_browse_btn.enabled is False
    assert win._stim_scan_target_entry is entry


def test_cancelling_the_dialog_logs_nothing_and_changes_nothing(tmp_path,
                                                                capture_debug):
    entry = _scene(tmp_path)
    win = _Window(entry, None)

    ControlWindow._on_browse_stim(win)

    assert capture_debug == []
    assert win.reloads == 0
    assert win.persisted == []
    assert win._current_choices.audio is None


def test_a_source_in_the_scene_folder_is_marked_as_such(tmp_path, capture_debug):
    """`outside_scene_folder` is the field that tells us whether the user is
    hitting the cross-folder case at all, so it has to be right both ways."""
    entry = _scene(tmp_path)
    inside = tmp_path / "New folder" / "beside.mp3"
    inside.write_bytes(b"\x00")

    ControlWindow._on_browse_stim(_Window(entry, str(inside)))

    picked = [e for e in capture_debug if e["kind"] == "browse.stim_picked"]
    assert picked[0]["outside_scene_folder"] is False
