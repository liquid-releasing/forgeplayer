# Library

The Library is a **launcher for haptic scenes** — not a video catalog. Point
it at a media folder (**📁 Root…**) and it lists one tile per *work* that has
something to play on your device.

## What becomes a tile

A tile is a **haptic asset paired with its video**: a funscript (or set of
funscripts), a `.forge` / `.output` bundle, or a pre-rendered e-stim sound —
plus the video it matches by name. A video with **no** funscript / bundle /
stim sound isn't a haptic scene, so it doesn't get a tile in the default view
(you can still show plain videos — see **Filters** below).

!!! note "ForgePlayer plays finished output, not FunscriptForge work files"
    ForgePlayer plays **loose funscripts**, `.output/` device folders, and
    `.forge` / `.forgeplay` **bundles** — the finished, shareable output of
    FunscriptForge. It deliberately **ignores FunscriptForge's working files
    and sidecars**: hidden `.<stem>.forge/` working directories and the
    intermediate `.chapters.json`, `.phrases.json`, `.peaks.json`, etc. sidecars
    an FSF project leaves next to your media. Those are editor state, not
    playable haptics, so they never create tiles or get played here. Finish your
    project in FunscriptForge (export a `.forge` bundle or an `.output/` folder)
    and *that* is what ForgePlayer picks up.

## How the Library matches files to a video

The **haptic asset leads**: the scanner finds the funscripts / bundles / stim
sounds in a folder, and each one finds *its* video by name. Matching is on a
**work key** — the filename reduced to the underlying work by stripping the
noise:

- codec / resolution / upscaler / quality tags (`x265`, `1080p`, `2160p`,
  `Iris3`, `Chf3`, `Hq`, `hb`, `5120x1440`, …)
- bracket / paren annotations (`[Supermassive 2022]`, `[E-Stim & Popper Edit]`)
- pipeline render *pass-numbers* — **but real ordinals are kept** (`Part 1`,
  `Vol 2`, so Part 1 and Part 2 stay separate works).

So `Klinik Industries Vi22 Hq Chf3 Iris3 5120x1440.mkv` and
`Klinik Industries Vi22 - Triphase.mp3` both reduce to `klinik industries
vi22` and pair into one tile. Matching runs strictest-first — exact key, then
"the video's name plus a descriptive tail" (`5sod_high - emily edit`), then
word-overlap for re-ordered names, then a within-folder fallback for a sound
whose video kept a stray encoder tag — and it never crosses an ordinal
boundary (`Vol 1` ≠ `Vol 2`).

Consequences:

- All **renders of one work** (4K + 1080p + ultrawide + upscaled) collapse
  into **one tile**; the picker lets you choose which to play.
- Funscripts / sounds in a **subfolder** fold into the parent scene — even
  nested ones like `Extras/Estim files/…`.
- A subfolder named exactly `hb` (handbrake re-encodes) folds its videos in as
  extra renders; the same work sitting **loose at the root *and* in a
  subfolder** merges into one tile.
- A stim **sound that matches no video is dropped** (a stray beat track never
  becomes a tile).

## Scene tiles

Each tile shows a thumbnail, the work name, running time, and content pills
(**VIDEO / AUDIO / FUNSCRIPT / FORGE**). Two corner controls:

- **↗ (top-right)** — open the scene's file location in Explorer, handy for
  checking what got grouped.
- **📌** — appears once you've saved picks for the scene; **click it to
  re-pick**. Clicking anywhere else on the tile just plays your saved pick.
- **"pick"** — shown when a scene has choices to make and you haven't picked
  yet.

Thumbnails are real frames pulled from the scene's video, generated **lazily**
(only for tiles you scroll past) and cached to `~/.forgeplayer/thumb_cache/`,
so the grid stays responsive on a large library and frames are instant next
visit. They prefer a standard-aspect render (an ultrawide frame makes a poor
letterboxed thumbnail) and skip near-black leader frames.

## Filters

Buttons under the root bar switch what's shown, each with a live count:

- **Videos with Funscripts** *(default)* — the curated haptic scenes.
- **Videos** — standalone videos with no haptics (source pieces, unscripted
  clips) that the player can still just play.
- **All** — both.

## Activating a scene

**Single-click** a tile to activate. If the scene has multiple variants
(more than one funscript set, or alternate video edits), a **picker
dialog** opens:

- **Funscript set** — for scenes with multiple authoring versions
  (e.g. "Magik Number 3 Pt 1 (6 channels)" vs "Magik Number 3 Pt 1
  (10 channels, prostate)"). Pick the one you want playing.
- **Video variant** — original vs upscaled vs ultrawide-crop, etc.
- **Stim audio** — the pre-rendered `.mp3` files in the folder that
  drive the stim port when content preference is "sound".
- **Subtitles** — None / language picks.

Defaults are sensible: highest-numbered set, original video, first
matched stim audio, no subtitle. Click **OK**.

Your picks are saved as a `<scene>.forgeplayer.json` pin in the scene
folder. Next time you single-click the tile, ForgePlayer skips the picker
and re-uses the pinned choices.

## Re-opening the picker

Click the **📌** button on a tile (or right-click → **Change picks…**, or
the title-bar button on the Live tab) to re-open the picker for the active
scene. New picks overwrite the pin.

## Refresh

If you add or remove files in a scene folder while ForgePlayer is
running, click **Refresh** to re-scan.

---

## Opening a `.forge` bundle

A `.forge` is a self-describing scene bundle exported from FunscriptForge —
the motion track, every device channel, the stim audio, events, and a
manifest, all in one file.

### Double-click to play

On Windows, the ForgePlayer **installer** registers the `.forge` file type,
so **double-clicking a `.forge` opens it straight in ForgePlayer and plays**
("Play in ForgePlayer"). Right-clicking offers "Edit in FunscriptForge" to
re-open it for editing. (The portable zip build doesn't register the type —
use the installer if you want the double-click association, or launch
ForgePlayer with the bundle path, e.g. `ForgePlayer.exe "Scene.forge"`.)

`.forge` bundles don't appear as Library tiles — they're single files you
open directly, not scanned scene folders.

### How it finds the video

A bundle is lean by default: it carries the funscripts, the channels, and
the stim audio, but **not** the (potentially multi-GB) source video. When
you open one, ForgePlayer relinks the video in this order:

1. **Inside the bundle** — if it was exported with **"include media"**, the
   video rides inside the `.forge` and plays directly. Fully self-contained;
   works on any machine, no external file needed.
2. **The original location** — the absolute path the video lived at when it
   was exported (recorded in the bundle's manifest). On the same machine,
   this resolves wherever the bundle itself happens to sit — the `.forge`
   does **not** have to be next to the video.
3. **Next to the bundle** — a video with the recorded filename sitting in
   the same folder as the `.forge` (or its parent). This is the case that
   needs adjacency: it's how a **shared** lean bundle finds its video on
   someone else's disk.

If none of those resolve, the scene **still opens and plays** — funscripts,
stim, everything — just with no picture, and ForgePlayer prompts you to
attach a video manually.

**Sharing tip:** for a bundle that "just plays" anywhere with zero setup,
export it with **include media** (option 1 — video inside). To share lean
bundles, keep the video file beside the `.forge` (option 3). For your own
machine, it finds the original wherever it is (option 2).
