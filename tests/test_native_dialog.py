# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Contract tests for the native file dialog fallback.

We deliberately never call `native_open_file` on Windows here — it would pop a
real modal dialog and block the test run. We only exercise the documented
fallback contract: on a non-Windows platform it must raise
`NativeDialogUnavailable` so the caller drops to QFileDialog.
"""
from __future__ import annotations

import pytest

from app import native_dialog


def test_non_windows_signals_fallback(monkeypatch):
    monkeypatch.setattr(native_dialog.sys, "platform", "linux")
    with pytest.raises(native_dialog.NativeDialogUnavailable):
        native_dialog.native_open_file(
            "Choose a file", "/tmp", [("All files", "*.*")],
        )
