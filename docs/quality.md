# Why ForgePlayer looks great

ForgePlayer is built on [libmpv](https://mpv.io/) — the engine behind mpv — configured for image quality over speed. If you've been using a Windows Media Player wrapper or a basic VLC setup, the difference is immediate and visible.

## The engine

libmpv is the reference media engine for modern desktop playback. It consistently outperforms VLC on scaling (EWA Lanczos family upscalers), has a proper GPU color pipeline, and handles HDR as a first-class citizen. ForgePlayer exposes it through a single-decoder architecture: one libmpv instance drives every output, so seeks are frame-perfect by construction and the CPU/GPU only does the expensive work (decode, upscale, tone-map) once.

Out of the box, ForgePlayer ships with a baked-in `mpv-defaults.conf` tuned for flagship image quality:

```ini
vo=gpu-next
hwdec=auto-safe
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=mitchell
video-sync=display-resample
interpolation=yes
deband=yes
dither-depth=auto
target-colorspace-hint=yes
```

You don't need to configure anything. It Just Works.

## GPU support

ForgePlayer uses whatever hardware decoder and renderer your system provides. The `hwdec=auto-safe` setting picks the right backend for each platform:

| GPU family | Hardware decode | HDR pass-through | Upscaling quality |
|---|---|---|---|
| **NVIDIA** (GTX 10-series+, all RTX) | NVDEC, every modern codec (H.264, HEVC, AV1, VP9) | HDR10, HDR10+, Dolby Vision (HEVC Profile 5/8) | Excellent — ewa_lanczossharp runs fast on CUDA |
| **AMD** (RX 400+, Radeon 5000+) | AMF / VA-API | HDR10 | Excellent |
| **Intel** (8th-gen iGPU+, all Arc) | QSV / D3D11VA | HDR10 on Arc + 11th-gen iGPU+ | Excellent |
| **Apple Silicon** (M1+, A18 Pro) | VideoToolbox | HDR10, Dolby Vision | Excellent |

If your GPU doesn't support hardware decode for a specific codec, mpv falls back to CPU decode transparently. Playback continues; the only cost is CPU usage.

## Making 1080p look great on 4K monitors

Most community content is 1080p. Most good monitors are 4K. ForgePlayer fills the gap with `ewa_lanczossharp`, the canonical high-quality spatial upscaler in the mpv ecosystem.

Technically, it's Elliptical Weighted Averaging Lanczos with a sharpening variant — edge-preserving, ring-free, and regarded in the videophile community as the best real-time spatial upscaler not requiring a neural network. Visually: 1080p content on your 4K monitor looks noticeably sharper than VLC's default, without the crispy over-sharpened look some TVs produce.

You don't have to do anything to get this. Load a 1080p pack onto a 4K wall, and upscaling happens automatically.

## HDR

ForgePlayer hands HDR content to your display correctly when:

1. The source is HDR-tagged (HDR10, HDR10+, Dolby Vision Profile 5/8)
2. Your GPU supports HDR output (see table above)
3. Your OS has HDR enabled for that monitor (Windows: Display Settings → HDR; macOS: System Settings → Displays → HDR)
4. Your monitor is HDR-capable (most modern Samsung Odyssey, LG C-series, etc.)

With those four in place, HDR content plays with full dynamic range and correct color primaries. The `target-colorspace-hint=yes` default tells mpv to pass HDR metadata through to the display driver.

If you're playing HDR content on an SDR display, mpv tone-maps it cleanly — darker shadows and brighter highlights than a naive clip, without the washed-out look of a bad SDR conversion.

For guidance on **producing** HDR content that plays well in ForgePlayer (Topaz Video AI workflow, model choices, verification), see [HDR content production](hdr-content.md).

## Overriding defaults

If you want to experiment or match a specific workflow, ForgePlayer loads a second config file after the bundled defaults:

```
~/.forgeplayer/mpv-user.conf
```

Anything you put here overrides the baseline. Common overrides:

```ini
# Use the legacy gpu backend if gpu-next has issues on your system
vo=gpu

# Switch to a different upscaler (faster, slightly less sharp)
scale=spline36

# Disable hardware decode (diagnosing hwdec problems)
hwdec=no

# Force a specific target peak brightness for HDR tone-mapping
target-peak=400
```

Full reference: [mpv's video documentation](https://mpv.io/manual/stable/#video).

## A note on why this matters

Several video + haptic players have shipped over the years wrapping Windows Media Foundation or a similarly conservative engine. They work, but they don't look great — and on flagship hardware (4K monitors, modern GPUs, HDR pipelines) that gap between "works" and "looks great" becomes glaring.

ForgePlayer is built explicitly to close that gap. mpv has been the preferred engine in the videophile and cinema communities for over a decade. Configured properly, it's indistinguishable from a purpose-built media engine costing orders of magnitude more. That's what's under the hood here, tuned for your monitor and your content.
