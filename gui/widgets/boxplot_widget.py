"""
gui/widgets/boxplot_widget.py  —  Gene expression boxplot display

Changes: 5 → 7 gene selector dropdowns.
"""

from __future__ import annotations
from collections import deque
from typing import Dict, List, Tuple

import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QComboBox,
    QLabel, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui  import QPainter, QColor, QPen, QBrush, QFont

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    BG_PANEL, BORDER, TEXT_PRIMARY, TEXT_MUTED,
    genome_color, btn_style,
)

_WINDOW  = 60
_N_GENES = 7   # number of gene selector dropdowns


class BoxplotCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._bars: List[tuple] = []
        self._max_expr = 64.0

    def set_data(self, bars: List[tuple], max_expr: float = 64.0):
        self._bars     = bars
        self._max_expr = max(max_expr, 1.0)
        self.update()

    def paintEvent(self, _event):
        import math as _math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(BG_PANEL))

        if not self._bars:
            p.setPen(QPen(QColor(TEXT_MUTED)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Select genes above to display expression")
            p.end()
            return

        n_genes   = len(self._bars)
        pad_top   = 8
        pad_bot   = 18
        draw_h    = h - pad_top - pad_bot
        slot_w    = w // n_genes

        for i, (gene_name, genome_stats) in enumerate(self._bars):
            x0  = i * slot_w
            n_g = len(genome_stats)
            inner_pad = 4
            avail_w   = slot_w - 2 * inner_pad
            bar_w     = max(4, avail_w // max(n_g, 1) - 2)

            # Log scale: y position based on log(v+1)
            _log_max = _math.log1p(self._max_expr)
            def y_of(v, _lm=_log_max):
                frac = _math.log1p(max(0.0, v)) / _lm if _lm > 0 else 0
                return pad_top + int(draw_h * (1.0 - frac))

            for j, (gid, stats) in enumerate(genome_stats):
                mn, q25, med, q75, mx = stats
                color = QColor(genome_color(gid))
                cx = x0 + inner_pad + j * (bar_w + 2) + bar_w // 2

                y_mn  = y_of(mn);  y_q25 = y_of(q25)
                y_med = y_of(med); y_q75 = y_of(q75)
                y_mx  = y_of(mx)

                p.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
                p.drawLine(cx, y_mx, cx, y_mn)
                p.setPen(QPen(color, 1))
                p.drawLine(cx - 3, y_mx, cx + 3, y_mx)
                p.drawLine(cx - 3, y_mn, cx + 3, y_mn)
                fill = QColor(color); fill.setAlpha(150)
                p.setBrush(QBrush(fill)); p.setPen(QPen(color, 1))
                p.drawRect(cx - bar_w // 2, y_q75, bar_w, y_q25 - y_q75)
                p.setPen(QPen(QColor("#ffffff"), 2))
                p.drawLine(cx - bar_w // 2, y_med, cx + bar_w // 2, y_med)

            font = QFont("Consolas", 7)
            p.setFont(font); p.setPen(QPen(QColor(TEXT_MUTED)))
            p.drawText(x0, h - pad_bot + 2, slot_w, pad_bot - 2,
                       Qt.AlignmentFlag.AlignCenter, gene_name)

        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        p.drawLine(0, pad_top, w, pad_top)
        p.end()


class GenomeSelectorPanel(QWidget):
    MAX_GENOMES = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(70)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(3)

        lbl = QLabel("Genomes")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:9px;")
        lay.addWidget(lbl)

        self._btns: List[QPushButton] = []
        self._gid_map: Dict[int, int] = {}
        for i in range(self.MAX_GENOMES):
            b = QPushButton("—")
            b.setCheckable(True)
            b.setFixedSize(64, 24)
            b.setEnabled(False)
            b.setStyleSheet(self._style("#444", False))
            b.clicked.connect(lambda _, idx=i: self._on_click(idx))
            self._btns.append(b)
            lay.addWidget(b)
        lay.addStretch()
        self._selected: List[int] = []

    @property
    def selected_genomes(self) -> List[int]:
        return list(self._selected)

    def update_live(self, live_ids: List[int],
                    counts: Dict[int, int] = None):
        """
        live_ids : all currently live genome ids.
        counts   : {gid: cell_count} — if provided, buttons and auto-selection
                   are sorted by count descending (most numerous first).
                   If omitted, order follows live_ids as given.
        """
        if counts:
            ordered = sorted(live_ids, key=lambda g: counts.get(g, 0), reverse=True)
        else:
            ordered = list(live_ids)

        # Auto-select top-N by count every tick
        self._selected = ordered[:self.MAX_GENOMES]

        for i, btn in enumerate(self._btns):
            if i < len(ordered):
                gid = ordered[i]
                self._gid_map[i] = gid
                checked = gid in self._selected
                btn.setText(f"G{gid}")
                btn.setChecked(checked)
                btn.setEnabled(True)
                btn.setStyleSheet(self._style(genome_color(gid), checked))
            else:
                self._gid_map.pop(i, None)
                btn.setText("—"); btn.setChecked(False); btn.setEnabled(False)
                btn.setStyleSheet(self._style("#444", False))

    def _on_click(self, slot: int):
        gid = self._gid_map.get(slot)
        if gid is None: return
        btn = self._btns[slot]
        if btn.isChecked():
            if gid not in self._selected: self._selected.append(gid)
        else:
            self._selected = [g for g in self._selected if g != gid]
        btn.setStyleSheet(self._style(genome_color(gid), btn.isChecked()))

    @staticmethod
    def _style(color: str, checked: bool) -> str:
        border = "2px solid #fff" if checked else f"1px solid {color}"
        return (
            f"QPushButton{{background:{color};color:#fff;"
            f"border:{border};border-radius:3px;"
            f"font-size:10px;font-weight:bold;}}"
            f"QPushButton:hover{{border:2px solid rgba(255,255,255,0.6);}}"
        )


class BoxplotWidget(QWidget):
    def __init__(self, all_genes: List[str], parent=None):
        super().__init__(parent)
        self._all_genes = all_genes
        self._selected_genes: List[str] = all_genes[:3] if all_genes else []
        self._history: Dict[str, deque] = {
            g: deque(maxlen=_WINDOW) for g in all_genes
        }

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Gene dropdowns — 7 slots
        ctrl = QHBoxLayout(); ctrl.setSpacing(3)
        ctrl.addWidget(QLabel("Genes:", styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))

        self._gene_combos: List[QComboBox] = []
        for i in range(_N_GENES):
            cb = QComboBox()
            cb.addItem("—")
            cb.addItems(all_genes)
            if i < len(self._selected_genes):
                cb.setCurrentText(self._selected_genes[i])
            cb.setStyleSheet(
                f"background:{BG_PANEL};color:{TEXT_PRIMARY};"
                f"border:1px solid {BORDER};font-size:10px;")
            cb.currentTextChanged.connect(self._rebuild)
            self._gene_combos.append(cb)
            ctrl.addWidget(cb)
        ctrl.addStretch()
        root.addLayout(ctrl)

        bottom = QHBoxLayout(); bottom.setSpacing(4)
        self._canvas = BoxplotCanvas()
        bottom.addWidget(self._canvas, stretch=1)
        self._genome_panel = GenomeSelectorPanel()
        self._genome_panel.update_live([0])
        bottom.addWidget(self._genome_panel)
        root.addLayout(bottom, stretch=1)

    def update_tick(self, gene_expr: Dict[int, Dict[str, float]]):
        for gene in self._all_genes:
            snap = {gid: expr.get(gene, 0.0) for gid, expr in gene_expr.items()}
            self._history[gene].append(snap)
        self._rebuild()

    def update_genomes(self, live_ids: List[int],
                       counts: Dict[int, int] = None):
        """Pass counts={gid: cell_count} to sort buttons by population size."""
        self._genome_panel.update_live(live_ids, counts)
        self._rebuild()

    def _rebuild(self):
        self._selected_genes = [
            cb.currentText() for cb in self._gene_combos
            if cb.currentText() != "—"
        ]
        selected_genomes = self._genome_panel.selected_genomes or [0]
        bars = []
        for gene in self._selected_genes:
            hist = self._history.get(gene)
            if not hist: continue
            genome_stats = []
            for gid in selected_genomes:
                vals = np.array([snap.get(gid, 0.0) for snap in hist], dtype=float)
                if len(vals) < 2: vals = np.zeros(2)
                stats = np.array([
                    vals.min(), np.percentile(vals, 25),
                    np.median(vals), np.percentile(vals, 75), vals.max(),
                ])
                genome_stats.append((gid, stats))
            bars.append((gene, genome_stats))
        self._canvas.set_data(bars)
