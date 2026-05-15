"""
gui/main_window.py  —  Navigation controller

Pages
-----
0  GenomeScreen
1  EnvScreen
2  SimScreen
3  DendrogramScreen
"""

from __future__ import annotations
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox
from PyQt6.QtCore    import Qt

from gui.utils.theme       import BG_DARK
from gui.utils.collections import genome_preset_to_objects, env_preset_to_object
from gui.utils.sim_runner  import SimRunner
from gui.screens.genome_screen     import GenomeScreen
from gui.screens.env_screen        import EnvScreen
from gui.screens.sim_screen        import SimScreen
from gui.screens.dendrogram_screen import DendrogramScreen
from gui.screens.evo_screen        import EvoScreen


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cell Simulation")
        self.resize(1260, 860)
        self.setStyleSheet(f"background:{BG_DARK};")

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._genome_screen = GenomeScreen()
        self._env_screen    = EnvScreen()
        self._sim_screen:   SimScreen | None = None
        self._dendro_screen = DendrogramScreen()
        self._evo_screen    = EvoScreen()
        self._runner:       SimRunner | None = None

        self._stack.addWidget(self._genome_screen)   # 0
        self._stack.addWidget(self._env_screen)      # 1
        self._stack.addWidget(self._dendro_screen)   # will shift to 3
        self._stack.addWidget(self._evo_screen)      # will shift to 4

        self._env_screen.go_back = self._go_genome

        # Connections
        self._genome_screen.confirmed.connect(self._on_genome_confirmed)
        self._genome_screen.env_button.clicked.connect(self._go_env)
        self._env_screen.launch_button.clicked.connect(self._on_launch)
        self._dendro_screen.go_back.connect(self._go_sim)
        self._dendro_screen.cryo_freeze_requested.connect(self._on_cryo_freeze)
        self._dendro_screen.open_evo.connect(self._go_evo)
        self._evo_screen.go_back.connect(self._go_dendro_from_evo)

        self._stack.setCurrentIndex(0)
        self._genome_preset = None

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_evo(self):
        """Navigate to EvoScreen, pushing current simulation data."""
        runner = getattr(self, '_runner', None)
        if runner is None or self._sim_screen is None:
            return
        tree    = self._sim_screen.genome_tree
        labels  = getattr(self._sim_screen, '_genome_labels', {})
        pops    = {}
        records = getattr(runner, 'all_records', [])
        mut_log = getattr(runner, 'all_mut_log', [])
        if records:
            last_tick = records[-1].get('Tick', 0)
            for r in records:
                if r.get('Tick') == last_tick and 'GenomeID' in r:
                    pops[r['GenomeID']] = (r['CellCount'], r.get('Energy', 0.0))
        self._evo_screen.push_data(
            mut_log    = mut_log,
            all_records= records,
            populations= pops,
            genome_tree= tree,
            genome_labels= labels,
        )
        self._stack.setCurrentWidget(self._evo_screen)

    def _go_dendro_from_evo(self):
        self._stack.setCurrentWidget(self._dendro_screen)

    def _go_genome(self): self._stack.setCurrentIndex(0)
    def _go_env(self):    self._stack.setCurrentIndex(1)

    def _go_sim(self):
        idx = self._stack.indexOf(self._sim_screen)
        if idx >= 0:
            self._stack.setCurrentIndex(idx)

    def _go_dendro(self):
        if self._sim_screen is None:
            return
        tree     = self._sim_screen.genome_tree
        max_ever = self._sim_screen.max_ever
        pops = {}
        if self._runner:
            records = getattr(self._runner, 'all_records', [])
            if records:
                last_tick = records[-1].get("Tick", 0)
                for r in records:
                    if r.get("Tick") == last_tick and "GenomeID" in r:
                        pops[r["GenomeID"]] = (r["CellCount"], r.get("Energy", 0.0))
            mut_log = getattr(self._runner, 'all_mut_log', [])
        else:
            mut_log = []
        # Pass live genome objects directly to dendrogram
        # (preset is built on-demand from Genome objects, not serialised dicts)
        runner = getattr(self, '_runner', None)
        genome_presets = {}
        if runner:
            live = getattr(runner, '_live_genomes_ref', {})
            # Build cellular_products map from environment
            env = getattr(runner, '_env_ref', None)
            if env:
                prod_map = {k: list(v) for k, v in env.product_defs.items()}
            else:
                prod_map = {}
            # Store prod_map in each 'genome_presets' slot so _build_preset can use it
            for gid in live:
                genome_presets[gid] = {'cellular_products': prod_map}

        labels = getattr(self._sim_screen, '_genome_labels', {})
        self._dendro_screen.push_data(tree, pops, max_ever, mut_log,
                                      genome_presets, labels)
        # Give dendrogram direct references to live Genome objects
        if runner:
            live = getattr(runner, '_live_genomes_ref', {})
            self._dendro_screen.set_live_genomes(live)
        self._stack.setCurrentIndex(self._stack.indexOf(self._dendro_screen))

    # ── Cryo: remove cells from running simulation ────────────────────────────

    def _on_cryo_freeze(self, gid: int, strain: str, desc: str,
                        cpv: int, n_vials: int):
        """Called when user freezes cells from dendrogram popup."""
        total = cpv * n_vials
        if self._runner is None:
            return
        self._runner.pause()
        time.sleep(0.08)
        genomes = self._runner._live_genomes_snapshot()
        for g in genomes:
            if g.genome_id == gid:
                removed = min(total, g.cell_count)
                g.cell_count = max(0, g.cell_count - removed)
                break
        self._runner.resume()

    # ── Genome confirmed ──────────────────────────────────────────────────────

    def _on_genome_confirmed(self, preset: dict):
        self._genome_preset = preset
        self._env_screen.set_genome_products(preset.get("cellular_products", {}))
        # Pass cryo injections to env_screen so it can display them
        cryo = getattr(self._genome_screen, '_cryo_injections', [])
        self._env_screen.set_cryo_injections(cryo)

    # ── Launch ────────────────────────────────────────────────────────────────

    def _on_launch(self):
        if self._genome_preset is None:
            QMessageBox.warning(self, "No genome",
                                "Please confirm a genome first (Page 1).")
            return

        env_preset = self._env_screen.get_confirmed_preset()

        # Collect cryo injections from env_screen (may have been modified there)
        cryo_injections = self._env_screen.get_cryo_injections()

        # Decide whether to use the editor genome or skip it (cryo-only start)
        use_editor_genome = self._env_screen.use_editor_genome()

        try:
            products = {}
            if use_editor_genome:
                genome, products = genome_preset_to_objects(self._genome_preset)
            else:
                # Still need a dummy genome to initialise the runner;
                # we'll remove it immediately by setting cell_count=0
                genome, products = genome_preset_to_objects(self._genome_preset)
                genome.cell_count = 0

            # Merge products from cryo presets too
            for inj in cryo_injections:
                cp = inj.get("preset", {}).get("cellular_products", {})
                for k, v in cp.items():
                    if k not in products:
                        products[k] = tuple(v) if isinstance(v, list) else v

            environment = env_preset_to_object(env_preset, products)
        except Exception as e:
            QMessageBox.critical(self, "Setup error", str(e))
            return

        ticks    = (999_999_999 if env_preset.get("infinite")
                    else env_preset.get("ticks", 3000))
        mut_ch   = env_preset.get("mutation_chance", 0.001)
        n_gen    = env_preset.get("n_genomes_allowed", 5)
        capacity = env_preset.get("support_cell_num", 1000)

        self._runner = SimRunner(
            genome            = genome,
            environment       = environment,
            max_ticks         = ticks,
            energy_cost       = "default",
            toxin_k           = env_preset.get("toxin_k", 1.0),
            mutation_chance   = mut_ch,
            n_genomes_allowed = n_gen,
            cryo_injections   = cryo_injections,
        )
        self._runner.pause()

        tox_names  = list(env_preset.get("toxins", {}).keys())
        prod_names = list(products.keys())
        gene_names = list(genome.gene_list)

        if self._sim_screen is not None:
            self._stack.removeWidget(self._sim_screen)
            self._sim_screen.deleteLater()

        self._sim_screen = SimScreen(
            runner            = self._runner,
            toxin_names       = tox_names,
            product_names     = prod_names,
            all_gene_names    = gene_names,
            capacity          = capacity,
            initial_mutation  = mut_ch,
        )
        self._sim_screen.finished.connect(self._go_genome)
        self._sim_screen.open_dendro.connect(self._go_dendro)

        dendro_idx = self._stack.indexOf(self._dendro_screen)
        self._stack.insertWidget(dendro_idx, self._sim_screen)
        self._stack.setCurrentWidget(self._sim_screen)
        self._sim_screen.start()
        # Clear genome list so it does not persist on next visit to env screen
        self._env_screen.clear_cryo_injections()
        self._genome_screen._cryo_injections = []
