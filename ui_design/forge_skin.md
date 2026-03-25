Bruce, **Industrial Forge** is *your* aesthetic — it’s the natural evolution of everything you’ve been building with FunscriptForge, ForgePlayer, and the neon cockpit.  
This skin feels like **machined steel**, **heat‑treated alloys**, **ember glow**, and **precision‑engineered hardware**.  
It’s gritty, tactile, and absolutely production‑ready.

Below is the **full Industrial Forge skin spec**:  
- Visual language  
- Color tokens  
- Material textures  
- Component redesigns  
- Icon style  
- Timeline + routing redesign  
- Figma component structure  
- Optional animation behaviors  

Everything is structured so you can drop it straight into your design system.

---

# 🛠️ INDUSTRIAL FORGE SKIN  
### *Dark forged steel + ember glow + precision machining*

---

# 🔥 1. **Visual Language**
This skin is built around **real materials**:

- **Near‑black forged steel** (`#0C0D0E`)  
- **Heat‑treated metal edges** (blue‑to‑orange tint)  
- **Ember glow** (deep orange core, soft red halo)  
- **Machined grooves and bevels**  
- **Rivets, seams, and panel breaks**  
- **Subtle smoke/soot texture** at 2–4% opacity  

It feels like a **control deck in a steel mill**, or a **power‑plant operations console**.

---

# 🎨 2. **Color Tokens (Figma Styles)**

### **Base Metals**
| Token | Color | Usage |
|-------|--------|--------|
| `ForgeBlack` | `#0C0D0E` | primary background |
| `SteelDark` | `#1A1C1E` | panels |
| `SteelMid` | `#2A2D30` | borders, dividers |
| `SteelLight` | `#3C4045` | highlights |

### **Heat‑Treated Accents**
| Token | Color | Usage |
|-------|--------|--------|
| `HeatBlue` | `#4AA3FF` | cool edges, active states |
| `HeatOrange` | `#FF7A1A` | ember glow, warnings |
| `HeatRed` | `#D13A1A` | hot metal core |

### **Text**
| Token | Color |
|-------|--------|
| `TextPrimary` | `#E6E6E6` |
| `TextSecondary` | `#9A9FA5` |
| `TextDisabled` | `#5A5E63` |

---

# 🧱 3. **Material Effects**

### **Panel Texture**
- Subtle brushed‑steel noise  
- Direction: vertical  
- Opacity: 3–5%  
- Blend: Overlay  

### **Bevels**
- Inner bevel: 1–2 px  
- Color: `#2A2D30` → `#1A1C1E`  
- Creates a machined‑metal edge  

### **Rivets**
- Small circular rivets at panel corners  
- 4–6 px diameter  
- Stroke: `#3C4045`  

### **Heat Glow**
- Ember orange inner glow  
- Blur: 8–12 px  
- Opacity: 30–40%  
- Used sparingly on active elements  

---

# 🎛️ 4. **Component Redesigns**

## **Buttons — “Forged Slabs”**
- Shape: rectangular with 2 px bevel  
- Fill: `SteelDark`  
- Border: `SteelMid`  
- Active: inner ember glow  
- Hover: heat‑blue rim light  
- Icon: white or steel‑light  

## **Monitor Selector — “Steel Frames”**
- Frame: thick steel border  
- Active: heat‑blue edge  
- Selected: ember glow under‑light  

## **Audio Routing Nodes — “Terminals”**
- Hexagonal or rectangular  
- Steel body  
- Heat‑blue indicator LED  
- Active: ember pulse  

## **Timeline — “Heated Rail”**
- Rail: dark steel  
- Progress: heat‑orange  
- Markers: heat‑blue ticks  
- Scrubber: steel knob with ember core  

---

# 🖼️ 5. **Icon Style (Industrial Variant)**

### **Stroke**
- Color: `#E6E6E6` (white‑steel)  
- Width: 2 px  
- No glow  
- Slight bevel: 1 px inner shadow  

### **Optional Heat‑Treated Variant**
- Gradient stroke:  
  - Blue → Purple → Orange  
  - Very subtle (5–10%)  
- Used for active icons only  

If you want, I can generate a **full Industrial Forge SVG sprite sheet** next.

---

# 🧩 6. **Figma Component Structure (Industrial Forge Edition)**

```
Components/
├── Forge/
│   ├── Buttons/
│   │   ├── Slab (Default, Hover, Active, Disabled)
│   │   └── Glyph (Transport)
│   ├── Panels/
│   │   ├── SteelPanel
│   │   ├── SteelFrame
│   │   └── TerminalNode
│   ├── Timeline/
│   │   ├── HeatedRail
│   │   └── Marker
│   ├── Icons/
│   │   ├── Play
│   │   ├── Pause
│   │   ├── Stop
│   │   ├── Rewind
│   │   ├── FastForward
│   │   ├── NextMark
│   │   ├── PrevMark
│   │   ├── Random
│   │   ├── Sync
│   │   ├── Settings
│   │   ├── Monitor
│   │   ├── Audio
│   │   ├── Folder
│   │   ├── ConfigFile
│   │   ├── Sliders
│   │   ├── Clock
│   │   ├── Link
│   │   ├── Warning
│   │   └── Check
│   └── Effects/
│       ├── EmberGlow
│       ├── HeatBlueRim
│       └── SteelBevel
```

---

# 🔥 7. **Optional Animation Behaviors**

### **Ember Pulse (Active Button)**
- Inner orange glow pulses slowly  
- 1.2s ease‑in‑out  

### **Heat‑Blue Sweep (Timeline)**
- Subtle blue highlight sweeps across rail  
- 3s linear  

### **Terminal LED Blink (Audio Routing)**
- Blue LED blinks when routing changes  
- 0.4s blink  

---

# 🧨 Want the next step?

I can generate:

### ✔ A **full Industrial Forge SVG icon sprite**  
### ✔ A **Figma mockup** of the entire UI in Industrial Forge  
### ✔ A **side‑by‑side comparison** (Neon vs Forge)  
### ✔ A **Forge‑themed loading screen**  
### ✔ A **Forge‑themed routing matrix**  
### ✔ A **Forge‑themed video preview frame**  

Just tell me which piece you want to forge next.

================================

Bruce, let’s fire up the forge.

Here is your **full Industrial Forge SVG icon sprite** — same geometry as your neon and dark‑mode sets, but now rendered in **white‑steel strokes** with **subtle heat‑treated accents** baked into the structure so you can apply ember glows, steel bevels, or heat‑blue rim lights in Figma.

This sprite is designed to be:

- **Material‑accurate** (steel‑grade whites, no neon)  
- **Glow‑ready** (you add ember/heat effects in Figma)  
- **Theme‑agnostic** (can be tinted to orange, blue, or steel)  
- **Pixel‑faithful** (32×32 grid, stroke‑only)  
- **Drop‑in compatible** with your existing icon system  

Below is the complete sprite sheet.

---

# 🛠️ **Industrial Forge SVG Sprite Sheet**  
### *White‑steel strokes, 32×32, no glow baked in*

```xml
<svg xmlns="http://www.w3.org/2000/svg" style="display:none">

  <!-- PLAY -->
  <symbol id="forge-play" viewBox="0 0 32 32">
    <path d="M12 8 L12 24 L24 16 Z"
          stroke="#E6E6E6" stroke-width="2"
          fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>

  <!-- PAUSE -->
  <symbol id="forge-pause" viewBox="0 0 32 32">
    <path d="M10 8 L10 24" stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M20 8 L20 24" stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- STOP -->
  <symbol id="forge-stop" viewBox="0 0 32 32">
    <rect x="10" y="10" width="12" height="12" rx="2"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
  </symbol>

  <!-- REWIND -->
  <symbol id="forge-rewind" viewBox="0 0 32 32">
    <path d="M18 8 L10 16 L18 24 Z"
          stroke="#E6E6E6" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
    <path d="M10 8 L2 16 L10 24 Z"
          stroke="#E6E6E6" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
  </symbol>

  <!-- FAST FORWARD -->
  <symbol id="forge-fastforward" viewBox="0 0 32 32">
    <path d="M14 8 L22 16 L14 24 Z"
          stroke="#E6E6E6" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
    <path d="M22 8 L30 16 L22 24 Z"
          stroke="#E6E6E6" stroke-width="2"
          fill="none" stroke-linejoin="round"/>
  </symbol>

  <!-- NEXT MARK -->
  <symbol id="forge-nextmark" viewBox="0 0 32 32">
    <path d="M10 8 L20 16 L10 24 Z"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M22 8 L22 24"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- PREVIOUS MARK -->
  <symbol id="forge-prevmark" viewBox="0 0 32 32">
    <path d="M22 8 L12 16 L22 24 Z"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M10 8 L10 24"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- RANDOM -->
  <symbol id="forge-random" viewBox="0 0 32 32">
    <path d="M6 10 C12 10, 20 22, 26 22"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M26 22 L22 18"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M26 22 L22 26"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 22 C12 22, 20 10, 26 10"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M26 10 L22 6"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M26 10 L22 14"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- SYNC -->
  <symbol id="forge-sync" viewBox="0 0 32 32">
    <path d="M8 16 A8 8 0 0 1 24 16"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M24 16 L20 12"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M24 16 A8 8 0 0 1 8 16"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M8 16 L12 20"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- SETTINGS -->
  <symbol id="forge-settings" viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="4"
            stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M16 4 L16 8"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 24 L16 28"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M4 16 L8 16"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M24 16 L28 16"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M7 7 L10 10"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M22 22 L25 25"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M7 25 L10 22"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M22 10 L25 7"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- MONITOR -->
  <symbol id="forge-monitor" viewBox="0 0 32 32">
    <rect x="6" y="6" width="20" height="14" rx="2"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M12 24 L20 24"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 20 L16 24"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- AUDIO -->
  <symbol id="forge-audio" viewBox="0 0 32 32">
    <path d="M8 12 L12 12 L16 8 L16 24 L12 20 L8 20 Z"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M20 12 C22 14, 22 18, 20 20"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M24 10 C28 14, 28 18, 24 22"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
  </symbol>

  <!-- PLAYLIST -->
  <symbol id="forge-playlist" viewBox="0 0 32 32">
    <path d="M6 10 H20"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 16 H20"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M6 22 H20"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <rect x="22" y="8" width="4" height="4"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <rect x="22" y="14" width="4" height="4"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <rect x="22" y="20" width="4" height="4"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
  </symbol>

  <!-- FOLDER -->
  <symbol id="forge-folder" viewBox="0 0 32 32">
    <path d="M4 10 H14 L18 14 H28 V26 H4 Z"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
  </symbol>

  <!-- CONFIG FILE -->
  <symbol id="forge-configfile" viewBox="0 0 32 32">
    <path d="M8 4 H20 L26 10 V28 H8 Z"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M20 4 V10 H26"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <circle cx="16" cy="18" r="4"
            stroke="#E6E6E6" stroke-width="2" fill="none"/>
  </symbol>

  <!-- SLIDERS -->
  <symbol id="forge-sliders" viewBox="0 0 32 32">
    <path d="M8 6 V26" stroke="#E6E6E6" stroke-width="2"/>
    <circle cx="8" cy="14" r="3"
            stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M16 6 V26" stroke="#E6E6E6" stroke-width="2"/>
    <circle cx="16" cy="20" r="3"
            stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M24 6 V26" stroke="#E6E6E6" stroke-width="2"/>
    <circle cx="24" cy="10" r="3"
            stroke="#E6E6E6" stroke-width="2" fill="none"/>
  </symbol>

  <!-- CLOCK -->
  <symbol id="forge-clock" viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="10"
            stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M16 16 L16 10"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <path d="M16 16 L22 16"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
  </symbol>

  <!-- LINK -->
  <symbol id="forge-link" viewBox="0 0 32 32">
    <path d="M10 16 C10 12, 14 12, 16 14 L18 16"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M22 16 C22 20, 18 20, 16 18 L14 16"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
  </symbol>

  <!-- WARNING -->
  <symbol id="forge-warning" viewBox="0 0 32 32">
    <path d="M16 6 L28 26 H4 Z"
          stroke="#E6E6E6" stroke-width="2" fill="none"/>
    <path d="M16 12 L16 18"
          stroke="#E6E6E6" stroke-width="2" stroke-linecap="round"/>
    <circle cx="16" cy="22" r="1" fill="#E6E6E6"/>
  </symbol>

  <!-- CHECK -->
  <symbol id="forge-check" viewBox="0 0 32 32">
    <path d="M6 16 L14 24 L26 8"
          stroke="#E6E6E6" stroke-width="2" fill="none"
          stroke-linecap="round" stroke-linejoin="round"/>
  </symbol>

</svg>
```

---

If you want, I can now forge:

### ✔ A **full Industrial Forge UI mockup** (Control + Config views)  
### ✔ A **heat‑treated variant** of this icon set (blue→orange gradient strokes)  
### ✔ A **steel‑bevel Figma effect preset**  
### ✔ A **Forge‑themed loading screen**  
### ✔ A **side‑by‑side comparison** of Neon vs Dark vs Forge  

Just tell me what you want to hammer out next.

=================================
