"""
gui_main.py

Entry point for the GUI.  Run:
    python gui_main.py

Dependencies
------------
    pip install PyQt6 numpy pandas

For Android packaging, use BeeWare Briefcase or python-for-android.
The gui/ package is structured so the backend (sim_runner, collections)
is pure Python — only the screen/widget files use PyQt6 and would need
adaptation for a different toolkit (e.g. Kivy, or a web frontend).
"""

import sys, os

# Make sure the project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Cell Simulation")
    app.setOrganizationName("CellSim")
    # Note: AA_UseHighDpiPixmaps was removed in PyQt6 — high-DPI is on by default.

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
