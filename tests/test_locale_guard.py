# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Regression tests for the libmpv "Non-C locale detected" launch crash.

The bug: Qt's QApplication constructor calls `setlocale(LC_ALL, "")` on Unix,
undoing the `LC_NUMERIC="C"` that importing python-mpv had set — and libmpv
refuses to create a handle under a non-C LC_NUMERIC, so the app died at launch
on every Mac and Linux desktop. See app/locale_guard.py for the full write-up.

These tests mostly drive `setlocale` through an injected fake rather than the
real one, so they assert the same behaviour on a CI runner with no locales
installed as on a developer's `en_US.UTF-8` machine.
"""

from __future__ import annotations

import locale

import pytest

from app.locale_guard import force_c_numeric_locale


class _FakeSetlocale:
    """Stand-in for `locale.setlocale` that records every call."""

    def __init__(self, current: str = "C", raises: bool = False):
        self.current = current
        self.raises = raises
        self.calls: list[tuple] = []

    def __call__(self, category, value=None):
        self.calls.append((category, value))
        if self.raises:
            raise locale.Error("unsupported locale setting")
        if value is None:
            return self.current
        self.current = value
        return value


def test_sets_c_when_locale_was_clobbered():
    """The Qt-clobbered case: restore "C" and report what it was."""
    fake = _FakeSetlocale(current="en_US.UTF-8")

    previous = force_c_numeric_locale(setlocale=fake)

    assert previous == "en_US.UTF-8"
    assert fake.current == "C"
    assert (locale.LC_NUMERIC, "C") in fake.calls


def test_no_write_when_already_c():
    """Idempotent — an already-correct locale is left alone, not re-set."""
    fake = _FakeSetlocale(current="C")

    assert force_c_numeric_locale(setlocale=fake) is None
    # Only the read; no write call carrying a value.
    assert [c for c in fake.calls if c[1] is not None] == []


def test_touches_only_lc_numeric():
    """Qt set LC_ALL deliberately (LC_CTYPE drives its charset handling).

    We narrow that change rather than undoing it, so no other category may be
    written — LC_ALL in particular would clobber Qt right back.
    """
    fake = _FakeSetlocale(current="de_DE.UTF-8")

    force_c_numeric_locale(setlocale=fake)

    assert {category for category, _ in fake.calls} == {locale.LC_NUMERIC}


def test_locale_error_is_swallowed():
    """Never raise out of app startup: a libmpv error message beats an opaque
    traceback from the guard that was supposed to prevent it."""
    fake = _FakeSetlocale(current="en_US.UTF-8", raises=True)

    assert force_c_numeric_locale(setlocale=fake) is None


def test_lc_numeric_is_c_after_a_real_qapplication(qapp):
    """End-to-end shape of the actual bug, against the real locale.

    On a machine with LANG set, constructing QApplication has by now flipped
    LC_NUMERIC away from "C" — that is the crash. On CI (LANG unset) it never
    moved. Either way the guard must leave it at "C", which is the condition
    libmpv checks before it will start.
    """
    assert qapp is not None  # QApplication is constructed by the fixture

    force_c_numeric_locale()

    assert locale.setlocale(locale.LC_NUMERIC) == "C"
