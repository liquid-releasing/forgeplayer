# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Shared pytest fixtures.

`qapp` is the minimal pattern for constructing PySide6 widgets in tests
without pulling in pytest-qt: one QApplication for the whole session (Qt
only tolerates a single instance per process), never `.exec()`'d. Nothing
here calls `app.processEvents()` or runs the event loop, so QTimers started
by a constructed widget (poll timers, the deferred update-check) never
actually fire during a test — tests call the target methods directly
instead of waiting on real signal delivery.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolate_app_home(tmp_path, monkeypatch):
    """Keep every test out of the developer's real `~/.forgeplayer`.

    Two things made this necessary, both found on 2026-09-16:

    - `ControlWindow.__init__` reads `preferences.json` and calls
      `LibraryPanel.set_root(prefs.library_root)`, which starts a real scan of
      whatever folder the developer last opened. On this machine that was an
      external drive holding ~14k files in one folder, and the suite went from
      12s to over 120s — results that depended on a machine's saved settings
      and on a drive being plugged in.
    - Pin tests write and DELETE pin files. Pointed at the real home folder
      they would have removed the developer's own remembered picks.

    Redirecting the module-level path constants covers both: preferences, the
    pin store, and the library catalog index. Tests that need their own
    locations still monkeypatch on top of this.
    """
    import app.preferences as prefs_mod
    import app.library.pins as pins_mod

    home = tmp_path / "_forgeplayer_home"
    home.mkdir()
    monkeypatch.setattr(prefs_mod, "_PREFS_PATH", home / "preferences.json")
    monkeypatch.setattr(pins_mod, "_PINS_DIR", home / "pins")
    monkeypatch.setattr(pins_mod, "_CATALOG_PATH", home / "catalog.json")
    return home
