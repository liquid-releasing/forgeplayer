# ForgePlayer — Getting Started demo (demofoundry test fixture)

A self-contained **test app + tour spec** for the [demofoundry] pipeline. It
reproduces ForgePlayer's get-started flow as clickable HTML so a browser
automation runner (Playwright) can drive it and demofoundry can lay TTS
narration + multi-language SRT over the recording.

**Source clip:** Big Buck Bunny (royalty-free, safe to publish).

## Why a mock instead of the real app

The real ForgePlayer is a native PySide6/Qt + libmpv desktop app — no DOM, so
Playwright can't drive it (see `../docs/demo-walkthrough.md`). This fixture is
the web-drivable stand-in. It **shows and animates** the UI; it does **not**
play real video, render a stim carrier, or touch a device. It's honest demo
scaffolding, not a web port of the player.

It's also a *better* demofoundry test fixture than the FunscriptForge BBB tour:
that one needs the whole vite app running at `:1430`; this is one static file.

## Files

| File | What it is |
|---|---|
| `getting-started.html` | The test app — real clickable tabs (Library → Setup → Preferences → Live → Play). Every element the tour targets carries a `data-tour` attribute. Tab clicks switch screens; Test/Calibrate pulse; Launch reveals the player wall; Play animates the transport. |
| `forgeplayer_tour.json` | The tour spec in demofoundry schema (mirrors `funscriptforge/internal/marketing/bbb_tour.json`): 8 scenes, `narrationSec` authoritative, `data-tour` action targets. ~356 s. |

## Run it

```sh
# serve the folder (the tour's baseUrl is http://localhost:5050/getting-started.html)
cd forgeplayer/demo
python -m http.server 5050
# then point demofoundry's runner at forgeplayer_tour.json
```

The page exposes `window.__forgeHighlight(dataTourName, true|false)` so the
runner can ring a target without relying on CSS hover.

## Scene order

Library (add a folder) → Setup (screens + crop) → Setup (audio roles) →
Preferences (synthesis algorithm) → Live (calibrate → launch) → Play → Close.

Narration source: adapted from `../docs/demo-walkthrough.md` (the SAY column),
retimed to `voiceWpm: 150`.

[demofoundry]: see memory `project_demofoundry` — tour-spec JSON + narration →
TTS narrator + multi-language SRT → localized demo video.
