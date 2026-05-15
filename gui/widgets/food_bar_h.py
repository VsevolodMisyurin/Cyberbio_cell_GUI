"""
gui/widgets/food_bar_h.py

Thin horizontal food-level bar for the top info strip.
Range: −3 σ … +3 σ.  Gradient: red → amber → green.
"""

from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QPainter, QColor, QLinearGradient, QBrush, QPen

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import ACCENT, DANGER, BORDER, TEXT_PRIMARY, TEXT_MUTED


class FoodBarH(QWidget):
    """Slim horizontal bar for Food level."""
    _MIN, _MAX = -3.0, 3.0

    def __init__(self, height: int = 18, parent=None):
        super().__init__(parent)
        self._value  = -3.0
        self._bar_h  = height
        self.setFixedHeight(height + 2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, v: float):
        self._value = max(self._MIN, min(self._MAX, v))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bar_h = h - 2
        pad   = 2

        # Background track
        p.setBrush(QBrush(QColor(BORDER)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, pad, w, bar_h, 3, 3)

        # Fill
        frac   = (self._value - self._MIN) / (self._MAX - self._MIN)
        fill_w = int(w * frac)

        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(DANGER))
        grad.setColorAt(0.5, QColor("#d29922"))
        grad.setColorAt(1.0, QColor(ACCENT))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(0, pad, fill_w, bar_h, 3, 3)

        # Centre tick (0 σ)
        mid_x = w // 2
        p.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DotLine))
        p.drawLine(mid_x, pad + 2, mid_x, pad + bar_h - 2)

        # Value text
        font = p.font(); font.setPointSize(8); p.setFont(font)
        p.setPen(QPen(QColor(TEXT_PRIMARY)))
        p.drawText(0, 0, w, h,
                   Qt.AlignmentFlag.AlignCenter,
                   f"Food {self._value:+.2f}σ")
        p.end()
