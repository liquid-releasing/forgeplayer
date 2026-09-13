# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Keep ``LC_NUMERIC`` at ``"C"`` so libmpv will start.

**The bug this exists for.** On macOS (and any Linux desktop with a real
``LANG``) ForgePlayer died at launch — the app "quit unexpectedly" after
printing, from libmpv's own C code::

    Non-C locale detected. This is not supported.
    Call 'setlocale(LC_NUMERIC, "C");' in your code.

libmpv refuses to create a handle unless ``LC_NUMERIC`` is ``"C"``. Its option
parser reads floats with ``strtod``, so a locale whose decimal separator isn't
``.`` would silently mis-parse every numeric option; upstream would rather fail
loudly than play back at the wrong speed.

**Why it bit us and not the library.** python-mpv already knows this and calls
``setlocale(LC_NUMERIC, "C")`` when it is imported. That is a fine fix right up
until something *re-*clobbers the locale afterwards — and Qt does exactly that:
``QCoreApplicationPrivate::init`` calls ``setlocale(LC_ALL, "")`` to pick up the
user's charset mapping, guarded on ``Q_OS_UNIX``. Our import order made that
inevitable: ``main`` imports ``app.control_window`` (and transitively ``mpv``)
at module scope, so python-mpv set the locale to ``"C"`` seconds *before*
``QApplication(sys.argv)`` set it straight back to ``en_US.UTF-8``. Every
``mpv.MPV(...)`` after that point was doomed.

**Why CI stayed green through all of it.** The clobber is only a clobber if the
environment names a non-C locale. GitHub's runners leave ``LANG`` unset, so
Qt's ``setlocale(LC_ALL, "")`` resolves to ``"C"`` and the bug is invisible;
every real desktop ships ``LANG=en_US.UTF-8`` (or similar) and reproduces it
100% of the time. Windows is unaffected for a different reason — Qt's
``setlocale`` call is inside an ``#ifdef Q_OS_UNIX``.

Only ``LC_NUMERIC`` is restored, deliberately. Qt wants the rest of the
categories it just set (``LC_CTYPE`` in particular drives its charset
handling), and ``LC_NUMERIC`` is the only one libmpv cares about — so this
narrows Qt's change rather than undoing it.
"""

from __future__ import annotations

import locale


def force_c_numeric_locale(setlocale=None) -> str | None:
    """Set ``LC_NUMERIC`` to ``"C"``; return the value it had before.

    Returns ``None`` if the locale was already ``"C"`` (nothing to do) or if
    the call failed. Idempotent and never raises: a process that somehow can't
    set the C locale is in worse trouble than we can fix here, and raising out
    of startup would replace a clear libmpv error with an opaque one.

    Call this **after** constructing ``QApplication``, not before — Qt
    overwrites the locale during construction, so an earlier call is undone.

    *setlocale* is injectable so tests can observe the calls without mutating
    the real process locale.
    """
    setlocale = locale.setlocale if setlocale is None else setlocale
    try:
        previous = setlocale(locale.LC_NUMERIC)
        if previous == "C":
            return None
        setlocale(locale.LC_NUMERIC, "C")
        return previous
    except locale.Error:
        return None
