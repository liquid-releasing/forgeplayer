# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""A scene with a stim audio file must play it, pin or no pin.

Dogfood 2026-09-16, scene "Mistress Luiza 1":

    "the stim source is set to none, even though there is an mp3 file
     available. the preference is set to funscripts. but in other videos, it
     seems to find the audio file if there is no funscript. I wonder what is
     different here."

What was different: that scene had a **pin**. A pin records only what was
picked when it was written, so a scene pinned before its mp3 existed replays
"no stim" forever. Scenes with no pin skip replay entirely and take the
scanner's defaults, which do include the audio — hence "other videos" working
and this one not.

Activation already self-healed a missing funscript set for exactly this reason
(a bundle-backed card pinned before bundle import existed). The audio half was
simply never written.

These drive `_on_scene_activated`'s choice resolution with pins stubbed, so
they assert the decision rather than the file I/O around it.
"""

from __future__ import annotations

import types

import pytest

from app.control_window import ControlWindow
from app.debug_log import DebugLog
from app.library.catalog import AudioVariant, FunscriptSet, SceneCatalogEntry, VideoVariant
from app.library.pins import Pin


@pytest.fixture(autouse=True)
def events():
    was = DebugLog.enabled
    DebugLog.set_enabled(False)
    DebugLog._events.clear()
    DebugLog.enabled = True
    yield DebugLog._events
    DebugLog._events.clear()
    DebugLog.enabled = was


def _entry(tmp_path, *, with_audio=True, with_funscript=False):
    folder = tmp_path / "Mistress Luiza 1"
    folder.mkdir(exist_ok=True)
    entry = SceneCatalogEntry(folder_path=str(folder), name="Mistress Luiza 1")
    video = folder / "Mistress Luiza-1.mp4"
    video.write_bytes(b"\x00")
    entry.videos.append(VideoVariant(path=str(video)))
    if with_audio:
        mp3 = folder / "Mistress Luiza-1.mp3"
        mp3.write_bytes(b"\x00")
        entry.audio_tracks.append(AudioVariant(path=str(mp3)))
    if with_funscript:
        entry.funscript_sets.append(
            FunscriptSet(base_stem="Mistress Luiza-1",
                         channels={"alpha": str(folder / "x.alpha.funscript")})
        )
    return entry


def _activate(monkeypatch, entry, pin):
    """Run _on_scene_activated's resolution, capturing the choices it lands on."""
    import app.control_window as cw

    monkeypatch.setattr(cw, "load_pin", lambda _e: pin)
    monkeypatch.setattr(cw, "save_pin", lambda *a, **k: None)
    captured = {}

    win = ControlWindow.__new__(ControlWindow)
    win._resolve_bundle_backed = lambda e: e
    win._apply_scene_choices = lambda e, c, **k: captured.update(entry=e, choices=c)

    ControlWindow._on_scene_activated(win, entry)
    return captured.get("choices")


# ── The reported bug ─────────────────────────────────────────────────────────

def test_a_pin_written_before_the_mp3_existed_still_plays_it(monkeypatch,
                                                             tmp_path, events):
    """THE bug. The pin names only a video; the mp3 is right there."""
    entry = _entry(tmp_path)
    pin = Pin(scene_name="Mistress Luiza 1",
              video_filename="Mistress Luiza-1.mp4")

    choices = _activate(monkeypatch, entry, pin)

    assert choices.audio is not None, "the scene's own mp3 was ignored"
    assert choices.audio.path.endswith("Mistress Luiza-1.mp3")
    assert any(e["kind"] == "library.activate.stim_audio_autofilled"
               for e in events)


def test_a_scene_with_no_pin_was_never_broken(monkeypatch, tmp_path, events):
    """The contrast the reporter noticed — kept so the two paths stay in
    agreement rather than only one of them working."""
    choices = _activate(monkeypatch, _entry(tmp_path), None)
    assert choices.audio is not None


# ── What must NOT be overridden ──────────────────────────────────────────────

def test_a_funscript_always_wins_over_the_audio_fallback(monkeypatch,
                                                         tmp_path, events):
    """Self-heal is a last resort, not a second opinion: a scene with real
    e-stim channels must not be switched to an mp3."""
    entry = _entry(tmp_path, with_funscript=True)
    choices = _activate(monkeypatch, entry, Pin(scene_name="Mistress Luiza 1"))

    assert choices.funscript_set is not None
    assert choices.audio is None
    assert not any(e["kind"] == "library.activate.stim_audio_autofilled"
                   for e in events)


def test_a_pinned_audio_pick_is_left_alone(monkeypatch, tmp_path, events):
    """A pin that DOES name an audio track resolves normally — the fallback
    must not reach in and re-pick."""
    entry = _entry(tmp_path)
    other = tmp_path / "elsewhere.mp3"
    other.write_bytes(b"\x00")
    entry.audio_tracks.append(AudioVariant(path=str(other)))
    pin = Pin(scene_name="Mistress Luiza 1",
              audio_filename="elsewhere.mp3", audio_path=str(other))

    choices = _activate(monkeypatch, entry, pin)

    assert choices.audio.path == str(other)
    assert not any(e["kind"] == "library.activate.stim_audio_autofilled"
                   for e in events)


def test_a_scene_with_no_audio_at_all_stays_silent(monkeypatch, tmp_path,
                                                   events):
    entry = _entry(tmp_path, with_audio=False)
    choices = _activate(monkeypatch, entry, Pin(scene_name="Mistress Luiza 1"))

    assert choices.audio is None
    assert choices.funscript_set is None


# ── A remembered out-of-folder pick must be SHOWN, not just played ───────────

def test_a_pinned_out_of_folder_audio_appears_in_the_picker(monkeypatch,
                                                            tmp_path, events):
    r"""Dogfood 2026-09-16, and the nastiest of the three because it destroyed
    the user's choice on contact.

    Browse can reach any directory, and `resolve_pin` rebuilds such a pick from
    the path it recorded — so the scene really was playing
    `G:\estim\...mp3`. But the Stim source combo lists only what the SCANNER
    found in the scene folder, so there was no row to select and it displayed
    "None (silent stim)" instead. One click on that combo applied the None it
    was showing and killed the stim.

    The source that is driving the haptics has to be IN the picker. The
    dropdown still offers the scene's own audio alongside it.
    """
    entry = _entry(tmp_path)                      # has Mistress Luiza-1.mp3
    far = tmp_path / "estim" / "Once You Plug In.mp3"
    far.parent.mkdir()
    far.write_bytes(b"\x00")
    pin = Pin(scene_name="Mistress Luiza 1",
              audio_filename="Once You Plug In.mp3", audio_path=str(far))

    choices = _activate(monkeypatch, entry, pin)

    assert choices.audio.path == str(far), "the remembered pick must win"
    paths = [a.path for a in entry.audio_tracks]
    assert str(far) in paths, "the picker cannot show what isn't in the entry"
    # ...and the scene's own audio is still offered as an alternative.
    assert any(p.endswith("Mistress Luiza-1.mp3") for p in paths)
    assert any(e["kind"] == "library.activate.grafted_audio" for e in events)


def test_grafting_does_not_duplicate_a_local_pick(monkeypatch, tmp_path, events):
    """A pin naming the scene's OWN audio resolves to the entry's existing
    variant — it must not be added a second time."""
    entry = _entry(tmp_path)
    local = entry.audio_tracks[0].path
    pin = Pin(scene_name="Mistress Luiza 1",
              audio_filename="Mistress Luiza-1.mp3", audio_path=local)

    _activate(monkeypatch, entry, pin)

    assert [a.path for a in entry.audio_tracks].count(local) == 1
    assert not any(e["kind"] == "library.activate.grafted_audio" for e in events)
