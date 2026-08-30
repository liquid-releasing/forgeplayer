# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Contract tests for the native file/folder dialogs.

We deliberately never let the real Win32 dialogs run here — they would pop a
modal window and block the test run. What's tested is the contract every caller
depends on: the work happens on a *separate* thread (the whole reason the app
doesn't hang while libmpv plays in-process), failures surface as
`NativeDialogUnavailable` so the caller can drop to QFileDialog, and no picker
in the app calls QFileDialog outside that fallback.
"""
from __future__ import annotations

import ast
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from app import native_dialog

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# The only functions allowed to touch QFileDialog directly — each is the
# documented non-Windows / native-error fallback. A new picker that calls
# QFileDialog itself reintroduces both the "old selector" chrome and the
# in-process-mpv hang, so this list is the gate.
_FALLBACK_FUNCTIONS = {
    "_pick_file",        # control_window: open
    "_pick_save_file",   # control_window: save-as
    "_pick_folder",      # control_window: folder
    "_pick_root",        # library_panel: library root folder
}


@pytest.mark.parametrize("call", [
    lambda: native_dialog.native_open_file("t", "/tmp", [("All", "*.*")]),
    lambda: native_dialog.native_save_file("t", "/tmp", [("All", "*.*")], "x"),
    lambda: native_dialog.native_pick_folder("t", "/tmp"),
])
def test_non_windows_signals_fallback(monkeypatch, call):
    monkeypatch.setattr(native_dialog.sys, "platform", "linux")
    with pytest.raises(native_dialog.NativeDialogUnavailable):
        call()


def test_work_runs_off_the_calling_thread(monkeypatch):
    """The GUI thread must never own the dialog's modal pump — that's the
    deadlock against mpv's event delivery."""
    monkeypatch.setattr(native_dialog.sys, "platform", "win32")
    seen: dict = {}

    def work():
        seen["thread"] = threading.current_thread()
        return "C:\\Videos"

    assert native_dialog._run_on_sta(work) == "C:\\Videos"
    assert seen["thread"] is not threading.current_thread()


def test_worker_error_becomes_fallback_signal(monkeypatch):
    """Callers catch exactly one exception type — a Win32/ctypes failure has to
    arrive as NativeDialogUnavailable, not as OSError from a dead thread."""
    monkeypatch.setattr(native_dialog.sys, "platform", "win32")

    def boom():
        raise OSError("CoCreateInstance(FileOpenDialog) failed")

    with pytest.raises(native_dialog.NativeDialogUnavailable) as exc:
        native_dialog._run_on_sta(boom)
    assert "CoCreateInstance" in str(exc.value)


def test_waiter_keeps_the_gui_thread_pumping(monkeypatch, qapp):
    """The GUI thread must run an event loop while the dialog is open.

    A GUI thread parked in join() stops repainting, and Windows stamps
    "(Not Responding)" on the title bar after a few seconds — indistinguishable
    from a real freeze to the person using it.
    """
    import time

    from app.native_dialog import qt_modal_waiter

    monkeypatch.setattr(native_dialog.sys, "platform", "win32")
    ticks = {"n": 0}
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.__setitem__("n", ticks["n"] + 1))
    timer.start()

    def work():
        time.sleep(0.25)          # stands in for the user browsing folders
        return r"C:\Users\me\Videos"

    try:
        result = native_dialog._run_on_sta(work, qt_modal_waiter(None))
    finally:
        timer.stop()

    assert result == r"C:\Users\me\Videos"
    assert ticks["n"] > 0, "event loop never ran — the window would grey out"


def test_waiter_blocks_input_to_its_window(monkeypatch, qapp):
    """The native dialog is owner-less, so nothing else enforces modality."""
    from app.native_dialog import qt_modal_waiter

    import time

    monkeypatch.setattr(native_dialog.sys, "platform", "win32")
    widget = QWidget()
    seen: dict = {}

    def work():
        # The waiter disables the window just after the thread starts, so wait
        # for it rather than racing it — a real dialog is open for seconds.
        deadline = time.time() + 2
        while time.time() < deadline and widget.isEnabled():
            time.sleep(0.01)
        seen["enabled_during"] = widget.isEnabled()
        return None

    native_dialog._run_on_sta(work, qt_modal_waiter(widget))
    assert seen["enabled_during"] is False
    assert widget.isEnabled(), "window must be re-enabled once the dialog closes"


def test_cancel_returns_none(monkeypatch):
    monkeypatch.setattr(native_dialog.sys, "platform", "win32")
    assert native_dialog._run_on_sta(lambda: None) is None


def _qfiledialog_call_sites() -> list[tuple[str, str, int]]:
    """(file, enclosing function, line) for every QFileDialog.getX(...) call."""
    sites: list[tuple[str, str, int]] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if "vendor" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "QFileDialog"
                    and node.func.attr.startswith("get")
                ):
                    sites.append((path.name, func.name, node.lineno))
    return sites


def test_every_picker_routes_through_the_native_dialog():
    """Regression gate for "all of the selectors".

    The Live-tab browse buttons were fixed in 2d0dddf but the folder and
    session pickers kept calling QFileDialog on the GUI thread — so the Library
    root picker still showed the old chrome and still froze the app. Any new
    QFileDialog call outside a fallback helper fails here.
    """
    offenders = [
        s for s in _qfiledialog_call_sites() if s[1] not in _FALLBACK_FUNCTIONS
    ]
    assert not offenders, (
        "these call QFileDialog directly instead of app/native_dialog.py: "
        + ", ".join(f"{f}:{line} in {fn}()" for f, fn, line in offenders)
    )


def test_fallback_helpers_are_all_present():
    """Guards the list above against a rename silently emptying the gate."""
    found = {
        fn for _f, fn, _line in _qfiledialog_call_sites()
    }
    assert found == _FALLBACK_FUNCTIONS


# ── owner window (dogfood 2026-08-30) ────────────────────────────────────────
#
# The dialogs used to be shown owner-less, so Windows placed them wherever it
# liked. On a 5120-wide ultrawide the Library root picker opened ~1900px from
# the console, and because qt_modal_waiter disables the console for the
# dialog's lifetime, the app just looked hung. An owner window makes Windows
# place the dialog on the owner's monitor.

def test_owner_is_dropped_without_a_waiter():
    """An owned dialog needs its owner's thread to keep pumping. That is the
    whole reason these were owner-less; the rule now lives in one place so no
    call site can pair an owner with a blocked GUI thread."""
    assert native_dialog._safe_owner(None, 4242) == 0


def test_owner_is_kept_when_a_waiter_pumps():
    assert native_dialog._safe_owner(lambda _t: None, 4242) == 4242


def test_owner_hwnd_for_handles_no_widget():
    assert native_dialog.owner_hwnd_for(None) == 0


def test_owner_hwnd_for_survives_a_broken_widget():
    """Placement is a nicety; failing to compute it must never break the
    picker, which is the part the user actually needs."""
    class _Broken:
        def window(self):
            raise RuntimeError("widget already destroyed")

    assert native_dialog.owner_hwnd_for(_Broken()) == 0


def test_owner_hwnd_for_returns_the_top_level_window(qapp):
    from PySide6.QtWidgets import QWidget

    top = QWidget()
    child = QWidget(top)
    assert native_dialog.owner_hwnd_for(child) == int(top.winId())


def test_every_native_picker_call_passes_an_owner():
    """Regression gate: a new picker that forgets owner_hwnd reintroduces the
    off-monitor dialog, which reads as a hung app rather than a misplaced
    window — so it is worth failing the build over."""
    import ast

    wanted = {"native_open_file", "native_save_file", "native_pick_folder"}
    offenders = []
    for path in (Path("app/control_window.py"), Path("app/library_panel.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None,
            )
            if fn not in wanted:
                continue
            if not any(kw.arg == "owner_hwnd" for kw in node.keywords):
                offenders.append(f"{path.name}:{node.lineno} {fn}()")

    assert not offenders, (
        "these open a native dialog without an owner window, so it can land "
        "on another monitor while the console sits disabled: "
        + ", ".join(offenders)
    )
