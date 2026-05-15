"""
gui/screens/env_screen.py  —  Page 2: Environment Editor

Changes
-------
• Toxin header: added "− Remove all" button next to "+ Add toxin".
• QCheckBox for "Infinite mode" styled with visible indicator.
• "Save env" → "Save environment".
"""

from __future__ import annotations
import copy
from typing import Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QCheckBox, QFrame, QInputDialog, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    BG_DARK, BG_PANEL, ACCENT, ACCENT2, DANGER,
    TEXT_PRIMARY, TEXT_MUTED, BORDER, btn_style,
)
from gui.utils.collections import (
    load_env_collection, save_env_to_collection, STABLE_ENV_PRESET,
)

_TOX_PARAMS = ["energy", "TPM", "common"]
_ED_STYLE = (
    f"background:{BG_DARK};color:{TEXT_PRIMARY};"
    f"border:1px solid {BORDER};border-radius:3px;padding:4px;"
)
_CB_STYLE = f"background:{BG_DARK};color:{TEXT_PRIMARY};border:1px solid {BORDER};"

_CHK_STYLE = (
    f"QCheckBox{{color:{TEXT_PRIMARY};font-size:13px;spacing:8px;}}"
    f"QCheckBox::indicator{{width:16px;height:16px;"
    f"border:2px solid #768390;border-radius:3px;background:#21262d;}}"
    f"QCheckBox::indicator:checked{{background:{ACCENT};"
    f"border:2px solid {ACCENT};image:none;}}"
    f"QCheckBox::indicator:hover{{border:2px solid #adbac7;}}"
)

_DEL_ROW_STYLE = (
    "QPushButton{background:#6e3030;color:#fff;border:none;"
    "border-radius:2px;font-size:11px;font-weight:bold;padding:0px;}"
    "QPushButton:hover{background:#da3633;}"
)


# ── ToxinRowWidget ────────────────────────────────────────────────────────────

class ToxinRowWidget(QWidget):
    delete_requested = pyqtSignal(object)

    def __init__(self, name="Toxin", sigma=-3.0, param="energy", base=0.01,
                 parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(6)

        self._name_ed = QLineEdit(str(name))
        self._name_ed.setPlaceholderText("Name")
        self._name_ed.setStyleSheet(_ED_STYLE)
        self._name_ed.setMinimumWidth(110)

        self._sigma_ed = QLineEdit(str(sigma))
        self._sigma_ed.setPlaceholderText("σ")
        self._sigma_ed.setStyleSheet(_ED_STYLE)
        self._sigma_ed.setFixedWidth(55)

        self._param_cb = QComboBox()
        self._param_cb.addItems(_TOX_PARAMS)
        if param in _TOX_PARAMS: self._param_cb.setCurrentText(param)
        self._param_cb.setStyleSheet(_CB_STYLE)
        self._param_cb.setFixedWidth(80)

        self._base_ed = QLineEdit(str(base))
        self._base_ed.setPlaceholderText("coeff")
        self._base_ed.setStyleSheet(_ED_STYLE)
        self._base_ed.setFixedWidth(65)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(28, 28)
        del_btn.setStyleSheet(_DEL_ROW_STYLE)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self))

        lay.addWidget(self._name_ed, stretch=1)
        lay.addWidget(QLabel("σ:", styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))
        lay.addWidget(self._sigma_ed)
        lay.addWidget(QLabel("→", styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))
        lay.addWidget(self._param_cb)
        lay.addWidget(QLabel("×", styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))
        lay.addWidget(self._base_ed)
        lay.addWidget(del_btn)

    def get_data(self):
        name = self._name_ed.text().strip()
        try:    sigma = float(self._sigma_ed.text())
        except: sigma = -3.0
        param = self._param_cb.currentText()
        try:    base = float(self._base_ed.text())
        except: base = 0.01
        return name, sigma, param, base


# ── ToxinListWidget ───────────────────────────────────────────────────────────

class ToxinListWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        lbl = QLabel("  TOXINS IN ENVIRONMENT")
        lbl.setStyleSheet(f"color:{ACCENT2};font-weight:bold;font-size:12px;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        add_btn = QPushButton("+ Add toxin")
        add_btn.setStyleSheet(btn_style(ACCENT2, font_size=11, padding="3px 10px"))
        add_btn.clicked.connect(lambda: self._add_row())   # lambda prevents bool arg

        clr_btn = QPushButton("− Remove all")
        clr_btn.setStyleSheet(btn_style("#6e3030", font_size=11, padding="3px 10px"))
        clr_btn.clicked.connect(self._remove_all)

        hdr.addWidget(add_btn)
        hdr.addWidget(clr_btn)
        lay.addLayout(hdr)

        self._rows_widget = QWidget()
        self._rows_widget.setStyleSheet(f"background:{BG_PANEL};border-radius:4px;")
        self._rows_lay = QVBoxLayout(self._rows_widget)
        self._rows_lay.setContentsMargins(4, 4, 4, 4)
        self._rows_lay.setSpacing(3)
        lay.addWidget(self._rows_widget)

        self._rows: list = []

    def load_toxins(self, toxins: Dict[str, list]):
        for r in list(self._rows):
            self._remove_row(r)
        for name, rec in toxins.items():
            self._add_row(name, rec[0], rec[1], rec[2])

    def get_toxins(self) -> Dict[str, list]:
        result = {}
        for row in self._rows:
            name, sigma, param, base = row.get_data()
            if name:
                result[name] = [sigma, param, base]
        return result

    def _add_row(self, name="Toxin", sigma=-3.0, param="energy", base=0.01):
        row = ToxinRowWidget(name, sigma, param, base)
        row.delete_requested.connect(self._remove_row)
        self._rows.append(row)
        self._rows_lay.addWidget(row)

    def _remove_row(self, row):
        if row in self._rows:
            self._rows.remove(row)
            self._rows_lay.removeWidget(row)
            row.deleteLater()

    def _remove_all(self):
        for r in list(self._rows):
            self._remove_row(r)


# ── EnvScreen ─────────────────────────────────────────────────────────────────

class EnvScreen(QWidget):
    confirmed = pyqtSignal(dict)

    def __init__(self, genome_products=None, parent=None):
        super().__init__(parent)
        self._genome_products = genome_products or {}
        self._preset = copy.deepcopy(STABLE_ENV_PRESET)
        self._build_ui()
        self._load_preset(self._preset)

    def set_genome_products(self, products):
        self._genome_products = products

    def _build_ui(self):
        self.setStyleSheet(f"background:{BG_DARK};color:{TEXT_PRIMARY};")
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Fixed top bar ─────────────────────────────────────────────────────
        top_frame = QFrame()
        top_frame.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border-bottom:1px solid {BORDER};}}")
        top_lay = QHBoxLayout(top_frame)
        top_lay.setContentsMargins(16, 10, 16, 10)

        title = QLabel("🌍  Environment Editor")
        title.setStyleSheet("font-size:18px;font-weight:bold;color:#e6edf3;")
        top_lay.addWidget(title)
        top_lay.addStretch()

        self._coll_combo = QComboBox()
        self._coll_combo.setMinimumWidth(200)
        self._coll_combo.setStyleSheet(
            f"background:{BG_DARK};color:{TEXT_PRIMARY};border:1px solid {BORDER};padding:4px;")
        load_btn = QPushButton("Load")
        load_btn.setStyleSheet(btn_style(ACCENT2, padding="4px 12px", font_size=12))
        load_btn.clicked.connect(self._on_load)
        top_lay.addWidget(QLabel("Collection:", styleSheet=f"color:{TEXT_MUTED};"))
        top_lay.addWidget(self._coll_combo)
        top_lay.addWidget(load_btn)
        self._refresh_collection()
        root.addWidget(top_frame)

        # ── Scrollable content ────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:{BG_DARK};}}")
        content = QWidget()
        content.setStyleSheet(f"background:{BG_DARK};")
        sc = QVBoxLayout(content)
        sc.setContentsMargins(16, 12, 16, 12)
        sc.setSpacing(12)

        self._tox_list = ToxinListWidget()
        sc.addWidget(self._tox_list)

        pf = QFrame()
        pf.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border:1px solid {BORDER};"
            f"border-radius:6px;padding:8px;}}")
        grid = QGridLayout(pf)
        grid.setSpacing(10)

        def field(lbl_txt, val):
            lbl = QLabel(lbl_txt); lbl.setStyleSheet(f"color:{TEXT_MUTED};")
            ed  = QLineEdit(str(val)); ed.setStyleSheet(_ED_STYLE)
            return lbl, ed

        lbl_food,  self._ed_food  = field("Initial food (σ)",        -3.0)
        lbl_cap,   self._ed_cap   = field("Capacity (support cells)",  1000)
        lbl_ticks, self._ed_ticks = field("Max ticks",                 3000)
        lbl_tk,    self._ed_tk    = field("Toxin k (global scale)",    1.0)
        lbl_mut,   self._ed_mut   = field("Mutation chance / tick",    0.001)
        lbl_ng,    self._ed_ng    = field("Max genome lineages",        5)

        # Styled checkbox — explicitly visible in dark theme
        self._inf_chk = QCheckBox("Infinite mode (run until extinction)")
        self._inf_chk.setStyleSheet(_CHK_STYLE)
        self._inf_chk.stateChanged.connect(
            lambda s: self._ed_ticks.setEnabled(not bool(s)))

        for (lbl, ed), r, c in [
            ((lbl_food,  self._ed_food),  0, 0),
            ((lbl_cap,   self._ed_cap),   0, 2),
            ((lbl_ticks, self._ed_ticks), 1, 0),
            ((lbl_tk,    self._ed_tk),    1, 2),
            ((lbl_mut,   self._ed_mut),   2, 0),
            ((lbl_ng,    self._ed_ng),    2, 2),
        ]:
            grid.addWidget(lbl, r, c)
            grid.addWidget(ed,  r, c + 1)
        grid.addWidget(self._inf_chk, 3, 0, 1, 4)
        sc.addWidget(pf)

        # ── Genome launch list ────────────────────────────────────────────
        gp = QFrame()
        gp.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border:1px solid {BORDER};"
            f"border-radius:6px;padding:6px;}}")
        gp_lay = QVBoxLayout(gp)
        gp_lay.setSpacing(4)

        gp_hdr = QHBoxLayout()
        gp_lbl = QLabel("Genomes at launch:")
        gp_lbl.setStyleSheet(f"color:{ACCENT2};font-weight:bold;font-size:11px;")
        gp_hdr.addWidget(gp_lbl)
        gp_hdr.addStretch()
        gp_lay.addLayout(gp_hdr)

        self._genome_rows_lay = QVBoxLayout()
        self._genome_rows_lay.setSpacing(3)
        gp_lay.addLayout(self._genome_rows_lay)
        sc.addWidget(gp)
        sc.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        # ── Fixed bottom bar ──────────────────────────────────────────────────
        bot_frame = QFrame()
        bot_frame.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border-top:1px solid {BORDER};}}")
        bot_lay = QHBoxLayout(bot_frame)
        bot_lay.setContentsMargins(16, 8, 16, 8)

        back_btn = QPushButton("← Genome")
        back_btn.setStyleSheet(btn_style("#3a3f47"))
        back_btn.clicked.connect(lambda: self.go_back())

        self._save_btn = QPushButton("💾  Save environment")
        self._save_btn.setStyleSheet(btn_style(ACCENT2))
        self._save_btn.clicked.connect(self._on_save)

        self._confirm_btn = QPushButton("✔  Confirm")
        self._confirm_btn.setStyleSheet(btn_style(ACCENT))
        self._confirm_btn.clicked.connect(self._on_confirm)

        self._launch_btn = QPushButton("▶  Launch simulation")
        self._launch_btn.setStyleSheet(btn_style("#8957e5"))
        self._launch_btn.setEnabled(False)

        bot_lay.addWidget(back_btn)
        bot_lay.addStretch()
        bot_lay.addWidget(self._save_btn)
        bot_lay.addWidget(self._confirm_btn)
        bot_lay.addWidget(self._launch_btn)
        root.addWidget(bot_frame)

    # ── Cryo / genome list ────────────────────────────────────────────────

    def set_cryo_injections(self, injections: list):
        """Called by MainWindow after genome is confirmed."""
        self._cryo_injections = list(injections)
        self._refresh_genome_rows()

    def get_cryo_injections(self) -> list:
        return getattr(self, '_cryo_injections', [])

    def clear_cryo_injections(self):
        """Called after simulation launch to reset the genome list."""
        self._cryo_injections = []
        self._refresh_genome_rows()

    def set_pending_populations(self, populations: list):
        """
        Called by some versions of MainWindow to show pending genomes.
        Delegates to set_cryo_injections if the population entries have
        the expected format, otherwise stores them for later use.
        """
        # Normalise: accept both {preset, cells, name} and legacy formats
        normalised = []
        for p in populations:
            if isinstance(p, dict):
                normalised.append({
                    "preset": p.get("preset", p.get("genome_preset", {})),
                    "cells":  p.get("cells", p.get("cell_count", 1)),
                    "name":   p.get("name", p.get("strain_name", "unknown")),
                })
        self._cryo_injections = normalised
        self._refresh_genome_rows()

    def use_editor_genome(self) -> bool:
        """True if the genome from the editor should be included."""
        return getattr(self, '_use_editor', True)

    def _refresh_genome_rows(self):
        # Clear existing rows
        while self._genome_rows_lay.count():
            item = self._genome_rows_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Editor genome row
        self._use_editor = True
        editor_row = QHBoxLayout()
        self._editor_chk = QPushButton("✕")
        self._editor_chk.setFixedSize(22, 22)
        self._editor_chk.setCheckable(True)
        self._editor_chk.setChecked(False)
        self._editor_chk.setStyleSheet(
            "QPushButton{background:#3a3f47;color:#aaa;border:none;"
            "border-radius:3px;font-size:10px;}"
            "QPushButton:checked{background:#da3633;color:#fff;}"
        )
        self._editor_chk.setToolTip("Click to exclude editor genome from launch")
        self._editor_chk.clicked.connect(self._on_editor_toggle)
        self._editor_lbl = QLabel("📝 Editor genome (cells from genome editor)")
        self._editor_lbl.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:11px;")
        editor_row.addWidget(self._editor_chk)
        editor_row.addWidget(self._editor_lbl)
        editor_row.addStretch()
        row_w = QWidget(); row_w.setLayout(editor_row)
        self._genome_rows_lay.addWidget(row_w)

        # Cryo rows
        for i, inj in enumerate(getattr(self, '_cryo_injections', [])):
            self._add_cryo_row(i, inj)

    def _on_editor_toggle(self, checked):
        self._use_editor = not checked
        self._editor_lbl.setStyleSheet(
            f"color:{'#555' if checked else TEXT_PRIMARY};font-size:11px;"
            + ("text-decoration:line-through;" if checked else "")
        )

    def _add_cryo_row(self, idx: int, inj: dict):
        row = QHBoxLayout()
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(22, 22)
        del_btn.setStyleSheet(
            "QPushButton{background:#6e3030;color:#fff;border:none;"
            "border-radius:3px;font-size:10px;}"
            "QPushButton:hover{background:#da3633;}"
        )
        del_btn.clicked.connect(lambda _, i=idx: self._remove_cryo(i))
        name  = inj.get('name', '?')
        cells = inj.get('cells', '?')
        lbl   = QLabel(f"❄ {name}  ({cells} cells)")
        lbl.setStyleSheet(f"color:#79c0ff;font-size:11px;")
        row.addWidget(del_btn)
        row.addWidget(lbl)
        row.addStretch()
        row_w = QWidget(); row_w.setLayout(row)
        self._genome_rows_lay.addWidget(row_w)

    def _remove_cryo(self, idx: int):
        inj = getattr(self, '_cryo_injections', [])
        if 0 <= idx < len(inj):
            inj.pop(idx)
        self._refresh_genome_rows()

    def go_back(self): pass

    @property
    def launch_button(self) -> QPushButton:
        return self._launch_btn

    def _refresh_collection(self):
        self._coll_combo.clear()
        for name in load_env_collection():
            self._coll_combo.addItem(name)

    def _load_preset(self, preset: Dict):
        self._tox_list.load_toxins(preset.get("toxins", {}))
        self._ed_food.setText(str(preset.get("initial_food", -3.0)))
        self._ed_cap.setText(str(preset.get("support_cell_num", 1000)))
        self._ed_ticks.setText(str(preset.get("ticks", 3000)))
        self._inf_chk.setChecked(preset.get("infinite", False))
        self._ed_tk.setText(str(preset.get("toxin_k", 1.0)))
        self._ed_mut.setText(str(preset.get("mutation_chance", 0.001)))
        self._ed_ng.setText(str(preset.get("n_genomes_allowed", 5)))

    def _collect_preset(self) -> Dict:
        p = {"toxins": self._tox_list.get_toxins()}
        try:    p["initial_food"]      = float(self._ed_food.text())
        except: p["initial_food"]      = -3.0
        try:    p["support_cell_num"]  = int(self._ed_cap.text())
        except: p["support_cell_num"]  = 1000
        try:    p["ticks"]             = int(self._ed_ticks.text())
        except: p["ticks"]             = 3000
        p["infinite"]                  = self._inf_chk.isChecked()
        try:    p["toxin_k"]           = float(self._ed_tk.text())
        except: p["toxin_k"]           = 1.0
        try:    p["mutation_chance"]   = float(self._ed_mut.text())
        except: p["mutation_chance"]   = 0.001
        try:    p["n_genomes_allowed"] = int(self._ed_ng.text())
        except: p["n_genomes_allowed"] = 5
        return p

    def _on_load(self):
        col = load_env_collection()
        name = self._coll_combo.currentText()
        if name in col:
            self._load_preset(col[name])

    def _on_confirm(self):
        self._launch_btn.setEnabled(True)
        self.confirmed.emit(self._collect_preset())

    def _on_save(self):
        name, ok = QInputDialog.getText(self, "Save environment", "Collection name:")
        if ok and name.strip():
            save_env_to_collection(name.strip(), self._collect_preset())
            self._refresh_collection()

    def get_confirmed_preset(self) -> Dict:
        return self._collect_preset()

    def get_toxin_names(self) -> list:
        return list(self._tox_list.get_toxins().keys())
