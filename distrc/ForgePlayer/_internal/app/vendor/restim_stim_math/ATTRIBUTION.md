# Attribution

The code in this directory is vendored from **restim** by diglet48 — the
canonical funscript-to-e-stim-audio math engine.

- **Original repository**: https://github.com/diglet48/restim
- **License**: MIT (see `LICENSE` in this directory)
- **Pinned commit**: see `VERSION`
- **Extracted subtree**: `stim_math/` (excluding `sensors/`)

## Why vendor instead of depend

restim is a Qt desktop application. It is not published as a library (no
`pyproject.toml` / `setup.py` / PyPI entry) and does not expose a CLI or
service mode. We therefore vendor only the pure-math layer we need and
respect the maintainer's design by not forking or reshaping the upstream
project.

The math we rely on — 3-phase waveform synthesis, coordinate transforms,
pulse envelope shaping, safety limits — is carefully-tuned domain work.
We do not attempt to reimplement it; we credit the original work and
track upstream via explicit sync.

## What is vendored

| File / subtree                      | Origin                                | Purpose                                           |
|-------------------------------------|---------------------------------------|---------------------------------------------------|
| `audio_gen/`                        | `stim_math/audio_gen/`                | Real-time audio synthesis (continuous + pulse)    |
| `amplitude_modulation.py`           | `stim_math/amplitude_modulation.py`   | Envelope modulation primitives                    |
| `axis.py`                           | `stim_math/axis.py`                   | `AbstractAxis`, `AbstractMediaSync` base classes  |
| `limits.py`                         | `stim_math/limits.py`                 | Safety / parameter limit constants                |
| `pulse.py`                          | `stim_math/pulse.py`                  | Pulse envelope shaping (for pulse-based devices)  |
| `sine_generator.py`                 | `stim_math/sine_generator.py`         | Carrier phase accumulator                         |
| `threephase.py`                     | `stim_math/threephase.py`             | 3-phase signal generator + calibration            |
| `threephase_coordinate_transform.py`| `stim_math/threephase_coordinate_transform.py` | 3-phase coordinate transforms            |
| `threephase_exponent.py`            | `stim_math/threephase_exponent.py`    | Exponent-based 3-phase shaping                    |
| `transforms.py`                     | `stim_math/transforms.py`             | Clarke transform matrices                         |
| `transforms_4.py`                   | `stim_math/transforms_4.py`           | 4-phase coordinate transforms                     |
| `trig.py`                           | `stim_math/trig.py`                   | Trig utilities used by waveform synthesis         |

## What is NOT vendored

- `stim_math/sensors/` — IMU / pressure / AS5311 position sensor glue
  (ForgePlayer does not consume motion-sensor streams).
- `device/` — hardware protocol drivers (FOC-Stim protobuf, NeoStim serial).
  ForgePlayer v0.0.2 ships commercial audio-device support only; future
  FOC-Stim integration will decide between vendoring this subtree or
  using restim's REST API.
- `qt_ui/`, `net/`, `designer/` — Qt GUI, network servers, UI designer
  files. Not applicable to a library consumer.
- `.github/`, `build instructions.txt`, platform build scripts — upstream
  release tooling.

## Modifications we apply on sync

One mechanical rewrite: internal imports are converted from the upstream
absolute form (`from stim_math.X import Y`) to package-relative form
(`from .X import Y` at top level, `from ..X import Y` from sub-packages).
This lets us drop the tree into `app/vendor/restim_stim_math/` without
requiring `sys.path` mutation or a PyInstaller hidden-imports hack.

The rewrite is deterministic and is re-applied automatically by
`scripts/sync_restim_stim_math.py update`. No human merge work per sync.

## Updating

```
python scripts/sync_restim_stim_math.py --check        # show diff vs upstream
python scripts/sync_restim_stim_math.py update --commit <sha>   # adopt
python -m pytest tests/                                # validate
```

Commit the result as `chore(vendor): bump restim to <sha>`.

## Credit

diglet48's restim represents years of domain expertise in electrical
stimulation signal processing. The 3-phase math, coordinate transforms,
and safety framing embedded in this subtree are authored by them and
their contributors. We are consumers, not authors.
