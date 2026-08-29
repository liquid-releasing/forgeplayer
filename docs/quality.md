# Why ForgePlayer looks great

ForgePlayer is built on [libmpv](https://mpv.io/) — the engine behind mpv — configured for image quality over speed. If you've been using a Windows Media Player wrapper or a basic VLC setup, the difference is immediate and visible.

## The engine

libmpv is the reference media engine for modern desktop playback. It has a proper GPU color pipeline and handles HDR as a first-class citizen. ForgePlayer runs one independent libmpv instance per output (primary + up to two mirrors), all driven from the same `SyncEngine` — play/pause/seek commands are issued to every active instance together, and each one decodes and renders its own copy against the same media clock. That's what keeps seeks in sub-frame sync across monitors; it's coordinated playback across N decoders, not a single shared decoder feeding multiple screens.

Out of the box, ForgePlayer configures libmpv directly in code
(`app/sync_engine.py`) rather than through a separate config file —
every player instance gets the same settings with no setup step:

```ini
hr_seek=yes
hwdec=auto-safe
demuxer_max_bytes=256MiB
demuxer_max_back_bytes=64MiB
vo=gpu
tone_mapping=bt.2390
hdr_compute_peak=yes
target-colorspace-hint=yes
```

- **`hr_seek=yes`** — frame-accurate seeking. mpv's default lands on
  the nearest prior keyframe (often several seconds short on typical
  encodes); this decodes forward from the keyframe to land exactly on
  the target, which the seek bar and chapter-nav both depend on.
- **`hwdec=auto-safe`** — GPU-decodes the video whenever a known-good
  hardware decoder is available (NVDEC, D3D11VA, …), falling back to
  software decode automatically for anything it can't offload. This
  is what keeps a high-bitrate 4K source from pegging the CPU and
  stalling haptic sync.
- **`demuxer_max_bytes` / `demuxer_max_back_bytes`** — a roomier
  read-ahead buffer so a big 4K file streams off disk without
  stalling the decode thread.
- **`vo=gpu`** — mpv's standard GPU video output. ForgePlayer
  previously used `gpu-next` (libplacebo) for its HDR compositing,
  but reverted after its Windows teardown reliably crashed the
  process when a player closed; see [HDR](#hdr) below.
- **`tone_mapping=bt.2390` / `hdr_compute_peak=yes`** — perceptual
  HDR→SDR tone-mapping so HDR content still looks reasonable while
  passthrough is disabled.
- **`target-colorspace-hint=yes`** — tells Windows to composite the
  mpv surface in the right colorspace when the desktop itself is in
  HDR mode (best-effort — skipped silently on older libmpv builds
  that don't support the option).

On machines with more than one GPU, ForgePlayer also pins mpv to the
NVIDIA adapter (`gpu_context=d3d11`, `d3d11_adapter=NVIDIA`) when one
is present — a confirmed AMD D3D11 driver bug otherwise let mpv land
on the wrong adapter on some hybrid-GPU laptops.

There's no separate "quality profile" to turn on, and no
`scale=`/`cscale=`/`deband=`/`interpolation=` tuning beyond mpv's own
built-in defaults — the list above is the complete, current set of
overrides. You don't need to configure anything to get this baseline.

## GPU support

ForgePlayer uses whatever hardware decoder and renderer your system provides. The `hwdec=auto-safe` setting picks the right backend for each platform:

| GPU family | Hardware decode | HDR pass-through |
|---|---|---|
| **NVIDIA** (GTX 10-series+, all RTX) | NVDEC, every modern codec (H.264, HEVC, AV1, VP9) | HDR10, HDR10+, Dolby Vision (HEVC Profile 5/8) |
| **AMD** (RX 400+, Radeon 5000+) | AMF / VA-API | HDR10 |
| **Intel** (8th-gen iGPU+, all Arc) | QSV / D3D11VA | HDR10 on Arc + 11th-gen iGPU+ |
| **Apple Silicon** (M1+, A18 Pro) | VideoToolbox | HDR10, Dolby Vision |

If your GPU doesn't support hardware decode for a specific codec, mpv falls back to CPU decode transparently. Playback continues; the only cost is CPU usage.

## Making 1080p look great on 4K monitors

Most community content is 1080p. Most good monitors are 4K. ForgePlayer doesn't configure a dedicated high-quality upscaler (`ewa_lanczossharp` and friends) today — scaling on a 4K wall uses mpv's own built-in default, the same one you'd get from a stock libmpv build. It still looks better than a lot of Windows Media Foundation-based players thanks to the GPU decode/render pipeline above, but it isn't the videophile-grade `ewa_lanczossharp` treatment some players advertise.

If you want that sharper upscaling, mpv supports it natively (`scale=ewa_lanczossharp`) — see [Overriding defaults](#overriding-defaults) below for how (and how not) to apply it today.

## HDR

!!! warning "HDR passthrough is disabled in v0.0.16"
    The HDR-on-Windows renderer (`gpu-next` / libplacebo) crashed on teardown,
    so v0.0.16 reverts to mpv's stable `gpu` renderer and **does not pass HDR
    through to the display**. HDR10 content plays tone-mapped to SDR; on an
    **HDR-ON** display it can look over-bright — turn Windows HDR **off** while
    testing. Passthrough returns once libplacebo's Windows teardown is fixed
    upstream. The rest of this section describes the intended (future) behavior.

ForgePlayer hands HDR content to your display correctly when:

1. The source is HDR-tagged (HDR10, HDR10+, Dolby Vision Profile 5/8)
2. Your GPU supports HDR output (see table above)
3. Your OS has HDR enabled for that monitor (Windows: Display Settings → HDR; macOS: System Settings → Displays → HDR)
4. Your monitor is HDR-capable (most modern Samsung Odyssey, LG C-series, etc.)

With those four in place, HDR content plays with full dynamic range and correct color primaries. The `target-colorspace-hint=yes` default tells mpv to pass HDR metadata through to the display driver.

If you're playing HDR content on an SDR display, mpv tone-maps it cleanly — darker shadows and brighter highlights than a naive clip, without the washed-out look of a bad SDR conversion.

For guidance on **producing** HDR content that plays well in ForgePlayer (Topaz Video AI workflow, model choices, verification), see [HDR content production](hdr-content.md).

## Overriding defaults

!!! note "No user config file today"
    There's currently no `~/.forgeplayer/mpv-user.conf` or equivalent —
    ForgePlayer doesn't load an external mpv config, and there's no CLI
    flag for passing extra mpv options either. The settings listed
    under [The engine](#the-engine) above are the whole story; there's
    nothing to override them with yet.

If you want different mpv behavior (a sharper upscaler, disabling
hardware decode to diagnose an `hwdec` problem, a different HDR target
peak, …), the only way today is to run ForgePlayer from source and
edit the `mpv.MPV(**kwargs)` call in `app/sync_engine.py` directly. A
user-facing override file is a reasonable future addition — see
[mpv's video documentation](https://mpv.io/manual/stable/#video) for
what's available to add.

## A note on why this matters

Several video + haptic players have shipped over the years wrapping Windows Media Foundation or a similarly conservative engine. They work, but they don't look great — and on flagship hardware (4K monitors, modern GPUs, HDR pipelines) that gap between "works" and "looks great" becomes glaring.

ForgePlayer is built explicitly to close that gap. mpv has been the preferred engine in the videophile and cinema communities for over a decade. Configured properly, it's indistinguishable from a purpose-built media engine costing orders of magnitude more. That's what's under the hood here, tuned for your monitor and your content.
