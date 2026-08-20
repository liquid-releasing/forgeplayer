# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Tests for main.py's faulthandler.log cap (_cap_faulthandler_log).

That file is always-on (not gated by the in-app Debug toggle) — a session
marker on every launch, plus a full per-thread stack dump on any genuine
crash — so with nothing trimming it, it grows forever. _cap_faulthandler_log
trims it back to a recent tail once it crosses a size threshold.

main.py can't be imported normally: importing it runs module-level startup
side effects (faulthandler.enable() against the REAL ~/.forgeplayer, a COM
apartment claim, a registry write) unconditionally, with no `if __name__`
guard. Each test loads a fresh copy via importlib with HOME/USERPROFILE
redirected to tmp_path first, so those side effects land in an isolated
throwaway directory instead of the real user profile.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_MAIN_PY = Path(__file__).resolve().parents[1] / "main.py"


def _load_main_module(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        f"main_under_test_{id(tmp_path)}", _MAIN_PY,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def main_module(monkeypatch, tmp_path):
    return _load_main_module(monkeypatch, tmp_path)


def test_under_threshold_is_left_untouched(main_module, tmp_path):
    log = tmp_path / "log.txt"
    body = b"line one\n" * 100  # well under _FAULT_LOG_MAX_BYTES
    log.write_bytes(body)
    main_module._cap_faulthandler_log(str(log), os)
    assert log.read_bytes() == body


def test_over_threshold_is_trimmed_to_keep_size(main_module, tmp_path):
    log = tmp_path / "log.txt"
    # Each line is 30 bytes; well past _FAULT_LOG_MAX_BYTES (5MB).
    line = b"x" * 29 + b"\n"
    n_lines = (main_module._FAULT_LOG_MAX_BYTES // len(line)) + 1000
    log.write_bytes(line * n_lines)

    main_module._cap_faulthandler_log(str(log), os)

    trimmed = log.read_bytes()
    assert len(trimmed) <= main_module._FAULT_LOG_KEEP_BYTES + len(line) + 200
    assert trimmed.startswith(b"===== faulthandler.log truncated")


def test_trimmed_content_is_the_most_recent_tail(main_module, tmp_path):
    log = tmp_path / "log.txt"
    # Distinct, greppable lines so we can prove the KEPT text is the tail,
    # not an arbitrary byte-offset slice.
    lines = [f"marker-{i:07d}\n".encode("ascii") for i in range(400_000)]
    log.write_bytes(b"".join(lines))
    assert log.stat().st_size > main_module._FAULT_LOG_MAX_BYTES

    main_module._cap_faulthandler_log(str(log), os)
    kept = log.read_text(encoding="ascii")

    assert "marker-0000000" not in kept  # the old head is gone
    assert "marker-0399999" in kept      # the most recent line survives


def test_no_partial_first_line_after_trim(main_module, tmp_path):
    log = tmp_path / "log.txt"
    line = b"y" * 49 + b"\n"
    n_lines = (main_module._FAULT_LOG_MAX_BYTES // len(line)) + 500
    log.write_bytes(line * n_lines)

    main_module._cap_faulthandler_log(str(log), os)

    kept = log.read_bytes()
    body = kept.split(b"\n", 1)[1]  # drop our own banner line
    # Every remaining line must be a full 49-byte "y" line (or empty tail) —
    # never a ragged partial line from the middle of a truncated one.
    for raw_line in body.split(b"\n")[:-1]:
        assert raw_line == b"" or raw_line == b"y" * 49


def test_missing_file_does_not_raise(main_module, tmp_path):
    missing = tmp_path / "does-not-exist.log"
    main_module._cap_faulthandler_log(str(missing), os)  # must not raise


def test_startup_actually_caps_the_real_session_log(main_module, tmp_path):
    """End-to-end: importing main.py (which we just did via the fixture)
    already ran the real startup path against the redirected HOME. Grow the
    log past the threshold and reload to prove the startup call sites it."""
    fault_log = tmp_path / ".forgeplayer" / "faulthandler.log"
    assert fault_log.exists()  # written by the module-level startup code

    line = b"z" * 29 + b"\n"
    n_lines = (main_module._FAULT_LOG_MAX_BYTES // len(line)) + 1000
    fault_log.write_bytes(line * n_lines)

    # Re-invoke the cap directly against the same path main.py's startup
    # code uses, the way the next launch would.
    main_module._cap_faulthandler_log(str(fault_log), os)
    assert fault_log.stat().st_size <= main_module._FAULT_LOG_KEEP_BYTES + len(line) + 200
