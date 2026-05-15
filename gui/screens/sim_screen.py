"""
gui/screens/sim_screen.py  —  Page 3: Live Simulation

Changes in this version
-----------------------
• Top bar: [⏸][−][▶][+]  Tick: N  Genomes: M  Cells: K  [horizontal food bar]
  [■ Finish]  ← Finish moved to top-right corner.
• Cells label turns red when total_cells > capacity.
• Genomes count label (white).
• Horizontal food bar spans the full top-strip width.
• Mutation slider relabelled ☢ Mutation chance.
• All buttons have hover/press feedback via btn_style.
• Bottom: BoxplotWidget (with built-in genome selector buttons on the right).
• New [🌿 Dendrogram] button bottom-right → page 4.
• Finish saves records AND mutation log.
• genome_tree / max_ever tracking for dendrogram.
"""

from __future__ import annotations
import os
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSizePolicy, QFileDialog, QMessageBox,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    BG_DARK, BG_PANEL, ACCENT, ACCENT2, DANGER, WARNING,
    TEXT_PRIMARY, TEXT_MUTED, BORDER, DEFAULT_TPS, SPEED_FACTOR,
    btn_style, genome_color,
)
from gui.utils.sim_runner    import SimRunner, TickState
from gui.widgets.field_widget     import FieldWidget
from gui.widgets.gauge_widget     import GaugeWidget
from gui.widgets.food_bar_h       import FoodBarH
from gui.widgets.boxplot_widget   import BoxplotWidget
from gui.widgets.population_widget import PopulationWidget
from gui.widgets.energy_bars_widget import EnergyBarsWidget


# ── helpers ───────────────────────────────────────────────────────────────────

def _lbl(text: str, color: str = TEXT_PRIMARY, size: int = 13,
         bold: bool = False) -> QLabel:
    w = QLabel(text)
    weight = "bold" if bold else "normal"
    w.setStyleSheet(
        f"color:{color};font-family:Consolas;font-size:{size}px;"
        f"font-weight:{weight};")
    return w


def _sep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet(f"background:{BORDER};"); f.setFixedWidth(1)
    return f


# ── Mutation slider ───────────────────────────────────────────────────────────

class MutSlider(QWidget):
    value_changed = pyqtSignal(float)
    _SCALE = 10000

    def __init__(self, initial: float = 0.001, parent=None):
        super().__init__(parent)
        self._value = initial
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        hdr = QHBoxLayout()
        hdr.addWidget(_lbl("☢ Mutation chance", TEXT_MUTED, 11))
        self._val_lbl = _lbl(f"{initial:.4f}", TEXT_PRIMARY, 11)
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        hdr.addWidget(self._val_lbl)
        lay.addLayout(hdr)

        row = QHBoxLayout(); row.setSpacing(3)
        m_btn = QPushButton("−"); m_btn.setFixedSize(26, 22)
        m_btn.setStyleSheet(btn_style("#3a3f47", padding="0px", font_size=13))
        p_btn = QPushButton("+"); p_btn.setFixedSize(26, 22)
        p_btn.setStyleSheet(btn_style("#3a3f47", padding="0px", font_size=13))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, int(0.20 * self._SCALE))
        self._slider.setValue(int(initial * self._SCALE))
        self._slider.setStyleSheet(
            f"QSlider::groove:horizontal{{background:{BORDER};height:4px;"
            f"border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{ACCENT};width:12px;"
            f"height:12px;margin:-4px 0;border-radius:6px;}}"
            f"QSlider::sub-page:horizontal{{background:{ACCENT};"
            f"border-radius:2px;}}"
        )
        self._slider.valueChanged.connect(self._on_slide)
        m_btn.clicked.connect(lambda: self._step(-1))
        p_btn.clicked.connect(lambda: self._step(+1))
        row.addWidget(m_btn); row.addWidget(self._slider, 1); row.addWidget(p_btn)
        lay.addLayout(row)

    @property
    def value(self) -> float:
        return self._value

    def _on_slide(self, v: int):
        self._value = v / self._SCALE
        self._val_lbl.setText(f"{self._value:.4f}")
        self.value_changed.emit(self._value)

    def _step(self, d: int):
        step = max(1, int(0.001 * self._SCALE))
        self._slider.setValue(self._slider.value() + d * step)


# ── _DropButton ───────────────────────────────────────────────────────────────

class _DropButton(QPushButton):
    """
    QPushButton that draws N water-drop emoji at full size, overlapping,
    centred in the button.  Supports an "active" state that turns the
    background red (for the continuous-inject toggle).
    """

    def __init__(self, n_drops: int, base_color: str, parent=None):
        super().__init__(parent)
        self._n      = n_drops
        self._base   = base_color
        self._active = False
        self._update_style()

    def set_active(self, active: bool):
        self._active = active
        self._update_style()
        self.update()

    def _update_style(self):
        bg = "#da3633" if self._active else self._base
        self.setStyleSheet(btn_style(bg, padding="0px", font_size=1))

    def paintEvent(self, event):
        # Draw the button background / frame via the normal mechanism
        super().paintEvent(event)

        from PyQt6.QtGui import QFont, QPainter, QColor
        from PyQt6.QtCore import Qt, QRect

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # drop_size = font pixel size for the emoji.
        # The drawing rect is made taller (+ extra_h) so the bottom of the
        # teardrop shape is not clipped by the rect boundary.
        w, h      = self.width(), self.height()
        drop_size = h - 14
        extra_h   = drop_size // 3   # extra height below so tail is not clipped
        overlap   = drop_size // 2

        total_w = drop_size + (self._n - 1) * (drop_size - overlap)
        x0 = (w - total_w) // 2
        # Shift upward slightly so the emoji sits centred visually
        y0 = (h - drop_size) // 2 - extra_h // 3

        font = QFont()
        font.setPixelSize(drop_size)
        p.setFont(font)

        for i in range(self._n):
            x = x0 + i * (drop_size - overlap)
            # Rect is taller than drop_size to avoid bottom clip
            p.drawText(QRect(x, y0, drop_size, drop_size + extra_h),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       "💧")

        p.end()


# ── ExtGaugeBlock ─────────────────────────────────────────────────────────────
#
# Three injection controls per gauge:
#   [+0.5σ] — cycle selector: 0.5 → 1.0 → 1.5 → 2.0 → 2.5 → 3.0 → 0.5 …
#   [💧]    — inject selected dose once on next tick
#   [💧💧💧]  — toggle continuous injection every tick (turns red when active)

class ExtGaugeBlock(QWidget):
    inject_once       = pyqtSignal(str, float)   # (toxin_name, delta)
    inject_continuous = pyqtSignal(str, float)   # start continuous: (name, delta)
    inject_stop       = pyqtSignal(str)           # stop continuous: name

    _DOSE_STEPS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

    def __init__(self, ext_toxin_names: List[str], parent=None):
        super().__init__(parent)
        self._dose_idx = 0          # index into _DOSE_STEPS
        self._continuous = False    # is continuous injection active?

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        choices = ext_toxin_names or ["—"]
        self._gauge = GaugeWidget(choices)
        lay.addWidget(self._gauge)

        # Row of three buttons
        row = QHBoxLayout(); row.setSpacing(3)

        # Dose selector button — cycles through steps
        self._dose_btn = QPushButton("+0.5σ")
        self._dose_btn.setStyleSheet(btn_style("#3a3f47", font_size=10, padding="2px 4px"))
        self._dose_btn.setToolTip("Click to cycle dose: 0.5 → 1.0 → … → 3.0")
        self._dose_btn.clicked.connect(self._cycle_dose)

        # Both drop buttons: same fixed size, drops drawn via QPainter subclass
        BTN_W, BTN_H = 35, 27

        self._once_btn = _DropButton(1, "#1a4a6e")
        self._once_btn.setFixedSize(BTN_W, BTN_H)
        self._once_btn.setToolTip("Inject selected dose once on next tick")
        self._once_btn.clicked.connect(self._on_inject_once)

        self._cont_btn = _DropButton(3, "#1a4a6e")
        self._cont_btn.setFixedSize(BTN_W, BTN_H)
        self._cont_btn.setCheckable(True)
        self._cont_btn.setToolTip("Toggle: inject selected dose every tick continuously")
        self._cont_btn.clicked.connect(self._on_toggle_continuous)

        self._dose_btn.setFixedHeight(BTN_H)

        row.addWidget(self._dose_btn, stretch=1)
        row.addWidget(self._once_btn)
        row.addWidget(self._cont_btn)
        lay.addLayout(row)

    def update_data(self, d: Dict[str, float]):
        self._gauge.update_data(d)

    @property
    def _dose(self) -> float:
        return self._DOSE_STEPS[self._dose_idx]

    def _cycle_dose(self):
        self._dose_idx = (self._dose_idx + 1) % len(self._DOSE_STEPS)
        self._dose_btn.setText(f"+{self._dose:.1f}σ")
        # If continuous is running, update its rate immediately
        if self._continuous:
            name = self._gauge._selected
            if name and name != "—":
                self.inject_continuous.emit(name, self._dose)

    def _on_inject_once(self):
        name = self._gauge._selected
        if name and name != "—":
            self.inject_once.emit(name, self._dose)

    def _on_toggle_continuous(self, checked: bool):
        self._continuous = checked
        name = self._gauge._selected
        if not name or name == "—":
            self._cont_btn.setChecked(False)
            self._continuous = False
            return
        if checked:
            self._cont_btn.set_active(True)
            self._cont_btn.setToolTip(
                f"Continuous injection active: +{self._dose:.1f}σ/tick — click to stop")
            self.inject_continuous.emit(name, self._dose)
        else:
            self._cont_btn.set_active(False)
            self._cont_btn.setToolTip(
                "Toggle: inject selected dose every tick continuously")
            self.inject_stop.emit(name)


# ── SimScreen ─────────────────────────────────────────────────────────────────

class SimScreen(QWidget):
    finished    = pyqtSignal()
    open_dendro = pyqtSignal()   # → page 4

    def __init__(
        self,
        runner:           SimRunner,
        toxin_names:      List[str],
        product_names:    List[str],
        all_gene_names:   List[str],
        capacity:         int   = 1000,
        initial_mutation: float = 0.001,
        parent=None,
    ):
        super().__init__(parent)
        self._runner        = runner
        self._all_tox       = toxin_names
        self._prod_names    = product_names
        self._all_genes     = all_gene_names
        self._capacity      = capacity
        self._tps           = DEFAULT_TPS
        self._playing       = False
        self._final_data    = None

        prod_set            = set(product_names)
        self._ext_tox       = [t for t in toxin_names if t not in prod_set]
        self._prod_choices  = product_names or ["—"]

        # Dendrogram data — initialised from runner's live_genomes
        # (populated in start() after runner is running)
        self._genome_tree:  Dict[int, Optional[int]] = {}
        self._max_ever:     Dict[int, int]           = {}
        self._genome_labels: Dict[int, str]          = {}  # gid -> display name

        self.setStyleSheet(f"background:{BG_DARK};color:{TEXT_PRIMARY};")
        self._build_ui()
        self._connect_runner()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(4)

        # ── TOP BAR ──────────────────────────────────────────────────────────
        top_frame = QFrame()
        top_frame.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border-bottom:1px solid {BORDER};"
            f"border-radius:0px;}}")
        top_lay = QVBoxLayout(top_frame)
        top_lay.setContentsMargins(8, 6, 8, 4)
        top_lay.setSpacing(4)

        # Row 1: controls + labels + Finish
        row1 = QHBoxLayout(); row1.setSpacing(5)

        self._pause_btn = QPushButton("⏸"); self._pause_btn.setFixedSize(40, 30)
        self._minus_btn = QPushButton("−");  self._minus_btn.setFixedSize(30, 30)
        self._play_btn  = QPushButton("▶"); self._play_btn.setFixedSize(40, 30)
        self._plus_btn  = QPushButton("+");  self._plus_btn.setFixedSize(30, 30)
        self._pause_btn.setStyleSheet(btn_style(WARNING, padding="2px"))
        self._minus_btn.setStyleSheet(btn_style("#3a3f47", padding="2px"))
        self._play_btn.setStyleSheet(btn_style(ACCENT, padding="2px"))
        self._plus_btn.setStyleSheet(btn_style("#3a3f47", padding="2px"))

        self._pause_btn.clicked.connect(self._on_pause)
        self._minus_btn.clicked.connect(self._on_minus)
        self._play_btn.clicked.connect(self._on_play)
        self._plus_btn.clicked.connect(self._on_plus)

        self._tick_lbl    = _lbl("Tick: 0", bold=True, size=14)
        self._tps_lbl     = _lbl(f"TPS: {self._tps:.2f}", TEXT_MUTED, 12)
        # Clickable toggle: switches between Genomes count and Mutations count
        self._counter_mode = 'genomes'   # 'genomes' | 'mutations'
        self._total_mutations = 0
        self._genomes_lbl = QPushButton("Genomes: 1")
        self._genomes_lbl.setFlat(True)
        self._genomes_lbl.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_PRIMARY};"
            f"font-family:Consolas;font-size:13px;border:none;padding:0px;}}"
            f"QPushButton:hover{{color:#ffffff;text-decoration:underline;}}"
        )
        self._genomes_lbl.setToolTip(
            "Click to toggle between genome count and total mutations")
        self._genomes_lbl.clicked.connect(self._toggle_counter)
        self._cells_lbl   = _lbl("Cells: 0", ACCENT, 13, bold=True)

        finish_btn = QPushButton("■  Finish & Save")
        finish_btn.setStyleSheet(btn_style("#444d58", font_size=12))
        finish_btn.setToolTip("Stop at current tick and save all results")
        finish_btn.clicked.connect(self._on_finish)

        self._food_bar = FoodBarH(height=22)
        self._food_bar.setFixedWidth(160)

        for w in [self._pause_btn, self._minus_btn, self._play_btn, self._plus_btn,
                  _sep(), self._tick_lbl, _sep(), self._tps_lbl, _sep(),
                  self._genomes_lbl, _sep(), self._cells_lbl, _sep(),
                  self._food_bar]:
            row1.addWidget(w)
        row1.addStretch()
        row1.addWidget(finish_btn)
        top_lay.addLayout(row1)

        root.addWidget(top_frame)

        # ── MIDDLE ROW ───────────────────────────────────────────────────────
        mid = QHBoxLayout(); mid.setSpacing(6)

        mid.addWidget(self._build_left_panel())
        self._field = FieldWidget()
        self._field.reset(self._capacity)
        mid.addWidget(self._field, stretch=3)
        mid.addWidget(self._build_right_panel())
        root.addLayout(mid, stretch=4)

        # ── BOXPLOT ──────────────────────────────────────────────────────────
        self._boxplot = BoxplotWidget(self._all_genes)
        self._boxplot.setMinimumHeight(130)
        self._boxplot.setMaximumHeight(190)
        root.addWidget(self._boxplot, stretch=1)

        # ── FOOTER ───────────────────────────────────────────────────────────
        foot = QHBoxLayout()
        foot.addStretch()
        dendro_btn = QPushButton("🌿  Dendrogram")
        dendro_btn.setStyleSheet(btn_style("#2d6a4f", font_size=12))
        dendro_btn.clicked.connect(self.open_dendro.emit)
        foot.addWidget(dendro_btn)
        root.addLayout(foot)

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(178)
        panel.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border:1px solid {BORDER};"
            f"border-radius:6px;}}")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        ext_choices = self._ext_tox or ["—"]
        self._ext_gauges: List[ExtGaugeBlock] = []
        for i in range(2):
            g = ExtGaugeBlock(ext_choices)
            if len(ext_choices) > i:
                g._gauge._combo.setCurrentIndex(i % len(ext_choices))
                g._gauge._selected = ext_choices[i % len(ext_choices)]
            g.inject_once.connect(self._on_inject_named)
            g.inject_continuous.connect(self._on_inject_continuous)
            g.inject_stop.connect(self._on_inject_stop)
            lay.addWidget(g)
            self._ext_gauges.append(g)
            if i < 1:
                f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
                f.setStyleSheet(f"background:{BORDER};"); f.setFixedHeight(1)
                lay.addWidget(f)

        f2 = QFrame(); f2.setFrameShape(QFrame.Shape.HLine)
        f2.setStyleSheet(f"background:{BORDER};"); f2.setFixedHeight(1)
        lay.addWidget(f2)

        self._mut_slider = MutSlider(self._runner._mutation_chance)
        self._mut_slider.value_changed.connect(self._on_mut_changed)
        lay.addWidget(self._mut_slider)
        lay.addStretch()

        f3 = QFrame(); f3.setFrameShape(QFrame.Shape.HLine)
        f3.setStyleSheet(f"background:{BORDER};"); f3.setFixedHeight(1)
        lay.addWidget(f3)

        reset_btn = QPushButton("☣  RESET  ☣")
        reset_btn.setFixedSize(164, 52)
        reset_btn.setStyleSheet(btn_style(DANGER, font_size=13))
        reset_btn.setToolTip("Destroy all genomes — restart from tick 0")
        reset_btn.clicked.connect(self._on_reset)
        lay.addWidget(reset_btn)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(210)
        panel.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border:1px solid {BORDER};"
            f"border-radius:6px;}}")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self._prod_gauges: List[GaugeWidget] = []
        for i in range(2):
            g = GaugeWidget(self._prod_choices)
            if len(self._prod_choices) > i:
                g._combo.setCurrentIndex(i % len(self._prod_choices))
                g._selected = self._prod_choices[i % len(self._prod_choices)]
            lay.addWidget(g)
            self._prod_gauges.append(g)

        f2 = QFrame(); f2.setFrameShape(QFrame.Shape.HLine)
        f2.setStyleSheet(f"background:{BORDER};"); f2.setFixedHeight(1)
        lay.addWidget(f2)

        self._pop_widget = PopulationWidget()
        self._pop_widget.setMinimumHeight(55)
        self._pop_widget.setMaximumHeight(110)
        lay.addWidget(self._pop_widget)

        f3 = QFrame(); f3.setFrameShape(QFrame.Shape.HLine)
        f3.setStyleSheet(f"background:{BORDER};"); f3.setFixedHeight(1)
        lay.addWidget(f3)

        en_lbl = QLabel("⚡ Energy (σ)")
        en_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
        lay.addWidget(en_lbl)

        self._energy_bars = EnergyBarsWidget()
        lay.addWidget(self._energy_bars)
        lay.addStretch()
        return panel

    # ── Runner ────────────────────────────────────────────────────────────────

    def _connect_runner(self):
        self._runner.signals.tick_done.connect(self._on_tick)
        self._runner.signals.sim_finished.connect(self._on_sim_finished)
        self._runner.signals.sim_error.connect(self._on_error)

    def start(self):
        self._runner.set_tps(self._tps)
        self._runner.resume()
        self._runner.start()
        self._playing = True
        # Initialise genome_tree from runner: all starting genomes are roots
        import time; time.sleep(0.05)  # brief wait for runner to initialise
        live = getattr(self._runner, '_live_genomes_ref', {})
        for gid, g in live.items():
            self._genome_tree[gid] = g.parent_id  # None for all roots
            self._genome_labels[gid] = getattr(g, '_strain_name',
                                                f'G{gid}')

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _on_tick(self, state: TickState):
        total = sum(cnt for cnt, _ in state.populations.values())
        n_gen = len(state.populations)

        self._total_mutations = len(getattr(self._runner, 'all_mut_log', []))
        self._tick_lbl.setText(f"Tick: {state.tick}")
        self._update_counter_label(n_gen)

        over_cap = total > self._capacity
        self._cells_lbl.setText(f"Cells: {total:,}")
        self._cells_lbl.setStyleSheet(
            f"color:{'#ff4444' if over_cap else ACCENT};"
            f"font-family:Consolas;font-size:13px;font-weight:bold;")

        # Update lineage tree
        for pid, cid in state.new_forks:
            self._genome_tree[cid] = pid
        for gid, (cnt, _) in state.populations.items():
            if gid not in self._genome_tree:
                self._genome_tree[gid] = None
            prev = self._max_ever.get(gid, 0)
            self._max_ever[gid] = max(prev, cnt)

        self._food_bar.set_value(state.food)

        self._field.apply_tick(state.populations, state.new_forks, state.extinct_ids)

        ext_data = {k: v for k, v in state.tox_levels.items()
                    if k in self._ext_tox}
        for g in self._ext_gauges:
            g.update_data(ext_data)

        prod_data = dict(state.product_levels)
        for g in self._prod_gauges:
            g.update_data(prod_data)

        self._pop_widget.update_populations(state.populations)
        counts = {gid: cnt for gid, (cnt, _) in state.populations.items()}
        top5 = sorted(counts, key=lambda g: counts[g], reverse=True)[:5]
        self._energy_bars.set_data(state.populations, top5)
        self._boxplot.update_tick(state.gene_expr)
        self._boxplot.update_genomes(list(state.populations.keys()), counts)

    # ── Controls ──────────────────────────────────────────────────────────────

    def _toggle_counter(self):
        self._counter_mode = (
            'mutations' if self._counter_mode == 'genomes' else 'genomes')
        self._update_counter_label(
            n_gen=None,   # will be refreshed on next tick
        )

    def _update_counter_label(self, n_gen):
        if self._counter_mode == 'genomes':
            if n_gen is not None:
                self._genomes_lbl.setText(f"Genomes: {n_gen}")
        else:
            self._genomes_lbl.setText(f"Mutations: {self._total_mutations}")

    def _on_pause(self):   self._runner.pause();  self._playing = False
    def _on_play(self):    self._runner.resume(); self._playing = True

    def _on_minus(self):
        self._tps = max(0.05, self._tps / SPEED_FACTOR)
        self._runner.set_tps(self._tps)
        self._tps_lbl.setText(f"TPS: {self._tps:.2f}")

    def _on_plus(self):
        self._tps = min(500.0, self._tps * SPEED_FACTOR)
        self._runner.set_tps(self._tps)
        self._tps_lbl.setText(f"TPS: {self._tps:.2f}")

    def _on_mut_changed(self, v: float):
        self._runner._mutation_chance = v

    def _on_inject_named(self, name: str, delta: float):
        self._runner.add_toxin(name, delta)

    def _on_inject_continuous(self, name: str, delta: float):
        self._runner.set_continuous_toxin(name, delta)

    def _on_inject_stop(self, name: str):
        self._runner.clear_continuous_toxin(name)

    def _on_reset(self):
        ans = QMessageBox.question(self, "Reset?",
            "Stop the simulation and return to the genome editor?\n"
            "Unsaved results will be lost.")
        if ans == QMessageBox.StandardButton.Yes:
            self._runner.stop()
            self._runner.wait(2000)
            self.finished.emit()

    # ── Finish / Save ─────────────────────────────────────────────────────────

    def _on_sim_finished(self, data):
        self._final_data = data
        self._playing = False
        QMessageBox.information(self, "Simulation complete",
                                "All ticks done. Click OK to save results.")
        self._save_results()

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Simulation error", msg)

    def _on_finish(self):
        self._runner.pause()
        self._runner.wait(500)

        if self._final_data is not None:
            self._save_results()
            return

        import pandas as pd
        r_records = getattr(self._runner, 'all_records', [])
        r_mut     = getattr(self._runner, 'all_mut_log', [])
        mut_cols  = ["Tick","ParentGenomeID","ParentCellCount",
                     "ChildGenomeID","GeneName","Attribute",
                     "ValueBefore","ValueAfter"]
        df_rec = pd.DataFrame(r_records)
        df_mut = (pd.DataFrame(r_mut, columns=mut_cols)
                  if r_mut else pd.DataFrame(columns=mut_cols))
        self._final_data = (df_rec, df_mut)
        self._save_results()

    def _save_results(self):
        if self._final_data is None:
            QMessageBox.information(self, "Nothing to save",
                                    "No tick data collected yet.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose folder for results")
        if folder:
            df_rec, df_mut = self._final_data
            try:
                df_rec.to_csv(os.path.join(folder, "records.csv"),      index=False)
                df_mut.to_csv(os.path.join(folder, "mutation_log.csv"), index=False)
                QMessageBox.information(
                    self, "Saved",
                    f"Saved {len(df_rec)} tick rows and "
                    f"{len(df_mut)} mutation events to:\n{folder}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Save failed", str(e))
        self.finished.emit()

    # ── Dendrogram data accessor ──────────────────────────────────────────────

    def get_dendro_data(self):
        """Return current data for DendrogramScreen.update()."""
        return self._genome_tree, \
               dict(self._runner.signals.tick_done.__self__._populations
                    if hasattr(self._runner.signals.tick_done, '__self__')
                    else {}), \
               self._max_ever

    @property
    def genome_tree(self):  return self._genome_tree
    @property
    def max_ever(self):     return self._max_ever
