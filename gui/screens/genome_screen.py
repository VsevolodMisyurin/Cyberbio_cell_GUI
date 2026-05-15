"""
gui/screens/genome_screen.py  —  Page 1: Genome Editor

Changes in this version
-----------------------
• Promoter/Enhancer columns show numeric values (1.25/2.0/4.0 and 4/16/64).
• "secret" added to _FTYPES list.
• ProductTableWidget completely redesigned:
    Columns: Name | Source | Cost/unit (energy)
    Source choices: "energy", "TPMsum", or any gene with ftype="secret".
    - Wastetoxin: always present, source=energy, cost fixed at 0.005, not removable.
    - CytokineX: optional, source=TPMsum, cost=0.
    - When a gene gets ftype="secret", a new product row appears automatically.
    - Env button is blocked until all secret genes are linked to a product source.
"""

from __future__ import annotations
import copy
from typing import Dict, Any, Optional, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSizePolicy, QInputDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui  import QFont, QColor

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    BG_DARK, BG_PANEL, ACCENT, ACCENT2, DANGER,
    TEXT_PRIMARY, TEXT_MUTED, BORDER, btn_style,
)
from gui.utils.collections import (
    load_genome_collection, save_genome_to_collection, STABLE_GENOME_PRESET,
)

# Promoter/enhancer default reference values (displayed as wk/av/st in UI)
_PROMOTERS  = [1.25, 2.0, 4.0]
_ENHANCERS  = [4, 16, 64]
_MODES      = ["qual", "quan"]
_FTYPES     = ["—", "energy", "process", "RNAdigest", "div",
               "detox", "toxresist", "mutsens", "mutrep", "toxsens", "secret"]

_ED_STYLE = (
    f"background:{BG_DARK};color:{TEXT_PRIMARY};"
    f"border:1px solid {BORDER};border-radius:3px;padding:4px;"
)
_CB_STYLE = f"background:{BG_DARK};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
_TBL_STYLE = (
    f"QTableWidget{{background:#1c2128;color:{TEXT_PRIMARY};"
    f"gridline-color:{BORDER};border:1px solid {BORDER};}}"
    f"QHeaderView::section{{background:#161b22;color:#adbac7;"
    f"border:none;border-bottom:1px solid {BORDER};padding:4px;"
    f"font-size:11px;font-weight:bold;}}"
    f"QTableWidget::item{{padding:3px;color:{TEXT_PRIMARY};}}"
    f"QTableWidget::item:selected{{background:#2d4a7a;color:#ffffff;}}"
)
_DEL_ROW_STYLE = (
    "QPushButton{background:#6e3030;color:#fff;border:none;"
    "border-radius:2px;font-size:11px;font-weight:bold;padding:0px;}"
    "QPushButton:hover{background:#da3633;}"
)


# ── GeneTableWidget ───────────────────────────────────────────────────────────

class GeneTableWidget(QWidget):
    genes_changed = pyqtSignal()   # emitted when any ftype changes

    _COLS = ["Name", "Thr", "Mode", "Prom", "Enh", "kDa",
             "ON conditions", "OFF conditions", "Func", "Coeff", ""]

    def __init__(self, category_name: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 8)
        lay.setSpacing(3)

        hdr = QHBoxLayout()
        lbl = QLabel(f"  {category_name.upper()}")
        lbl.setStyleSheet(f"color:{ACCENT2};font-weight:bold;font-size:12px;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        add_btn = QPushButton("+ Add gene")
        add_btn.setStyleSheet(btn_style(ACCENT2, font_size=11, padding="3px 10px"))
        add_btn.clicked.connect(lambda: self._append_row())
        clr_btn = QPushButton("− Remove all")
        clr_btn.setStyleSheet(btn_style("#6e3030", font_size=11, padding="3px 10px"))
        clr_btn.clicked.connect(self._clear_all)
        hdr.addWidget(add_btn)
        hdr.addWidget(clr_btn)
        lay.addLayout(hdr)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(10, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(10, 26)
        for col, w in enumerate([110, 40, 60, 65, 65, 55, 0, 0, 90, 70, 26]):
            if 0 < w < 200:
                self._table.setColumnWidth(col, w)
        self._table.setStyleSheet(_TBL_STYLE)
        self._table.setAlternatingRowColors(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.verticalHeader().setVisible(False)
        lay.addWidget(self._table)

    def load_genes(self, genes: Dict[str, list]):
        self._table.setRowCount(0)
        for name, rec in genes.items():
            self._append_row(name, rec)
        self._auto_height()

    def get_genes(self) -> Dict[str, tuple]:
        result = {}
        for row in range(self._table.rowCount()):
            name = (self._table.item(row, 0) or QTableWidgetItem("")).text().strip()
            if not name:
                continue
            def cell(c):
                it = self._table.item(row, c)
                return it.text() if it else ""
            def cb(c):
                w = self._table.cellWidget(row, c)
                return w.currentText() if w else ""
            try:
                thr   = int(cell(1)) if cell(1) else 2
                mode  = cb(2) or "qual"
                # Promoter: plain numeric field
                try:    prom = float(cell(3)) if cell(3) else 2.0
                except: prom = 2.0
                # Enhancer: plain numeric field
                try:    enh  = float(cell(4)) if cell(4) else 16.0
                except: enh  = 16.0
                kda   = float(cell(5)) if cell(5) else 50.0
                on_c  = [s.strip() for s in cell(6).split(";") if s.strip()]
                off_c = [s.strip() for s in cell(7).split(";") if s.strip()]
                ft    = cb(8)
                coeff = float(cell(9)) if cell(9) else 0.0
                func  = (ft, coeff) if ft and ft != "—" else False
                result[name] = (thr, mode, prom, enh, kda, on_c, off_c, func)
            except Exception:
                continue
        return result

    def get_secret_genes(self) -> List[str]:
        """Return names of genes with ftype='secret'."""
        result = []
        for row in range(self._table.rowCount()):
            name_it = self._table.item(row, 0)
            if not name_it: continue
            name = name_it.text().strip()
            fcb  = self._table.cellWidget(row, 8)
            if fcb and fcb.currentText() == "secret":
                result.append(name)
        return result

    def _append_row(self, name="NEWGENE", rec=None):
        rec = rec or [2, "qual", 2.0, 16, 50, [], [], False]
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(name))
        self._table.setItem(row, 1, QTableWidgetItem(str(rec[0])))

        # Mode combo
        cb_mode = QComboBox(); cb_mode.addItems(_MODES)
        mode_val = rec[1] if len(rec) > 1 else "qual"
        if mode_val in _MODES: cb_mode.setCurrentText(mode_val)
        cb_mode.setStyleSheet(_CB_STYLE)
        self._table.setCellWidget(row, 2, cb_mode)

        # Promoter: numeric text field (default values 1.25 / 2.0 / 4.0)
        prom_val = rec[2] if len(rec) > 2 else 2.0
        if isinstance(prom_val, str):
            prom_val = {"wk": 1.25, "av": 2.0, "st": 4.0}.get(prom_val, 2.0)
        try:    prom_val = float(prom_val)
        except: prom_val = 2.0
        self._table.setItem(row, 3, QTableWidgetItem(str(round(prom_val, 4))))

        # Enhancer: numeric text field (default values 4 / 16 / 64)
        enh_val = rec[3] if len(rec) > 3 else 16
        if isinstance(enh_val, str):
            enh_val = {"wk": 4, "av": 16, "st": 64}.get(enh_val, 16)
        try:    enh_val = float(enh_val)
        except: enh_val = 16.0
        self._table.setItem(row, 4, QTableWidgetItem(str(round(enh_val, 4))))

        self._table.setItem(row, 5, QTableWidgetItem(str(rec[4] if len(rec) > 4 else 50)))
        on_s  = "; ".join(rec[5]) if len(rec) > 5 and isinstance(rec[5], list) else ""
        off_s = "; ".join(rec[6]) if len(rec) > 6 and isinstance(rec[6], list) else ""
        self._table.setItem(row, 6, QTableWidgetItem(on_s))
        self._table.setItem(row, 7, QTableWidgetItem(off_s))

        fcb = QComboBox(); fcb.addItems(_FTYPES)
        coeff = 0.0
        if len(rec) > 7 and rec[7] and isinstance(rec[7], (list, tuple)):
            ft = rec[7][0]; coeff = rec[7][1]
            if ft in _FTYPES: fcb.setCurrentText(ft)
        fcb.setStyleSheet(_CB_STYLE)
        fcb.currentTextChanged.connect(lambda _: self.genes_changed.emit())
        self._table.setCellWidget(row, 8, fcb)
        self._table.setItem(row, 9, QTableWidgetItem(str(coeff)))

        del_btn = QPushButton("×")
        del_btn.setFixedSize(22, 22)
        del_btn.setStyleSheet(_DEL_ROW_STYLE)
        del_btn.clicked.connect(lambda _, b=del_btn: self._delete_row_by_btn(b))
        self._table.setCellWidget(row, 10, del_btn)
        self._auto_height()

    def _delete_row_by_btn(self, btn):
        for r in range(self._table.rowCount()):
            if self._table.cellWidget(r, 10) is btn:
                self._table.removeRow(r)
                self._auto_height()
                self.genes_changed.emit()
                return

    def _clear_all(self):
        self._table.setRowCount(0)
        self._auto_height()
        self.genes_changed.emit()

    def _auto_height(self):
        rows  = self._table.rowCount()
        row_h = self._table.verticalHeader().defaultSectionSize()
        hdr_h = self._table.horizontalHeader().height()
        self._table.setFixedHeight(hdr_h + rows * row_h + 4)


# ── ProductTableWidget ────────────────────────────────────────────────────────

class ProductTableWidget(QWidget):
    """
    Cellular products table.
    Columns: Name | Source | Cost/unit

    Source options:
      "energy"      — proportional to energy spent by cell
      "TPMsum"      — proportional to total TPM
      "secret:<gene>" — driven by protein level of a gene with ftype=secret

    Wastetoxin: always present, source=energy, cost=0.005, not removable.
    CytokineX:  optional, source=TPMsum, cost=0.
    When a gene acquires ftype=secret: a new row appears automatically.
    """

    _COLS = ["Name", "Source", "Cost/unit (energy)", ""]

    WASTETOXIN = "Wastetoxin"
    CYTOKINEX  = "CytokineX"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 8)
        lay.setSpacing(3)

        hdr = QHBoxLayout()
        lbl = QLabel("  CELLULAR PRODUCTS")
        lbl.setStyleSheet(f"color:{ACCENT2};font-weight:bold;font-size:12px;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        add_cyto_btn = QPushButton("+ CytokineX")
        add_cyto_btn.setStyleSheet(btn_style(ACCENT2, font_size=11, padding="3px 10px"))
        add_cyto_btn.clicked.connect(self._add_cytokinex)
        hdr.addWidget(add_cyto_btn)

        add_btn = QPushButton("+ Custom product")
        add_btn.setStyleSheet(btn_style("#3a5f3a", font_size=11, padding="3px 10px"))
        add_btn.clicked.connect(lambda: self._append("NewProduct", "energy", 0.001))
        hdr.addWidget(add_btn)
        lay.addLayout(hdr)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(self._COLS)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 26)
        self._table.setStyleSheet(_TBL_STYLE)
        self._table.setAlternatingRowColors(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.verticalHeader().setVisible(False)
        lay.addWidget(self._table)

        self._secret_choices: List[str] = []   # "secret:<gene>" items
        # Add mandatory Wastetoxin
        self._ensure_wastetoxin()

    # ── Loading ───────────────────────────────────────────────────────────────

    def load_products(self, products: Dict[str, Any]):
        self._table.setRowCount(0)
        for name, rec in products.items():
            mode  = rec[0] if rec else "energy"
            coeff = rec[1] if len(rec) > 1 else 0.0
            removable = (name != self.WASTETOXIN)
            self._append(name, mode, coeff, removable=removable)
        self._ensure_wastetoxin()
        self._auto_height()

    def get_products(self) -> Dict[str, tuple]:
        result = {}
        for row in range(self._table.rowCount()):
            it = self._table.item(row, 0)
            if not it or not it.text().strip():
                continue
            name = it.text().strip()
            # Source: combo or label
            src_w = self._table.cellWidget(row, 1)
            mode  = src_w.currentText() if isinstance(src_w, QComboBox) else \
                    (self._table.item(row, 1).text() if self._table.item(row, 1) else "energy")
            ci    = self._table.item(row, 2)
            try:   coeff = float(ci.text()) if ci else 0.0
            except: coeff = 0.0
            result[name] = (mode, coeff)
        return result

    # ── Secret gene sync ──────────────────────────────────────────────────────

    def sync_secret_genes(self, secret_genes: List[str]):
        """Called when gene tables change. Ensures each secret gene has a product row."""
        new_choices = [f"secret:{g}" for g in secret_genes]
        self._secret_choices = new_choices

        # Update all source combos to reflect available secret genes
        used_secrets = set()
        for row in range(self._table.rowCount()):
            w = self._table.cellWidget(row, 1)
            if isinstance(w, QComboBox):
                cur = w.currentText()
                if cur.startswith("secret:"):
                    used_secrets.add(cur)

        # Add missing secret gene rows
        for choice in new_choices:
            if choice not in used_secrets:
                gene_name = choice[len("secret:"):]
                self._append(f"{gene_name}_product", choice, 0.005, removable=True)

        # Rebuild combos in source columns
        for row in range(self._table.rowCount()):
            w = self._table.cellWidget(row, 1)
            name_it = self._table.item(row, 0)
            if name_it and name_it.text() == self.WASTETOXIN:
                continue   # Wastetoxin source is fixed
            if isinstance(w, QComboBox):
                cur = w.currentText()
                w.blockSignals(True)
                w.clear()
                w.addItems(["energy", "TPMsum"] + new_choices)
                if cur in ["energy", "TPMsum"] + new_choices:
                    w.setCurrentText(cur)
                w.blockSignals(False)

        self._auto_height()

    def unlinked_secrets(self) -> List[str]:
        """Return list of secret:<gene> choices not yet assigned to any product."""
        used = set()
        for row in range(self._table.rowCount()):
            w = self._table.cellWidget(row, 1)
            if isinstance(w, QComboBox) and w.currentText().startswith("secret:"):
                used.add(w.currentText())
        return [c for c in self._secret_choices if c not in used]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure_wastetoxin(self):
        """Make sure Wastetoxin row exists and is first."""
        for row in range(self._table.rowCount()):
            it = self._table.item(row, 0)
            if it and it.text() == self.WASTETOXIN:
                return
        self._table.insertRow(0)
        name_it = QTableWidgetItem(self.WASTETOXIN)
        name_it.setFlags(name_it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(0, 0, name_it)
        # Source: fixed label "energy"
        src_lbl = QLabel("energy")
        src_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        src_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        self._table.setCellWidget(0, 1, src_lbl)
        # Cost: fixed 0.005, not editable
        cost_it = QTableWidgetItem("0.005")
        cost_it.setFlags(cost_it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(0, 2, cost_it)
        # No delete button
        self._auto_height()

    def _add_cytokinex(self):
        # Check if already present
        for row in range(self._table.rowCount()):
            it = self._table.item(row, 0)
            if it and it.text() == self.CYTOKINEX:
                return
        self._append(self.CYTOKINEX, "TPMsum", 0.0, removable=True)

    def _append(self, name="NewProduct", mode="energy", coeff=0.001,
                removable=True):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(name))

        src_cb = QComboBox()
        src_cb.addItems(["energy", "TPMsum"] + self._secret_choices)
        if mode in ["energy", "TPMsum"] + self._secret_choices:
            src_cb.setCurrentText(mode)
        elif mode.startswith("secret:") and mode not in self._secret_choices:
            src_cb.addItem(mode)
            src_cb.setCurrentText(mode)
        src_cb.setStyleSheet(_CB_STYLE)
        self._table.setCellWidget(row, 1, src_cb)

        self._table.setItem(row, 2, QTableWidgetItem(str(coeff)))

        if removable:
            del_btn = QPushButton("×")
            del_btn.setFixedSize(22, 22)
            del_btn.setStyleSheet(_DEL_ROW_STYLE)
            del_btn.clicked.connect(lambda _, b=del_btn: self._delete_by_btn(b))
            self._table.setCellWidget(row, 3, del_btn)

        self._auto_height()

    def _delete_by_btn(self, btn):
        for r in range(self._table.rowCount()):
            if self._table.cellWidget(r, 3) is btn:
                self._table.removeRow(r)
                self._auto_height()
                return

    def _auto_height(self):
        rows  = self._table.rowCount()
        row_h = self._table.verticalHeader().defaultSectionSize()
        hdr_h = self._table.horizontalHeader().height()
        self._table.setFixedHeight(hdr_h + rows * row_h + 4)


# ── Separator ─────────────────────────────────────────────────────────────────

def _section_line() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background:{BORDER};"); f.setFixedHeight(1)
    return f


# ── GenomeScreen ──────────────────────────────────────────────────────────────

class GenomeScreen(QWidget):
    confirmed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preset = copy.deepcopy(STABLE_GENOME_PRESET)
        self._build_ui()
        self._load_preset(self._preset)

    def _build_ui(self):
        self.setStyleSheet(f"background:{BG_DARK};color:{TEXT_PRIMARY};")
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # Top bar
        top_frame = QFrame()
        top_frame.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border-bottom:1px solid {BORDER};}}")
        top_lay = QHBoxLayout(top_frame)
        top_lay.setContentsMargins(16, 10, 16, 10)
        title = QLabel("🧬  Genome Editor")
        title.setStyleSheet("font-size:18px;font-weight:bold;color:#e6edf3;")
        top_lay.addWidget(title)
        top_lay.addStretch()

        self._coll_combo = QComboBox()
        self._coll_combo.setMinimumWidth(220)
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

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:{BG_DARK};}}")
        content = QWidget(); content.setStyleSheet(f"background:{BG_DARK};")
        sc = QVBoxLayout(content)
        sc.setContentsMargins(16, 10, 16, 10)
        sc.setSpacing(4)

        self._tables: Dict[str, GeneTableWidget] = {}
        for cat in ["receptors", "metabolism", "kinases", "cell_cycle", "division"]:
            t = GeneTableWidget(cat)
            t.genes_changed.connect(self._on_genes_changed)
            self._tables[cat] = t
            sc.addWidget(t)
            sc.addWidget(_section_line())

        self._prod_table = ProductTableWidget()
        sc.addWidget(self._prod_table)
        sc.addWidget(_section_line())

        # Global params
        pf = QFrame()
        pf.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border:1px solid {BORDER};"
            f"border-radius:6px;padding:6px;}}")
        grid = QGridLayout(pf); grid.setSpacing(8)
        def _field(lbl_text, val):
            lbl = QLabel(lbl_text); lbl.setStyleSheet(f"color:{TEXT_MUTED};")
            ed  = QLineEdit(str(val)); ed.setStyleSheet(_ED_STYLE)
            return lbl, ed
        lbl_cc, self._ed_cc = _field("Initial cell count", 10)
        lbl_en, self._ed_en = _field("Starting energy (σ)", 0.0)
        lbl_ps, self._ed_ps = _field("Protein stability (0–1)", 0.7)
        for col, (l, e) in enumerate([(lbl_cc, self._ed_cc),
                                       (lbl_en, self._ed_en),
                                       (lbl_ps, self._ed_ps)]):
            grid.addWidget(l, 0, col*2); grid.addWidget(e, 0, col*2+1)
        sc.addWidget(pf)
        sc.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        # Bottom bar
        bot_frame = QFrame()
        bot_frame.setStyleSheet(
            f"QFrame{{background:{BG_PANEL};border-top:1px solid {BORDER};}}")
        bot_lay = QHBoxLayout(bot_frame)
        bot_lay.setContentsMargins(16, 8, 16, 8)

        cryo_btn = QPushButton("❄  Cryobank")
        cryo_btn.setStyleSheet(btn_style("#1a5276"))
        cryo_btn.clicked.connect(self._on_cryobank)

        self._save_btn = QPushButton("💾  Save to collection")
        self._save_btn.setStyleSheet(btn_style(ACCENT2))
        self._save_btn.clicked.connect(self._on_save)

        self._confirm_btn = QPushButton("✔  Confirm genome")
        self._confirm_btn.setStyleSheet(btn_style(ACCENT))
        self._confirm_btn.clicked.connect(self._on_confirm)

        self._env_btn = QPushButton("🌍  Environment  →")
        self._env_btn.setStyleSheet(btn_style("#8957e5"))
        self._env_btn.setEnabled(False)

        bot_lay.addWidget(cryo_btn)
        bot_lay.addStretch()
        bot_lay.addWidget(self._save_btn)
        bot_lay.addWidget(self._confirm_btn)
        bot_lay.addWidget(self._env_btn)
        root.addWidget(bot_frame)

    # ── Gene change handler ───────────────────────────────────────────────────

    def _on_genes_changed(self):
        """Sync secret genes to product table; validate env button."""
        secret_genes = []
        for t in self._tables.values():
            secret_genes.extend(t.get_secret_genes())
        self._prod_table.sync_secret_genes(secret_genes)
        self._validate_env_btn()

    def _validate_env_btn(self):
        """Env button only active after confirm AND no unlinked secret genes."""
        unlinked = self._prod_table.unlinked_secrets()
        if unlinked:
            self._env_btn.setEnabled(False)
            self._env_btn.setToolTip(
                f"Link these secret genes first: {', '.join(unlinked)}")
        # else: enabled if previously confirmed

    # ── helpers ───────────────────────────────────────────────────────────────

    def _refresh_collection(self):
        self._coll_combo.clear()
        for name in load_genome_collection():
            self._coll_combo.addItem(name)

    def _load_preset(self, preset):
        for cat in ["receptors", "metabolism", "kinases", "cell_cycle", "division"]:
            self._tables[cat].load_genes(preset.get(cat, {}))
        self._prod_table.load_products(preset.get("cellular_products", {}))
        self._ed_cc.setText(str(preset.get("cell_count", 10)))
        self._ed_en.setText(str(preset.get("energy", 0.0)))
        self._ed_ps.setText(str(preset.get("protein_stability", 0.7)))
        self._on_genes_changed()

    def _collect_preset(self):
        p = {}
        for cat in ["receptors", "metabolism", "kinases", "cell_cycle", "division"]:
            p[cat] = self._tables[cat].get_genes()
        p["cellular_products"] = self._prod_table.get_products()
        try:    p["cell_count"]        = int(self._ed_cc.text())
        except: p["cell_count"]        = 10
        try:    p["energy"]            = float(self._ed_en.text())
        except: p["energy"]            = 0.0
        try:    p["protein_stability"] = float(self._ed_ps.text())
        except: p["protein_stability"] = 0.7
        return p

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_cryobank(self):
        from gui.widgets.cryobank_dialog import CryobankDialog
        from PyQt6.QtWidgets import QDialog
        dlg = CryobankDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.result_data()
        if data is None:
            return
        preset, cells, strain_name, _ = data
        msg = (f"Strain '{strain_name}' ({cells} cells) added.\n"
               "It will start as an independent genome alongside the one you define here.")
        QMessageBox.information(self, "Strain loaded", msg)
        if not hasattr(self, '_cryo_injections'):
            self._cryo_injections = []
        self._cryo_injections.append(
            {"preset": preset, "cells": cells, "name": strain_name})

    def _on_load(self):
        col = load_genome_collection()
        name = self._coll_combo.currentText()
        if name in col:
            self._load_preset(col[name])

    def _on_confirm(self):
        # Check all secret genes are linked
        unlinked = self._prod_table.unlinked_secrets()
        if unlinked:
            QMessageBox.warning(
                self, "Unlinked secret genes",
                f"Please assign a product source for: {', '.join(unlinked)}\n"
                "Every gene with function 'secret' must be linked to a product.")
            return
        self._preset = self._collect_preset()
        self._env_btn.setEnabled(True)
        self._env_btn.setToolTip("")
        self.confirmed.emit(self._preset)

    def _on_save(self):
        name, ok = QInputDialog.getText(self, "Save genome", "Collection name:")
        if ok and name.strip():
            save_genome_to_collection(name.strip(), self._collect_preset())
            self._refresh_collection()

    def get_confirmed_preset(self):
        return self._preset if self._env_btn.isEnabled() else None

    @property
    def env_button(self) -> QPushButton:
        return self._env_btn
