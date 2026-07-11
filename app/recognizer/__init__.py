# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Media recognizer — turn a folder of files into distinct playable TITLES.

Built inside forgeplayer first (build-then-extract). The package is kept
extraction-clean: its only cross-package dependency is the funscript channel
taxonomy (``app.library.channels``), which is itself domain vocabulary that
travels WITH the recognizer when it becomes a shared package consumed by
forgeplayer, forgeassembler, and (ported) forgemoment.

Stages:
  canonicalize  — filename → title identity (name + ordinal, quality stripped)
  cluster       — group files into distinct titles (name proposes)
  match         — attach funscripts / bundles / audio to each title
  probe         — duration + funscript-span (content adjudicates ties) [later]
"""

from app.recognizer.canonicalize import (
    Ordinal,
    RecognizedFile,
    Role,
    canonicalize,
    resolution_rank,
)
from app.recognizer.cluster import TitleCluster, cluster_files
from app.recognizer.match import reconcile
from app.recognizer.probe import (
    funscript_span_ms,
    mpv_duration_ms,
    probe_resolve,
)

__all__ = [
    "Ordinal",
    "RecognizedFile",
    "Role",
    "TitleCluster",
    "canonicalize",
    "cluster_files",
    "funscript_span_ms",
    "mpv_duration_ms",
    "probe_resolve",
    "reconcile",
    "resolution_rank",
]


def recognize_titles(files, *, fuzzy_threshold: float = 0.6):
    """Convenience: canonicalize → cluster → reconcile a list of paths/files.

    Accepts paths (str/Path) or pre-canonicalized RecognizedFile objects and
    returns the reconciled list of TitleClusters. The pure NAME pipeline — the
    duration probe (probe.py) layers on top only when confidence is low.
    """
    recs = [f if isinstance(f, RecognizedFile) else canonicalize(f) for f in files]
    return reconcile(cluster_files(recs), fuzzy_threshold=fuzzy_threshold)
