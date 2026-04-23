# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Library panel — visual grid of scanned scenes.

Architecture (see `project_forgeplayer_folder_heuristics.md` for the full
4-stage library lifecycle):

- `LibraryModel`      — Qt model wrapping a list of `SceneCatalogEntry`,
                        plus filter + sort state. Feeds QListView.
- `LibraryCardDelegate` — paints one scene card (thumbnail placeholder,
                          name, device badges, ambiguity indicator).
- `LibraryPanel`      — composite widget: toolbar (root picker + search) +
                        virtualized QListView + filter chips.

The panel emits `scene_activated(entry)` when the user taps a card. Ambiguous
scenes will eventually route through a select-picker overlay before loading;
for alpha the signal just fires and the caller decides.

No thumbnails / duration yet — those need ffprobe + caching (polish pass).
For now cards show a filled placeholder rectangle and "—:—:—" duration.
"""

from __future__ import annotations

import os
from enum import Enum

from PySide6.QtCore import (
    QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QPainter, QPalette, QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListView, QPushButton, QStackedWidget, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QToolButton, QVBoxLayout, QWidget,
)

from app.library import (
    SceneCatalogEntry,
    scan_library_root,
)
from app.library.channels import GENERATION_BADGES, DeviceGeneration


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


# Card geometry — generous for touch but still grid-dense
_CARD_W  = 240
_CARD_H  = 210
_THUMB_H = 130
_PAD     = 12


class LibraryFilter(str, Enum):
    """Which filter chip is currently active in the Library toolbar."""
    ALL       = "all"
    RECENT    = "recent"
    FAVORITES = "favorites"
    WITH_PRESET = "with_preset"
    PLAYLISTS = "playlists"


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
        self._filter: LibraryFilter = LibraryFilter.ALL

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
            if self._filter == LibraryFilter.WITH_PRESET and entry.preset_path is None:
                continue
            # RECENT / FAVORITES / PLAYLISTS are Phase 2 — alpha shows "ALL"
            # when those filters are picked, until the data model exists.
            out.append(entry)
        out.sort(key=lambda e: e.name.lower())
        self._visible = out


# ── Delegate ──────────────────────────────────────────────────────────────────

class LibraryCardDelegate(QStyledItemDelegate):
    """Paints one scene card.

    Layout (top-to-bottom inside the card's inner rect):

        [     thumbnail placeholder     ]     ← _THUMB_H tall
        {scene name — 1 line, elided}
        {duration placeholder · badges}
        {ambiguity indicator if needed}
    """

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

        # Thumbnail placeholder
        thumb_rect = QRect(rect.x() + _PAD, rect.y() + _PAD,
                           rect.width() - 2 * _PAD, _THUMB_H)
        painter.setBrush(QBrush(_BG))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(thumb_rect, 4, 4)

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

        # Duration placeholder (lazy ffprobe later)
        painter.setPen(QPen(_TEXT_MUTED))
        duration = "—:—:—"
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

        # Ambiguity indicator (if applicable) — top-right corner of card
        if entry.is_ambiguous:
            painter.setPen(QPen(_AMBIGUOUS))
            painter.setFont(small_font)
            tag = "pick"
            tw = small_fm.horizontalAdvance(tag)
            tag_x = rect.right() - _PAD - tw
            tag_y = rect.y() + _PAD + small_fm.ascent()
            painter.drawText(tag_x, tag_y, tag)

        painter.restore()


# ── Panel widget ──────────────────────────────────────────────────────────────

class LibraryPanel(QWidget):
    """Scene library view — root picker, search, filter chips, scene grid.

    Emits `scene_activated(SceneCatalogEntry)` when the user double-clicks
    or taps Enter on a scene card. Ambiguity + select-picker handling are
    the caller's concern (phase 2 of the UI slice).
    """

    scene_activated = Signal(object)   # SceneCatalogEntry
    root_changed    = Signal(str)      # absolute path

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

        # Filter chip row
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        self._chips: dict[LibraryFilter, QToolButton] = {}
        for label, filter_val in [
            ("All",         LibraryFilter.ALL),
            ("Recent",      LibraryFilter.RECENT),
            ("Favorites",   LibraryFilter.FAVORITES),
            ("With preset", LibraryFilter.WITH_PRESET),
            ("Playlists",   LibraryFilter.PLAYLISTS),
        ]:
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(32)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda _=False, f=filter_val: self._model.set_filter(f))
            chip_row.addWidget(btn)
            self._chips[filter_val] = btn
        self._chips[LibraryFilter.ALL].setChecked(True)
        chip_row.addStretch()

        # Count label
        self._count_label = QLabel("0 scenes")
        self._count_label.setStyleSheet("color: #9ba3c4;")
        chip_row.addWidget(self._count_label)
        layout.addLayout(chip_row)

        # Scene grid (virtualized)
        self._view = QListView()
        self._view.setModel(self._model)
        self._view.setItemDelegate(LibraryCardDelegate(self._view))
        self._view.setViewMode(QListView.IconMode)
        self._view.setResizeMode(QListView.Adjust)
        self._view.setMovement(QListView.Static)
        self._view.setUniformItemSizes(True)
        self._view.setFlow(QListView.LeftToRight)
        self._view.setWrapping(True)
        self._view.setSpacing(0)
        self._view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._view.setMouseTracking(True)
        self._view.doubleClicked.connect(self._on_activated)
        self._view.activated.connect(self._on_activated)  # Enter key

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

    def _on_activated(self, index: QModelIndex) -> None:
        entry = self._model.entry_at(index)
        if entry is not None:
            self.scene_activated.emit(entry)
