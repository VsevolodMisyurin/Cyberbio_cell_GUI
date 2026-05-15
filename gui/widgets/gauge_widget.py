"""
gui/widgets/gauge_widget.py

Analogue-style gauge.

Layout: dial on top (more vertical space), selector combo below.
- No combo above the dial — saves space.
- Dial geometry: centre shifted slightly lower, more room for scale labels.
- Combo below acts as both selector and label.
"""

from __future__ import annotations
import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QSizePolicy
from PyQt6.QtCore    import Qt, QRectF
from PyQt6.QtGui     import QPainter, QColor, QPen, QFont, QBrush

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import BG_PANEL, ACCENT, DANGER, TEXT_PRIMARY, TEXT_MUTED, BORDER


class GaugeDial(QWidget):
    _MIN, _MAX  = -3.0, 3.0
    _START_DEG  = 220     # slightly narrower sweep so scale labels fit
    _SPAN_DEG   = 260

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = -3.0
        self.setFixedSize(148, 118)

    def set_value(self, v: float):
        self._value = max(self._MIN, min(self._MAX, v))
        self.update()

    def paintEvent(self, _event):
        p  = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Centre a bit lower than mid to give room for top scale labels
        cx = w // 2
        cy = int(h * 0.62)
        r  = int(min(w, h) * 0.38)

        # Background arc
        p.setPen(QPen(QColor(BORDER), 6))
        p.drawArc(QRectF(cx-r, cy-r, 2*r, 2*r),
                  self._START_DEG * 16, -self._SPAN_DEG * 16)

        # Fill arc
        frac   = (self._value - self._MIN) / (self._MAX - self._MIN)
        filled = int(frac * self._SPAN_DEG)
        p.setPen(QPen(QColor(ACCENT) if self._value < 0 else QColor(DANGER), 6))
        p.drawArc(QRectF(cx-r, cy-r, 2*r, 2*r),
                  self._START_DEG * 16, -filled * 16)

        # Needle
        nd  = self._START_DEG - frac * self._SPAN_DEG
        rad = math.radians(nd)
        nx  = cx + int((r-10) * math.cos(rad))
        ny  = cy - int((r-10) * math.sin(rad))
        p.setPen(QPen(QColor(TEXT_PRIMARY), 2))
        p.drawLine(cx, cy, nx, ny)

        # Centre dot
        p.setBrush(QBrush(QColor(TEXT_PRIMARY))); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx-4, cy-4, 8, 8)

        # Value label — below centre (more space)
        font = QFont("Consolas", 9)
        p.setFont(font); p.setPen(QPen(QColor(TEXT_MUTED)))
        p.drawText(0, h-18, w, 18, Qt.AlignmentFlag.AlignCenter,
                   f"{self._value:+.2f} σ")

        # Scale labels — placed slightly further out so they're not clipped
        font.setPointSize(7); p.setFont(font)
        for sigma, label in [(-3, "-3"), (0, "0"), (3, "+3")]:
            fs  = (sigma - self._MIN) / (self._MAX - self._MIN)
            ds  = self._START_DEG - fs * self._SPAN_DEG
            rs  = math.radians(ds)
            lx  = cx + int((r+14) * math.cos(rs)) - 9
            ly  = cy - int((r+14) * math.sin(rs)) - 7
            p.drawText(lx, ly, 18, 14, Qt.AlignmentFlag.AlignCenter, label)
        p.end()


class GaugeWidget(QWidget):
    """
    Gauge dial + selector combo BELOW the dial.
    The combo serves as both label (shows current selection) and dropdown
    selector.  No separate header combo above the dial.
    """

    def __init__(self, choices: list, parent=None):
        super().__init__(parent)
        self.setFixedWidth(160)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 4)
        lay.setSpacing(2)

        self._dial = GaugeDial()
        lay.addWidget(self._dial, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._combo = QComboBox()
        self._combo.addItems(choices)
        self._combo.setStyleSheet(
            f"background:{BG_PANEL}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; font-size:10px;"
        )
        self._combo.currentTextChanged.connect(self._on_select)
        lay.addWidget(self._combo)

        self._data: dict = {}
        self._selected = choices[0] if choices else ""

    def update_data(self, data: dict):
        self._data = data
        self._refresh()

    def update_choices(self, choices: list):
        cur = self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(choices)
        if cur in choices: self._combo.setCurrentText(cur)
        self._combo.blockSignals(False)
        self._selected = self._combo.currentText()
        self._refresh()

    def _on_select(self, name: str):
        self._selected = name
        self._refresh()

    def _refresh(self):
        self._dial.set_value(self._data.get(self._selected, -3.0))
