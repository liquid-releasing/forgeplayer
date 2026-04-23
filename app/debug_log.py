# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Debug event log — lightweight instrumentation for dogfood sessions.

Mirrors the pattern from FunscriptForge's alpha-2 debug mode: a toggle in
the main UI flips `DebugLog.enabled`, button clicks and lifecycle events
call `DebugLog.record(...)`, and an Export button writes the captured
list to a timestamped JSON file the user can share in a bug report.

Usage:
    from app.debug_log import DebugLog
    DebugLog.record("click.play", slot=1)
    DebugLog.mark("reproduced freeze here")
    DebugLog.export()

No-op when disabled — every call through `record()` returns immediately
if `enabled` is False, so production/default paths pay almost nothing.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class DebugLog:
    """Process-wide singleton event recorder. Cheap when disabled.

    When enabled, events are also streamed to a JSONL file on disk (one JSON
    object per line) so a hard freeze / crash / task-kill still leaves a
    recoverable log at `~/.forgeplayer/debug-stream-<start-time>.jsonl`.
    """

    enabled: bool = False
    _events: list[dict[str, Any]] = []
    _started_at: float = time.time()
    _stream_path: Path | None = None

    @classmethod
    def _stream_append(cls, event: dict) -> None:
        """Best-effort disk write. Never raises — debug instrumentation must
        not affect production paths."""
        if cls._stream_path is None:
            return
        try:
            with open(cls._stream_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")
                fh.flush()
        except Exception:
            pass

    @classmethod
    def _open_stream(cls) -> None:
        target = Path.home() / ".forgeplayer"
        try:
            target.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            cls._stream_path = target / f"debug-stream-{stamp}.jsonl"
            cls._stream_append({
                "t": 0.0,
                "wall": datetime.now().isoformat(timespec="milliseconds"),
                "kind": "stream.opened",
                "path": str(cls._stream_path),
            })
        except Exception:
            cls._stream_path = None

    @classmethod
    def _close_stream(cls) -> None:
        if cls._stream_path is not None:
            cls._stream_append({
                "t": round(time.time() - cls._started_at, 3),
                "wall": datetime.now().isoformat(timespec="milliseconds"),
                "kind": "stream.closed",
            })
        cls._stream_path = None

    @classmethod
    def set_enabled(cls, on: bool) -> None:
        """Toggle debug capture. Opens/closes the on-disk stream."""
        if on and not cls.enabled:
            cls._open_stream()
        elif cls.enabled and not on:
            cls._close_stream()
        cls.enabled = on

    @classmethod
    def record(cls, kind: str, **fields: Any) -> None:
        if not cls.enabled:
            return
        event = {
            "t": round(time.time() - cls._started_at, 3),
            "wall": datetime.now().isoformat(timespec="milliseconds"),
            "kind": kind,
            **fields,
        }
        cls._events.append(event)
        cls._stream_append(event)

    @classmethod
    def mark(cls, note: str = "") -> None:
        """User-inserted marker. Captured even when not yet enabled so the
        user can flag a moment and then go back and turn on debug."""
        event = {
            "t": round(time.time() - cls._started_at, 3),
            "wall": datetime.now().isoformat(timespec="milliseconds"),
            "kind": "mark",
            "note": note,
        }
        cls._events.append(event)
        cls._stream_append(event)

    @classmethod
    def reset(cls) -> None:
        cls._events.clear()
        cls._started_at = time.time()

    @classmethod
    def event_count(cls) -> int:
        return len(cls._events)

    @classmethod
    def stream_path(cls) -> Path | None:
        return cls._stream_path

    @classmethod
    def export(cls, target_dir: Path | None = None) -> Path:
        """Write captured events as JSON to `~/.forgeplayer/debug-<ts>.json`
        (or *target_dir* if given). Returns the written path."""
        if target_dir is None:
            target_dir = Path.home() / ".forgeplayer"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = target_dir / f"debug-{stamp}.json"
        payload = {
            "started_at": datetime.fromtimestamp(cls._started_at).isoformat(),
            "event_count": len(cls._events),
            "env": {
                "cwd": os.getcwd(),
            },
            "events": list(cls._events),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
