# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""ClickableSlider — QSlider subclass that jumps to the clicked position.

Default QSlider steps by page-size on click. This variant jumps the handle
directly to the clicked pixel, matching the behaviour every video player
user expects from a seek bar.

Also emits `sliderReleased` after a single click so callers that already
wire `sliderPressed` / `sliderReleased` for scrubbing don't need a second
code path for click-to-seek.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider

# Amber ticks — same family as the FunscriptForge marker accent, and it
# reads over both the filled and unfilled groove without fighting the
# handle colour.
_MARKER_COLOR = QColor(255, 176, 71)


class ClickableSlider(QSlider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Marker positions as fractions (0..1) of the track. Painted as
        # thin vertical ticks over the groove so the user can see that
        # named jump points exist (authored in FunscriptForge). Empty =
        # nothing to draw.
        self._marker_fracs: list[float] = []

    def set_markers(self, fractions) -> None:
        """Replace the marker ticks. `fractions` are 0..1 track positions
        (marker_at_ms / duration_ms). Out-of-range values are clamped;
        None entries dropped."""
        self._marker_fracs = [
            max(0.0, min(1.0, float(f))) for f in fractions if f is not None
        ]
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if not self._marker_fracs:
            return
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt,
            QStyle.SubControl.SC_SliderGroove, self,
        )
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt,
            QStyle.SubControl.SC_SliderHandle, self,
        )
        painter = QPainter(self)
        pen = QPen(_MARKER_COLOR)
        pen.setWidth(2)
        painter.setPen(pen)
        if self.orientation() == Qt.Orientation.Horizontal:
            span = max(1, groove.width() - handle.width())
            x0 = groove.x() + handle.width() // 2
            y_top = max(0, groove.y() - 2)
            y_bot = min(self.height(), groove.y() + groove.height() + 2)
            for f in self._marker_fracs:
                x = x0 + int(span * f)
                painter.drawLine(x, y_top, x, y_bot)
        else:
            span = max(1, groove.height() - handle.height())
            y0 = groove.y() + handle.height() // 2
            x_left = max(0, groove.x() - 2)
            x_right = min(self.width(), groove.x() + groove.width() + 2)
            for f in self._marker_fracs:
                y = y0 + int(span * f)
                painter.drawLine(x_left, y, x_right, y)
        painter.end()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider,
                opt,
                QStyle.SubControl.SC_SliderHandle,
                self,
            )
            # If the user clicked directly on the handle, let Qt handle it
            # (so drag continues to work). Otherwise, jump.
            if not handle.contains(event.position().toPoint()):
                if self.orientation() == Qt.Orientation.Horizontal:
                    groove = self.style().subControlRect(
                        QStyle.ComplexControl.CC_Slider,
                        opt,
                        QStyle.SubControl.SC_SliderGroove,
                        self,
                    )
                    span = max(1, groove.width() - handle.width())
                    pos = int(event.position().x()) - groove.x() - handle.width() // 2
                    pos = max(0, min(span, pos))
                    value = self.minimum() + (self.maximum() - self.minimum()) * pos // span
                else:
                    groove = self.style().subControlRect(
                        QStyle.ComplexControl.CC_Slider,
                        opt,
                        QStyle.SubControl.SC_SliderGroove,
                        self,
                    )
                    span = max(1, groove.height() - handle.height())
                    pos = int(event.position().y()) - groove.y() - handle.height() // 2
                    pos = max(0, min(span, pos))
                    value = self.minimum() + (self.maximum() - self.minimum()) * pos // span
                self.setValue(value)
                self.sliderPressed.emit()
                self.sliderReleased.emit()
                event.accept()
                return
        super().mousePressEvent(event)
