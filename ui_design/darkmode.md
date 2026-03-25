Bruce, here it is — the **full dark‑mode version of your entire UI**, rendered in a way that mirrors exactly how it will look in Figma.  
This is not a “dimmed neon” mode — this is a **true matte‑dark industrial mode**, optimized for clarity, low‑glare, and long‑session usability on your 12.3″ ultrawide panel.

I’ll give you:

- A **full‑panel mockup** of CONTROL VIEW (dark mode)  
- A **full‑panel mockup** of CONFIG VIEW (dark mode)  
- The **dark‑mode design tokens** (colors, strokes, shadows)  
- The **component differences** vs neon mode  
- The **theme‑switch behavior**  

Everything is structured so you can drop it straight into your Figma component library.

---

# 🌑 **DARK‑MODE CONTROL VIEW (Figma‑Ready Mockup)**  
### *1920×720 ultrawide — matte, low‑glow, industrial*

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [CONFIG]    [CONTROL]                                                         │
│──────────────────────────────────────────────────────────────────────────────│
│  SYNC   PLAY ALL   PAUSE ALL   STOP ALL   SETTINGS                            │
│  (all buttons: matte charcoal, subtle 1px border)                             │
├──────────────────────────────────────────────────────────────────────────────┤
│  MON 1 (4K)     MON 2 (4K)     MON 3 (QHD ULTRAWIDE)                          │
│  (selected monitor: soft gray highlight, no glow)                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌───────────────────────────────┐  ┌────────────────────────────────────────┐ │
│ │     VIDEO PREVIEW             │  │   TIMELINE (dark rail, white scrub)   │ │
│ │   [thumbnail placeholder]     │  │   markers: white ticks                 │ │
│ └───────────────────────────────┘  └────────────────────────────────────────┘ │
│                                                                              │
│ PLAYLIST                                                                     │
│  • Clip 01                                                                   │
│  • Clip 02                                                                   │
│  • Clip 03                                                                   │
│  • Clip 04                                                                   │
│  • Clip 05                                                                   │
└─────────────────────────────────────┴────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────────────┐
│ AUDIO ROUTING:   7.1 A   7.1 B   USB 1   USB 2   PC OUT                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### **Dark‑mode characteristics**
- No neon glows  
- Matte charcoal panels  
- Soft gray borders  
- White icons  
- High‑contrast timeline  
- Playlist items with subtle hover states  
- Buttons feel like **hardware**, not holograms  

---

# 🌑 **DARK‑MODE CONFIG VIEW (Figma‑Ready Mockup)**  
### *Video selection, audio routing, device mapping — all in matte dark*

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [CONFIG]    [CONTROL]                                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                               CONFIGURATION                                   │
├──────────────────────────────────────────────────────────────────────────────┤

VIDEO SOURCES
┌──────────────────────────────────────────────────────────────────────────────┐
│ MON 1 (4K)   [videoFile.mp4 ▼]   Browse   [Preview]                           │
│ MON 2 (4K)   [videoFile.mp4 ▼]   Browse   [Preview]                           │
│ MON 3 (QHD)  [videoFile.mp4 ▼]   Browse   [Preview]                           │
└──────────────────────────────────────────────────────────────────────────────┘

AUDIO SOURCES
┌──────────────────────────────────────────────────────────────────────────────┐
│ 7.1 A   [audioFile.wav ▼]   [Device: 7.1 A ▼]   Test                          │
│ 7.1 B   [audioFile.wav ▼]   [Device: 7.1 B ▼]   Test                          │
│ USB 1   [audioFile.wav ▼]   [Device: USB 1 ▼]   Test                          │
│ USB 2   [audioFile.wav ▼]   [Device: USB 2 ▼]   Test                          │
│ PC OUT  [audioFile.wav ▼]   [Device: PC OUT ▼]  Test                          │
└──────────────────────────────────────────────────────────────────────────────┘

ROUTING MATRIX
┌──────────────────────────────────────────────────────────────────────────────┐
│ Monitor     Video Source           Audio Output       Status                 │
│ Mon 1       clip01_4k.mp4          7.1 A              ✔                      │
│ Mon 2       clip01_4k_right.mp4    7.1 B              ✔                      │
│ Mon 3       clip01_ultra.mp4       USB 1              ✔                      │
└──────────────────────────────────────────────────────────────────────────────┘

SYNC ENGINE
┌──────────────────────────────────────────────────────────────────────────────┐
│ Master Clock: [Mon 1 ▼]                                                     │
│ Drift Correction: [AUTO ▼]                                                  │
│ Audio Offset:  [====|====] 0ms                                              │
│ Video Offset:  [====|====] 0ms                                              │
└──────────────────────────────────────────────────────────────────────────────┘

SAVE / LOAD
┌──────────────────────────────────────────────────────────────────────────────┐
│ Load Config   Save Config   New Config                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### **Dark‑mode characteristics**
- All icons switch to **white stroke**  
- All dropdowns use **charcoal panels**  
- Routing matrix uses **white/gray text**  
- Status icons:  
  - ✔ = white  
  - ⚠ = yellow (still visible in dark mode)  

---

# 🎨 **Dark‑Mode Design Tokens (Figma Styles)**

### **Colors**
| Token | Value | Usage |
|-------|--------|--------|
| `Surface` | `#0E0F11` | main background |
| `Panel` | `#15171A` | UI panels |
| `PanelBorder` | `#2A2C2F` | 1px borders |
| `TextPrimary` | `#FFFFFF` | main text |
| `TextSecondary` | `#A0A4A8` | labels |
| `IconPrimary` | `#FFFFFF` | all icons |
| `Accent` | `#4A8BFF` | subtle highlights |
| `Warning` | `#F8FF00` | routing issues |

### **Effects**
- No outer glows  
- Very subtle inner shadow: `rgba(0,0,0,0.4)`  
- Buttons: 1px border, no glow  

---

# 🧩 **Component Differences (Dark vs Neon)**

### **Buttons**
- Neon: glowing cyan/magenta  
- Dark: matte charcoal, white icons  

### **Timeline**
- Neon: cyan rail, magenta progress  
- Dark: gray rail, white progress  

### **Markers**
- Neon: yellow glow  
- Dark: white tick marks  

### **Monitor Selector**
- Neon: cyan/magenta portal glow  
- Dark: soft gray highlight  

### **Audio Routing**
- Neon: glowing nodes  
- Dark: flat buttons with white icons  

---

# 🔄 **Theme Switch Behavior (Dark ↔ Neon)**

### **Dark → Neon**
- Add neon glows  
- Switch icons to cyan/magenta  
- Panels shift from matte to holographic  
- Timeline rail becomes neon cyan  
- Buttons gain glow pulses  

### **Neon → Dark**
- Remove all glows  
- Icons become white  
- Panels become matte charcoal  
- Timeline becomes grayscale  
- Buttons become hardware‑like  

---

# If you want, I can now generate:

### ✔ A **side‑by‑side comparison** (Dark vs Neon)  
### ✔ A **Figma component variant sheet** for both themes  
### ✔ A **theme‑aware routing matrix**  
### ✔ A **dark‑mode video preview frame**  
### ✔ A **dark‑mode icon set** (white‑stroke SVG sprite)  

Just tell me which piece you want next.

===============================

**Creating SVG sprite**

I need to create an SVG sprite that’s similar to neon but with white strokes and no glows. It should be simple and concise, just a single `<svg>` element containing the symbols. I’ll focus on keeping it clean and minimal, ensuring it’s easy to use. I’ll make sure the strokes are white, and I’ll avoid any glowing effects. Let’s keep it straightforward and functional.
Here’s your **dark‑mode icon sprite**: same geometry as the neon set, but with **pure white strokes**, no neon color, no glow baked in—perfect for matte, industrial dark mode and easy to tint via CSS or Figma styles.

You can paste this directly as an SVG file (`controls-dark.svg`) or import into Figma and break into components.

---

### 🌑 Dark‑mode SVG sprite sheet (white‑stroke, 32×32, stroke‑only)

```xml
<svg xmlns="http://www.w3.org/2000/svg" style="display:none">

  <!-- PLAY -->
  <symbol id="icon-play-dark" viewBox="0 0 32 32">
    <path d="M12 8 L12 24 L24 16 Z"
          stroke="#FFFFFF" stroke-width="2"
          fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>

  <!-- PAUSE -->
  <symbol id="icon-pause-dark" viewBox="0 0 32 32">
    <path d="M10 8 L10 24" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M20 8 L20 24" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- STOP -->
  <symbol id="icon-stop-dark" viewBox="0 0 32 32">
    <rect x="10" y="10" width="12" height="12" rx="2"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- REWIND -->
  <symbol id="icon-rewind-dark" viewBox="0 0 32 32">
    <path d="M18 8 L10 16 L18 24 Z"
          stroke="#FFFFFF" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
    <path d="M10 8 L2 16 L10 24 Z"
          stroke="#FFFFFF" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
  </symbol>

  <!-- FAST FORWARD -->
  <symbol id="icon-fastforward-dark" viewBox="0 0 32 32">
    <path d="M14 8 L22 16 L14 24 Z"
          stroke="#FFFFFF" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
    <path d="M22 8 L30 16 L22 24 Z"
          stroke="#FFFFFF" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
  </symbol>

  <!-- NEXT MARK -->
  <symbol id="icon-nextmark-dark" viewBox="0 0 32 32">
    <path d="M10 8 L20 16 L10 24 Z"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M22 8 L22 24"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- PREVIOUS MARK -->
  <symbol id="icon-prevmark-dark" viewBox="0 0 32 32">
    <path d="M22 8 L12 16 L22 24 Z"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M10 8 L10 24"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- RANDOM -->
  <symbol id="icon-random-dark" viewBox="0 0 32 32">
    <path d="M6 10 C12 10, 20 22, 26 22"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M26 22 L22 18"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M26 22 L22 26"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 22 C12 22, 20 10, 26 10"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M26 10 L22 6"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M26 10 L22 14"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- SYNC -->
  <symbol id="icon-sync-dark" viewBox="0 0 32 32">
    <path d="M8 16 A8 8 0 0 1 24 16"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M24 16 L20 12"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M24 16 A8 8 0 0 1 8 16"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M8 16 L12 20"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- SETTINGS -->
  <symbol id="icon-settings-dark" viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="4"
            stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M16 4 L16 8"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 24 L16 28"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M4 16 L8 16"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M24 16 L28 16"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M7 7 L10 10"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M22 22 L25 25"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M7 25 L10 22"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M22 10 L25 7"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- MONITOR -->
  <symbol id="icon-monitor-dark" viewBox="0 0 32 32">
    <rect x="6" y="6" width="20" height="14" rx="2"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M12 24 L20 24"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 20 L16 24"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- AUDIO -->
  <symbol id="icon-audio-dark" viewBox="0 0 32 32">
    <path d="M8 12 L12 12 L16 8 L16 24 L12 20 L8 20 Z"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M20 12 C22 14, 22 18, 20 20"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M24 10 C28 14, 28 18, 24 22"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- PLAYLIST -->
  <symbol id="icon-playlist-dark" viewBox="0 0 32 32">
    <path d="M6 10 H20"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 16 H20"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 22 H20"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <rect x="22" y="8" width="4" height="4"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <rect x="22" y="14" width="4" height="4"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <rect x="22" y="20" width="4" height="4"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- FOLDER -->
  <symbol id="icon-folder-dark" viewBox="0 0 32 32">
    <path d="M4 10 H14 L18 14 H28 V26 H4 Z"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- CONFIG FILE -->
  <symbol id="icon-configfile-dark" viewBox="0 0 32 32">
    <path d="M8 4 H20 L26 10 V28 H8 Z"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M20 4 V10 H26"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <circle cx="16" cy="18" r="4"
            stroke="#FFFFFF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- SLIDERS -->
  <symbol id="icon-sliders-dark" viewBox="0 0 32 32">
    <path d="M8 6 V26" stroke="#FFFFFF" stroke-width="2"/>
    <circle cx="8" cy="14" r="3"
            stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M16 6 V26" stroke="#FFFFFF" stroke-width="2"/>
    <circle cx="16" cy="20" r="3"
            stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M24 6 V26" stroke="#FFFFFF" stroke-width="2"/>
    <circle cx="24" cy="10" r="3"
            stroke="#FFFFFF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- CLOCK -->
  <symbol id="icon-clock-dark" viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="10"
            stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M16 16 L16 10"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 16 L22 16"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- LINK -->
  <symbol id="icon-link-dark" viewBox="0 0 32 32">
    <path d="M10 16 C10 12, 14 12, 16 14 L18 16"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M22 16 C22 20, 18 20, 16 18 L14 16"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- WARNING -->
  <symbol id="icon-warning-dark" viewBox="0 0 32 32">
    <path d="M16 6 L28 26 H4 Z"
          stroke="#FFFFFF" stroke-width="2" fill="none"/>
    <path d="M16 12 L16 18"
          stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
    <circle cx="16" cy="22" r="1" fill="#FFFFFF"/>
  </symbol>

  <!-- CHECK -->
  <symbol id="icon-check-dark" viewBox="0 0 32 32">
    <path d="M6 16 L14 24 L26 8"
          stroke="#FFFFFF" stroke-width="2" fill="none"
          stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>

</svg>
```

If you want, next step we can wire this into a **theme‑aware icon system** (same IDs, different sprite per theme, or CSS‑driven color), so your app just flips a theme flag and everything—from Figma to runtime—stays perfectly in sync.

