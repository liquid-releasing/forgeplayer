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
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class ClickableSlider(QSlider):
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
