# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Update check against the version badge published at forgeplayer.app.

`forgeplayer-web` (the marketing site) publishes `latest-version.json` at
its root, kept in sync with GitHub Releases by its own CI — the same badge
the site's hero text reads:

    {"tag": "v0.0.15", "name": "ForgePlayer 0.0.15", "published_at": "..."}

Checking that file here means the in-app notice can never claim a version
the site itself doesn't also claim. See forgeplayer-web/RELEASING.md for
the publish pipeline.

This is a network call — run it via UpdateCheckJob on a QThreadPool worker,
never on the GUI thread (the same rule the library-scan and stim-folder-
scan fixes established this session).
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Signal

LATEST_VERSION_URL = "https://forgeplayer.app/latest-version.json"
_TIMEOUT_S = 6.0


@dataclass
class UpdateCheckResult:
    ok: bool = False         # False = network/parse failure; nothing else is meaningful
    latest_tag: str = ""     # e.g. "v0.0.16", exactly as published
    latest_name: str = ""    # e.g. "ForgePlayer 0.0.16"
    is_newer: bool = False   # latest_tag > current_version, when both parse as X.Y.Z


def _parse_version(tag: str) -> tuple[int, ...] | None:
    """'v0.0.15' / '0.0.15' / 'v0.0.15-alpha' -> (0, 0, 15).

    None for anything that doesn't parse as dotted integers — callers treat
    that as "can't judge newer/older", not as an error to raise on. A stray
    hand-edited or future non-numeric tag should never crash the check.
    """
    core = tag.strip()
    if core[:1] in ("v", "V"):
        core = core[1:]
    core = core.split("-", 1)[0].split("+", 1)[0]
    if not core:
        return None
    try:
        return tuple(int(p) for p in core.split("."))
    except ValueError:
        return None


def check_for_update(current_version: str) -> UpdateCheckResult:
    """Synchronous network call — call from a worker thread only."""
    try:
        req = urllib.request.Request(
            LATEST_VERSION_URL,
            headers={"User-Agent": "ForgePlayer-update-check"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag") or "")
        name = str(data.get("name") or tag)
    except Exception:
        return UpdateCheckResult(ok=False)
    if not tag:
        return UpdateCheckResult(ok=False)
    latest = _parse_version(tag)
    current = _parse_version(current_version)
    is_newer = bool(latest is not None and current is not None and latest > current)
    return UpdateCheckResult(
        ok=True, latest_tag=tag, latest_name=name, is_newer=is_newer,
    )


class UpdateCheckSignals(QObject):
    done = Signal(object)  # UpdateCheckResult


class UpdateCheckJob(QRunnable):
    def __init__(self, current_version: str, signals: UpdateCheckSignals) -> None:
        super().__init__()
        self._current_version = current_version
        self._signals = signals

    def run(self) -> None:  # noqa: D401 — QRunnable entry point
        self._signals.done.emit(check_for_update(self._current_version))
