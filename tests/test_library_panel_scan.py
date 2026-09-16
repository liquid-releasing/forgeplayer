# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for LibraryPanel's async root scan (_ScanJob/_ScanSignals) and its
staleness guard.

_rescan() used to call scan_library_root() synchronously on the GUI thread —
a root on a spun-down/disconnected drive could block the whole app for a long
time with zero feedback (2026-08-20 dogfood: "took more than a minute with no
return in sight"). It's since moved to a QThreadPool worker.

These tests call _on_scan_done directly rather than waiting on the real
worker thread + queued cross-thread signal: the QThreadPool/Signal plumbing
itself is PySide6's own well-tested machinery, and since our tests never pump
the Qt event loop (no qapp.processEvents()/exec()), a queued cross-thread
signal literally cannot be delivered here regardless of how fast the worker
finishes — calling the slot directly is what actually exercises the
app-specific logic worth protecting: the "is this result still relevant"
guard.
"""

from __future__ import annotations

from app.library.catalog import SceneCatalogEntry
import pytest

from app.library_panel import LibraryPanel


def _entry(name: str) -> SceneCatalogEntry:
    return SceneCatalogEntry(folder_path=f"/scenes/{name}", name=name)


def test_rescan_with_empty_root_clears_model_synchronously(qapp, tmp_path):
    panel = LibraryPanel()
    panel._root = ""
    panel._model.load([_entry("stale")])

    panel._rescan()

    assert panel._model._all == []


def test_rescan_dispatches_and_shows_scanning_state(qapp, tmp_path):
    panel = LibraryPanel()
    panel._root = str(tmp_path)  # a real, empty, fast-to-scan directory

    panel._rescan()

    # The worker thread runs concurrently, but its result can only be
    # delivered through a queued signal once the Qt event loop is pumped —
    # which this test never does — so this state is guaranteed to still
    # hold immediately after _rescan() returns, not just "usually".
    assert panel._pick_btn.isEnabled() is False
    assert panel._rescan_btn.isEnabled() is False
    # Asserts the PROPERTY, not the exact wording: the label has to say a scan
    # is under way AND name the folder. A bare "Scanning…" read as "nothing is
    # happening" once a big external root pushed the walk past a few minutes
    # (dogfood 2026-09-16), so the folder name and the "can take a few minutes"
    # warning were added. Pinning the literal string just makes that kind of
    # wording fix look like a regression.
    label = panel._count_label.text()
    assert "Scanning" in label
    assert tmp_path.name in label


def test_on_scan_done_applies_matching_root(qapp):
    panel = LibraryPanel()
    panel._root = "/library/root-a"
    panel._pick_btn.setEnabled(False)
    panel._rescan_btn.setEnabled(False)

    fresh = [_entry("Scene A"), _entry("Scene B")]
    panel._on_scan_done("/library/root-a", fresh)

    assert panel._model._all == fresh
    assert panel._pick_btn.isEnabled() is True
    assert panel._rescan_btn.isEnabled() is True


def test_on_scan_done_drops_result_for_superseded_root(qapp):
    """User changed root again before the old scan for the PREVIOUS root
    returned — that stale result must never clobber the newer pick."""
    panel = LibraryPanel()
    panel._root = "/library/root-b"  # the user has since moved on to root-b
    already_showing = [_entry("Scene from root-b")]
    panel._model.load(already_showing)

    stale_result_for_root_a = [_entry("Scene from stale root-a")]
    panel._on_scan_done("/library/root-a", stale_result_for_root_a)

    assert panel._model._all == already_showing  # untouched by the stale result
    # Buttons still re-enable regardless — the scan (whichever root it was
    # for) really did finish, so the UI shouldn't stay stuck "Scanning…".
    assert panel._pick_btn.isEnabled() is True
    assert panel._rescan_btn.isEnabled() is True


def test_on_scan_done_empty_result_for_matching_root_clears_model(qapp):
    panel = LibraryPanel()
    panel._root = "/library/root-c"
    panel._model.load([_entry("old scene")])

    panel._on_scan_done("/library/root-c", [])

    assert panel._model._all == []


# ── Busy cursor while the walk runs ──────────────────────────────────────────
#
# Dogfood 2026-09-16: pointing the library at a big external root took minutes,
# and the static UI read as "root folder does not seem to be updating". The
# cursor is the part people actually notice, so it spins for the duration.
#
# Qt's override cursor is a STACK. These tests exist mostly to guard the
# balance: an unbalanced push strands the whole app under a permanent spinner,
# and an unbalanced pop clobbers a cursor somebody else set.

def _override():
    from PySide6.QtWidgets import QApplication
    return QApplication.overrideCursor()


@pytest.fixture(autouse=True)
def _drain_override_cursors():
    """Qt's override cursor is application-global and these tests deliberately
    start scans that never deliver a result, so each one can leave a cursor
    pushed. Drain the stack around every test — otherwise the leak shows up as
    a failure in whichever test happens to run next, which is exactly how these
    first failed."""
    from PySide6.QtWidgets import QApplication
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()
    yield
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


def test_the_cursor_spins_during_a_scan(qapp, tmp_path):
    panel = LibraryPanel()
    panel._root = str(tmp_path)
    assert _override() is None

    panel._rescan()
    try:
        assert _override() is not None, "no busy cursor while scanning"
    finally:
        panel._on_scan_done(str(tmp_path), [])


def test_the_cursor_is_released_when_the_scan_lands(qapp, tmp_path):
    panel = LibraryPanel()
    panel._root = str(tmp_path)
    panel._rescan()

    panel._on_scan_done(str(tmp_path), [])

    assert _override() is None


def test_a_stale_result_still_releases_the_cursor(qapp, tmp_path):
    """The result is dropped, but the scan that owned the cursor has still
    finished. Returning early without popping is how an app ends up stuck
    showing a spinner forever."""
    panel = LibraryPanel()
    panel._root = str(tmp_path)
    panel._rescan()

    panel._on_scan_done("/some/other/root", [])

    assert _override() is None


def test_switching_to_a_missing_root_mid_scan_releases_the_cursor(qapp, tmp_path):
    panel = LibraryPanel()
    panel._root = str(tmp_path)
    panel._rescan()

    panel._root = str(tmp_path / "gone")     # e.g. the drive was unplugged
    panel._rescan()

    assert _override() is None


def test_repeated_scans_do_not_stack_cursors(qapp, tmp_path):
    """Two pushes and one pop would leave the spinner up forever. set_root()
    calls _rescan() directly, so a second scan CAN start while one is in
    flight even though the buttons are disabled."""
    panel = LibraryPanel()
    panel._root = str(tmp_path)

    panel._rescan()
    panel._rescan()
    panel._on_scan_done(str(tmp_path), [])

    assert _override() is None, "cursor stack left unbalanced"
