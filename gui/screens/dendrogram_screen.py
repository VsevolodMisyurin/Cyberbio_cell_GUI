"""
gui/screens/dendrogram_screen.py  —  Page 4: Genome Lineage Tree

Key features in this version
-----------------------------
• Aggregated net diff shown in popup:
    For each gene attribute, only the net change vs G0 (or vs nearest ancestor)
    is shown.  If a parameter mutated back to its original value, it is omitted.
    Categorical (promoter/enhancer) attrs compared by value equality.
    Numeric attrs (func_coeff, cond_value, size_kda, threshold) compared with
    a small epsilon so trivial float noise is suppressed.

• Save genome to collection uses save_genome_to_collection() → ~/.cell_sim/genome_collection.json

• Cryo-freeze button in popup:
    Enter strain name, description, cell count, vial count.
    On confirm: removes cells from simulation (via cryo_freeze_requested signal),
    saves vials to ~/.cell_sim/cryobank.json.

• Full mutation history is always kept in mut_log (never pruned).
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Set, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSizePolicy, QFrame, QComboBox,
    QLineEdit, QInputDialog, QSpinBox, QDialog, QDialogButtonBox,
    QScrollArea, QTextEdit,
)
from PyQt6.QtCore  import Qt, QRectF, QPointF, pyqtSignal, QPoint
from PyQt6.QtGui   import (
    QPainter, QColor, QPen, QBrush, QFont,
    QWheelEvent, QMouseEvent,
)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    BG_DARK, BG_PANEL, BORDER, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT, ACCENT2, DANGER,
    genome_color, btn_style,
)
from gui.utils.collections import (
    save_genome_to_collection, save_to_cryobank,
)

# ── Layout constants ───────────────────────────────────────────────────────────
_R_MAX     = 80
_R_MIN     = 28
_ASPECT    = 0.52
_LEVEL_GAP = 220
_SIBLING_W = 200
_MARGIN    = 120

_MODE_ALL      = "all"
_MODE_HIDE_EXT = "hide_extinct"
_MODE_BACKBONE = "backbone"

_NUMERIC_ATTRS = frozenset({"func_coeff", "cond_value", "size_kda", "threshold"})
_NUMERIC_EPS   = 1e-6


# ── Tree helpers ───────────────────────────────────────────────────────────────

def _is_extinct(gid, pops): return gid not in pops or pops[gid][0] == 0
def _ancestors(gid, tree):
    r, cur = [], tree.get(gid)
    while cur is not None: r.append(cur); cur = tree.get(cur)
    return r

def _live_descendants(gid, children, pops):
    result, stack = set(), [gid]
    while stack:
        n = stack.pop()
        if not _is_extinct(n, pops): result.add(n)
        stack.extend(children.get(n, []))
    return result

def _build_children(tree):
    ch = {g: [] for g in tree}
    for g, p in tree.items():
        if p is not None: ch.setdefault(p, []).append(g)
    return ch

def _find_visible_parent(gid, tree, visible):
    cur = tree.get(gid)
    while cur is not None:
        if cur in visible: return cur
        cur = tree.get(cur)
    return None


# ── Aggregated diff computation ────────────────────────────────────────────────

def _aggregate_diff(gid: int, tree: Dict, mut_events: Dict[int, List[dict]]) -> str:
    """
    Walk from G0 down to gid, collecting all mutation events along the path.
    Then collapse per (gene, attribute): keep only the FIRST value_before and
    the LAST value_after.  If net change is zero (or below epsilon), omit.

    Format per changed attribute:
        GENE.attribute: before → after
    """
    # Collect path from root to gid (exclusive of root ancestors above G0)
    path = list(reversed(_ancestors(gid, tree))) + [gid]

    # Per (gene, attr): track first_before and running last_after
    first_before: Dict[tuple, object] = {}
    last_after:   Dict[tuple, object] = {}

    for node in path:
        for ev in mut_events.get(node, []):
            key = (ev.get("GeneName", "?"), ev.get("Attribute", "?"))
            if key not in first_before:
                first_before[key] = ev.get("ValueBefore")
            last_after[key] = ev.get("ValueAfter")

    if not first_before:
        return "No net mutations vs G0"

    lines = []
    for (gene, attr), before in first_before.items():
        after = last_after[(gene, attr)]
        # Skip if net change is zero
        if attr in _NUMERIC_ATTRS:
            try:
                if abs(float(str(after)) - float(str(before))) < _NUMERIC_EPS:
                    continue
            except (ValueError, TypeError):
                if str(before) == str(after): continue
        else:
            if str(before) == str(after):
                continue
        # Format numeric nicely
        if attr in _NUMERIC_ATTRS:
            try:
                bef_s = f"{float(str(before)):.4g}"
                aft_s = f"{float(str(after)):.4g}"
            except Exception:
                bef_s, aft_s = str(before), str(after)
        else:
            bef_s, aft_s = str(before), str(after)
        lines.append(f"{gene}.{attr}: {bef_s} → {aft_s}")

    return "\n".join(lines) if lines else "No net mutations vs G0"


# ── Cryo-freeze dialog ────────────────────────────────────────────────────────

class CryoDialog(QDialog):
    """
    Dialog to freeze cells into the cryobank.
    Fields: strain name, description, cells per vial, number of vials.
    """
    def __init__(self, genome_id: int, available_cells: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"❄  Freeze cells — G{genome_id}")
        self.setFixedWidth(360)
        self.setStyleSheet(f"background:{BG_PANEL};color:{TEXT_PRIMARY};")
        self._available = available_cells

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 12)

        def _field(label, widget):
            row = QHBoxLayout()
            lbl = QLabel(label); lbl.setStyleSheet(f"color:{TEXT_MUTED};min-width:120px;")
            row.addWidget(lbl); row.addWidget(widget, stretch=1)
            lay.addLayout(row)

        self._name_ed = QLineEdit(f"G{genome_id}_strain")
        self._name_ed.setStyleSheet(
            f"background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};border-radius:3px;padding:4px;")
        _field("Strain name:", self._name_ed)

        self._desc_ed = QLineEdit()
        self._desc_ed.setPlaceholderText("optional description")
        self._desc_ed.setStyleSheet(
            f"background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};border-radius:3px;padding:4px;")
        _field("Description:", self._desc_ed)

        spin_style = (
            f"QSpinBox{{background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};border-radius:3px;padding:3px;}}"
            "QSpinBox::up-button{width:20px;}"
            "QSpinBox::down-button{width:20px;}"
        )
        self._cells_spin = QSpinBox()
        self._cells_spin.setRange(1, available_cells)
        self._cells_spin.setValue(min(10, available_cells))
        self._cells_spin.setKeyboardTracking(False)
        self._cells_spin.setStyleSheet(spin_style)
        _field(f"Cells/vial (max {available_cells}):", self._cells_spin)

        self._vials_spin = QSpinBox()
        self._vials_spin.setRange(1, 100)
        self._vials_spin.setValue(1)
        self._vials_spin.setKeyboardTracking(False)
        self._vials_spin.setStyleSheet(spin_style)
        _field("Number of vials:", self._vials_spin)

        self._total_lbl = QLabel()
        self._total_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        lay.addWidget(self._total_lbl)
        self._cells_spin.valueChanged.connect(self._update_total)
        self._vials_spin.valueChanged.connect(self._update_total)
        self._update_total()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            btn_style(ACCENT, font_size=12))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            btn_style("#3a3f47", font_size=12))
        lay.addWidget(btns)

    def _update_total(self):
        total = self._cells_spin.value() * self._vials_spin.value()
        over  = total > self._available
        color = DANGER if over else TEXT_MUTED
        self._total_lbl.setText(
            f"Total cells needed: {total}  (available: {self._available})")
        self._total_lbl.setStyleSheet(f"color:{color};font-size:11px;")

    @property
    def strain_name(self): return self._name_ed.text().strip() or "unnamed"
    @property
    def description(self):  return self._desc_ed.text().strip()
    @property
    def cells_per_vial(self): return self._cells_spin.value()
    @property
    def n_vials(self): return self._vials_spin.value()
    @property
    def total_cells(self): return self.cells_per_vial * self.n_vials


# ── MutationPopup ─────────────────────────────────────────────────────────────

class MutationPopup(QFrame):
    save_genome_requested  = pyqtSignal(int, str)         # gid, name
    cryo_freeze_requested  = pyqtSignal(int, str, str, int, int)
    # (gid, strain_name, description, cells_per_vial, n_vials)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border:1px solid {BORDER};"
            f"border-radius:6px;}}")
        self.setFixedWidth(340)
        self.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        self._title = QLabel()
        self._title.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-weight:bold;font-size:12px;")
        lay.addWidget(self._title)

        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setFixedHeight(120)
        self._body.setStyleSheet(
            f"background:{BG_DARK};color:{TEXT_MUTED};"
            f"font-family:Consolas;font-size:10px;"
            f"border:1px solid {BORDER};border-radius:3px;")
        lay.addWidget(self._body)

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("💾 Save genome")
        self._save_btn.setStyleSheet(btn_style(ACCENT2, font_size=11, padding="4px 8px"))
        self._save_btn.clicked.connect(self._on_save)

        self._cryo_btn = QPushButton("❄  Freeze cells")
        self._cryo_btn.setStyleSheet(btn_style("#1a5276", font_size=11, padding="4px 8px"))
        self._cryo_btn.clicked.connect(self._on_cryo)

        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._cryo_btn)
        lay.addLayout(btn_row)

        self._gid: Optional[int] = None
        self._available_cells: int = 0
        self._genome_preset: Optional[dict] = None

    def show_for(self, gid: int, title: str, body: str, pos: QPoint,
                 available_cells: int = 0, genome_preset: dict = None):
        self._gid             = gid
        self._available_cells = available_cells
        self._genome_preset   = genome_preset
        self._title.setText(title)
        self._body.setPlainText(body)
        self._cryo_btn.setEnabled(available_cells > 0)
        self.adjustSize()
        self.move(pos)
        self.show()
        self.raise_()

    def _on_save(self):
        if self._gid is None: return
        name, ok = QInputDialog.getText(
            self, "Save genome", f"Name for G{self._gid}:")
        if ok and name.strip():
            self.save_genome_requested.emit(self._gid, name.strip())

    def _on_cryo(self):
        if self._gid is None: return
        dlg = CryoDialog(self._gid, self._available_cells, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.total_cells > self._available_cells:
                return  # not enough cells
            self.cryo_freeze_requested.emit(
                self._gid, dlg.strain_name, dlg.description,
                dlg.cells_per_vial, dlg.n_vials)


# ── DendroCanvas ──────────────────────────────────────────────────────────────

class DendroCanvas(QWidget):
    popup_requested = pyqtSignal(int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background:{BG_DARK};")
        self.setMouseTracking(True)

        self._scale  = 1.0
        self._offset = QPointF(_MARGIN, _MARGIN)
        self._drag_start: Optional[QPointF] = None
        self._drag_orig:  Optional[QPointF] = None

        self._tree:        Dict[int, Optional[int]]       = {}
        self._populations: Dict[int, Tuple[int, float]]   = {}
        self._max_ever:    Dict[int, int]                 = {}
        self._mut_events:  Dict[int, List[dict]]          = {}
        self._node_tips:   Dict[int, str]                 = {}
        self._positions:   Dict[int, Tuple[float, float]] = {}
        self._edges:       List[Tuple[int, int]]          = []
        self._mode        = _MODE_ALL
        self._all_genomes_presets: Dict[int, dict]        = {}
        self._genome_labels: Dict[int, str]               = {}

    def push_data(self, tree, populations, max_ever, mut_events, node_tips, genome_presets):
        self._tree        = tree
        self._populations = populations
        self._max_ever    = max_ever
        self._mut_events  = mut_events
        self._node_tips   = node_tips
        self._all_genomes_presets = genome_presets
        self._relayout()
        self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        self._relayout()
        self.update()

    def centre_on(self, gid: int):
        if gid not in self._positions: return
        cx, cy = self._positions[gid]
        w, h   = self.width(), self.height()
        self._offset = QPointF(w/2 - cx*self._scale, h/2 - cy*self._scale)
        self.update()

    def _relayout(self):
        tree, populations = self._tree, self._populations
        if not tree: return
        children = _build_children(tree)

        if self._mode == _MODE_ALL:
            visible = set(tree.keys())
        elif self._mode == _MODE_HIDE_EXT:
            visible = {g for g in tree if not _is_extinct(g, populations) or g == 0}
        else:
            live    = {g for g in tree if not _is_extinct(g, populations)}
            visible = {0} | live
            for gid in list(live):
                for anc in _ancestors(gid, tree):
                    if anc in visible: break
                    live_ch = [c for c in children.get(anc, [])
                               if _live_descendants(c, children, populations)]
                    if len(live_ch) >= 2: visible.add(anc)

        edges: List[Tuple[int,int]] = []
        for gid in visible:
            if gid == 0: continue
            vp = _find_visible_parent(gid, tree, visible)
            if vp is not None: edges.append((vp, gid))
        self._edges = edges

        eff_ch: Dict[int, List[int]] = {g: [] for g in visible}
        for p, c in edges: eff_ch.setdefault(p, []).append(c)
        roots   = [g for g in visible if _find_visible_parent(g, tree, visible) is None]
        leaf_x  = [0.0]
        pos: Dict[int, Tuple[float,float]] = {}

        def place(g, level):
            ch = eff_ch.get(g, [])
            if not ch:
                x = _MARGIN + leaf_x[0] * _SIBLING_W; leaf_x[0] += 1
            else:
                xs = [place(c, level+1) for c in ch]; x = sum(xs)/len(xs)
            pos[g] = (x, _MARGIN + level * _LEVEL_GAP); return x

        for r in roots: place(r, 0)
        self._positions = pos

    def _rx(self, gid):
        return _R_MIN + (_R_MAX - _R_MIN) * math.log1p(
            max(self._max_ever.get(gid,1),1)) / math.log1p(10_000)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG_DARK))
        p.translate(self._offset); p.scale(self._scale, self._scale)

        if not self._positions:
            p.setPen(QPen(QColor(TEXT_MUTED)))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Open the dendrogram after running at least one tick.")
            p.end(); return

        p.setPen(QPen(QColor("#444c56"), 2))
        for pid, cid in self._edges:
            if pid not in self._positions or cid not in self._positions: continue
            px, py = self._positions[pid]; cx, cy = self._positions[cid]
            p.drawLine(QPointF(px, py + self._rx(pid)*_ASPECT),
                       QPointF(cx, cy - self._rx(cid)*_ASPECT))

        fn = QFont("Consolas", 9); fs = QFont("Consolas", 7)
        for gid, (cx, cy) in self._positions.items():
            rx = self._rx(gid); ry = rx * _ASPECT
            max_c = max(self._max_ever.get(gid,1),1)
            cur_c = self._populations.get(gid,(0,0))[0]
            extinct = _is_extinct(gid, self._populations)

            p.setBrush(QBrush(QColor("#424a53")))
            p.setPen(QPen(QColor("#636e7b"), 1))
            p.drawEllipse(QRectF(cx-rx, cy-ry, 2*rx, 2*ry))
            if not extinct:
                frac = min(1.0, math.log1p(cur_c)/math.log1p(max_c))
                irx, iry = rx*frac, ry*frac
                col = QColor(genome_color(gid)); col.setAlpha(220)
                p.setBrush(QBrush(col)); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx-irx, cy-iry, 2*irx, 2*iry))

            lbl_text = self._genome_labels.get(gid, f"G{gid}")
            p.setFont(fn); p.setPen(QPen(QColor("#ffffff")))
            p.drawText(QRectF(cx-rx, cy-ry, 2*rx, ry),
                       Qt.AlignmentFlag.AlignCenter, lbl_text)
            p.setFont(fs); p.setPen(QPen(QColor("#adbac7")))
            p.drawText(QRectF(cx-rx, cy, 2*rx, ry),
                       Qt.AlignmentFlag.AlignCenter,
                       f"†{max_c}" if extinct else str(cur_c))

            # Info pin
            p.setBrush(QBrush(QColor("#d29922"))); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(cx-6, cy-ry-6, 12, 12))
            p.setFont(fs); p.setPen(QPen(QColor("#0d1117")))
            p.drawText(QRectF(cx-6, cy-ry-6, 12, 12),
                       Qt.AlignmentFlag.AlignCenter, "i")
        p.end()

    def _scene_pos(self, ep): sp = (ep - self._offset)/self._scale; return sp.x(), sp.y()

    def mousePressEvent(self, event: QMouseEvent):
        sx, sy = self._scene_pos(event.position())
        for gid, (cx, cy) in self._positions.items():
            pin_x, pin_y = cx, cy - self._rx(gid)*_ASPECT
            if abs(sx-pin_x) < 10 and abs(sy-pin_y) < 10:
                self.popup_requested.emit(gid, event.globalPosition().toPoint())
                return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._drag_orig  = QPointF(self._offset)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start is not None:
            self._offset = self._drag_orig + (event.position() - self._drag_start)
            self.update()

    def mouseReleaseEvent(self, _e): self._drag_start = None; self._drag_orig = None

    def wheelEvent(self, event: QWheelEvent):
        f = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        self._scale = max(0.1, min(6.0, self._scale * f)); self.update()


# ── DendrogramScreen ──────────────────────────────────────────────────────────

class DendrogramScreen(QWidget):
    go_back               = pyqtSignal()
    cryo_freeze_requested = pyqtSignal(int, str, str, int, int)
    open_evo              = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tree:            Dict[int, Optional[int]] = {}
        self._populations:     Dict[int, Tuple[int, float]] = {}
        self._max_ever:        Dict[int, int] = {}
        self._mut_log:         List[dict] = []   # full history, never pruned
        self._mut_events:      Dict[int, List[dict]] = {}
        self._genome_presets:  Dict[int, dict] = {}
        self._live_genome_objs: Dict[int, object] = {}
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background:{BG_DARK};color:{TEXT_PRIMARY};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        top = QFrame()
        top.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-bottom:1px solid {BORDER};}}")
        tl = QHBoxLayout(top); tl.setContentsMargins(12,7,12,7); tl.setSpacing(8)

        title = QLabel("🌿  Genome Lineage Tree")
        title.setStyleSheet("font-size:16px;font-weight:bold;color:#e6edf3;")
        tl.addWidget(title); tl.addSpacing(12)

        self._btn_all  = QPushButton("Show all")
        self._btn_hide = QPushButton("Hide extinct")
        self._btn_bb   = QPushButton("Minimal backbone")
        for btn, mode in [(self._btn_all, _MODE_ALL),
                          (self._btn_hide, _MODE_HIDE_EXT),
                          (self._btn_bb, _MODE_BACKBONE)]:
            btn.setCheckable(True)
            btn.setStyleSheet(btn_style("#3a3f47", font_size=11, padding="4px 10px"))
            btn.clicked.connect(lambda _, m=mode, b=btn: self._set_mode(m, b))
            tl.addWidget(btn)
        self._btn_all.setChecked(True)

        tl.addSpacing(16)
        tl.addWidget(QLabel("⊕", styleSheet=f"color:{TEXT_MUTED};font-size:14px;"))
        tl.addWidget(QLabel("Centre:", styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))

        self._centre_combo = QComboBox()
        self._centre_combo.setFixedWidth(90)
        self._centre_combo.setStyleSheet(
            f"background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};font-size:11px;")
        tl.addWidget(self._centre_combo)

        cb = QPushButton("⊕"); cb.setFixedSize(30,26)
        cb.setStyleSheet(btn_style("#2d6a4f", padding="2px", font_size=14))
        cb.clicked.connect(self._on_centre)
        tl.addWidget(cb)
        tl.addStretch()
        tl.addWidget(QLabel("Scroll=zoom · Drag=pan · 🟡=info",
                             styleSheet=f"color:{TEXT_MUTED};font-size:10px;"))
        root.addWidget(top)

        container = QWidget(); container.setStyleSheet(f"background:{BG_DARK};")
        cl = QVBoxLayout(container); cl.setContentsMargins(0,0,0,0)
        self._canvas = DendroCanvas(container)
        self._canvas.popup_requested.connect(self._show_popup)
        cl.addWidget(self._canvas)

        self._popup = MutationPopup(container)
        self._popup.save_genome_requested.connect(self._on_save_genome)
        self._popup.cryo_freeze_requested.connect(self._on_cryo)

        root.addWidget(container, stretch=1)

        bot = QFrame()
        bot.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-top:1px solid {BORDER};}}")
        bl = QHBoxLayout(bot); bl.setContentsMargins(16,8,16,8)
        back = QPushButton("← Back to simulation")
        back.setStyleSheet(btn_style("#3a3f47"))
        back.clicked.connect(self.go_back.emit)
        bl.addWidget(back)
        bl.addStretch()
        evo_btn = QPushButton("📈  Evolutionary Changes")
        evo_btn.setStyleSheet(btn_style("#1f4e79", font_size=11))
        evo_btn.clicked.connect(self.open_evo.emit)
        bl.addWidget(evo_btn)
        root.addWidget(bot)

    # ── Mode ──────────────────────────────────────────────────────────────────

    def _set_mode(self, mode, active_btn):
        for b in [self._btn_all, self._btn_hide, self._btn_bb]:
            b.setChecked(b is active_btn)
        self._canvas.set_mode(mode)
        self._rebuild_tips(mode)
        self._popup.hide()

    # ── Centre ────────────────────────────────────────────────────────────────

    def _on_centre(self):
        data = self._centre_combo.currentData()
        self._canvas.centre_on(data if data is not None else 0)

    # ── Popup ─────────────────────────────────────────────────────────────────

    def _show_popup(self, gid: int, global_pos: QPoint):
        if self._popup.isVisible() and self._popup._gid == gid:
            self._popup.hide(); return

        tip = self._canvas._node_tips.get(gid, "No net mutations vs G0")
        title = f"G{gid}  —  net changes vs G0"
        available = self._populations.get(gid, (0,0))[0]
        preset    = self._build_preset(gid)

        container = self._popup.parent()
        lp = container.mapFromGlobal(global_pos)
        px = min(lp.x()+10, container.width()  - self._popup.width() - 4)
        py = min(lp.y()+10, container.height() - 250)
        self._popup.show_for(gid, title, tip, QPoint(px, py),
                             available_cells=available, genome_preset=preset)

    def mousePressEvent(self, event):
        self._popup.hide(); super().mousePressEvent(event)

    # ── Save genome ───────────────────────────────────────────────────────────

    def _on_save_genome(self, gid: int, name: str):
        preset = self._build_preset(gid)
        if preset:
            save_genome_to_collection(name, preset)

    # ── Cryo ──────────────────────────────────────────────────────────────────

    def _on_cryo(self, gid: int, strain: str, desc: str, cpv: int, n_vials: int):
        from PyQt6.QtWidgets import QMessageBox
        preset = self._build_preset(gid) or {}
        vials  = [{"cells": cpv, "label": f"vial_{i+1}"} for i in range(n_vials)]
        save_to_cryobank(strain, desc, preset, vials)
        total = cpv * n_vials
        self.cryo_freeze_requested.emit(gid, strain, desc, cpv, n_vials)
        QMessageBox.information(
            self, "Strain frozen",
            f"Strain '{strain}' frozen successfully.\n"
            f"{n_vials} vial(s) x {cpv} cells = {total} cells removed from simulation."
        )

    # ── Tips rebuild ──────────────────────────────────────────────────────────

    def _rebuild_tips(self, mode: str):
        tree    = self._tree
        pops    = self._populations
        events  = self._mut_events
        children = _build_children(tree)
        tips: Dict[int, str] = {}
        for gid in tree:
            if mode in (_MODE_ALL, _MODE_HIDE_EXT):
                tips[gid] = _aggregate_diff(gid, tree, events)
            else:
                vis = {g for g in tree if not _is_extinct(g, pops) or g == 0}
                vp  = _find_visible_parent(gid, tree, vis)
                if vp is None:
                    tips[gid] = _aggregate_diff(gid, tree, events)
                else:
                    # Net diff from vp to gid only
                    sub: Dict[int, List[dict]] = {}
                    cur = gid
                    while cur is not None and cur != vp:
                        sub[cur] = events.get(cur, [])
                        cur = tree.get(cur)
                    tips[gid] = _aggregate_diff(gid, {g: tree.get(g) for g in sub} | {vp: None}, sub)
        self._canvas._node_tips = tips
        self._canvas.update()

    # ── Public API ────────────────────────────────────────────────────────────

    def push_data(self,
                  genome_tree:    Dict[int, Optional[int]],
                  populations:    Dict[int, Tuple[int, float]],
                  max_ever:       Dict[int, int],
                  mut_log:        List[dict],
                  genome_presets: Dict[int, dict] = None,
                  genome_labels:  Dict[int, str]  = None):
        self._tree           = genome_tree
        self._populations    = populations
        self._max_ever       = max_ever
        self._genome_presets = genome_presets or {}

        # Accumulate full history (never prune)
        for ev in mut_log:
            cid = ev.get("ChildGenomeID")
            if cid is not None and ev not in self._mut_log:
                self._mut_log.append(ev)

        # Rebuild per-gid event index
        self._mut_events = {}
        for ev in self._mut_log:
            cid = ev.get("ChildGenomeID")
            if cid is not None:
                self._mut_events.setdefault(cid, []).append(ev)

        # Build aggregated tips
        mode = self._canvas._mode
        tips: Dict[int, str] = {}
        for gid in genome_tree:
            tips[gid] = _aggregate_diff(gid, genome_tree, self._mut_events)
        self._canvas._node_tips = tips

        # Update combo
        all_ids = sorted(genome_tree.keys())
        self._centre_combo.blockSignals(True)
        self._centre_combo.clear()
        for gid in all_ids:
            self._centre_combo.addItem(f"G{gid}", gid)
        self._centre_combo.blockSignals(False)

        self._genome_labels = genome_labels or {}
        self._canvas._genome_labels = self._genome_labels
        self._canvas.push_data(genome_tree, populations, max_ever,
                                self._mut_events, tips, self._genome_presets)

    def set_live_genomes(self, live_genome_objs: dict):
        """Pass {gid: Genome} so we can build presets from live objects."""
        self._live_genome_objs = dict(live_genome_objs)

    def _build_preset(self, gid: int) -> dict:
        """Build a genome preset dict from the live Genome object for gid.
        Falls back to stored _genome_presets if no live object available."""
        live_g = self._live_genome_objs.get(gid)
        if live_g is not None:
            from gui.utils.collections import genome_to_preset
            preset = genome_to_preset(live_g)
            # Merge cellular_products from stored data
            stored = self._genome_presets.get(gid, {})
            if 'cellular_products' in stored:
                preset['cellular_products'] = stored['cellular_products']
            return preset
        return self._genome_presets.get(gid, {})

    def update(self, genome_tree, populations, max_ever,  # type: ignore
               mut_log=None, genome_presets=None, genome_labels=None):
        self.push_data(genome_tree, populations, max_ever,
                       mut_log or [], genome_presets or {}, genome_labels or {})
