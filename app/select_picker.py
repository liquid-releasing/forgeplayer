# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""SelectPicker — modal dialog for ambiguous scenes.

Appears when the user taps a scene card and the scanner flagged it as
ambiguous (`SceneCatalogEntry.is_ambiguous`). Shows only the radio groups
that correspond to `needs_*_choice` flags that are True — hiding groups
that the player can decide automatically (resolution by wall config,
aspect by wall type, etc.).

Returns a `SelectionChoices` dataclass with the user's picks. The caller
is responsible for persistence (writing `{stem}.forgeplayer.json`) and
for handing the chosen files to the playback engine.

Two buttons — `Play once` (doesn't persist) vs `Save & Play` (persists).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.library.catalog import (
    AudioVariant,
    FunscriptSet,
    SceneCatalogEntry,
    SubtitleTrack,
    VideoVariant,
)


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class SelectionChoices:
    """The user's choices captured from the picker.

    Any field set to None means the user didn't pick (or there was nothing
    to pick). The caller should fall back to the scene's `default_*` for
    that slot when None.

    Persistence is always-on since 2026-04-24 (pin persistence design in
    ``memory/project_forgeplayer_pin_persistence.md``): the caller always
    writes a pin file after the picker accepts. The old ``save_as_preset``
    flag was removed — there's no "play once" mode.
    """
    video: VideoVariant | None = None
    audio: AudioVariant | None = None
    funscript_set: FunscriptSet | None = None
    subtitle: SubtitleTrack | None = None


# ── Theme (matches library_panel palette) ────────────────────────────────────

_ACCENT = "#ff6b30"
_TEXT_MUTED = "#9ba3c4"


# Funscript sets whose base stem ends with one of these are per-toy renders
# (a FunscriptForge "station" output for a specific physical device), not the
# e-stim/haptic-audio set ForgePlayer actually plays. We hide them from the
# picker for now — ForgePlayer drives audio-based stim, not these toys. ("yet":
# routing to them is a later phase.)
_DEVICE_TARGET_SUFFIXES = frozenset({
    "handy", "lovense", "ossm", "osr2", "sr6", "vacuglide",
    "keon", "launch", "kiiroo", "max", "edge",
})


def _is_device_target(fset: FunscriptSet) -> bool:
    """True when this set is a per-toy render (…stem.handy / .lovense / …),
    not the e-stim set."""
    tail = fset.base_stem.rsplit(".", 1)
    return len(tail) == 2 and tail[1].lower() in _DEVICE_TARGET_SUFFIXES


# ── Dialog ───────────────────────────────────────────────────────────────────

class SelectPicker(QDialog):
    """Modal dialog composed of applicable radio-button groups.

    Construction:
        picker = SelectPicker(entry, parent)
        if picker.exec() == QDialog.Accepted:
            choices = picker.choices()
            # Use choices.video / .audio / .funscript_set / .subtitle
            if choices.save_as_preset:
                write_pin_json(...)
    """

    def __init__(
        self,
        entry: SceneCatalogEntry,
        parent=None,
        *,
        preselect: SelectionChoices | None = None,
        change_mode: bool = False,
    ) -> None:
        """*preselect*: pre-check the radios matching the fields of this
        existing SelectionChoices (used by "Change picks" to show the
        user's current pins as the starting state).

        *change_mode*: swap the title to "Change picks" for clarity when
        the picker is re-opened from a pinned scene.
        """
        super().__init__(parent)
        self._entry = entry
        self._preselect = preselect

        # Track radio-group state so choices() can read them after accept
        self._video_group: QButtonGroup | None = None
        self._audio_group: QButtonGroup | None = None
        self._funscript_group: QButtonGroup | None = None
        self._subtitle_group: QButtonGroup | None = None

        # Index-per-group → VideoVariant / AudioVariant / FunscriptSet / None
        self._video_map: dict[int, VideoVariant] = {}
        self._audio_map: dict[int, AudioVariant] = {}
        self._funscript_map: dict[int, FunscriptSet] = {}
        self._subtitle_map: dict[int, SubtitleTrack | None] = {}

        if change_mode:
            self.setWindowTitle(f"Change picks — {entry.name}")
        else:
            self.setWindowTitle(f"Pick options — {entry.name}")
        self.setMinimumWidth(520)
        self._build_ui()

    # ── Public API ──

    def choices(self) -> SelectionChoices:
        """Read the current radio state into a SelectionChoices dataclass.
        Call after `exec()` returns Accepted."""
        out = SelectionChoices()

        if self._video_group is not None and self._video_group.checkedId() >= 0:
            out.video = self._video_map.get(self._video_group.checkedId())
        else:
            out.video = self._entry.default_video

        if self._audio_group is not None and self._audio_group.checkedId() >= 0:
            out.audio = self._audio_map.get(self._audio_group.checkedId())
        else:
            out.audio = self._entry.default_audio

        if self._funscript_group is not None and self._funscript_group.checkedId() >= 0:
            out.funscript_set = self._funscript_map.get(self._funscript_group.checkedId())
        else:
            out.funscript_set = self._entry.default_funscript_set

        if self._subtitle_group is not None and self._subtitle_group.checkedId() >= 0:
            out.subtitle = self._subtitle_map.get(self._subtitle_group.checkedId())
        # else out.subtitle stays None (no subtitles available or user didn't pick)

        return out

    # ── UI construction ──

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setStyleSheet("background: #1a1d27; border-bottom: 1px solid #2d3148;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel(self._entry.name)
        title_font = QFont(title.font())
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title)

        sub = QLabel("Pick what to play for this scene:")
        sub.setStyleSheet(f"color: {_TEXT_MUTED};")
        header_layout.addWidget(sub)
        root.addWidget(header)

        # Body — scrollable in case many subtitle tracks etc.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(14)

        # Always-on "what will play" summary so the dialog is never blank and
        # the user can see which video + stim source is actually selected —
        # even when nothing is ambiguous (the common case for a single-variant
        # scene, where every group below is hidden). Answers the dogfood
        # report: "the UI doesn't say which one it picked."
        body_layout.addWidget(self._build_summary())

        # Only offer a funscript-set choice among real e-stim sets — hide the
        # per-toy renders (.handy/.lovense/…). If that leaves a single set,
        # there's nothing to choose, so the group is skipped entirely.
        estim_sets = [
            fs for fs in self._entry.funscript_sets if not _is_device_target(fs)
        ]
        if len(estim_sets) > 1:
            body_layout.addWidget(self._build_funscript_group(estim_sets))
        if self._entry.needs_video_choice:
            body_layout.addWidget(self._build_video_group())
        if self._entry.needs_audio_choice:
            body_layout.addWidget(self._build_audio_group())
        if self._entry.needs_subtitle_choice:
            body_layout.addWidget(self._build_subtitle_group())

        # Generation-variant indicator (informational for now — phase 2 will
        # add a proper per-channel picker).
        if self._entry.needs_generation_variant_choice:
            note = QLabel(
                "⚠ This scene has device-generation variants "
                "(-stereostim / -foc-stim / -2b). Alpha uses the default "
                "plain channels; explicit variant routing is a later phase."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #eab308; background: #2a2313; "
                              "padding: 8px; border-radius: 4px;")
            body_layout.addWidget(note)

        body_layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Button row
        footer = QFrame()
        footer.setStyleSheet("background: #1a1d27; border-top: 1px solid #2d3148;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 12, 20, 12)
        footer_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumWidth(100)
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(btn_cancel)

        # Single Play button — picks are auto-saved on accept. The old
        # Play once / Save & Play split was replaced 2026-04-24 per the
        # pin-persistence redesign (no user choice to make).
        btn_play = QPushButton("Play")
        btn_play.setMinimumWidth(130)
        btn_play.setMinimumHeight(36)
        btn_play.setStyleSheet(
            f"background: {_ACCENT}; color: white; font-weight: bold; "
            f"border-radius: 4px;"
        )
        btn_play.clicked.connect(self.accept)
        footer_layout.addWidget(btn_play)

        root.addWidget(footer)

    # ── Summary ──

    def _build_summary(self) -> QWidget:
        """Read-only 'what will play' — the resolved default selections. Makes
        the picker self-explanatory even when there's nothing to choose."""
        box = _group_box("What will play")
        layout = box.layout()

        def _row(label: str, value: str, *, warn: bool = False) -> None:
            r = QLabel(f"{label}:  {value}")
            r.setWordWrap(True)
            r.setStyleSheet(
                "color: #eab308;" if warn else f"color: {_TEXT_MUTED};"
            )
            layout.addWidget(r)

        v = self._entry.default_video
        _row("Video", v.filename if v else "(none)")

        # Stim source: sound preference plays a stim audio file; otherwise the
        # funscript set synthesises. None of either → the stim is missing
        # (commonly because it's still inside a .forge / .output bundle the
        # library scan doesn't unpack).
        a = self._entry.default_audio
        fs = self._entry.default_funscript_set
        if a is not None:
            _row("Stim", f"{Path(a.path).name}")
        elif fs is not None:
            chans = len(fs.channels) + (1 if fs.main_path else 0)
            _row("Stim", f"{fs.base_stem}  ({chans} funscript channels)")
        else:
            _row(
                "Stim",
                "(none found in this folder — open the .forge bundle directly "
                "to play its stim)",
                warn=True,
            )

        if self._entry.has_prostate:
            _row("Prostate", "available")

        return box

    # ── Radio group builders ──

    def _build_funscript_group(self, sets: list[FunscriptSet]) -> QWidget:
        """Funscript edit-variants (Magik-style). *sets* is the already-filtered
        list of e-stim sets to offer (per-toy renders excluded by the caller)."""
        box = _group_box("Funscript set")
        layout = box.layout()

        self._funscript_group = QButtonGroup(self)
        preselect_stem = (
            self._preselect.funscript_set.base_stem
            if self._preselect and self._preselect.funscript_set
            else None
        )
        for i, fset in enumerate(sets):
            label = fset.base_stem
            detail_bits: list[str] = []
            if fset.channels:
                detail_bits.append(f"{len(fset.channels)} channels")
            if fset.has_prostate:
                detail_bits.append("prostate")
            if fset.has_generation_variants:
                detail_bits.append("gen-variants")
            if detail_bits:
                label += f"  ({', '.join(detail_bits)})"

            rb = QRadioButton(label)
            rb.setMinimumHeight(28)
            if preselect_stem is not None:
                rb.setChecked(fset.base_stem == preselect_stem)
            elif i == 0:
                rb.setChecked(True)
            self._funscript_group.addButton(rb, i)
            self._funscript_map[i] = fset
            layout.addWidget(rb)

        return box

    def _build_video_group(self) -> QWidget:
        box = _group_box("Video variant")
        layout = box.layout()

        self._video_group = QButtonGroup(self)
        preselect_path = (
            self._preselect.video.path
            if self._preselect and self._preselect.video
            else None
        )
        for i, v in enumerate(self._entry.videos):
            label = v.filename
            detail_bits: list[str] = []
            if v.is_upscaled:
                upscalers = v.tags & {"iris", "chf", "topaz", "rhea", "proteus", "nyx"}
                if upscalers:
                    detail_bits.append(f"upscaled ({', '.join(sorted(upscalers))})")
                else:
                    detail_bits.append("upscaled")
            if v.is_aspect_variant:
                detail_bits.append("aspect variant")
            if not detail_bits:
                detail_bits.append("original")
            label += f"  ({', '.join(detail_bits)})"

            rb = QRadioButton(label)
            rb.setMinimumHeight(28)
            if preselect_path is not None:
                rb.setChecked(v.path == preselect_path)
            elif i == 0:
                rb.setChecked(True)
            self._video_group.addButton(rb, i)
            self._video_map[i] = v
            layout.addWidget(rb)

        return box

    def _build_audio_group(self) -> QWidget:
        # "Stim audio" — the picked track routes to the haptic device (the
        # USB dongle in a typical baseline setup), NOT a scene-audio override.
        # See project_forgeplayer_multichannel_audio.md for the routing model.
        box = _group_box("Stim audio")
        layout = box.layout()

        self._audio_group = QButtonGroup(self)
        preselect_path = (
            self._preselect.audio.path
            if self._preselect and self._preselect.audio
            else None
        )
        for i, a in enumerate(self._entry.audio_tracks):
            label = a.filename
            if a.stem_matches_main_video:
                label += "  (matched)"
            elif a.descriptor:
                label += f"  (alt: {a.descriptor})"
            else:
                label += "  (alternate)"

            rb = QRadioButton(label)
            rb.setMinimumHeight(28)
            if preselect_path is not None:
                rb.setChecked(a.path == preselect_path)
            elif i == 0:
                rb.setChecked(True)
            self._audio_group.addButton(rb, i)
            self._audio_map[i] = a
            layout.addWidget(rb)

        return box

    def _build_subtitle_group(self) -> QWidget:
        box = _group_box("Subtitles")
        layout = box.layout()

        self._subtitle_group = QButtonGroup(self)
        preselect_path = (
            self._preselect.subtitle.path
            if self._preselect and self._preselect.subtitle
            else None
        )

        # None option first, default-selected unless the preselect specifies
        # a subtitle (see docs/architecture — user opts in explicitly).
        rb_none = QRadioButton("None")
        rb_none.setMinimumHeight(28)
        rb_none.setChecked(preselect_path is None)
        self._subtitle_group.addButton(rb_none, 0)
        self._subtitle_map[0] = None
        layout.addWidget(rb_none)

        for i, sub in enumerate(self._entry.subtitles, start=1):
            label = f"{sub.language.upper()}" if sub.language != "unknown" else sub.filename
            label += f"  ({Path(sub.path).name})"
            rb = QRadioButton(label)
            rb.setMinimumHeight(28)
            if preselect_path is not None:
                rb.setChecked(sub.path == preselect_path)
            self._subtitle_group.addButton(rb, i)
            self._subtitle_map[i] = sub
            layout.addWidget(rb)

        return box



# ── Helpers ──────────────────────────────────────────────────────────────────

def _group_box(title: str) -> QWidget:
    """Titled container for a radio group — 'Funscript set', 'Video variant', etc."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)

    label = QLabel(title)
    f = QFont(label.font())
    f.setPointSize(10)
    f.setBold(True)
    label.setFont(f)
    v.addWidget(label)

    # Spacer line
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setStyleSheet("color: #2d3148;")
    v.addWidget(line)

    return w
