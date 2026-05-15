"""
gui/screens/evo_screen.py  —  Page 5: Evolutionary Changes

Shows how a specific gene attribute evolved tick-by-tick from a root
genome to a selected descendant genome.

Layout
──────
┌──────────────────────────────────────────────────────────────────────┐
│  ← Dendrogram   [title]                      [→ Dendrogram] (unused)│
├────────────────────────────────┬─────────────────────────────────────┤
│                                │  Genome selector panel (right)      │
│  CHART (matplotlib-style       │  [root G0] → descendants list       │
│         drawn with QPainter)   │  Each selected genome = one line    │
│                                │  Alive first, dead below            │
│                                │                                     │
├────────────────────────────────┴─────────────────────────────────────┤
│  Root: [combo]   Gene: [combo]   Attr: [combo]                       │
└──────────────────────────────────────────────────────────────────────┘

Data contract
─────────────
push_data(mut_log, all_records, populations, genome_tree, genome_labels)
  mut_log      : list of dicts — all mutation events
  all_records  : list of dicts — all tick records (GenomeID, Tick, ...)
  populations  : {gid: (cell_count, energy)} — current state
  genome_tree  : {gid: parent_gid | None}
  genome_labels: {gid: str}
"""

from __future__ import annotations
import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QComboBox, QSizePolicy, QScrollArea,
)
from PyQt6.QtCore  import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui   import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics,
)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    BG_DARK, BG_PANEL, BORDER, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT, ACCENT2, DANGER, genome_color, btn_style,
)

# ── Constants ─────────────────────────────────────────────────────────────────
# promoter and enhancer are now numeric (1.25/2.0/4.0 and 4/16/64)
_ALL_ATTRS = ["threshold", "promoter", "enhancer",
              "func_coeff", "cond_value", "size_kda"]

def _QUAL_ORDER(v):  return v   # passthrough — all attrs are now numeric
def _QUAL_LABELS(v): return v   # passthrough

# ── Helpers ───────────────────────────────────────────────────────────────────

def _descendants(root: int, tree: Dict[int, Optional[int]]) -> Set[int]:
    """All descendants of root (inclusive)."""
    children: Dict[int, List[int]] = defaultdict(list)
    for gid, parent in tree.items():
        if parent is not None:
            children[parent].append(gid)
    result, stack = {root}, [root]
    while stack:
        n = stack.pop()
        for c in children.get(n, []):
            result.add(c); stack.append(c)
    return result

def _is_qual(attr: str) -> bool:
    return False   # promoter/enhancer are now numeric

def _attr_to_float(value, attr: str) -> Optional[float]:
    if _is_qual(attr):
        return float(_QUAL_ORDER.get(str(value), 0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _float_to_label(v: float, attr: str) -> str:
    if _is_qual(attr):
        return _QUAL_LABELS.get(int(round(v)), str(v))
    return f"{v:.4g}"

def _round_x_ticks(max_tick: int, n: int = 10) -> List[int]:
    """Return up to n nicely-rounded x-axis tick positions."""
    if max_tick <= 0:
        return [0]
    for step in [1000, 500, 200, 100, 50, 20, 10, 5, 2, 1]:
        ticks = list(range(0, max_tick + 1, step))
        if len(ticks) <= n:
            if max_tick not in ticks:
                ticks.append(max_tick)
            return sorted(set(ticks))
    return list(range(0, max_tick + 1))


# ── Chart canvas ──────────────────────────────────────────────────────────────

class EvoCanvas(QWidget):
    """Draws the evolutionary attribute chart."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background:{BG_DARK};")

        # Data: list of (gid, [(tick, value_float), ...])
        self._series: List[Tuple[int, List[Tuple[int, float]]]] = []
        self._attr   = ""
        self._max_x  = 0
        self._min_y  = 0.0
        self._max_y  = 1.0

    def set_series(self, series: List[Tuple[int, List[Tuple[int, float]]]],
                   attr: str):
        self._series = series
        self._attr   = attr
        if series:
            all_x = [t for _, pts in series for t, _ in pts]
            all_y = [v for _, pts in series for _, v in pts]
            self._max_x = max(all_x) if all_x else 0
            self._min_y = min(all_y) if all_y else 0.0
            self._max_y = max(all_y) if all_y else 1.0
            if self._min_y == self._max_y:
                self._min_y -= 0.5; self._max_y += 0.5
        else:
            self._max_x = 0
            self._min_y, self._max_y = 0.0, 1.0
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(BG_DARK))

        pad_l, pad_r, pad_t, pad_b = 68, 20, 12, 36

        draw_w = w - pad_l - pad_r
        draw_h = h - pad_t - pad_b

        if draw_w < 10 or draw_h < 10:
            p.end(); return

        def cx(tick):
            return pad_l + (tick / max(self._max_x, 1)) * draw_w

        def cy(val):
            span = self._max_y - self._min_y
            return pad_t + draw_h - ((val - self._min_y) / span) * draw_h

        # Grid
        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        n_y = 4
        for i in range(n_y + 1):
            yv  = self._min_y + i * (self._max_y - self._min_y) / n_y
            yp  = cy(yv)
            p.drawLine(QPointF(pad_l, yp), QPointF(w - pad_r, yp))

        # Axes
        p.setPen(QPen(QColor(TEXT_MUTED), 1))
        p.drawLine(pad_l, pad_t, pad_l, h - pad_b)
        p.drawLine(pad_l, h - pad_b, w - pad_r, h - pad_b)

        font_s = QFont("Consolas", 8); p.setFont(font_s)
        fm = QFontMetrics(font_s)

        # Y labels
        for i in range(n_y + 1):
            yv  = self._min_y + i * (self._max_y - self._min_y) / n_y
            yp  = cy(yv)
            lbl = _float_to_label(yv, self._attr)
            tw  = fm.horizontalAdvance(lbl)
            p.setPen(QPen(QColor(TEXT_MUTED)))
            p.drawText(int(pad_l - tw - 4), int(yp + fm.ascent() / 2), lbl)

        # X labels
        x_ticks = _round_x_ticks(self._max_x)
        for t in x_ticks:
            xp  = cx(t)
            lbl = str(t)
            tw  = fm.horizontalAdvance(lbl)
            p.drawText(int(xp - tw / 2), int(h - pad_b + 14), lbl)
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(xp, pad_t), QPointF(xp, h - pad_b))
            p.setPen(QPen(QColor(TEXT_MUTED)))

        # No data message
        if not self._series:
            p.setPen(QPen(QColor(TEXT_MUTED)))
            p.setFont(QFont("Consolas", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Select root genome, gene, attribute\nand at least one descendant genome")
            p.end(); return

        # Series lines
        for gid, pts in self._series:
            if not pts: continue
            color = QColor(genome_color(gid))
            p.setPen(QPen(color, 2))
            path_pts = [(cx(t), cy(v)) for t, v in pts]
            for i in range(1, len(path_pts)):
                p.drawLine(QPointF(*path_pts[i-1]), QPointF(*path_pts[i]))
            # Dots
            p.setBrush(QBrush(color)); p.setPen(Qt.PenStyle.NoPen)
            for xp, yp in path_pts:
                p.drawEllipse(QRectF(xp - 3, yp - 3, 6, 6))

        p.end()


# ── Genome selector panel ─────────────────────────────────────────────────────

class GenomeSelectorList(QWidget):
    """
    Vertical stack of combo-boxes for selecting descendant genomes.
    Rules:
    - Always at least one combo (showing alive genomes first, then dead).
    - Selecting a genome adds a new combo below (up to some max).
    - Selecting '—' in a combo removes it (and collapses the list).
    - Order of combos reflects selection order.
    """
    selection_changed = pyqtSignal()

    _MAX = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._combos: List[QComboBox] = []
        self._choices: List[str] = []   # ordered: alive first
        self._gid_map: Dict[str, int]  = {}   # label -> gid

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self._lay = lay

        self._add_combo()   # start with one empty combo

    # ── Public ────────────────────────────────────────────────────────────────

    def set_available(self, alive: List[int], dead: List[int],
                      labels: Dict[int, str]):
        """Update which genomes can be selected."""
        self._choices = []
        self._gid_map = {}
        for gid in alive:
            lbl = f"✓ {labels.get(gid, f'G{gid}')}"
            self._choices.append(lbl)
            self._gid_map[lbl] = gid
        for gid in dead:
            lbl = f"† {labels.get(gid, f'G{gid}')}"
            self._choices.append(lbl)
            self._gid_map[lbl] = gid

        # Refresh all combos
        for cb in self._combos:
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("—")
            cb.addItems(self._choices)
            if cur in self._choices:
                cb.setCurrentText(cur)
            cb.blockSignals(False)
        self._rebuild()

    def selected_gids(self) -> List[int]:
        result = []
        for cb in self._combos:
            t = cb.currentText()
            if t != "—" and t in self._gid_map:
                result.append(self._gid_map[t])
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _add_combo(self):
        cb = QComboBox()
        cb.addItem("—")
        cb.addItems(self._choices)
        cb.setStyleSheet(
            f"background:{BG_PANEL};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};font-size:11px;"
        )
        cb.currentTextChanged.connect(self._on_change)
        self._combos.append(cb)
        self._lay.addWidget(cb)

    def _rebuild(self):
        """Remove trailing empty combos, keep at least one, add one if needed."""
        # Remove all-empty combos from the end (keep at least one)
        while len(self._combos) > 1:
            last = self._combos[-1]
            if last.currentText() == "—":
                self._combos.pop()
                self._lay.removeWidget(last)
                last.deleteLater()
            else:
                break

        # If last combo has a selection and we can add more, append empty
        if (self._combos[-1].currentText() != "—"
                and len(self._combos) < self._MAX):
            self._add_combo()

    def _on_change(self, _text: str):
        self._rebuild()
        self.selection_changed.emit()


# ── EvoScreen ─────────────────────────────────────────────────────────────────

class EvoScreen(QWidget):
    go_back = pyqtSignal()   # → DendrogramScreen

    def __init__(self, parent=None):
        super().__init__(parent)

        # Data
        self._mut_log:      List[dict]                    = []
        self._all_records:  List[dict]                    = []
        self._populations:  Dict[int, Tuple[int, float]]  = {}
        self._genome_tree:  Dict[int, Optional[int]]      = {}
        self._genome_labels: Dict[int, str]               = {}

        # Derived
        self._roots:     List[int] = []   # gids with parent=None
        self._all_gids:  List[int] = []

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(f"background:{BG_DARK};color:{TEXT_PRIMARY};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        top = QFrame()
        top.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border-bottom:1px solid {BORDER};}}")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 8, 12, 8)

        back_btn = QPushButton("← Dendrogram")
        back_btn.setStyleSheet(btn_style("#3a3f47", font_size=11))
        back_btn.clicked.connect(self.go_back.emit)
        tl.addWidget(back_btn)

        title = QLabel("📈  Evolutionary Changes")
        title.setStyleSheet(
            "font-size:16px;font-weight:bold;color:#e6edf3;margin-left:12px;")
        tl.addWidget(title)
        tl.addStretch()
        root.addWidget(top)

        # Middle: chart + selector
        mid = QHBoxLayout()
        mid.setContentsMargins(8, 8, 4, 4)
        mid.setSpacing(6)

        self._canvas = EvoCanvas()
        mid.addWidget(self._canvas, stretch=1)

        # Right: genome selector
        sel_frame = QFrame()
        sel_frame.setFixedWidth(190)
        sel_frame.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border:1px solid {BORDER};"
            f"border-radius:6px;}}")
        sel_lay = QVBoxLayout(sel_frame)
        sel_lay.setContentsMargins(6, 6, 6, 6)
        sel_lay.setSpacing(4)
        sel_lay.addWidget(QLabel("Descendant genomes:",
            styleSheet=f"color:{TEXT_MUTED};font-size:10px;"))

        # Scrollable selector list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        self._sel_list = GenomeSelectorList()
        self._sel_list.selection_changed.connect(self._rebuild_chart)
        scroll.setWidget(self._sel_list)
        sel_lay.addWidget(scroll, stretch=1)
        mid.addWidget(sel_frame)

        root.addLayout(mid, stretch=1)

        # Bottom controls
        bot_frame = QFrame()
        bot_frame.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border-top:1px solid {BORDER};}}")
        bl = QHBoxLayout(bot_frame)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(12)

        # Root genome selector
        bl.addWidget(QLabel("Root genome:",
            styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))
        self._root_combo = QComboBox()
        self._root_combo.setMinimumWidth(130)
        self._root_combo.setStyleSheet(
            f"background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};font-size:11px;")
        self._root_combo.currentIndexChanged.connect(self._on_root_change)
        bl.addWidget(self._root_combo)

        bl.addWidget(QLabel("|", styleSheet=f"color:{BORDER};"))

        # Gene selector
        bl.addWidget(QLabel("Gene:",
            styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))
        self._gene_combo = QComboBox()
        self._gene_combo.setMinimumWidth(110)
        self._gene_combo.setStyleSheet(
            f"background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};font-size:11px;")
        self._gene_combo.addItem("—")
        self._gene_combo.currentTextChanged.connect(self._rebuild_chart)
        bl.addWidget(self._gene_combo)

        # Attribute selector
        bl.addWidget(QLabel("Attribute:",
            styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))
        self._attr_combo = QComboBox()
        self._attr_combo.setMinimumWidth(110)
        self._attr_combo.setStyleSheet(
            f"background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};font-size:11px;")
        self._attr_combo.addItem("—")
        self._attr_combo.addItems(_ALL_ATTRS)
        self._attr_combo.currentTextChanged.connect(self._rebuild_chart)
        bl.addWidget(self._attr_combo)

        bl.addStretch()
        root.addWidget(bot_frame)

    # ── Public API ────────────────────────────────────────────────────────────

    def push_data(self,
                  mut_log:       List[dict],
                  all_records:   List[dict],
                  populations:   Dict[int, Tuple[int, float]],
                  genome_tree:   Dict[int, Optional[int]],
                  genome_labels: Dict[int, str]):
        self._mut_log      = mut_log
        self._all_records  = all_records
        self._populations  = populations
        self._genome_tree  = genome_tree
        self._genome_labels = genome_labels

        self._all_gids = sorted(genome_tree.keys())
        self._roots    = [g for g, p in genome_tree.items() if p is None]

        # Build gene list from mut_log + records
        genes: Set[str] = set()
        for ev in mut_log:
            g = ev.get("GeneName")
            if g: genes.add(g)
        # Also from all_records column names
        if all_records:
            exclude = {"Tick","GenomeID","ParentID","Energy","CellCount","Food",
                       "mut_detected","tox_detected"}
            for k in all_records[0]:
                if k not in exclude and not k[0].isupper() or k.isupper():
                    genes.add(k)
        self._all_genes = sorted(genes)

        # Refresh root combo
        self._root_combo.blockSignals(True)
        self._root_combo.clear()
        for r in self._roots:
            lbl = genome_labels.get(r, f"G{r}")
            self._root_combo.addItem(lbl, r)
        self._root_combo.blockSignals(False)

        # Refresh gene combo
        self._gene_combo.blockSignals(True)
        cur_gene = self._gene_combo.currentText()
        self._gene_combo.clear()
        self._gene_combo.addItem("—")
        self._gene_combo.addItems(self._all_genes)
        if cur_gene in self._all_genes:
            self._gene_combo.setCurrentText(cur_gene)
        self._gene_combo.blockSignals(False)

        self._on_root_change()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_root_change(self):
        root_gid = self._root_combo.currentData()
        if root_gid is None:
            self._sel_list.set_available([], [], {})
            self._rebuild_chart()
            return

        # Descendants of selected root (excluding the root itself)
        desc = _descendants(root_gid, self._genome_tree) - {root_gid}
        alive = [g for g in desc if g in self._populations and self._populations[g][0] > 0]
        dead  = [g for g in desc if g not in alive]
        alive.sort(key=lambda g: -self._populations.get(g, (0,0))[0])
        dead.sort()
        self._sel_list.set_available(alive, dead, self._genome_labels)
        self._rebuild_chart()

    def _rebuild_chart(self):
        gene  = self._gene_combo.currentText()
        attr  = self._attr_combo.currentText()
        root_gid = self._root_combo.currentData()

        if gene == "—" or attr == "—" or root_gid is None:
            self._canvas.set_series([], attr if attr != "—" else "")
            return

        selected_gids = self._sel_list.selected_gids()
        if not selected_gids:
            self._canvas.set_series([], attr)
            return

        series = []
        for gid in selected_gids:
            pts = self._build_series(root_gid, gid, gene, attr)
            if pts:
                series.append((gid, pts))

        self._canvas.set_series(series, attr)

    def _build_series(self, root_gid: int, target_gid: int,
                      gene: str, attr: str) -> List[Tuple[int, float]]:
        """
        Build (tick, value) series for `gene.attr` from root to target.
        Strategy:
          1. Find the initial value of the attribute in the root genome
             (look for the first record containing this genome).
          2. Walk the mutation log along the lineage path from root to target.
             Each mutation event that touches (gene, attr) gives us a new value
             at a specific tick.
          3. Return step-function points: the value holds constant until
             the next mutation event.
        """
        # Build lineage path: root -> ... -> target
        path = []
        cur = target_gid
        while cur is not None:
            path.append(cur)
            cur = self._genome_tree.get(cur)
        path.reverse()   # root first

        if path[0] != root_gid:
            return []   # target not descended from root

        # Get initial attribute value for root genome
        # Scan mut_log to find value_before of first mutation for (gene, attr) on root
        init_val = self._get_initial_value(root_gid, gene, attr)
        if init_val is None:
            return []

        # Collect mutation events along path, in tick order
        events: List[Tuple[int, float]] = []
        for gid in path[1:]:   # skip root (it's the baseline)
            for ev in self._mut_log:
                if (ev.get("ChildGenomeID") == gid
                        and ev.get("GeneName") == gene
                        and ev.get("Attribute") == attr):
                    tick = ev.get("Tick", 0)
                    val  = _attr_to_float(ev.get("ValueAfter"), attr)
                    if val is not None:
                        events.append((tick, val))

        # Determine last tick for this genome
        last_tick = self._last_tick(target_gid)

        # Build step function
        events.sort(key=lambda e: e[0])
        pts: List[Tuple[int, float]] = [(0, init_val)]
        cur_val = init_val
        for tick, val in events:
            if tick > 0:
                pts.append((tick - 1, cur_val))  # value just before change
            pts.append((tick, val))
            cur_val = val
        pts.append((last_tick, cur_val))   # hold until last known tick

        return pts

    def _get_initial_value(self, root_gid: int,
                            gene: str, attr: str) -> Optional[float]:
        """
        Get the initial value of gene.attr for root_gid.
        Try: value_before of the earliest mutation on this (gene, attr)
        originating from root lineage.  If no mutations exist, fall back to
        scanning all_records column if attr is a gene expression column.
        """
        # Find earliest mutation that touches (gene, attr) in root lineage
        # The value_before of the first such event = initial state
        earliest = None
        for ev in self._mut_log:
            if (ev.get("GeneName") == gene
                    and ev.get("Attribute") == attr):
                parent = ev.get("ParentGenomeID")
                if parent == root_gid or parent in _descendants(
                        root_gid, self._genome_tree):
                    tick = ev.get("Tick", 0)
                    if earliest is None or tick < earliest[0]:
                        earliest = (tick, ev.get("ValueBefore"))

        if earliest is not None:
            v = _attr_to_float(earliest[1], attr)
            if v is not None:
                return v

        # Fallback: if attr is 'threshold' and gene is in records, try extracting
        # from the first record of root_gid
        if attr == "threshold" and self._all_records:
            for r in self._all_records:
                if r.get("GenomeID") == root_gid and gene in r:
                    v = _attr_to_float(r[gene], attr)
                    if v is not None:
                        return v

        return None

    def _last_tick(self, gid: int) -> int:
        """Last tick at which genome gid appears in all_records."""
        last = 0
        for r in self._all_records:
            if r.get("GenomeID") == gid:
                t = r.get("Tick", 0)
                if t > last:
                    last = t
        return last
