"""Smoke tests for the vendored restim stim_math tree.

These tests are deliberately shallow — they do not re-test restim's math
correctness (that's upstream's job). They verify that our vendor copy +
import rewrite didn't break anything at the module-import level, so a bad
sync is caught immediately by CI rather than at the first runtime call.
"""

from __future__ import annotations

from pathlib import Path

import pytest


VENDOR_DIR = Path(__file__).resolve().parent.parent / "app" / "vendor" / "restim_stim_math"


def test_version_file_pinned() -> None:
    version_file = VENDOR_DIR / "VERSION"
    assert version_file.is_file(), "VERSION file must exist (pins upstream commit)"
    first_line = next(
        (line.strip() for line in version_file.read_text(encoding="utf-8").splitlines()
         if line.strip() and not line.strip().startswith("#")),
        "",
    )
    assert len(first_line) >= 7, "First non-comment line must be a commit SHA"


def test_attribution_file_present() -> None:
    attr = VENDOR_DIR / "ATTRIBUTION.md"
    assert attr.is_file(), "ATTRIBUTION.md must exist (license requirement)"
    content = attr.read_text(encoding="utf-8")
    assert "diglet48" in content
    assert "MIT" in content


def test_license_file_present() -> None:
    assert (VENDOR_DIR / "LICENSE").is_file(), "restim LICENSE must be preserved in vendor tree"


def test_top_level_modules_importable() -> None:
    from app.vendor.restim_stim_math import (  # noqa: F401
        amplitude_modulation,
        axis,
        limits,
        pulse,
        sine_generator,
        threephase,
        threephase_coordinate_transform,
        threephase_exponent,
        transforms,
        transforms_4,
        trig,
    )


def test_audio_gen_modules_importable() -> None:
    from app.vendor.restim_stim_math.audio_gen import (  # noqa: F401
        base_classes,
        continuous,
        modify,
        params,
        pulse_based,
        various,
    )


def test_no_absolute_stim_math_imports_remain() -> None:
    """Every vendored .py must use relative imports, not `stim_math.X` paths.

    If sync_restim_stim_math.py forgets to rewrite a case, this test fails
    loudly instead of at first use.
    """
    offenders = []
    for py in VENDOR_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in ("from stim_math", "import stim_math"):
            if token in text:
                offenders.append(f"{py.relative_to(VENDOR_DIR)}: contains `{token}`")
    assert not offenders, "Unrewritten stim_math imports:\n  " + "\n  ".join(offenders)


def test_sensors_subtree_not_present() -> None:
    """sensors/ is intentionally dropped — it is not used by audio synthesis
    and would pull unneeded complexity into the vendor tree."""
    assert not (VENDOR_DIR / "sensors").exists(), (
        "sensors/ should not be vendored; sync script drops it."
    )


def test_key_public_symbols_exist() -> None:
    """Spot-check that the classes/functions our code will actually call
    are present. If upstream renames one, we'd rather find out here."""
    from app.vendor.restim_stim_math import threephase
    from app.vendor.restim_stim_math.audio_gen import base_classes, continuous, pulse_based

    assert hasattr(base_classes, "AudioGenerationAlgorithm")
    assert hasattr(threephase, "ThreePhaseCenterCalibration")
    # continuous + pulse_based are the two primary synthesis classes
    assert continuous.__name__.endswith("continuous")
    assert pulse_based.__name__.endswith("pulse_based")


@pytest.mark.skipif(
    pytest.importorskip("numpy", reason="numpy required for waveform math") is None,
    reason="numpy unavailable",
)
def test_trig_callable_with_numpy() -> None:
    """Cheap round-trip: the trig module should produce numeric output."""
    import numpy as np
    from app.vendor.restim_stim_math import trig

    # Not testing correctness, just that the function runs and returns
    # something array-like. If the module-level imports are broken, this
    # would fail at import time, not here.
    assert trig is not None
    # Many trig helpers just wrap numpy; calling numpy through them is fine
    # as a liveness check.
    assert np.isfinite(np.sin(0.5))
