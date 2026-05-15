"""
gui/widgets/population_widget.py

Vertical bar chart showing current cell counts per genome.
Up to 5 genomes can be selected for display.
Bar colour matches the genome's colour on the field.
"""

from __future__ import annotations
import math
from typing import Dict, List, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QButtonGroup,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui  import QPainter, QColor, QBrush, QPen, QFont

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import BG_PANEL, BORDER, TEXT_PRIMARY, TEXT_MUTED, genome_color


class PopBars(QWidget):
    """The actual drawing canvas."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(55)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._data: List[Tuple[int, int]] = []   # [(genome_id, count), ...]
        self._max_count = 1

    def set_data(self, data: List[Tuple[int, int]]):
        self._data = data
        self._max_count = max((c for _, c in data), default=1) or 1
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(BG_PANEL))

        if not self._data:
            p.setPen(QPen(QColor(TEXT_MUTED)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No genomes")
            p.end()
            return

        n       = len(self._data)
        pad     = 6
        lbl_h   = 16
        draw_h  = h - pad - lbl_h
        slot_w  = (w - 2 * pad) // n
        bar_w   = max(8, slot_w - 6)
        font = QFont("Consolas", 7)
        p.setFont(font)

        for i, (gid, count) in enumerate(self._data):
            frac  = count / self._max_count
            bar_h = int(draw_h * frac)
            x     = pad + i * slot_w + (slot_w - bar_w) // 2
            y     = pad + draw_h - bar_h

            color = QColor(genome_color(gid))
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, max(pad, y), bar_w, max(2, bar_h), 3, 3)

            p.setPen(QPen(QColor(TEXT_PRIMARY)))
            p.drawText(x - 4, max(0, y - 13), bar_w + 8, 13,
                       Qt.AlignmentFlag.AlignCenter, str(count))

            # genome id label below
            p.setPen(QPen(QColor(TEXT_MUTED)))
            p.drawText(x - 4, h - lbl_h + 2, bar_w + 8, lbl_h - 2,
                       Qt.AlignmentFlag.AlignCenter, f"G{gid}")

        p.end()


class PopulationWidget(QWidget):
    """
    Bar chart + 5 genome selector buttons.
    Buttons are coloured by genome colour, enabled only for live genomes.
    """
    MAX_DISPLAY = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._live: Dict[int, int] = {}     # gid → count
        self._selected: List[int] = []      # which gids to show
        self._btn_map: Dict[int, QPushButton] = {}   # slot index → button

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)

        self._bars = PopBars()
        lay.addWidget(self._bars, stretch=1)

        # 5 selector buttons
        btn_col = QVBoxLayout()
        btn_col.setSpacing(3)
        lbl = QLabel("Show:")
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
        btn_col.addWidget(lbl)
        self._slot_btns: List[QPushButton] = []
        for i in range(self.MAX_DISPLAY):
            b = QPushButton(f"—")
            b.setCheckable(True)
            b.setFixedSize(52, 24)
            b.setStyleSheet(self._btn_style("#444", False))
            b.setEnabled(False)
            b.clicked.connect(lambda checked, idx=i: self._on_slot_click(idx))
            self._slot_btns.append(b)
            btn_col.addWidget(b)
        btn_col.addStretch()
        lay.addLayout(btn_col)

    def update_populations(self, populations: Dict[int, Tuple[int, float]]):
        """populations: {gid: (count, energy)}"""
        self._live = {gid: cnt for gid, (cnt, _) in populations.items()}

        # Auto-select top-N by cell count (descending), update every tick
        top_n = sorted(self._live, key=lambda g: self._live[g], reverse=True)
        self._selected = top_n[:self.MAX_DISPLAY]

        # Button slots: top-N genomes ordered by count (most numerous first)
        live_list = top_n
        for i, btn in enumerate(self._slot_btns):
            if i < len(live_list):
                gid = live_list[i]
                color = genome_color(gid)
                checked = gid in self._selected
                btn.setText(f"G{gid}")
                btn.setChecked(checked)
                btn.setEnabled(True)
                btn.setProperty("gid", gid)
                btn.setStyleSheet(self._btn_style(color, checked))
            else:
                btn.setText("—")
                btn.setChecked(False)
                btn.setEnabled(False)
                btn.setProperty("gid", None)
                btn.setStyleSheet(self._btn_style("#444", False))

        self._refresh_bars()

    def _on_slot_click(self, slot_idx: int):
        btn = self._slot_btns[slot_idx]
        gid = btn.property("gid")
        if gid is None:
            return
        if btn.isChecked():
            if gid not in self._selected:
                self._selected.append(gid)
        else:
            self._selected = [g for g in self._selected if g != gid]
        color = genome_color(gid)
        btn.setStyleSheet(self._btn_style(color, btn.isChecked()))
        self._refresh_bars()

    def _refresh_bars(self):
        data = [(gid, self._live.get(gid, 0)) for gid in self._selected]
        self._bars.set_data(data)

    @staticmethod
    def _btn_style(color: str, checked: bool) -> str:
        border = "2px solid #fff" if checked else f"1px solid {color}"
        return (
            f"QPushButton{{background:{color};color:#fff;"
            f"border:{border};border-radius:3px;"
            f"font-size:10px;font-weight:bold;}}"
        )
