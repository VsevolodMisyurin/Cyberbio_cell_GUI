"""
gui/widgets/food_widget.py

Simple vertical bar showing Food level in [-3, +3] σ range.
Looks like a liquid level meter.  Drawn with QPainter.
"""

from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QPainter, QColor, QBrush, QPen, QLinearGradient

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import BG_PANEL, ACCENT, BORDER, TEXT_PRIMARY, TEXT_MUTED, DANGER


class FoodBar(QWidget):
    """Single vertical bar for food level."""
    _MIN, _MAX = -3.0, 3.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = -3.0
        self.setMinimumSize(60, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_value(self, v: float):
        self._value = max(self._MIN, min(self._MAX, v))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad  = 8
        bar_w = w - 2 * pad
        bar_h = h - 30   # leave room for labels

        # Background track
        p.setBrush(QBrush(QColor(BORDER)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(pad, 10, bar_w, bar_h, 4, 4)

        # Fill level
        frac   = (self._value - self._MIN) / (self._MAX - self._MIN)
        fill_h = int(bar_h * frac)
        fill_y = 10 + bar_h - fill_h

        # Gradient: red (low) → green (high)
        grad = QLinearGradient(0, 10 + bar_h, 0, 10)
        grad.setColorAt(0.0, QColor(DANGER))
        grad.setColorAt(0.5, QColor("#d29922"))
        grad.setColorAt(1.0, QColor(ACCENT))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(pad, fill_y, bar_w, fill_h, 4, 4)

        # Border
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawRoundedRect(pad, 10, bar_w, bar_h, 4, 4)

        # Scale lines
        p.setPen(QPen(QColor(TEXT_MUTED), 1))
        font = p.font(); font.setPointSize(7); p.setFont(font)
        for sigma, label in [(-3, "-3"), (0, "0"), (3, "+3")]:
            frac_s = (sigma - self._MIN) / (self._MAX - self._MIN)
            y = int(10 + bar_h * (1.0 - frac_s))
            p.drawLine(pad, y, pad + bar_w, y)
            p.drawText(0, y - 6, w, 12, Qt.AlignmentFlag.AlignCenter, label)

        # Value label at bottom
        p.setPen(QPen(QColor(TEXT_PRIMARY)))
        font.setPointSize(9); p.setFont(font)
        p.drawText(0, h - 18, w, 18,
                   Qt.AlignmentFlag.AlignCenter,
                   f"{self._value:+.2f}σ")
        p.end()


class FoodWidget(QWidget):
    """Food bar + title label."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)

        title = QLabel("🍃 Food")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;font-weight:bold;")
        lay.addWidget(title)

        self._bar = FoodBar()
        lay.addWidget(self._bar, stretch=1)

    def set_value(self, v: float):
        self._bar.set_value(v)
