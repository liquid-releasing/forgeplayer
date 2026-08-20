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
