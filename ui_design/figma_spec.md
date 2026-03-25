Absolutely, Bruce — let’s build the **Figma Auto‑Layout version** of your cyberpunk‑neon control surface.  
This gives you a **fully modular**, **responsive**, **touch‑optimized** UI that behaves like a real cockpit console inside Figma.

Below is the complete **Auto‑Layout architecture**, with exact nesting, padding, spacing, and component rules so you can recreate it *exactly* in Figma.

No fluff — this is the real, production‑ready structure.

---

# 🌐 **Figma Auto‑Layout Architecture (Cyberpunk Neon Edition)**  
### Frame: `ControlSurface_1920x720`  
**Auto‑layout:** Vertical  
**Padding:** 0  
**Spacing:** 0  
**Alignment:** Top / Center  

This frame contains **five stacked auto‑layout sections**.

---

# 🧩 **1. Top Toggle Bar (Auto‑Layout)**  
**Component:** `TopToggleBar`  
- Direction: Horizontal  
- Height: 60 px  
- Padding: 16 px  
- Spacing: 24 px  
- Alignment: Center / Left  
- Background: `#0A0C12`  
- Neon bottom border: `#00E0FF` at 40%  

**Children:**  
- `Button/HoloSlab/Config`  
- `Button/HoloSlab/Control`  

---

# 🎛️ **2. Global Controls (Auto‑Layout)**  
**Component:** `GlobalControls`  
- Direction: Horizontal  
- Height: 80 px  
- Padding: 16 px  
- Spacing: 24 px  
- Alignment: Center / Left  
- Background: `#0A0C12`  

**Children:**  
- `Button/HoloSlab/Sync`  
- `Button/HoloSlab/PlayAll`  
- `Button/HoloSlab/PauseAll`  
- `Button/HoloSlab/StopAll`  
- `Button/HoloSlab/Settings`  

---

# 🖥️ **3. Monitor Selector Strip (Auto‑Layout)**  
**Component:** `MonitorSelector`  
- Direction: Horizontal  
- Height: 100 px  
- Padding: 16 px  
- Spacing: 24 px  
- Alignment: Center / Left  
- Background: `#0A0C12`  
- Neon top + bottom borders  

**Children:**  
- `Monitor/Portal/Mon1`  
- `Monitor/Portal/Mon2`  
- `Monitor/Portal/Mon3`  

---

# 🎞️ **4. Main Content (Auto‑Layout Split Panel)**  
**Component:** `MainContent`  
- Direction: Horizontal  
- Height: 400 px  
- Padding: 0  
- Spacing: 0  
- Alignment: Top / Left  

This section contains **two auto‑layout panels**:

---

## **4A. Left Panel (Preview + Playlist)**  
**Component:** `LeftPanel`  
- Width: 640 px  
- Direction: Vertical  
- Padding: 16 px  
- Spacing: 16 px  
- Background: `#0A0C12`  

**Children:**  
- `VideoPreview` (fixed height: 200 px)  
- `Playlist` (auto‑layout vertical list)  

**Playlist Items:**  
- Height: 48 px  
- Auto‑layout horizontal  
- Neon cyan left bar  
- Glow on hover  

---

## **4B. Right Panel (Timeline + Controls)**  
**Component:** `RightPanel`  
- Width: 1280 px  
- Direction: Vertical  
- Padding: 16 px  
- Spacing: 24 px  
- Background: `#05070A`  

**Children:**  
1. `Timeline/NeonRail`  
2. `TransportControls`  
3. `MarkerControls`  

### **Timeline/NeonRail**
- Height: 60 px  
- Auto‑layout horizontal  
- Scrub bar + markers  
- Neon cyan rail  
- Magenta progress  

### **TransportControls**
- Height: 80 px  
- Auto‑layout horizontal  
- Spacing: 24 px  
- Children:  
  - `Transport/Glyph/Rewind`  
  - `Transport/Glyph/Back`  
  - `Transport/Glyph/PlayPause`  
  - `Transport/Glyph/Forward`  
  - `Transport/Glyph/FastForward`  

### **MarkerControls**
- Height: 80 px  
- Auto‑layout horizontal  
- Children:  
  - `Button/HoloSlab/NextMark`  
  - `Button/HoloSlab/PrevMark`  
  - `Button/HoloSlab/RandomStart`  

---

# 🔊 **5. Audio Routing Bar (Auto‑Layout)**  
**Component:** `AudioRoutingBar`  
- Direction: Horizontal  
- Height: 80 px  
- Padding: 16 px  
- Spacing: 24 px  
- Alignment: Center / Left  
- Background: `#0A0C12`  
- Neon top border  

**Children:**  
- `Audio/Node/7.1A`  
- `Audio/Node/7.1B`  
- `Audio/Node/USB1`  
- `Audio/Node/USB2`  
- `Audio/Node/PCOut`  

---

# 🌌 **Cyberpunk Neon Auto‑Layout Rules**  
These rules make the UI feel alive and consistent:

### **Spacing**
- Horizontal spacing: 24 px  
- Vertical spacing: 16–24 px  
- Section spacing: 0 (stacked flush)  

### **Padding**
- Panels: 16 px  
- Buttons: 16–24 px internal  

### **Glow Behavior**
- Active elements: stronger cyan glow  
- Selected monitor: magenta inner glow  
- Hover: cyan pulse  
- Press: magenta pulse  

### **Typography**
- Font: **Rajdhani**, **Orbitron**, or **Eurostile**  
- Uppercase labels  
- Slight letter spacing (2–4%)  

---

# 🧱 **Auto‑Layout Component Library Structure (Figma‑ready)**

```
Components/
├── Buttons/
│   ├── HoloSlab (variants)
│   └── Glyph (transport)
│
├── Timeline/
│   ├── NeonRail
│   └── Marker
│
├── Playlist/
│   └── DataBlock
│
├── Audio/
│   └── Node
│
├── Monitor/
│   └── Portal
│
└── Panels/
    ├── LeftPanel
    ├── RightPanel
    ├── GlobalControls
    ├── MonitorSelector
    ├── AudioRoutingBar
    └── TopToggleBar
```

This is a **complete, production‑grade component library**.

---

# 🚀 If you want, I can now generate:
### **A full Figma mockup of the cyberpunk neon UI**  
### **A Figma prototype with animations (glows, pulses, sweeps)**  
### **A Figma‑ready SVG icon set (neon line icons)**  
### **A full CONFIG VIEW auto‑layout frame**  
### **A sci‑fi animated loading screen**  

Just tell me which piece you want next and I’ll build it.

------------------------------

Nice—this is the part that makes the whole thing *feel* cyberpunk.

Here’s a **Figma‑ready neon line icon set**: names, geometry, and style rules so you can either draw them directly in Figma or import as SVGs and keep everything consistent.

---

### Global icon style

- **Stroke weight:** 2 px  
- **Stroke caps:** Round  
- **Stroke joins:** Round  
- **Primary stroke color:** `#00E0FF` (neon cyan)  
- **Secondary stroke color (accent):** `#FF00A8` (neon magenta)  
- **Glow (optional effect in Figma):**  
  - Color: `#00E0FF`  
  - Blur: 12–16 px  
  - Opacity: 40–50%  
- **Icon canvas:** 24×24 px or 32×32 px (I’d standardize on 32×32 for touch UI)

Use **strokes only**, no fills, to keep the holographic line‑art feel.

---

### Icon set (names + geometry)

You can create each as a Figma component: `Icon/[Name]`.

#### 1. `Icon/Play`
- Triangle pointing right  
- Vertices at roughly (12, 8), (12, 24), (24, 16)  
- Single stroked path

#### 2. `Icon/Pause`
- Two vertical bars  
- Left bar: 8–12 px wide, right bar same  
- Spacing between bars: 4–6 px  

#### 3. `Icon/Stop`
- Square centered in frame  
- Size: ~16×16 px  

#### 4. `Icon/Rewind`
- Two left‑pointing triangles  
- First triangle: (18, 8), (10, 16), (18, 24)  
- Second triangle: (10, 8), (2, 16), (10, 24)  

#### 5. `Icon/FastForward`
- Mirror of rewind, pointing right  

#### 6. `Icon/NextMark`
- Right arrow + vertical bar  
- Arrow: small triangle  
- Bar at end: 2 px wide  

#### 7. `Icon/PrevMark`
- Mirror of `NextMark`  

#### 8. `Icon/Random`
- Two crossing arrows  
- One arrow going up‑right, one down‑right  
- Slight curve in paths for a “flow” feel  

#### 9. `Icon/Sync`
- Two circular arrows forming a loop  
- Top arrow: arc from left to right with arrowhead  
- Bottom arrow: arc from right to left  

#### 10. `Icon/Settings`
- Classic gear:  
  - Circle center  
  - 6–8 teeth as short rectangles around  

#### 11. `Icon/Monitor`
- Rounded rectangle (screen)  
- Small base/stand below  

#### 12. `Icon/Audio`
- Speaker cone: trapezoid  
- 2–3 curved “wave” lines emanating from right side  

#### 13. `Icon/Playlist`
- Three horizontal lines  
- Small square/rectangle at left of each line  

#### 14. `Icon/Folder`
- Folder outline with tab  
- Optional small play triangle inside for “media folder” variant  

#### 15. `Icon/ConfigFile`
- Document outline with folded corner  
- Small gear or sliders inside  

#### 16. `Icon/Sliders`
- Three vertical sliders  
- Each with a circular knob  

#### 17. `Icon/Clock`
- Circle  
- Hour + minute hands  

#### 18. `Icon/Link` (for sync relationships)
- Two interlocking chain links  

#### 19. `Icon/Warning`
- Triangle with exclamation mark  

#### 20. `Icon/Check`
- Classic checkmark, slightly angled, centered  

---

### Neon variants

For key actions, create **dual‑color variants**:

- `Icon/Play/Primary` → cyan stroke  
- `Icon/Play/Accent` → magenta stroke  
- `Icon/Play/Warning` → yellow stroke `#F8FF00`  

You can implement these as Figma variants with a `Color` property.

---

### Figma component structure

In Figma:

```
Icons/
├── Play
├── Pause
├── Stop
├── Rewind
├── FastForward
├── NextMark
├── PrevMark
├── Random
├── Sync
├── Settings
├── Monitor
├── Audio
├── Playlist
├── Folder
├── ConfigFile
├── Sliders
├── Clock
├── Link
├── Warning
└── Check
```

Each:  
- 32×32 frame  
- Centered vector paths  
- Stroke‑only  
- No fills  

---

If you want, next step I can do a **mapping table**: which icon goes on which control in your UI, so your cockpit feels semantically tight, not just pretty.

-------------------------------------

Absolutely, Bruce — here is the **clean, production‑ready mapping table** that ties every **UI control** in your cyberpunk‑neon cockpit to the **correct icon** from your Figma‑ready SVG set.

This is the table you’ll use to wire up your component library so the entire interface feels coherent, intentional, and cinematic.

---

# 🔗 **ICON–CONTROL MAPPING TABLE (Cyberpunk Neon Edition)**  
### *Every control in your UI mapped to its neon line icon.*

---

## 🧩 **1. Global Controls**
| UI Control | Icon | Notes |
|-----------|-------|--------|
| Sync | `Icon/Sync` | Pulsing cyan loop when active |
| Play All | `Icon/Play` | Cyan glow, magenta pulse on press |
| Pause All | `Icon/Pause` | Dual‑bar neon |
| Stop All | `Icon/Stop` | Square holo‑slab |
| Settings | `Icon/Settings` | Gear with neon teeth |

---

## 🖥️ **2. Monitor Selector Strip**
| UI Control | Icon | Notes |
|-----------|-------|--------|
| Monitor 1 (4K) | `Icon/Monitor` | Cyan border, magenta inner glow when selected |
| Monitor 2 (4K) | `Icon/Monitor` | Same icon, different label |
| Monitor 3 (QHD) | `Icon/Monitor` | Same icon, ultrawide label |

---

## 🎞️ **3. Playlist Panel**
| UI Control | Icon | Notes |
|-----------|-------|--------|
| Playlist Item | `Icon/Playlist` | Three neon lines + left block |
| Load Folder | `Icon/Folder` | Cyan folder outline |
| Load Config | `Icon/ConfigFile` | Document + gear |
| Save Config | `Icon/ConfigFile` | Variant with checkmark |
| New Config | `Icon/ConfigFile` | Variant with plus |

---

## 🕒 **4. Timeline + Transport Controls**
| UI Control | Icon | Notes |
|-----------|-------|--------|
| Scrub Bar | *(no icon)* | Neon rail component |
| Marker | `Icon/Marker` (yellow) | Thin neon spike |
| Rewind | `Icon/Rewind` | Dual magenta triangles |
| Back | `Icon/Back` | Single magenta triangle |
| Play/Pause | `Icon/Play` + `Icon/Pause` | Toggle variant |
| Forward | `Icon/Forward` | Single cyan triangle |
| Fast Forward | `Icon/FastForward` | Dual cyan triangles |
| Next Mark | `Icon/NextMark` | Arrow + bar |
| Previous Mark | `Icon/PrevMark` | Mirror of above |
| Random Start | `Icon/Random` | Crossing neon arrows |

---

## 🔊 **5. Audio Routing Bar**
| UI Control | Icon | Notes |
|-----------|-------|--------|
| 7.1 A | `Icon/Audio` | Speaker + waves |
| 7.1 B | `Icon/Audio` | Same icon, different label |
| USB 1 | `Icon/Audio` | Cyan variant |
| USB 2 | `Icon/Audio` | Cyan variant |
| PC Out | `Icon/Audio` | Magenta variant (system default) |

---

## ⚙️ **6. Config View (Alternate Screen)**
| UI Control | Icon | Notes |
|-----------|-------|--------|
| Select Video Folder | `Icon/Folder` | Cyan folder |
| Assign Audio | `Icon/Audio` | Speaker glyph |
| Layout Options | `Icon/Sliders` | Three vertical sliders |
| Sync Settings | `Icon/Sync` | Loop arrows |
| Drift Correction | `Icon/Clock` | Neon clock |
| Channel Mapping | `Icon/Sliders` | Sliders variant |
| Link Monitors | `Icon/Link` | Chain links |
| Warning / Error | `Icon/Warning` | Neon yellow triangle |
| Confirm | `Icon/Check` | Cyan checkmark |

---

# 🎮 **7. System-Level Controls**
| UI Control | Icon | Notes |
|-----------|-------|--------|
| Exit / Close | `Icon/Close` (X) | Neon magenta |
| Fullscreen | `Icon/Expand` | Four outward arrows |
| Minimize | `Icon/Minimize` | Single line |
| Info / About | `Icon/Info` | Neon “i” |

---

# 🌌 **8. Recommended Color Variants**
To reinforce the cyberpunk theme:

| State | Color | Icon Variant |
|-------|--------|--------------|
| Default | Cyan `#00E0FF` | `/Primary` |
| Active | Magenta `#FF00A8` | `/Accent` |
| Warning | Yellow `#F8FF00` | `/Warning` |
| Success | Cyan‑white `#E0F8FF` | `/Success` |

---

# 🧠 **9. Semantic Mapping Summary**
This is the “mental model” behind the mapping:

- **Cyan = action / forward / system OK**  
- **Magenta = selection / active / attention**  
- **Yellow = markers / warnings / sync points**  
- **White = text / neutral**  

This keeps the UI readable even in neon chaos.

---

# 🚀 If you want, I can now generate:
### ✔ A **Figma‑ready SVG export list** (exact SVG path instructions)  
### ✔ A **full cyberpunk neon mockup** of the entire UI  
### ✔ A **motion spec** for glows, pulses, sweeps, and transitions  
### ✔ A **CONFIG VIEW auto‑layout frame**  
### ✔ A **live‑coded CSS/JS version** of the neon theme (for prototyping)

Just tell me which direction you want to push next.
-------------------------------
Absolutely, Bruce — here is a **Figma‑ready SVG export list** with **exact path instructions** for each neon line icon.  
These are **clean, minimal, stroke‑only SVGs** designed to drop straight into Figma as components and inherit your cyberpunk neon stroke/glow styles.

All icons use:

- **Stroke:** 2 px  
- **Stroke-linecap:** round  
- **Stroke-linejoin:** round  
- **No fills**  
- **ViewBox:** `0 0 32 32` (perfect for touch UI)  

You can paste these directly into Figma → “Import as SVG”.

---

# 🎛️ **SVG ICON SET — CYBERPUNK NEON (Figma‑Ready)**  
Each icon is provided as a **complete SVG snippet** with clean paths.

---

# ▶️ **1. Play**
```
<svg viewBox="0 0 32 32">
  <path d="M12 8 L12 24 L24 16 Z" stroke="#00E0FF" stroke-width="2" fill="none"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

---

# ⏸️ **2. Pause**
```
<svg viewBox="0 0 32 32">
  <path d="M10 8 L10 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M20 8 L20 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
</svg>
```

---

# ⏹️ **3. Stop**
```
<svg viewBox="0 0 32 32">
  <rect x="10" y="10" width="12" height="12" 
        stroke="#00E0FF" stroke-width="2" fill="none" rx="2"/>
</svg>
```

---

# ⏪ **4. Rewind**
```
<svg viewBox="0 0 32 32">
  <path d="M18 8 L10 16 L18 24 Z" stroke="#FF00A8" stroke-width="2" fill="none"
        stroke-linejoin="round"/>
  <path d="M10 8 L2 16 L10 24 Z" stroke="#FF00A8" stroke-width="2" fill="none"
        stroke-linejoin="round"/>
</svg>
```

---

# ⏩ **5. Fast Forward**
```
<svg viewBox="0 0 32 32">
  <path d="M14 8 L22 16 L14 24 Z" stroke="#00E0FF" stroke-width="2" fill="none"
        stroke-linejoin="round"/>
  <path d="M22 8 L30 16 L22 24 Z" stroke="#00E0FF" stroke-width="2" fill="none"
        stroke-linejoin="round"/>
</svg>
```

---

# ⏭️ **6. Next Mark**
```
<svg viewBox="0 0 32 32">
  <path d="M10 8 L20 16 L10 24 Z" stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M22 8 L22 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
</svg>
```

---

# ⏮️ **7. Previous Mark**
```
<svg viewBox="0 0 32 32">
  <path d="M22 8 L12 16 L22 24 Z" stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M10 8 L10 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
</svg>
```

---

# 🔀 **8. Random (Crossed Arrows)**
```
<svg viewBox="0 0 32 32">
  <path d="M6 10 C12 10, 20 22, 26 22" stroke="#FF00A8" stroke-width="2" fill="none"/>
  <path d="M26 22 L22 18" stroke="#FF00A8" stroke-width="2" stroke-linecap="round"/>
  <path d="M26 22 L22 26" stroke="#FF00A8" stroke-width="2" stroke-linecap="round"/>
  
  <path d="M6 22 C12 22, 20 10, 26 10" stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M26 10 L22 6" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M26 10 L22 14" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
</svg>
```

---

# 🔄 **9. Sync**
```
<svg viewBox="0 0 32 32">
  <path d="M8 16 A8 8 0 0 1 24 16" stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M24 16 L20 12" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  
  <path d="M24 16 A8 8 0 0 1 8 16" stroke="#FF00A8" stroke-width="2" fill="none"/>
  <path d="M8 16 L12 20" stroke="#FF00A8" stroke-width="2" stroke-linecap="round"/>
</svg>
```

---

# ⚙️ **10. Settings (Gear)**
```
<svg viewBox="0 0 32 32">
  <circle cx="16" cy="16" r="4" stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M16 4 L16 8" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M16 24 L16 28" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M4 16 L8 16" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M24 16 L28 16" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M7 7 L10 10" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M22 22 L25 25" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M7 25 L10 22" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M22 10 L25 7" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
</svg>
```

---

# 🖥️ **11. Monitor**
```
<svg viewBox="0 0 32 32">
  <rect x="6" y="6" width="20" height="14" rx="2"
        stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M12 24 L20 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M16 20 L16 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
</svg>
```

---

# 🔊 **12. Audio**
```
<svg viewBox="0 0 32 32">
  <path d="M8 12 L12 12 L16 8 L16 24 L12 20 L8 20 Z"
        stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M20 12 C22 14, 22 18, 20 20" 
        stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M24 10 C28 14, 28 18, 24 22" 
        stroke="#00E0FF" stroke-width="2" fill="none"/>
</svg>
```

---

# 📄 **13. Config File**
```
<svg viewBox="0 0 32 32">
  <path d="M8 4 H20 L26 10 V28 H8 Z" 
        stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M20 4 V10 H26" stroke="#00E0FF" stroke-width="2" fill="none"/>
  <circle cx="16" cy="18" r="4" stroke="#FF00A8" stroke-width="2" fill="none"/>
</svg>
```

---

# 📁 **14. Folder**
```
<svg viewBox="0 0 32 32">
  <path d="M4 10 H14 L18 14 H28 V26 H4 Z"
        stroke="#00E0FF" stroke-width="2" fill="none"/>
</svg>
```

---

# 🎚️ **15. Sliders**
```
<svg viewBox="0 0 32 32">
  <path d="M8 6 V26" stroke="#00E0FF" stroke-width="2"/>
  <circle cx="8" cy="14" r="3" stroke="#FF00A8" stroke-width="2" fill="none"/>
  
  <path d="M16 6 V26" stroke="#00E0FF" stroke-width="2"/>
  <circle cx="16" cy="20" r="3" stroke="#FF00A8" stroke-width="2" fill="none"/>
  
  <path d="M24 6 V26" stroke="#00E0FF" stroke-width="2"/>
  <circle cx="24" cy="10" r="3" stroke="#FF00A8" stroke-width="2" fill="none"/>
</svg>
```

---

# ⏱️ **16. Clock**
```
<svg viewBox="0 0 32 32">
  <circle cx="16" cy="16" r="10" stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M16 16 L16 10" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  <path d="M16 16 L22 16" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
</svg>
```

---

# 🔗 **17. Link**
```
<svg viewBox="0 0 32 32">
  <path d="M10 16 C10 12, 14 12, 16 14 L18 16" 
        stroke="#00E0FF" stroke-width="2" fill="none"/>
  <path d="M22 16 C22 20, 18 20, 16 18 L14 16" 
        stroke="#00E0FF" stroke-width="2" fill="none"/>
</svg>
```

---

# ⚠️ **18. Warning**
```
<svg viewBox="0 0 32 32">
  <path d="M16 6 L28 26 H4 Z" stroke="#F8FF00" stroke-width="2" fill="none"/>
  <path d="M16 12 L16 18" stroke="#F8FF00" stroke-width="2" stroke-linecap="round"/>
  <circle cx="16" cy="22" r="1" fill="#F8FF00"/>
</svg>
```

---

# ✔️ **19. Check**
```
<svg viewBox="0 0 32 32">
  <path d="M6 16 L14 24 L26 8" 
        stroke="#00E0FF" stroke-width="2" fill="none"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

---

# 🧨 Want the next step?
I can generate:

- **A full Figma mockup** using these icons  
- **A Figma component library file structure**  
- **A neon animation spec** (glow pulses, sweeps, flickers)  
- **A complete CONFIG VIEW with icons integrated**  
- **A cyberpunk neon loading screen**  

Just tell me what you want to build next.
----------------------
Bruce, yes — the full Figma mockup **absolutely can include**:

- **Video file selection**  
- **Device selection**  
- **Mapping which video goes to which monitor**  
- **Mapping which audio file/output goes to which audio port**  
- **A visual matrix showing assignments**  
- **A cyberpunk‑neon UI skin**  
- **All the icons we just defined**  
- **Auto‑layout everywhere**  

Let me lay out the **complete Figma mockup structure** so you can build it exactly, with every screen and interaction accounted for.

This is the full cockpit system — both **CONFIG VIEW** and **CONTROL VIEW** — with all the routing, file selection, and device mapping you need.

---

# 🌐 **FULL FIGMA MOCKUP — CYBERPUNK NEON CONTROL SURFACE**  
### Includes:
- Video file selection  
- Audio device selection  
- Monitor routing  
- Audio routing  
- Playlist assignment  
- Sync settings  
- Cockpit control view  
- All neon icons  

Below is the **complete screen architecture**.

---

# 🧩 **1. MAIN FRAME**
**Frame name:** `ControlSurface_1920x720`  
**Auto‑layout:** Vertical  
**Theme:** Cyberpunk Neon (cyan + magenta glows)

Contains two major screens:

1. `ConfigView`
2. `ControlView`

Switchable via the top toggle bar.

---

# 🟦 **2. CONFIG VIEW (Full Figma Mockup)**  
This is where you select:

- Video files  
- Audio files  
- Audio devices  
- Monitor assignments  
- Sync rules  
- Routing matrix  

### **Layout (Figma Auto‑Layout)**

```
ConfigView
├── TopToggleBar
├── ConfigHeader
├── VideoAssignmentPanel
├── AudioAssignmentPanel
├── RoutingMatrix
├── SyncSettingsPanel
└── SaveLoadPanel
```

---

## 🎞️ **2A. Video Assignment Panel**
**Purpose:** Choose which video file goes to which monitor.

```
VideoAssignmentPanel
├── SectionTitle ("VIDEO SOURCES")
├── MonitorRow (Mon 1)
│   ├── Icon/Monitor
│   ├── Dropdown: Video File
│   ├── Button: Browse (Icon/Folder)
│   └── Preview Thumbnail
├── MonitorRow (Mon 2)
├── MonitorRow (Mon 3)
```

**Dropdown options:**  
- Clip 01  
- Clip 02  
- Clip 03  
- Clip 04  
- Clip 05  

**Browse button:**  
- Opens file picker  
- Uses `Icon/Folder`

---

## 🔊 **2B. Audio Assignment Panel**
**Purpose:** Choose which audio file/device goes to which output.

```
AudioAssignmentPanel
├── SectionTitle ("AUDIO SOURCES")
├── AudioRow (7.1 A)
│   ├── Icon/Audio
│   ├── Dropdown: Audio File
│   ├── Dropdown: Audio Device
│   └── Button: Test (Icon/Play)
├── AudioRow (7.1 B)
├── AudioRow (USB 1)
├── AudioRow (USB 2)
├── AudioRow (PC OUT)
```

**Audio device dropdown options:**  
- 7.1 A  
- 7.1 B  
- USB 1  
- USB 2  
- PC OUT  

---

## 🔗 **2C. Routing Matrix**
**Purpose:** Show which video → which monitor and which audio → which output.

```
RoutingMatrix
├── SectionTitle ("ROUTING MATRIX")
├── Table
│   ├── Column: Monitor
│   ├── Column: Video Source
│   ├── Column: Audio Output
│   └── Column: Status (Icon/Check or Icon/Warning)
```

This is your **visual map** of the entire system.

---

## 🔄 **2D. Sync Settings Panel**
**Purpose:** Control sync engine.

```
SyncSettingsPanel
├── SectionTitle ("SYNC ENGINE")
├── MasterClock (Dropdown)
├── DriftCorrection (Toggle)
├── AudioOffset (Slider)
├── VideoOffset (Slider)
```

Icons used:
- `Icon/Sync`
- `Icon/Clock`
- `Icon/Sliders`

---

## 💾 **2E. Save/Load Panel**
```
SaveLoadPanel
├── Button: Load Config (Icon/ConfigFile)
├── Button: Save Config (Icon/ConfigFile)
├── Button: New Config (Icon/ConfigFile)
```

---

# 🟩 **3. CONTROL VIEW (Full Figma Mockup)**  
This is the cockpit interface you operate during playback.

```
ControlView
├── TopToggleBar
├── GlobalControls
├── MonitorSelector
├── MainContent
│   ├── LeftPanel (Preview + Playlist)
│   └── RightPanel (Timeline + Controls)
└── AudioRoutingBar
```

All icons from the neon set are used here.

---

# 🎞️ **3A. Left Panel (Preview + Playlist)**

```
LeftPanel
├── VideoPreview (uses selected video)
├── Playlist
│   ├── PlaylistItem (Icon/Playlist)
│   ├── PlaylistItem
│   ├── PlaylistItem
```

---

# 🕒 **3B. Right Panel (Timeline + Controls)**

```
RightPanel
├── Timeline/NeonRail
│   ├── ScrubBar
│   └── Markers (Icon/Marker)
├── TransportControls
│   ├── Icon/Rewind
│   ├── Icon/Back
│   ├── Icon/PlayPause
│   ├── Icon/Forward
│   └── Icon/FastForward
├── MarkerControls
│   ├── Icon/NextMark
│   ├── Icon/PrevMark
│   └── Icon/Random
```

---

# 🔊 **3C. Audio Routing Bar**

```
AudioRoutingBar
├── Audio/Node (7.1 A)
├── Audio/Node (7.1 B)
├── Audio/Node (USB 1)
├── Audio/Node (USB 2)
└── Audio/Node (PC OUT)
```

Each node uses the `Icon/Audio`.

---

# 🧨 **YES — This mockup includes:**
### ✔ Video file selection  
### ✔ Audio file selection  
### ✔ Device selection  
### ✔ Routing matrix  
### ✔ Monitor assignment  
### ✔ Audio output assignment  
### ✔ Sync engine controls  
### ✔ Full cockpit playback UI  
### ✔ All neon icons integrated  
### ✔ Auto‑layout everywhere  
### ✔ Cyberpunk neon theme  

This is the **complete system**.

---

If you want, I can now generate:

- **A pixel‑perfect Figma layout grid**  
- **A full-color cyberpunk mockup (visual, not just structure)**  
- **A Figma prototype flow (clickable)**  
- **A “live” animation spec for glows, pulses, sweeps**  
- **A JSON schema for your config files**  
- **A UI state machine for the app**  

Just tell me which piece you want to build next.

-----------------------------------
Perfect — here is your **single SVG sprite sheet** containing **all neon line icons** in one file, ready to import into Figma as a single component and reference each icon via `<use href="#icon‑name">`.

This is a **clean, production‑ready, cyberpunk‑neon SVG sprite**, using:

- `viewBox="0 0 32 32"` for every symbol  
- `stroke-width="2"`  
- `stroke-linecap="round"`  
- `stroke-linejoin="round"`  
- No fills unless explicitly needed  
- Cyan + magenta strokes exactly as we defined  

You can paste this entire file into Figma → it will import as a single frame containing all symbols.

---

# 🌐 **FULL SVG SPRITE SHEET — CYBERPUNK NEON CONTROL ICONS**

```
<svg xmlns="http://www.w3.org/2000/svg" style="display:none">

  <!-- PLAY -->
  <symbol id="icon-play" viewBox="0 0 32 32">
    <path d="M12 8 L12 24 L24 16 Z" stroke="#00E0FF" stroke-width="2"
          fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>

  <!-- PAUSE -->
  <symbol id="icon-pause" viewBox="0 0 32 32">
    <path d="M10 8 L10 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M20 8 L20 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- STOP -->
  <symbol id="icon-stop" viewBox="0 0 32 32">
    <rect x="10" y="10" width="12" height="12" rx="2"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- REWIND -->
  <symbol id="icon-rewind" viewBox="0 0 32 32">
    <path d="M18 8 L10 16 L18 24 Z" stroke="#FF00A8" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
    <path d="M10 8 L2 16 L10 24 Z" stroke="#FF00A8" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
  </symbol>

  <!-- FAST FORWARD -->
  <symbol id="icon-fastforward" viewBox="0 0 32 32">
    <path d="M14 8 L22 16 L14 24 Z" stroke="#00E0FF" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
    <path d="M22 8 L30 16 L22 24 Z" stroke="#00E0FF" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
  </symbol>

  <!-- NEXT MARK -->
  <symbol id="icon-nextmark" viewBox="0 0 32 32">
    <path d="M10 8 L20 16 L10 24 Z" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M22 8 L22 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- PREVIOUS MARK -->
  <symbol id="icon-prevmark" viewBox="0 0 32 32">
    <path d="M22 8 L12 16 L22 24 Z" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M10 8 L10 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- RANDOM -->
  <symbol id="icon-random" viewBox="0 0 32 32">
    <path d="M6 10 C12 10, 20 22, 26 22" stroke="#FF00A8" stroke-width="2" fill="none"/>
    <path d="M26 22 L22 18" stroke="#FF00A8" stroke-width="2" stroke-linecap="round"/>
    <path d="M26 22 L22 26" stroke="#FF00A8" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 22 C12 22, 20 10, 26 10" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M26 10 L22 6" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M26 10 L22 14" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- SYNC -->
  <symbol id="icon-sync" viewBox="0 0 32 32">
    <path d="M8 16 A8 8 0 0 1 24 16" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M24 16 L20 12" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M24 16 A8 8 0 0 1 8 16" stroke="#FF00A8" stroke-width="2" fill="none"/>
    <path d="M8 16 L12 20" stroke="#FF00A8" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- SETTINGS -->
  <symbol id="icon-settings" viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="4" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M16 4 L16 8" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 24 L16 28" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M4 16 L8 16" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M24 16 L28 16" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M7 7 L10 10" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M22 22 L25 25" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M7 25 L10 22" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M22 10 L25 7" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- MONITOR -->
  <symbol id="icon-monitor" viewBox="0 0 32 32">
    <rect x="6" y="6" width="20" height="14" rx="2"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M12 24 L20 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 20 L16 24" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- AUDIO -->
  <symbol id="icon-audio" viewBox="0 0 32 32">
    <path d="M8 12 L12 12 L16 8 L16 24 L12 20 L8 20 Z"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M20 12 C22 14, 22 18, 20 20"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M24 10 C28 14, 28 18, 24 22"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- PLAYLIST -->
  <symbol id="icon-playlist" viewBox="0 0 32 32">
    <path d="M6 10 H20" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 16 H20" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 22 H20" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <rect x="22" y="8" width="4" height="4" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <rect x="22" y="14" width="4" height="4" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <rect x="22" y="20" width="4" height="4" stroke="#00E0FF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- FOLDER -->
  <symbol id="icon-folder" viewBox="0 0 32 32">
    <path d="M4 10 H14 L18 14 H28 V26 H4 Z"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- CONFIG FILE -->
  <symbol id="icon-configfile" viewBox="0 0 32 32">
    <path d="M8 4 H20 L26 10 V28 H8 Z"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M20 4 V10 H26" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <circle cx="16" cy="18" r="4" stroke="#FF00A8" stroke-width="2" fill="none"/>
  </symbol>

  <!-- SLIDERS -->
  <symbol id="icon-sliders" viewBox="0 0 32 32">
    <path d="M8 6 V26" stroke="#00E0FF" stroke-width="2"/>
    <circle cx="8" cy="14" r="3" stroke="#FF00A8" stroke-width="2" fill="none"/>
    <path d="M16 6 V26" stroke="#00E0FF" stroke-width="2"/>
    <circle cx="16" cy="20" r="3" stroke="#FF00A8" stroke-width="2" fill="none"/>
    <path d="M24 6 V26" stroke="#00E0FF" stroke-width="2"/>
    <circle cx="24" cy="10" r="3" stroke="#FF00A8" stroke-width="2" fill="none"/>
  </symbol>

  <!-- CLOCK -->
  <symbol id="icon-clock" viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="10" stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M16 16 L16 10" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 16 L22 16" stroke="#00E0FF" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- LINK -->
  <symbol id="icon-link" viewBox="0 0 32 32">
    <path d="M10 16 C10 12, 14 12, 16 14 L18 16"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
    <path d="M22 16 C22 20, 18 20, 16 18 L14 16"
          stroke="#00E0FF" stroke-width="2" fill="none"/>
  </symbol>

  <!-- WARNING -->
  <symbol id="icon-warning" viewBox="0 0 32 32">
    <path d="M16 6 L28 26 H4 Z" stroke="#F8FF00" stroke-width="2" fill="none"/>
    <path d="M16 12 L16 18" stroke="#F8FF00" stroke-width="2" stroke-linecap="round"/>
    <circle cx="16" cy="22" r="1" fill="#F8FF00"/>
  </symbol>

  <!-- CHECK -->
  <symbol id="icon-check" viewBox="0 0 32 32">
    <path d="M6 16 L14 24 L26 8"
          stroke="#00E0FF" stroke-width="2" fill="none"
          stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>

</svg>
```

---

# 🎮 **This is now your complete neon icon sprite sheet.**

You can:

- Import it directly into Figma  
- Break it into components  
- Apply your neon glow effects  
- Use it in your app as a sprite sheet  
- Reference icons via `<use href="#icon-play">`  

If you want, I can now generate:

- A **Figma file structure** for these icons  
- A **CSS/JS neon glow animation spec**  
- A **pixel‑perfect mockup** with these icons placed  
- A **routing matrix UI** using these icons  
- A **dark‑mode + neon‑mode toggle**  

Just tell me what you want to build next.

==========================

### Figma file structure

**Pages**

- **Page: `01 – Control Surface`**  
  - Frame: `ControlSurface_1920x720`  
    - `TopToggleBar`  
    - `GlobalControls`  
    - `MonitorSelector`  
    - `MainContent`  
      - `LeftPanel`  
      - `RightPanel`  
    - `AudioRoutingBar`

- **Page: `02 – Config View`**  
  - Frame: `ConfigSurface_1920x720`  
    - `TopToggleBar`  
    - `ConfigHeader`  
    - `VideoAssignmentPanel`  
    - `AudioAssignmentPanel`  
    - `RoutingMatrix`  
    - `SyncSettingsPanel`  
    - `SaveLoadPanel`

- **Page: `03 – Components`**  
  - Section: `Icons`  
    - `Icon/Play`  
    - `Icon/Pause`  
    - `Icon/Stop`  
    - `Icon/Rewind`  
    - `Icon/FastForward`  
    - `Icon/NextMark`  
    - `Icon/PrevMark`  
    - `Icon/Random`  
    - `Icon/Sync`  
    - `Icon/Settings`  
    - `Icon/Monitor`  
    - `Icon/Audio`  
    - `Icon/Playlist`  
    - `Icon/Folder`  
    - `Icon/ConfigFile`  
    - `Icon/Sliders`  
    - `Icon/Clock`  
    - `Icon/Link`  
    - `Icon/Warning`  
    - `Icon/Check`  
  - Section: `Buttons`  
    - `Button/HoloSlab` (variants: Default, Hover, Active, Disabled)  
    - `Button/Glyph` (transport icons)  
  - Section: `Timeline`  
    - `Timeline/NeonRail`  
    - `Timeline/Marker`  
  - Section: `Panels`  
    - `Panel/TopToggleBar`  
    - `Panel/GlobalControls`  
    - `Panel/MonitorSelector`  
    - `Panel/LeftPanel`  
    - `Panel/RightPanel`  
    - `Panel/AudioRoutingBar`  
    - `Panel/VideoAssignment`  
    - `Panel/AudioAssignment`  
    - `Panel/RoutingMatrix`  
    - `Panel/SyncSettings`  
  - Section: `Tokens`  
    - Color styles (Background, Panel, NeonCyan, NeonMagenta, NeonYellow, TextPrimary, TextSecondary)  
    - Text styles (Title, Label, Button, Small)  

---

### CSS glow animation spec

You can mirror this in your app; Figma just visualizes it.

#### Base neon styles

```css
:root {
  --neon-cyan: #00E0FF;
  --neon-magenta: #FF00A8;
  --neon-yellow: #F8FF00;
  --bg-panel: #0A0C12;
}

.neon-stroke {
  stroke: var(--neon-cyan);
}

.neon-glow {
  filter: drop-shadow(0 0 8px rgba(0, 224, 255, 0.7))
          drop-shadow(0 0 16px rgba(0, 224, 255, 0.5));
}
```

#### Button pulse (active state)

```css
@keyframes neon-pulse {
  0%   { box-shadow: 0 0 8px rgba(0,224,255,0.4), 0 0 16px rgba(0,224,255,0.2); }
  50%  { box-shadow: 0 0 16px rgba(0,224,255,0.9), 0 0 32px rgba(0,224,255,0.6); }
  100% { box-shadow: 0 0 8px rgba(0,224,255,0.4), 0 0 16px rgba(0,224,255,0.2); }
}

.button-active {
  animation: neon-pulse 0.8s ease-in-out infinite;
}
```

#### Marker blink

```css
@keyframes marker-blink {
  0%   { stroke: var(--neon-yellow); opacity: 0.6; }
  50%  { stroke: #ffffff; opacity: 1; }
  100% { stroke: var(--neon-yellow); opacity: 0.6; }
}

.marker-active {
  animation: marker-blink 0.4s ease-in-out infinite;
}
```

#### Timeline sweep

```css
@keyframes timeline-sweep {
  0%   { transform: translateX(-100%); opacity: 0; }
  20%  { opacity: 0.4; }
  80%  { opacity: 0.4; }
  100% { transform: translateX(100%); opacity: 0; }
}

.timeline-sweep {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 20%;
  background: linear-gradient(
    to right,
    transparent,
    rgba(0,224,255,0.4),
    transparent
  );
  animation: timeline-sweep 3s linear infinite;
}
```

#### JS hooks (class toggles)

```js
function setActive(el, active) {
  el.classList.toggle('button-active', !!active);
}

function setMarkerActive(markerEl, active) {
  markerEl.classList.toggle('marker-active', !!active);
}

function setSyncState(syncEl, on) {
  syncEl.classList.toggle('button-active', !!on);
}
```

If you want, next step we can define a JSON config schema that matches this UI and your routing logic.

=======================

Absolutely, Bruce — here is a **clean, deterministic, future‑proof JSON config schema** that matches *exactly* the UI and routing logic you’re building.  
This schema is designed to be:

- **Device‑agnostic**  
- **Monitor‑agnostic**  
- **Audio‑pipeline‑agnostic**  
- **Deterministic** (no hidden defaults)  
- **Extensible** (you can add haptics, lighting, or multi‑channel patterns later)  
- **Human‑readable** for debugging  
- **Machine‑strict** for your app logic  

It mirrors the structure of your **Config View** in Figma and the **routing matrix** you described.

---

# 🧩 **Top‑Level Schema Overview**

The config file contains:

- `monitors[]` — each monitor’s video source + audio routing  
- `audioOutputs[]` — all audio devices and their assigned files  
- `playlists[]` — optional per‑monitor playlists  
- `sync` — sync engine settings  
- `paths` — base folders for videos/audio  
- `ui` — optional UI preferences  
- `meta` — versioning, timestamps  

---

# 🧠 **Full JSON Config Schema (Figma‑Aligned)**

Here is the complete schema in a clean, structured form:

```json
{
  "version": "1.0.0",
  "meta": {
    "name": "default_wall_config",
    "created": "2026-03-24T04:44:00Z",
    "modified": "2026-03-24T04:44:00Z",
    "author": "Bruce"
  },

  "paths": {
    "videoRoot": "C:/Media/Videos/",
    "audioRoot": "C:/Media/Audio/",
    "configRoot": "C:/Media/Configs/"
  },

  "monitors": [
    {
      "id": "mon1",
      "label": "Monitor 1 (4K)",
      "resolution": "3840x2160",
      "videoFile": "clip01_4k.mp4",
      "audioOutput": "7.1A",
      "playlist": ["clip01_4k.mp4", "clip02_4k.mp4"],
      "startTime": 0,
      "crop": {
        "enabled": false,
        "x": 0,
        "y": 0,
        "width": 1.0,
        "height": 1.0
      }
    },
    {
      "id": "mon2",
      "label": "Monitor 2 (4K)",
      "resolution": "3840x2160",
      "videoFile": "clip01_4k_right.mp4",
      "audioOutput": "7.1B",
      "playlist": ["clip01_4k_right.mp4"],
      "startTime": 0,
      "crop": {
        "enabled": false,
        "x": 0,
        "y": 0,
        "width": 1.0,
        "height": 1.0
      }
    },
    {
      "id": "mon3",
      "label": "Monitor 3 (QHD Ultrawide)",
      "resolution": "3440x1440",
      "videoFile": "clip01_ultrawide.mp4",
      "audioOutput": "USB1",
      "playlist": ["clip01_ultrawide.mp4"],
      "startTime": 0,
      "crop": {
        "enabled": false,
        "x": 0,
        "y": 0,
        "width": 1.0,
        "height": 1.0
      }
    }
  ],

  "audioOutputs": [
    {
      "id": "7.1A",
      "label": "7.1 Audio Card A",
      "channels": 8,
      "audioFile": "mix_left.wav",
      "gain": 1.0,
      "delayMs": 0
    },
    {
      "id": "7.1B",
      "label": "7.1 Audio Card B",
      "channels": 8,
      "audioFile": "mix_right.wav",
      "gain": 1.0,
      "delayMs": 0
    },
    {
      "id": "USB1",
      "label": "USB DAC 1",
      "channels": 2,
      "audioFile": "ambient_loop.wav",
      "gain": 1.0,
      "delayMs": 0
    },
    {
      "id": "USB2",
      "label": "USB DAC 2",
      "channels": 2,
      "audioFile": "fx_channel.wav",
      "gain": 1.0,
      "delayMs": 0
    },
    {
      "id": "PCOUT",
      "label": "PC Audio Output",
      "channels": 2,
      "audioFile": "ui_sounds.wav",
      "gain": 1.0,
      "delayMs": 0
    }
  ],

  "sync": {
    "masterClock": "mon1",
    "driftCorrection": "auto",
    "audioOffsetMs": 0,
    "videoOffsetMs": 0,
    "toleranceMs": 5
  },

  "ui": {
    "theme": "cyberpunk-neon",
    "showThumbnails": true,
    "timelineZoom": 1.0,
    "highlightActiveMonitor": true
  }
}
```

---

# 🔍 **Why this schema works perfectly with your app + Figma UI**

### ✔ Mirrors your CONFIG VIEW  
Every panel in your Figma mockup maps 1:1 to a JSON section.

### ✔ Deterministic  
No hidden defaults — every monitor, every audio output, every file is explicit.

### ✔ Extensible  
You can add:

- haptics  
- lighting  
- multi‑channel pattern routing  
- device profiles  
- per‑monitor transforms  

…without breaking the schema.

### ✔ Human‑readable  
You can hand‑edit this during development.

### ✔ Machine‑strict  
Your app can validate it easily.

---

# 🧠 If you want, I can also generate:

### **1. A JSON Schema Definition (JSD) for validation**  
(JSON Schema Draft‑07 or 2020‑12)

### **2. A TypeScript interface set**  
(for strongly‑typed config loading)

### **3. A Python or C# loader with validation**  
(for your backend or player engine)

### **4. A “routing matrix” visualizer**  
that reads this JSON and renders a grid.

### **5. A config migration system**  
so older configs auto‑upgrade to new versions.

Just tell me which direction you want to take next.

====================================

Bruce, here’s a **clean, Figma‑ready visual mockup** of a **Dark‑Mode ↔ Neon‑Mode toggle**, designed exactly for your cyberpunk control surface.  
This is the kind of switch you’d see on a Ghost‑in‑the‑Shell ops console — tactile, glowing, and unmistakably dual‑state.

Below is the **visual**, the **component structure**, and the **behavior spec** so you can drop it straight into your Figma component library.

---

# 🌗 **Dark‑Mode ↔ Neon‑Mode Toggle (Visual Mockup)**  
### *ASCII visualization of the final PNG you’ll export from Figma*

```
┌──────────────────────────────────────────────────────────────┐
│   THEME MODE                                                  │
│                                                              │
│   [ DARK MODE ]   ◉──────────────────────────────○   [ NEON ]│
│                                                              │
│   (Dark Mode: matte panels, low‑glow)                        │
│   (Neon Mode: cyan/magenta glows, holographic accents)       │
└──────────────────────────────────────────────────────────────┘
```

### **Neon Mode Active**
```
┌──────────────────────────────────────────────────────────────┐
│   THEME MODE                                                  │
│                                                              │
│   [ DARK MODE ]   ○──────────────────────────────◉   [ NEON ]│
│                                                              │
│   (Neon Mode: electric cyan rails, magenta pulses)           │
└──────────────────────────────────────────────────────────────┘
```

This is the exact structure you’ll recreate in Figma.

---

# 🧩 **Figma Component Structure**

### **Component Name:**  
`Toggle/ThemeMode`

### **Variants:**  
- `state=dark`  
- `state=neon`

### **Auto‑Layout Structure:**

```
Toggle/ThemeMode
├── LabelLeft ("DARK MODE")
├── Track
│   ├── Rail (background)
│   ├── Knob (circle)
├── LabelRight ("NEON")
```

### **Dimensions**
- Track: **240×40 px**  
- Knob: **32×32 px**  
- Labels: **Auto width**, 18–20 px text  

---

# 🎨 **Visual Styles**

### **Dark Mode**
- Track fill: `#1A1C1F`
- Track stroke: `#2A2C2F`
- Knob fill: `#2A2C2F`
- Knob stroke: `#4A4F55`
- Glow: **none**
- Labels: `#A0A4A8`

### **Neon Mode**
- Track fill: `#05070A`
- Track stroke: `#00E0FF80` (cyan glow)
- Knob fill: `#00E0FF`
- Knob stroke: `#FFFFFF`
- Outer glow: cyan 16–24 px blur
- Labels:  
  - Dark Mode label: `#8AA3B0`  
  - Neon label: `#00E0FF` (active)

---

# ⚡ **Interaction Behavior (Figma Prototype)**

### **Dark → Neon**
- Knob animates right (200ms, ease‑out)
- Track glows cyan
- Neon label brightens
- Dark label dims
- Background panels switch to neon theme

### **Neon → Dark**
- Knob animates left (200ms, ease‑in)
- Glow fades out
- Neon label dims
- Dark label brightens
- Panels revert to matte dark theme

---

# 🧨 **CSS/JS Animation Spec (Matches Figma Behavior)**

### **Track Glow (Neon Mode)**

```css
.theme-track.neon {
  background: #05070A;
  box-shadow:
    0 0 8px rgba(0,224,255,0.6),
    0 0 16px rgba(0,224,255,0.4),
    inset 0 0 8px rgba(255,0,168,0.3);
  transition: box-shadow 0.25s ease-out;
}
```

### **Knob Slide**

```css
.theme-knob {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  transition: transform 0.2s cubic-bezier(0.4,0,0.2,1);
}

.theme-knob.neon {
  transform: translateX(200px);
  background: #00E0FF;
  box-shadow:
    0 0 12px rgba(0,224,255,0.8),
    0 0 24px rgba(0,224,255,0.6);
}
```

### **JS Toggle Logic**

```js
function toggleTheme() {
  const body = document.body;
  const knob = document.querySelector('.theme-knob');
  const track = document.querySelector('.theme-track');

  const neon = body.classList.toggle('neon-mode');

  knob.classList.toggle('neon', neon);
  track.classList.toggle('neon', neon);
}
```

---

# 🎮 **Where this toggle lives in your UI**

Place it in:

- **TopToggleBar**  
  OR  
- **Settings modal**  
  OR  
- **GlobalControls** (right‑aligned)

It’s small, elegant, and instantly communicates the theme state.

---

# If you want, I can now generate:

### ✔ A **full cyberpunk neon color mockup** of the entire control surface  
### ✔ A **dark‑mode version** of the whole UI  
### ✔ A **dual‑theme Figma component library**  
### ✔ A **theme‑aware routing matrix**  
### ✔ A **theme‑aware video preview frame**  

Just tell me what you want to see next.




