# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Single source of truth for the app version.

Shown in the session bar (so a dogfooder always knows which build they're
running — the #1 source of "did my fix land?" confusion) and used by the
window title. The release workflow can stamp this at build time; the literal
here is the dev/working value.
"""

from __future__ import annotations

__version__ = "0.0.8"
