"""
gui/utils/sim_runner.py

Runs the cell simulation in a background QThread so the UI stays
responsive.  Emits signals each tick with the data the UI needs.

Architecture
------------
SimRunner          – QThread subclass; owns the simulation loop.
SimState           – lightweight dataclass passed via signal each tick.
SimSignals         – QObject that holds all pyqtSignal definitions
                     (separate from QThread to avoid MRO issues).
"""

from __future__ import annotations
import sys, os, time, random, copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from PyQt6.QtCore import QThread, QObject, pyqtSignal, QMutex, QMutexLocker

from core.genome      import Genome, reset_id_counter
from core.environment import Environment
from core.simulation  import run_simulation, _tick_one_genome, _attach_env_cols
from core.simulation  import evaluate_toxins, generate_cellular_products
from biology.mutations import mutate_genome_tracked


# ---------------------------------------------------------------------------
# State object emitted every tick
# ---------------------------------------------------------------------------

@dataclass
class TickState:
    tick:          int
    # genome_id → (cell_count, energy)
    populations:   Dict[int, Tuple[int, float]]
    # shared environment
    food:          float
    tox_levels:    Dict[str, float]   # name → sigma
    product_levels: Dict[str, float]  # name → sigma
    # genome_id → {gene_name → expr_level}
    gene_expr:     Dict[int, Dict[str, float]]
    # new forks this tick: list of (parent_id, child_id)
    new_forks:     List[Tuple[int, int]]
    # genomes that died this tick
    extinct_ids:   List[int]


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class SimSignals(QObject):
    tick_done      = pyqtSignal(object)   # TickState
    sim_finished   = pyqtSignal(object)   # final DataFrames tuple
    sim_error      = pyqtSignal(str)


# ---------------------------------------------------------------------------
# Runner thread
# ---------------------------------------------------------------------------

class SimRunner(QThread):
    """
    Runs the simulation one tick at a time, sleeping between ticks to
    match the target TPS (ticks per second).

    Control interface
    -----------------
    pause()   – pause after current tick
    resume()  – resume
    set_tps() – change speed
    add_toxin(name, delta_sigma) – inject toxin mid-run
    stop()    – request clean shutdown
    """

    def __init__(
        self,
        genome:      Genome,
        environment: Environment,
        max_ticks:   int,
        energy_cost,
        toxin_k:     float,
        mutation_chance: float,
        n_genomes_allowed: int,
        tps:         float = 1.0,
        cryo_injections: list = None,
    ):
        super().__init__()
        self.signals   = SimSignals()
        self._genome   = genome
        self._env      = environment
        self._max_ticks = max_ticks
        self._energy_cost = energy_cost
        self._toxin_k  = toxin_k
        self._mutation_chance = mutation_chance
        self._n_genomes = n_genomes_allowed
        self._cryo_injections: list = cryo_injections or []

        self._tps      = tps
        self._paused   = False
        self._stopped  = False
        self._mutex    = QMutex()

        # toxin injection queue: list of (name, delta) — one-shot
        self._toxin_queue: List[Tuple[str, float]] = []

        # continuous toxin injection: {name: delta} — added every tick
        self._continuous_toxins: dict = {}

        # Public: accumulated records — readable by SimScreen at any time
        self.all_records:  List[dict] = []
        self.all_mut_log:  List[dict] = []

    # ── Control ──────────────────────────────────────────────────────────────

    def pause(self):
        with QMutexLocker(self._mutex):
            self._paused = True

    def resume(self):
        with QMutexLocker(self._mutex):
            self._paused = False

    def set_tps(self, tps: float):
        with QMutexLocker(self._mutex):
            self._tps = max(0.05, tps)

    def add_toxin(self, name: str, delta: float):
        with QMutexLocker(self._mutex):
            self._toxin_queue.append((name, delta))

    def set_continuous_toxin(self, name: str, delta: float):
        """Add delta sigma to toxin every tick until cleared."""
        with QMutexLocker(self._mutex):
            self._continuous_toxins[name] = delta

    def clear_continuous_toxin(self, name: str):
        """Stop continuous injection for this toxin."""
        with QMutexLocker(self._mutex):
            self._continuous_toxins.pop(name, None)

    def _live_genomes_snapshot(self):
        return list(getattr(self, "_live_genomes_ref", {}).values())

    def stop(self):
        with QMutexLocker(self._mutex):
            self._stopped = True

    # ── Main loop ────────────────────────────────────────────────────────────

    def run(self):
        """Main simulation loop — runs in background thread."""
        from biology.metabolism import default_energy_cost
        import pandas as pd

        env = self._env
        self._env_ref = env  # expose for genome_to_preset
        genome = self._genome
        self._env_ref = env  # keep reference for genome_to_preset

        energy_cost = (
            default_energy_cost(genome.gene_count)
            if self._energy_cost == "default"
            else self._energy_cost
        )

        product_names = list(env.product_defs.keys())
        toxin_names   = [n for n in env.toxins if n not in env.product_defs]

        import core.genome as _gmod
        from gui.utils.collections import genome_preset_to_genome_no_reset as _cryo_build

        # Step 1: reset counter, create founder genome at ID 0
        _gmod.reset_id_counter()
        # genome was already created by caller; reassign a fresh ID
        genome.genome_id = _gmod._next_id()   # = 0
        genome.parent_id = None

        # Step 2: create cryo genomes sequentially, each gets next ID
        cryo_genomes = []
        for inj in self._cryo_injections:
            try:
                cryo_g, _ = _cryo_build(inj["preset"])
                cryo_g.cell_count = inj.get("cells", 1)
                cryo_g.energy = 0.0
                cryo_g.parent_id = None            # independent root
                cryo_g._strain_name = inj.get("name", f"G{cryo_g.genome_id}")
                cryo_genomes.append(cryo_g)
                print(f"[CRYO] Loaded strain '{cryo_g._strain_name}' "
                      f"ID={cryo_g.genome_id} cells={cryo_g.cell_count} "
                      f"genes={cryo_g.gene_count}")
                if cryo_g.gene_count > 0:
                    first_gene = list(cryo_g.genes.values())[0]
                    print(f"[CRYO]   First gene: {first_gene.name} "
                          f"on_cond={first_gene.on_conditions}")
                else:
                    print(f"[CRYO] WARNING: genome has 0 genes! preset keys: "
                          f"{list(inj.get('preset', {}).keys())}")
            except Exception as e:
                import traceback
                print(f"[CRYO] Injection failed: {e}")
                traceback.print_exc()

        # Step 3: build live_genomes — skip founder if cell_count == 0
        live_genomes: Dict[int, Genome] = {}
        if genome.cell_count > 0:
            live_genomes[genome.genome_id] = genome
        for cg in cryo_genomes:
            live_genomes[cg.genome_id] = cg

        self._live_genomes_ref = live_genomes
        self.all_records  = []
        self.all_mut_log  = []

        try:
            for tick in range(self._max_ticks):
                # ── Check control flags ───────────────────────────────────
                while True:
                    with QMutexLocker(self._mutex):
                        stopped  = self._stopped
                        paused   = self._paused
                        tps      = self._tps
                        injects   = list(self._toxin_queue)
                        self._toxin_queue.clear()
                        continuous = dict(self._continuous_toxins)
                    if stopped:
                        return
                    if not paused:
                        break
                    time.sleep(0.05)

                # ── Apply toxin injections ────────────────────────────────
                for tox_name, delta in injects:
                    if tox_name in env.toxins:
                        sigma, rest = env.toxins[tox_name].as_tuple()
                        env.toxins[tox_name].sigma = min(3.0, sigma + delta)

                # ── Apply continuous toxins (every tick) ──────────────────
                for tox_name, delta in continuous.items():
                    if tox_name in env.toxins:
                        sigma, rest = env.toxins[tox_name].as_tuple()
                        env.toxins[tox_name].sigma = min(3.0, sigma + delta)

                # ── Tick start ────────────────────────────────────────────
                t0 = time.perf_counter()

                env.food = max(min(env.food + 1.0, 3.0), -3.0)
                tick_food = env.food

                toxins_dict  = env.toxins_as_dict()
                env_products = dict(env.product_levels)

                for gobj in live_genomes.values():
                    prev_expr     = gobj.expr_dict()
                    prev_status   = gobj.status_dict()
                    TPM_sum       = sum(prev_expr.values())
                    energy_spent  = TPM_sum * energy_cost
                    support_ratio = gobj.cell_count / env.support_cell_num
                    prev_prot = {name: gene.protein
                                  for name, gene in gobj.genes.items()}
                    env_products, toxins_dict = generate_cellular_products(
                        prev_expr=prev_expr, prev_status=prev_status,
                        cellular_products=env.product_defs,
                        env_products=env_products, toxins=toxins_dict,
                        energy_spent=energy_spent, TPM_sum=TPM_sum,
                        support_ratio=support_ratio,
                        gene_prot=prev_prot,
                    )

                tox_penalties, tox_levels = evaluate_toxins(toxins_dict, self._toxin_k)
                total_toxins = max(tox_levels.values()) if tox_levels else -3.0

                new_genomes: List[Genome] = []
                dead_ids:    List[int]    = []
                new_forks:   List[Tuple[int,int]] = []
                food_delta = 0.0
                tick_records_start = len(self.all_records)

                for gobj in list(live_genomes.values()):
                    total_live = len(live_genomes) + len(new_genomes)
                    at_cap   = (total_live >= self._n_genomes)
                    singleton = (gobj.cell_count == 1)
                    can_mutate = (self._mutation_chance > 0
                                  and (not at_cap or singleton))

                    if can_mutate and gobj.cell_count > 0:
                        pending = mutate_genome_tracked(gobj.genes, self._mutation_chance)
                        if pending:
                            parent_cells_pre = gobj.cell_count
                            child = gobj.fork()
                            gobj.genes = {n: g.copy()
                                          for n, g in gobj.reference_genes.items()}
                            new_genomes.append(child)
                            new_forks.append((gobj.genome_id, child.genome_id))

                            for ev in pending:
                                self.all_mut_log.append({
                                    "Tick": tick,
                                    "ParentGenomeID": gobj.genome_id,
                                    "ParentCellCount": parent_cells_pre,
                                    "ChildGenomeID": child.genome_id,
                                    "GeneName": ev.gene_name,
                                    "Attribute": ev.attribute,
                                    "ValueBefore": ev.value_before,
                                    "ValueAfter": ev.value_after,
                                })
                            if gobj.cell_count == 0:
                                dead_ids.append(gobj.genome_id)

                            # tick child immediately
                            c_rec, c_stop, _, c_fc = _tick_one_genome(
                                genome=child,
                                toxins_dict=toxins_dict,
                                tox_penalties=tox_penalties,
                                tox_levels=tox_levels,
                                total_toxins=total_toxins,
                                tick_food=tick_food,
                                energy_cost=energy_cost,
                                support_cell_num=env.support_cell_num,
                            )
                            food_delta += c_fc
                            c_rec["Tick"] = tick
                            _attach_env_cols(c_rec, env_products, tox_levels,
                                             product_names, toxin_names)
                            self.all_records.append(c_rec)
                            if c_stop:
                                dead_ids.append(child.genome_id)
                                new_genomes.remove(child)

                    rec, stop, _, fc = _tick_one_genome(
                        genome=gobj,
                        toxins_dict=toxins_dict,
                        tox_penalties=tox_penalties,
                        tox_levels=tox_levels,
                        total_toxins=total_toxins,
                        tick_food=tick_food,
                        energy_cost=energy_cost,
                        support_cell_num=env.support_cell_num,
                    )
                    food_delta += fc
                    rec["Tick"] = tick
                    _attach_env_cols(rec, env_products, tox_levels,
                                     product_names, toxin_names)
                    if gobj.genome_id not in dead_ids:
                        self.all_records.append(rec)
                    if stop and gobj.genome_id not in dead_ids:
                        dead_ids.append(gobj.genome_id)

                # post-detox
                _, tox_levels_post = evaluate_toxins(toxins_dict, self._toxin_k)
                for name in env_products:
                    if name in toxins_dict:
                        env_products[name] = toxins_dict[name][0]
                for r in self.all_records[tick_records_start:]:
                    for n in product_names:
                        if n in tox_levels_post:
                            r[n] = round(tox_levels_post[n], 3)
                    for n in toxin_names:
                        if n in tox_levels_post:
                            r[n] = round(tox_levels_post[n], 3)

                env.update_toxins_from_dict(toxins_dict)
                env.update_product_levels_from_dict(env_products)

                final_food = round(max(min(tick_food - food_delta, 3.0), -3.0), 3)
                for r in self.all_records[tick_records_start:]:
                    r["Food"] = final_food
                env.food = final_food

                for child in new_genomes:
                    live_genomes[child.genome_id] = child
                for gid in dead_ids:
                    live_genomes.pop(gid, None)

                # ── Build TickState and emit ──────────────────────────────
                populations = {
                    gid: (g.cell_count, g.energy)
                    for gid, g in live_genomes.items()
                }
                gene_expr = {
                    gid: g.expr_dict()
                    for gid, g in live_genomes.items()
                }
                state = TickState(
                    tick=tick,
                    populations=populations,
                    food=final_food,
                    tox_levels=dict(tox_levels_post),
                    product_levels={n: env_products.get(n, -3.0)
                                    for n in product_names},
                    gene_expr=gene_expr,
                    new_forks=new_forks,
                    extinct_ids=list(dead_ids),
                )
                self.signals.tick_done.emit(state)

                if not live_genomes:
                    break

                # ── Sleep to match TPS ────────────────────────────────────
                elapsed = time.perf_counter() - t0
                sleep_t = max(0.0, 1.0 / tps - elapsed)
                if sleep_t > 0:
                    time.sleep(sleep_t)

            # ── Emit final results ────────────────────────────────────────
            import pandas as pd
            df_rec = pd.DataFrame(self.all_records)
            mut_cols = ["Tick","ParentGenomeID","ParentCellCount",
                        "ChildGenomeID","GeneName","Attribute",
                        "ValueBefore","ValueAfter"]
            df_mut = (pd.DataFrame(self.all_mut_log, columns=mut_cols)
                      if self.all_mut_log else pd.DataFrame(columns=mut_cols))
            self.signals.sim_finished.emit((df_rec, df_mut))

        except Exception as exc:
            import traceback
            self.signals.sim_error.emit(traceback.format_exc())
