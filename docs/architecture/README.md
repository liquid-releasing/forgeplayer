# Architecture & Design (internal)

These are **dev-facing** docs — design decisions, integration boundaries
with upstream projects, debugging history. Not the user manual.

When ForgePlayer publishes user docs via mkdocs, **exclude this folder**
in `mkdocs.yml` (or move to `docs/internal/architecture/` and exclude
`docs/internal/`). User-facing pages live at the `docs/` root level
(`hdr-content.md`, `quality.md`, etc.).

## What's here

| File | Audience | Purpose |
| --- | --- | --- |
| [restim-channels.md](restim-channels.md) | Devs + scripters | Canonical list of restim-recognized funscript filenames; what's restim's vs ours. |
| [stim-synthesis.md](stim-synthesis.md) | Devs | Phase tracking + device support matrix + channel consumption table for the v0.0.2 native funscript playback path. |
| [funscript-implementation.md](funscript-implementation.md) | Upstream maintainers (Edger, diglet48) + devs | Read-along companion to `funscript-tools/FUNDAMENTAL_OPERATIONS.md` and restim source — describes how ForgePlayer consumes each channel + operation. Includes "open questions for upstream" section. |
| [audio-routing.md](audio-routing.md) | Devs | The control panel's source→destination model: audio-source protocol (`sample_rate` + `generate_block_with_clocks`), aux streams, source-detection cascade, threading. Read this before adding a new source class or destination role. |

## What this folder is NOT

- **Not user docs.** Use `docs/` root files for that. Architecture docs
  reference upstream-project internals (line numbers, vendor commits,
  GC pressure, etc.) that confuse the average user.
- **Not API reference.** Generated reference goes elsewhere when we
  build it.
- **Not changelogs.** Per-release notes belong in `CHANGELOG.md` or
  GitHub releases.

## Updating

Add a row to the table above when you add a doc. Keep file count low —
prefer extending existing docs over fragmenting.
