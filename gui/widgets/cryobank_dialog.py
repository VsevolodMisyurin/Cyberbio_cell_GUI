"""
gui/widgets/cryobank_dialog.py

Dialog shown from GenomeScreen when user clicks "❄ Cryobank".
Lists all frozen strains; user picks strain + vial, then confirms.
Returns (genome_preset, cells) so the caller can inject it into the simulation.
"""

from __future__ import annotations
from typing import Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QDialogButtonBox, QFrame, QSplitter,
)
from PyQt6.QtCore import Qt

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui.utils.theme import (
    BG_DARK, BG_PANEL, BORDER, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT, ACCENT2, btn_style,
)
from gui.utils.collections import load_cryobank, remove_vial_from_cryobank


class CryobankDialog(QDialog):
    """
    Shows frozen strains on the left and vials on the right.
    On OK: returns the selected (genome_preset, cells_per_vial, strain_name, vial_idx).
    The caller is responsible for calling remove_vial_from_cryobank() if desired.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("❄  Cryobank — select a frozen strain")
        self.setMinimumSize(580, 380)
        self.setStyleSheet(f"background:{BG_PANEL};color:{TEXT_PRIMARY};")

        self._bank = load_cryobank()
        self._selected_strain: Optional[str] = None
        self._selected_vial:   Optional[int] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Select a strain and vial to add to the next simulation:",
                             styleSheet=f"color:{TEXT_MUTED};font-size:11px;"))

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: strain list
        left = QFrame(); left.setStyleSheet(f"background:{BG_DARK};border-radius:4px;")
        ll = QVBoxLayout(left); ll.setContentsMargins(6,6,6,6)
        ll.addWidget(QLabel("Strains:", styleSheet=f"color:{TEXT_MUTED};font-size:10px;"))
        self._strain_list = QListWidget()
        self._strain_list.setStyleSheet(
            f"QListWidget{{background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:none;font-size:11px;}}"
            f"QListWidget::item:selected{{background:{ACCENT2};}}"
        )
        for name, entry in self._bank.items():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            desc = entry.get("description", "")
            if desc: item.setToolTip(desc)
            self._strain_list.addItem(item)
        self._strain_list.currentItemChanged.connect(self._on_strain_select)
        ll.addWidget(self._strain_list, stretch=1)
        splitter.addWidget(left)

        # Right: vial list + info
        right = QFrame(); right.setStyleSheet(f"background:{BG_DARK};border-radius:4px;")
        rl = QVBoxLayout(right); rl.setContentsMargins(6,6,6,6)
        rl.addWidget(QLabel("Vials:", styleSheet=f"color:{TEXT_MUTED};font-size:10px;"))
        self._vial_list = QListWidget()
        self._vial_list.setStyleSheet(
            f"QListWidget{{background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:none;font-size:11px;}}"
            f"QListWidget::item:selected{{background:{ACCENT2};}}"
        )
        self._vial_list.currentItemChanged.connect(self._on_vial_select)
        rl.addWidget(self._vial_list, stretch=1)

        self._info_lbl = QLabel()
        self._info_lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
        self._info_lbl.setWordWrap(True)
        rl.addWidget(self._info_lbl)
        splitter.addWidget(right)

        splitter.setSizes([220, 340])
        lay.addWidget(splitter, stretch=1)

        # Consume vial checkbox
        self._consume_chk = QPushButton("✓  Remove vial after use")
        self._consume_chk.setCheckable(True)
        self._consume_chk.setChecked(True)
        self._consume_chk.setStyleSheet(
            btn_style("#3a3f47", font_size=11, padding="4px 10px"))
        lay.addWidget(self._consume_chk, alignment=Qt.AlignmentFlag.AlignLeft)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            btn_style(ACCENT, font_size=12))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            btn_style("#3a3f47", font_size=12))
        btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        lay.addWidget(btns)

    def _on_strain_select(self, item):
        self._selected_strain = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._selected_vial   = None
        self._vial_list.clear()
        self._ok_btn.setEnabled(False)

        if not self._selected_strain:
            return
        entry = self._bank.get(self._selected_strain, {})
        desc  = entry.get("description", "—")
        self._info_lbl.setText(f"Description: {desc}")

        for i, vial in enumerate(entry.get("vials", [])):
            cells = vial.get("cells", "?")
            label = vial.get("label", f"vial_{i+1}")
            item2 = QListWidgetItem(f"{label}  —  {cells} cells")
            item2.setData(Qt.ItemDataRole.UserRole, i)
            self._vial_list.addItem(item2)

    def _on_vial_select(self, item):
        self._selected_vial = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._ok_btn.setEnabled(self._selected_vial is not None)

    def result_data(self) -> Optional[Tuple[dict, int, str, int]]:
        """Returns (genome_preset, cells, strain_name, vial_idx) or None."""
        if self._selected_strain is None or self._selected_vial is None:
            return None
        entry  = self._bank.get(self._selected_strain, {})
        preset = entry.get("genome_preset", {})
        vials  = entry.get("vials", [])
        if self._selected_vial >= len(vials):
            return None
        cells = vials[self._selected_vial].get("cells", 1)

        if self._consume_chk.isChecked():
            remove_vial_from_cryobank(self._selected_strain, self._selected_vial)

        return preset, cells, self._selected_strain, self._selected_vial
