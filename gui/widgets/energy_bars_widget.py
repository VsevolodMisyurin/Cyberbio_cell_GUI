"""
gui/widgets/energy_bars_widget.py

Compact widget showing energy level for up to 5 genomes.
Each genome gets one slim horizontal bar (like FoodBarH) in its genome colour.
Range: −3 σ … +3 σ.  Gradient: red (low) → amber → green (high).
Height per bar: ~22 px.  Total widget height ≤ ~120 px for 5 bars.
"""

from __future__ import annotations
import math
from typing import Dict, List, Tuple

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import (
    QPainter, QColor, QLinearGradient, QBrush, QPen, QFont,
)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    ACCENT, DANGER, BORDER, TEXT_PRIMARY, TEXT_MUTED,
    BG_PANEL, genome_color,
)

_MIN, _MAX = -3.0, 3.0
_BAR_H     = 18    # height of each bar strip (px)
_PAD_V     = 3     # vertical gap between bars


class EnergyBarsWidget(QWidget):
    """
    Up to 5 horizontal energy bars, one per genome.
    Each bar is coloured in the genome's colour and shows its energy σ value.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Each entry: (gid, energy_sigma)
        self._data: List[Tuple[int, float]] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._update_height()

    def set_data(self, populations: Dict[int, Tuple[int, float]],
                 top_gids: List[int]):
        """
        populations : {gid: (cell_count, energy)}
        top_gids    : ordered list of gids to display (top-5 by count)
        """
        self._data = [
            (gid, populations[gid][1])
            for gid in top_gids
            if gid in populations
        ]
        self._update_height()
        self.update()

    def _update_height(self):
        n = max(len(self._data), 1)
        self.setFixedHeight(n * (_BAR_H + _PAD_V) + _PAD_V)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.fillRect(self.rect(), QColor(BG_PANEL))

        if not self._data:
            p.setPen(QPen(QColor(TEXT_MUTED)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "—")
            p.end()
            return

        font = QFont("Consolas", 7)
        p.setFont(font)

        # Label column width (e.g. "G0 ")
        lbl_w = 22

        for i, (gid, energy) in enumerate(self._data):
            y = _PAD_V + i * (_BAR_H + _PAD_V)
            bar_x = lbl_w
            bar_w = w - lbl_w - 2

            # Genome label
            g_color = QColor(genome_color(gid))
            p.setPen(QPen(g_color))
            p.drawText(0, y, lbl_w, _BAR_H, Qt.AlignmentFlag.AlignCenter, f"G{gid}")

            # Background track
            p.setBrush(QBrush(QColor(BORDER)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(bar_x, y, bar_w, _BAR_H, 3, 3)

            # Fill level
            frac   = (energy - _MIN) / (_MAX - _MIN)
            frac   = max(0.0, min(1.0, frac))
            fill_w = int(bar_w * frac)

            # Gradient in genome colour tones: dark→full colour
            grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            dark = QColor(g_color); dark.setAlpha(80)
            grad.setColorAt(0.0, dark)
            grad.setColorAt(1.0, g_color)
            p.setBrush(QBrush(grad))
            if fill_w > 0:
                p.drawRoundedRect(bar_x, y, fill_w, _BAR_H, 3, 3)

            # Centre tick (0 σ)
            mid_x = bar_x + bar_w // 2
            p.setPen(QPen(QColor("#555555"), 1, Qt.PenStyle.DotLine))
            p.drawLine(mid_x, y + 2, mid_x, y + _BAR_H - 2)

            # Value text
            p.setPen(QPen(QColor(TEXT_PRIMARY)))
            val_str = f"{energy:+.2f}σ"
            p.drawText(bar_x, y, bar_w, _BAR_H,
                       Qt.AlignmentFlag.AlignCenter, val_str)

        p.end()
