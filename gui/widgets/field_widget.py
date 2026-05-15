"""
gui/widgets/field_widget.py

Simulation field — a QWidget that renders coloured cell dots on a white
background.  Uses QPainter directly (no OpenGL dependency) which is fast
enough for tens of thousands of small squares.

Performance notes
-----------------
- All positions are stored in a flat numpy array (N×2 float32).
- Each tick we apply jitter in-place (vectorised, no Python loop).
- QPainter draws all dots of the same genome colour in a single
  drawRects() call after batching into a QVector of QRect.
- This keeps the per-tick paint cost O(N) with a very small constant.
"""

from __future__ import annotations
import random
import math
from typing import Dict, List, Tuple, Optional

import numpy as np

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore    import Qt, QRect, QPoint, QSize
from PyQt6.QtGui     import QPainter, QColor, QPen, QBrush

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    BG_FIELD, CELL_DOT_PX, JITTER_PX, genome_color,
)


class FieldWidget(QWidget):
    """
    White square field.  Each cell is a small coloured square.

    Public API
    ----------
    reset(capacity)          – clear field, set capacity
    apply_tick(populations, new_forks, extinct_ids)
                             – update dot counts / colours
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setSizePolicy(
            *[__import__("PyQt6.QtWidgets", fromlist=["QSizePolicy"])
              .QSizePolicy.Policy.Expanding] * 2
        )
        self._capacity      = 1000
        # genome_id → np array shape (N, 2) of float32 positions
        self._positions:    Dict[int, np.ndarray] = {}
        self._colors:       Dict[int, QColor]     = {}
        self.setStyleSheet(f"background: {BG_FIELD};")

    # ── Public ────────────────────────────────────────────────────────────────

    def reset(self, capacity: int = 1000):
        self._capacity  = max(1, capacity)
        self._positions = {}
        self._colors    = {}
        self.update()

    def apply_tick(
        self,
        populations:  Dict[int, Tuple[int, float]],   # gid → (count, energy)
        new_forks:    List[Tuple[int, int]],           # [(parent_id, child_id)]
        extinct_ids:  List[int],
    ):
        w, h   = self.width(), self.height()
        dot    = CELL_DOT_PX
        jitter = JITTER_PX

        # Assign colours for new genome ids
        for gid in populations:
            if gid not in self._colors:
                self._colors[gid] = QColor(genome_color(gid))

        # Remove extinct genomes
        for gid in extinct_ids:
            self._positions.pop(gid, None)
            self._colors.pop(gid, None)

        # Update dot counts per genome
        for gid, (count, _energy) in populations.items():
            if gid not in self._positions:
                # brand-new genome: scatter dots randomly
                if count > 0:
                    xs = np.random.uniform(0, w - dot, count).astype(np.float32)
                    ys = np.random.uniform(0, h - dot, count).astype(np.float32)
                    self._positions[gid] = np.stack([xs, ys], axis=1)
                continue

            cur = self._positions[gid]
            cur_n = len(cur)

            if count == 0:
                self._positions[gid] = np.empty((0, 2), dtype=np.float32)
            elif count > cur_n:
                # Cells added (division): place new dots near existing ones
                n_new = count - cur_n
                if cur_n > 0:
                    # pick random parents and scatter offspring nearby
                    parents = cur[np.random.randint(0, cur_n, n_new)]
                    offsets = np.random.uniform(-dot * 3, dot * 3,
                                               (n_new, 2)).astype(np.float32)
                    new_pts = np.clip(parents + offsets,
                                     [0, 0], [w - dot, h - dot])
                else:
                    xs = np.random.uniform(0, w - dot, n_new).astype(np.float32)
                    ys = np.random.uniform(0, h - dot, n_new).astype(np.float32)
                    new_pts = np.stack([xs, ys], axis=1)
                self._positions[gid] = np.vstack([cur, new_pts])
            elif count < cur_n:
                # Cells removed (death): drop random dots
                keep = np.random.choice(cur_n, count, replace=False)
                self._positions[gid] = cur[keep]

        # For newly-forked child: if child already initialised, its dot
        # should be near its parent's position (handled by the count==0 branch
        # → new random; that's fine — child dots don't need to match parent)

        # Apply jitter to all dots
        for gid, pts in self._positions.items():
            if len(pts) == 0:
                continue
            j = np.random.uniform(-jitter, jitter,
                                  pts.shape).astype(np.float32)
            pts += j
            np.clip(pts[:, 0], 0, w - dot, out=pts[:, 0])
            np.clip(pts[:, 1], 0, h - dot, out=pts[:, 1])

        self.update()   # schedule repaint

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(BG_FIELD))

        dot = CELL_DOT_PX
        # Draw founder (id 0) first so newer genomes appear on top
        order = sorted(self._positions.keys())

        for gid in order:
            pts = self._positions[gid]
            if len(pts) == 0:
                continue
            color = self._colors.get(gid, QColor("#aaaaaa"))
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)

            # Batch all rects for this colour
            rects = [
                QRect(int(x), int(y), dot, dot)
                for x, y in pts
            ]
            for r in rects:
                painter.drawRect(r)

        painter.end()
