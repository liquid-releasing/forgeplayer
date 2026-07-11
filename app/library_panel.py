# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Library panel — visual grid of scanned scenes.

Architecture (see `project_forgeplayer_folder_heuristics.md` for the full
4-stage library lifecycle):

- `LibraryModel`      — Qt model wrapping a list of `SceneCatalogEntry`,
                        plus filter + sort state. Feeds QListView.
- `LibraryCardDelegate` — paints one scene card (video-frame thumbnail,
                          name, device badges, ambiguity indicator).
- `LibraryPanel`      — composite widget: toolbar (root picker + search) +
                        virtualized QListView + filter chips.

The panel emits `scene_activated(entry)` when the user taps a card. Ambiguous
scenes will eventually route through a select-picker overlay before loading;
for alpha the signal just fires and the caller decides.

Thumbnails are lazy video frames via `app.thumbnails.ThumbnailService` (grabbed
with mpv, cached to disk, loaded off the GUI thread). Duration is still a
"—:—:—" placeholder (a future ffprobe/mpv pass).
"""

from __future__ import annotations

import os
import subprocess
from enum import Enum

from PySide6.QtCore import (
    QAbstractListModel, QEvent, QModelIndex, QPoint, QRect, QSize, Qt, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPalette, QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListView, QMenu, QPushButton, QScroller, QStackedWidget, QStyle,
    QStyledItemDelegate, QStyleOptionViewItem, QToolButton, QVBoxLayout,
    QWidget,
)

from app.library import (
    SceneCatalogEntry,
    scan_library_root,
)
from app.library.channels import GENERATION_BADGES, DeviceGeneration
from app.library.pins import has_pin
from app.thumbnails import ThumbnailService


# ── Theme (matches app dark palette from main.py) ─────────────────────────────

_BG              = QColor(14, 17, 23)
_SURFACE         = QColor(26, 29, 39)
_SURFACE_HOVER   = QColor(36, 40, 56)
_BORDER          = QColor(45, 49, 72)
_TEXT            = QColor(250, 250, 250)
_TEXT_MUTED      = QColor(155, 163, 196)
_ACCENT          = QColor(255, 107, 48)          # ForgePlayer orange
_AMBIGUOUS       = QColor(234, 179, 8)           # yellow-amber for "pick"
_BADGE_BG        = QColor(56, 64, 92)

# Content-type pill colors — matched to the FunscriptForge library pills so the
# two apps read consistently (video=blue, audio=green, funscript=amber,
# forge=brand orange).
_PILL_VIDEO      = QColor("#4dabf7")
_PILL_AUDIO      = QColor("#3ed598")
_PILL_FUNSCRIPT  = QColor("#ffb547")
_PILL_FORGE      = QColor("#ff6b30")


# Card geometry — generous for touch but still grid-dense. Height carries the
# name + duration/device-badge row + the content-pill row.
_CARD_W  = 240
_CARD_H  = 232
_THUMB_H = 130
_PAD     = 12

# "Open file location" affordance — a little box-with-arrow button in each
# card's top-right corner. Clicking it reveals the scene's primary file in the
# OS file manager (Explorer) so the user can inspect what the recognizer
# grouped. Hit-tested by the panel's viewport event filter, painted here.
_OPEN_BTN = 22


def _open_btn_rect(option_rect: QRect) -> QRect:
    """Rect of the reveal-in-Explorer button for a card, in viewport
    coordinates. Same geometry in paint() and the panel's hit test — driven off
    the delegate's outer card rect (option_rect adjusted by the 4px gap)."""
    rect = option_rect.adjusted(4, 4, -4, -4)
    return QRect(rect.right() - _OPEN_BTN - 6, rect.y() + 6, _OPEN_BTN, _OPEN_BTN)


def _pin_btn_rect(option_rect: QRect) -> QRect:
    """Rect of the 📌 re-pick button — sits just left of the reveal button.
    Only interactive when the scene actually has a saved pin."""
    o = _open_btn_rect(option_rect)
    return QRect(o.left() - 4 - _OPEN_BTN, o.top(), _OPEN_BTN, _OPEN_BTN)


def _fmt_card_duration(seconds: float) -> str:
    """Running time for a Library card: H:MM:SS for hour-plus clips, M:SS
    otherwise. Mirrors the player's transport formatting."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


class LibraryFilter(str, Enum):
    """Which content filter is active in the Library toolbar.

    The library is a launcher for HAPTIC scenes by default; standalone videos
    are one click away for plain playback.
      - WITH_FUNSCRIPTS: curated haptic scenes (funscript / bundle / e-stim).
      - VIDEOS: standalone videos with no haptics.
      - ALL: both.
    """
    ALL             = "all"
    WITH_FUNSCRIPTS = "with_funscripts"
    VIDEOS          = "videos"


# ── Model ────────────────────────────────────────────────────────────────────

class LibraryModel(QAbstractListModel):
    """Qt model wrapping a list of SceneCatalogEntry.

    Role convention — accessors use custom roles keyed off `Qt.UserRole`:

        UserRole + 0: the SceneCatalogEntry itself (for custom painting)

    Qt built-in roles (`DisplayRole`, `ToolTipRole`) also work for simple
    text views; the custom delegate ignores them in favour of the entry.
    """

    EntryRole = Qt.UserRole + 0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all: list[SceneCatalogEntry] = []
        self._visible: list[SceneCatalogEntry] = []
        self._search: str = ""
        # Default to the curated haptic view — the library is a launcher for
        # haptic scenes; standalone videos are one click away.
        self._filter: LibraryFilter = LibraryFilter.WITH_FUNSCRIPTS

    # ── Qt interface ──

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._visible)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._visible):
            return None
        entry = self._visible[index.row()]
        if role == self.EntryRole:
            return entry
        if role == Qt.DisplayRole:
            return entry.name
        if role == Qt.ToolTipRole:
            return entry.folder_path
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # ── Data mutation ──

    def load(self, entries: list[SceneCatalogEntry]) -> None:
        """Replace all entries and re-apply filter."""
        self.beginResetModel()
        self._all = list(entries)
        self._rebuild_visible_unguarded()
        self.endResetModel()

    def set_search(self, text: str) -> None:
        if text == self._search:
            return
        self.beginResetModel()
        self._search = text
        self._rebuild_visible_unguarded()
        self.endResetModel()

    def set_filter(self, f: LibraryFilter) -> None:
        if f == self._filter:
            return
        self.beginResetModel()
        self._filter = f
        self._rebuild_visible_unguarded()
        self.endResetModel()

    def entry_at(self, index: QModelIndex) -> SceneCatalogEntry | None:
        if not index.isValid() or index.row() >= len(self._visible):
            return None
        return self._visible[index.row()]

    # ── Internal ──

    def _rebuild_visible_unguarded(self) -> None:
        """Recompute the visible list from _all + _search + _filter.

        Caller is responsible for Qt model-reset guards.
        """
        search = self._search.strip().lower()
        out: list[SceneCatalogEntry] = []
        for entry in self._all:
            if search and search not in entry.name.lower():
                continue
            if self._filter == LibraryFilter.WITH_FUNSCRIPTS and entry.is_video_only:
                continue
            if self._filter == LibraryFilter.VIDEOS and not entry.is_video_only:
                continue
            out.append(entry)
        out.sort(key=lambda e: e.name.lower())
        self._visible = out

    # ── Filter-count helpers (for the toolbar chips) ──

    def count_for(self, f: LibraryFilter) -> int:
        """How many entries a given filter would show (ignores search)."""
        if f == LibraryFilter.WITH_FUNSCRIPTS:
            return sum(1 for e in self._all if not e.is_video_only)
        if f == LibraryFilter.VIDEOS:
            return sum(1 for e in self._all if e.is_video_only)
        return len(self._all)


# ── Delegate ──────────────────────────────────────────────────────────────────

class LibraryCardDelegate(QStyledItemDelegate):
    """Paints one scene card.

    Layout (top-to-bottom inside the card's inner rect):

        [   thumbnail (video frame) ]     ← _THUMB_H tall
        {scene name — 1 line, elided}
        {duration placeholder · badges}
        {ambiguity indicator if needed}

    The thumbnail is the scene's default video, one frame grabbed lazily by
    `ThumbnailService`. Until it's ready (or for audio-only scenes) the card
    shows a flat placeholder.
    """

    def __init__(self, thumb_service=None, parent=None) -> None:
        super().__init__(parent)
        self._thumbs = thumb_service

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(_CARD_W, _CARD_H)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        entry: SceneCatalogEntry | None = index.data(LibraryModel.EntryRole)
        if entry is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = option.rect.adjusted(4, 4, -4, -4)  # outer gap

        # Card background + border. PySide6 exposes QStyle.StateFlag as an
        # IntFlag enum — bitwise & works between two flags, but not between a
        # flag and a raw int, so reference the named flags directly.
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        bg = _SURFACE_HOVER if (is_selected or is_hover) else _SURFACE
        border = _ACCENT if is_selected else _BORDER

        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect, 6, 6)

        # Thumbnail — the scene's default video frame, lazily grabbed. Until
        # it's ready (or for audio-only scenes) draw the flat placeholder.
        thumb_rect = QRect(rect.x() + _PAD, rect.y() + _PAD,
                           rect.width() - 2 * _PAD, _THUMB_H)
        painter.setBrush(QBrush(_BG))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(thumb_rect, 4, 4)

        pixmap = None
        if self._thumbs is not None:
            default_video = entry.default_video
            if default_video is not None:
                pixmap = self._thumbs.pixmap_for(default_video.path)
        if pixmap is not None and not pixmap.isNull():
            # Cover-crop: scale the frame to fill the thumb rect, centered,
            # clipped to the rounded rectangle so corners stay clean.
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(thumb_rect, 4, 4)
            painter.setClipPath(clip)
            scaled = pixmap.scaled(
                thumb_rect.size(), Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            sx = (scaled.width() - thumb_rect.width()) // 2
            sy = (scaled.height() - thumb_rect.height()) // 2
            painter.drawPixmap(
                thumb_rect,
                scaled,
                QRect(sx, sy, thumb_rect.width(), thumb_rect.height()),
            )
            painter.restore()

        # Text zone below thumbnail
        text_y = thumb_rect.bottom() + 6
        text_rect = QRect(
            rect.x() + _PAD, text_y,
            rect.width() - 2 * _PAD,
            rect.bottom() - text_y - _PAD,
        )

        # Scene name (elided to fit one line)
        painter.setPen(QPen(_TEXT))
        name_font = QFont(painter.font())
        name_font.setPointSize(10)
        name_font.setBold(True)
        painter.setFont(name_font)
        fm = QFontMetrics(name_font)
        elided_name = fm.elidedText(entry.name, Qt.ElideMiddle, text_rect.width())
        painter.drawText(
            text_rect.x(), text_rect.y() + fm.ascent(),
            elided_name,
        )

        # Duration + badges row
        line2_y = text_rect.y() + fm.height() + 4
        small_font = QFont(painter.font())
        small_font.setPointSize(8)
        small_font.setBold(False)
        painter.setFont(small_font)
        small_fm = QFontMetrics(small_font)

        # Duration — the real running time, probed by the thumbnail pass (same
        # mpv open) and cached. Shows the placeholder until that lands, then the
        # `ready` repaint swaps in the real time.
        painter.setPen(QPen(_TEXT_MUTED))
        duration = "—:—:—"
        dv = entry.default_video
        if self._thumbs is not None and dv is not None:
            secs = self._thumbs.duration_for(dv.path)
            if secs:
                duration = _fmt_card_duration(secs)
        painter.drawText(
            text_rect.x(), line2_y + small_fm.ascent(),
            duration,
        )

        # Device badges next to duration (same line)
        badge_x = text_rect.x() + small_fm.horizontalAdvance(duration) + 12
        badge_strings = [
            GENERATION_BADGES[g]
            for g in sorted(entry.supported_generations, key=lambda x: x.value)
        ]
        if entry.has_prostate:
            badge_strings.append("p•")
        for badge in badge_strings:
            w = small_fm.horizontalAdvance(badge)
            bg_rect = QRect(badge_x - 2, line2_y + 1, w + 4, small_fm.height() + 1)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(_BADGE_BG))
            painter.drawRoundedRect(bg_rect, 3, 3)
            painter.setPen(QPen(_TEXT))
            painter.drawText(badge_x, line2_y + small_fm.ascent(), badge)
            badge_x += w + 8

        # Content-type pills (line 3) — what the scene actually carries:
        # video / audio / funscript / forge. Same palette + outlined-translucent
        # look as the FunscriptForge library pills so the two apps read the same.
        line3_y = line2_y + small_fm.height() + 5
        content_pills: list[tuple[str, QColor]] = []
        if entry.videos:
            content_pills.append(("VIDEO", _PILL_VIDEO))
        if entry.audio_tracks:
            content_pills.append(("AUDIO", _PILL_AUDIO))
        if entry.funscript_sets or entry.bundle_path:
            content_pills.append(("FUNSCRIPT", _PILL_FUNSCRIPT))
        # FORGE — this scene came from a .forge bundle (authored package), not a
        # loose scanned folder. Distinguishes portable bundles at a glance.
        if entry.bundle_path:
            content_pills.append(("FORGE", _PILL_FORGE))
        pill_x = text_rect.x()
        pill_h = small_fm.height() + 2
        for label, color in content_pills:
            w = small_fm.horizontalAdvance(label)
            pill_w = w + 10
            pill_rect = QRect(pill_x, line3_y, pill_w, pill_h)
            fill = QColor(color); fill.setAlpha(0x26)
            border = QColor(color); border.setAlpha(0x66)
            painter.setPen(QPen(border))
            painter.setBrush(QBrush(fill))
            painter.drawRoundedRect(pill_rect, 3, 3)
            painter.setPen(QPen(color))
            painter.drawText(pill_x + 5, line3_y + small_fm.ascent() + 1, label)
            pill_x += pill_w + 5

        # Reveal-in-Explorer button (box with an NE arrow) — top-right corner.
        # Semi-opaque so it stays legible over a bright thumbnail. Click routed
        # through the panel's viewport event filter (see LibraryPanel.eventFilter).
        btn = _open_btn_rect(option.rect)
        btn_bg = QColor(_SURFACE)
        btn_bg.setAlpha(230)
        painter.setPen(QPen(_BORDER, 1))
        painter.setBrush(QBrush(btn_bg))
        painter.drawRoundedRect(btn, 4, 4)
        glyph = QColor(_ACCENT) if is_hover else QColor(_TEXT_MUTED)
        painter.setPen(QPen(glyph, 1.5))
        painter.setBrush(Qt.NoBrush)
        # a small "window" square, open toward the arrow…
        sq = QRect(btn.x() + 5, btn.y() + 9, 8, 8)
        painter.drawRoundedRect(sq, 1, 1)
        # …with a diagonal arrow escaping its top-right corner.
        tip = QPoint(btn.right() - 4, btn.y() + 5)
        painter.drawLine(QPoint(sq.center().x() + 1, sq.center().y() - 1), tip)
        painter.drawLine(tip, QPoint(tip.x() - 5, tip.y()))
        painter.drawLine(tip, QPoint(tip.x(), tip.y() + 5))

        # Corner affordances, left of the reveal button:
        #  • 📌 pin BUTTON when the scene has saved picks — clicking it re-opens
        #    the picker (change picks); clicking the tile body plays the pin.
        #  • "pick" indicator when the scene needs a choice and has no pin yet —
        #    a hint that tapping opens the picker (not itself a button).
        painter.setFont(small_font)
        if has_pin(entry):
            pin = _pin_btn_rect(option.rect)
            pin_bg = QColor(_SURFACE)
            pin_bg.setAlpha(230)
            painter.setPen(QPen(_BORDER, 1))
            painter.setBrush(QBrush(pin_bg))
            painter.drawRoundedRect(pin, 4, 4)
            painter.setPen(QPen(_ACCENT))
            painter.setBrush(Qt.NoBrush)
            painter.drawText(pin, Qt.AlignCenter, "📌")
        elif entry.is_ambiguous:
            painter.setPen(QPen(_AMBIGUOUS))
            tw = small_fm.horizontalAdvance("pick")
            painter.drawText(btn.left() - 6 - tw,
                             rect.y() + _PAD + small_fm.ascent(), "pick")

        painter.restore()


# ── Panel widget ──────────────────────────────────────────────────────────────

class LibraryPanel(QWidget):
    """Scene library view — root picker, search, filter chips, scene grid.

    Emits `scene_activated(SceneCatalogEntry)` when the user double-clicks
    or taps Enter on a scene card. Ambiguity + select-picker handling are
    the caller's concern (phase 2 of the UI slice).
    """

    scene_activated                = Signal(object)   # SceneCatalogEntry
    scene_change_picks_requested   = Signal(object)   # SceneCatalogEntry
    root_changed                   = Signal(str)      # absolute path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root: str = ""
        self._model = LibraryModel(self)
        self._build_ui()

    # ── Public API ──

    def set_root(self, path: str) -> None:
        """Point the library at a root folder and scan."""
        if not path:
            return
        self._root = os.path.abspath(path)
        self._root_label.setText(self._root)
        self._rescan()
        self.root_changed.emit(self._root)

    def rescan(self) -> None:
        """Trigger a rescan of the current root."""
        self._rescan()

    # ── UI construction ──

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 10, 12, 12)

        # Top toolbar: root picker + rescan + search
        top = QHBoxLayout()

        pick_btn = QPushButton("📁 Root…")
        pick_btn.setMinimumHeight(36)
        pick_btn.clicked.connect(self._pick_root)
        top.addWidget(pick_btn)

        self._root_label = QLabel("(no root selected)")
        self._root_label.setStyleSheet("color: #9ba3c4;")
        self._root_label.setMinimumWidth(200)
        top.addWidget(self._root_label, 1)

        rescan_btn = QPushButton("⟳ Rescan")
        rescan_btn.setMinimumHeight(36)
        rescan_btn.clicked.connect(self._rescan)
        top.addWidget(rescan_btn)

        search_label = QLabel("🔍")
        search_label.setStyleSheet("color: #9ba3c4; font-size: 14px;")
        top.addWidget(search_label)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter scenes by name…")
        self._search.setToolTip(
            "Type part of a scene name to narrow the card list below"
        )
        self._search.setMinimumWidth(240)
        self._search.setMinimumHeight(36)
        self._search.setStyleSheet(
            "QLineEdit { background: #1a1d27; border: 1px solid #2d3148; "
            "border-radius: 4px; padding: 4px 8px; color: #e0e0e0; } "
            "QLineEdit:focus { border-color: #ff6b30; }"
        )
        self._search.textChanged.connect(self._model.set_search)
        top.addWidget(self._search)

        layout.addLayout(top)

        # Filter chip row — content filters (the library is a haptic-scene
        # launcher by default; standalone videos are one click away).
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        self._chips: dict[LibraryFilter, QToolButton] = {}
        self._chip_labels: dict[LibraryFilter, str] = {
            LibraryFilter.ALL:             "All",
            LibraryFilter.WITH_FUNSCRIPTS: "Videos with Funscripts",
            LibraryFilter.VIDEOS:          "Videos",
        }
        for filter_val in (
            LibraryFilter.ALL,
            LibraryFilter.WITH_FUNSCRIPTS,
            LibraryFilter.VIDEOS,
        ):
            btn = QToolButton()
            btn.setText(self._chip_labels[filter_val])
            btn.setCheckable(True)
            btn.setMinimumHeight(32)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda _=False, f=filter_val: self._model.set_filter(f))
            chip_row.addWidget(btn)
            self._chips[filter_val] = btn
        self._chips[LibraryFilter.WITH_FUNSCRIPTS].setChecked(True)
        chip_row.addStretch()

        # Count label
        self._count_label = QLabel("0 scenes")
        self._count_label.setStyleSheet("color: #9ba3c4;")
        chip_row.addWidget(self._count_label)
        layout.addLayout(chip_row)

        # Lazy video-frame thumbnails. Generated paint-driven (only for cards
        # the user scrolls past) and cached to disk; a card repaints when its
        # frame becomes ready.
        self._thumbs = ThumbnailService(self)
        self._thumbs.ready.connect(self._on_thumbnail_ready)

        # Scene grid (virtualized)
        self._view = QListView()
        self._view.setModel(self._model)
        self._view.setItemDelegate(LibraryCardDelegate(self._thumbs, self._view))
        self._view.setViewMode(QListView.IconMode)
        self._view.setResizeMode(QListView.Adjust)
        self._view.setMovement(QListView.Static)
        self._view.setUniformItemSizes(True)
        self._view.setFlow(QListView.LeftToRight)
        self._view.setWrapping(True)
        self._view.setSpacing(0)
        self._view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._view.setMouseTracking(True)
        # Single-click activation — matches the touch / cockpit UX
        # expectation that one tap loads the scene. We DON'T also
        # connect `activated` (double-click + Enter) because that
        # would fire a second activation when the user double-clicks
        # out of habit, opening the picker modal twice. Keyboard Enter
        # support is dropped as part of this trade — re-add via a
        # KeyPressEvent override if it becomes important.
        self._view.clicked.connect(self._on_activated)
        self._view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_context_menu)
        # Intercept clicks on the per-card reveal-in-Explorer button before they
        # register as scene activations.
        self._view.viewport().installEventFilter(self)

        # Kinetic touch scroll. Without this, Qt treats touch events on the
        # viewport as item clicks rather than scroll gestures — drags select
        # cards instead of scrolling the grid, and tapping the scrollbar
        # often misses (touch tolerance vs. scrollbar's mouse-tuned width).
        # ``TouchGesture`` keeps mouse-wheel + scrollbar working as before;
        # touch drag now flicks the list with momentum.
        QScroller.grabGesture(
            self._view.viewport(),
            QScroller.ScrollerGestureType.TouchGesture,
        )

        # Dark scrollbar / list background
        self._view.setStyleSheet(
            "QListView { background: #0e1117; border: 1px solid #2d3148; "
            "border-radius: 6px; }"
        )

        # Stack: welcome empty-state ↔ scene grid. Shown on first-run / after
        # user clears the library. One action only — no thinking required.
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_welcome())  # index 0
        self._stack.addWidget(self._view)             # index 1
        layout.addWidget(self._stack, 1)

        # Refresh count + empty-state whenever model resets
        self._model.modelReset.connect(self._update_count)
        self._model.modelReset.connect(self._update_empty_state)
        self._update_empty_state()

    def _build_welcome(self) -> QWidget:
        """First-run empty state — one big CTA, nothing else."""
        w = QWidget()
        w.setStyleSheet("background: #0e1117;")
        v = QVBoxLayout(w)
        v.setContentsMargins(40, 40, 40, 40)
        v.addStretch()

        title = QLabel("Welcome to ForgePlayer")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf = QFont(title.font())
        tf.setPointSize(22)
        tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet("color: #e0e0e0;")
        v.addWidget(title)

        v.addSpacing(8)

        sub = QLabel("Point me at your media folder and I'll list your scenes.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: #9ba3c4; font-size: 14px;")
        v.addWidget(sub)

        v.addSpacing(32)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        big_scan = QPushButton("⬡  Scan a folder")
        big_scan.setMinimumHeight(56)
        big_scan.setMinimumWidth(240)
        big_scan.setStyleSheet(
            "QPushButton { background: #ff6b30; color: white; font-size: 16px; "
            "font-weight: bold; border-radius: 8px; padding: 0 20px; } "
            "QPushButton:hover { background: #ff8c5a; }"
        )
        big_scan.clicked.connect(self._pick_root)
        btn_row.addWidget(big_scan)
        btn_row.addStretch()
        v.addLayout(btn_row)

        v.addStretch()
        return w

    def _update_empty_state(self) -> None:
        """Swap between welcome and scene grid based on whether we have any
        scenes to show (not just filtered — total)."""
        has_scenes = len(self._model._all) > 0
        self._stack.setCurrentIndex(1 if has_scenes else 0)

    # ── Event handlers ──

    def _pick_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Pick library root folder", self._root or os.getcwd(),
        )
        if folder:
            self.set_root(folder)

    def _rescan(self) -> None:
        if not self._root or not os.path.isdir(self._root):
            self._model.load([])
            return
        scenes = scan_library_root(self._root)
        self._model.load(scenes)

    def _update_count(self) -> None:
        total = len(self._model._all)
        shown = self._model.rowCount()
        if shown == total:
            self._count_label.setText(f"{total} scenes")
        else:
            self._count_label.setText(f"{shown} of {total} scenes")
        # Each filter chip carries its own count so the split is visible at a
        # glance (e.g. "Videos with Funscripts (86)" vs "Videos (52)").
        for f, btn in self._chips.items():
            btn.setText(f"{self._chip_labels[f]}  ({self._model.count_for(f)})")

    def _on_thumbnail_ready(self, _video_path: str) -> None:
        """A lazily-grabbed frame finished — repaint the grid so the card
        that requested it swaps its placeholder for the frame. viewport
        update is cheap and Qt coalesces a burst of readys into one paint."""
        self._view.viewport().update()

    def eventFilter(self, obj, event) -> bool:
        """Hit-test a card's corner buttons on left-release. The reveal button
        opens the file location; the 📌 button re-opens the picker. Either
        CONSUMES the event so it doesn't also fire `clicked` → scene activation
        (a plain tile click still plays the saved pick)."""
        if obj is self._view.viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                pos = event.position().toPoint()
                index = self._view.indexAt(pos)
                if index.isValid():
                    entry = self._model.entry_at(index)
                    if entry is not None:
                        vrect = self._view.visualRect(index)
                        if _open_btn_rect(vrect).contains(pos):
                            self._reveal_in_explorer(entry)
                            return True
                        if has_pin(entry) and _pin_btn_rect(vrect).contains(pos):
                            self.scene_change_picks_requested.emit(entry)
                            return True
        return super().eventFilter(obj, event)

    def _reveal_in_explorer(self, entry: SceneCatalogEntry) -> None:
        """Open the OS file manager with the scene's primary file selected, so
        the user can see exactly what the recognizer grouped. Falls back to the
        scene folder when there's no concrete file (or on any failure)."""
        target = None
        dv = entry.default_video
        if dv is not None:
            target = dv.path
        elif entry.funscript_sets:
            fs = entry.funscript_sets[0]
            target = fs.main_path or next(iter(fs.channels.values()), None)
        elif entry.audio_tracks:
            target = entry.audio_tracks[0].path
        try:
            if target and os.path.isfile(target):
                # `explorer /select,<path>` reveals + highlights the file. It
                # returns a non-zero exit code even on success, so don't check.
                subprocess.run(["explorer", "/select,", os.path.normpath(target)])
                return
        except Exception:
            pass
        folder = entry.folder_path
        if folder and os.path.isdir(folder):
            try:
                os.startfile(folder)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _on_activated(self, index: QModelIndex) -> None:
        entry = self._model.entry_at(index)
        if entry is not None:
            self.scene_activated.emit(entry)

    def _on_context_menu(self, pos) -> None:
        index = self._view.indexAt(pos)
        entry = self._model.entry_at(index)
        if entry is None:
            return
        menu = QMenu(self)
        reveal_action = menu.addAction("⧉ Open file location")
        change_action = menu.addAction("↻ Change picks…")
        if not has_pin(entry):
            change_action.setEnabled(False)
            change_action.setToolTip(
                "No saved picks yet — the picker opens on first play."
            )
        chosen = menu.exec(self._view.viewport().mapToGlobal(pos))
        if chosen is reveal_action:
            self._reveal_in_explorer(entry)
        elif chosen is change_action:
            self.scene_change_picks_requested.emit(entry)
