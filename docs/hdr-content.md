# Producing HDR content for ForgePlayer

ForgePlayer plays HDR content with full dynamic range and correct metadata (see [Quality](quality.md)). But it can only play what you produce. This page covers how to generate HDR10 content — especially via Topaz Video AI — that ForgePlayer will handle correctly.

## The short version

To produce HDR content that plays well in ForgePlayer:

1. Use an **HDR-capable enhancement model** (not every Topaz model preserves HDR)
2. Output as **10-bit HEVC** (or better — ProRes 4444 XQ for mastering)
3. Preserve **BT.2020 color primaries** and **SMPTE 2084 (PQ)** transfer function
4. Verify with `ffprobe` that HDR metadata survived the encode

If any step fails, the output will silently fall back to SDR and look worse than the source.

## Topaz Video AI — model selection

Not all Topaz models preserve HDR. Some models convert to BT.709 (SDR) internally, so even if your source is HDR10, the output is SDR. Model HDR support changes between Topaz versions — always confirm in the current Topaz documentation.

### General guide (2026-vintage Topaz Video AI)

| Model | HDR support | Speed on RTX 4070 | Best for |
|---|---|---|---|
| **Iris MQ** | ✅ HDR-capable | Slow — heavy model | Medium-quality restoration with HDR preservation |
| **Proteus Fine Tune** | ✅ HDR-capable | Moderate | Parametric control + HDR preservation |
| **NYX-3 / NYX Sharp** | ✅ HDR-capable (verify per-version) | Fast | Denoise + mild sharpening, HDR sources |
| **RHEA** | ✅ HDR-capable | Slow on 4K→8K workflows | High-end upscaling, newest flagship model |
| **Artemis / Gaia / Theia** | ❌ SDR-trained | Fast | SDR content only — will strip HDR |

### RHEA + NYX machine requirements

- **GPU:** NVIDIA RTX 20-series or newer strongly recommended (Tensor cores are how Topaz gets its speed). Intel Arc A700+ and AMD RX 6000+ also supported.
- **VRAM:** 8 GB minimum for 1080p workflows, **12 GB recommended for 4K**, 16+ GB for 8K. An RTX 4070 (12 GB) handles RHEA at 4K input but will be slow on 4K→8K upscales.
- **System RAM:** 32 GB recommended for 4K HDR workflows.

Your machine supports these models if Topaz's **Processing** panel shows non-zero FPS estimates when you select the model and add an HDR source. If it shows "GPU not supported" or falls back to CPU, the hardware isn't eligible for that model.

### If "Iris MQ comes to its knees"

Iris MQ is the heaviest restoration-class model Topaz ships. "Comes to its knees" typically means:

- **4K input with Iris MQ → likely 1-3 FPS on RTX 4070.** Normal.
- Solutions:
  1. Downscale source to 1440p before Iris MQ, then upscale to 4K with a lighter model like Proteus or RHEA
  2. Use Proteus Fine Tune instead — nearly-as-good restoration at 5-10× the speed, HDR-capable
  3. Process overnight. Topaz batch-processes happily; start the render before bed

## Export settings

Topaz's default export settings often downgrade HDR. Explicit settings to use:

| Setting | Value | Why |
|---|---|---|
| **Container** | MP4 or MKV | Both carry HDR10 metadata; MKV is more forgiving |
| **Codec** | HEVC (H.265) Main10 profile | H.264 cannot carry HDR10 reliably |
| **Encoder** | NVIDIA NVENC (fast) or CPU x265 (best quality) | NVENC on RTX 4070 = real-time or faster; x265 slow but visually cleanest |
| **Pixel format** | 10-bit YUV 4:2:0 (yuv420p10le) | 8-bit silently downgrades to SDR |
| **Color primaries** | BT.2020 | HDR10 standard; Topaz's "Preserve source HDR" should set this |
| **Transfer function** | PQ (SMPTE 2084) | HDR10 standard |
| **Max CLL / Max FALL** | "Preserve from source" or explicit values | Peak brightness metadata |
| **Bitrate** | 50+ Mbps for 4K HDR, 25+ Mbps for 1080p HDR | Lower bitrates cause banding that HDR emphasizes |

The **"Preserve source HDR"** or **"Pass through HDR metadata"** checkbox (varies by Topaz version, usually in Output / Encoder settings) is the master switch. If it's off, HDR metadata won't survive even with correct codec settings.

## Verification

After export, run `ffprobe` to confirm HDR survived:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=pix_fmt,color_space,color_transfer,color_primaries \
  output.mp4
```

**Expected output for valid HDR10:**

```
pix_fmt=yuv420p10le
color_space=bt2020nc
color_transfer=smpte2084
color_primaries=bt2020
```

Any of these failure modes means HDR was stripped:

| ffprobe output | Problem |
|---|---|
| `pix_fmt=yuv420p` (no `10le`) | Output is 8-bit → SDR |
| `color_transfer=bt709` | Transfer function is SDR gamma |
| `color_space=bt709` | Color space is SDR |
| `color_primaries=bt709` | Primaries are SDR (Rec. 709) |

If any of these are wrong, re-export with corrected settings or try a different Topaz model.

For Dolby Vision verification (if producing DV content), use `mediainfo` — it parses DV metadata that ffprobe doesn't fully expose.

## Alternatives to Topaz

| Tool | HDR preservation | Use case |
|---|---|---|
| **DaVinci Resolve (free or Studio)** | ✅ First-class HDR support | Color grading, final mastering, finer control than Topaz |
| **FFmpeg (manual)** | ✅ If you know what you're doing | Scripted pipelines, batch processing |
| **HandBrake** | ⚠ Partial — strips some metadata | Avoid for HDR work |
| **Shutter Encoder** | ✅ | Free GUI wrapper around FFmpeg with correct HDR presets |

For a reference FFmpeg command that re-encodes HDR10 preserving all metadata:

```bash
ffmpeg -i input.mp4 \
  -c:v libx265 -preset slow -crf 18 \
  -pix_fmt yuv420p10le \
  -x265-params "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:hdr-opt=1:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1):max-cll=1000,400" \
  -c:a copy \
  output.mp4
```

The `master-display` and `max-cll` values come from your source file's metadata — read them with `mediainfo input.mp4`.

## Summary workflow

1. **Source:** Verify HDR with `ffprobe` (should show BT.2020 + SMPTE 2084)
2. **Topaz model:** Pick an HDR-capable one (Iris MQ, Proteus Fine Tune, NYX, RHEA)
3. **Topaz export:** HEVC Main10, 10-bit, NVENC fast or CPU slow, "Preserve HDR" on
4. **Verify output:** `ffprobe` shows `yuv420p10le`, `bt2020nc`, `smpte2084`
5. **Play in ForgePlayer** with Windows/macOS HDR enabled for the target monitor

When all five steps check out, you get the full HDR pipeline end-to-end.
