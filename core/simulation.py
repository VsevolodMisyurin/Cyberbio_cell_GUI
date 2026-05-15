"""
core/simulation.py

Multi-genome simulation engine.

All gene-function logic is an exact port of original engine.py:

  • _process_gene_functions uses the SEQUENTIAL RNAdigest algorithm from
    original process_gene_functions (step 12): iterates targets one-by-one,
    cuts as much as possible from each until to_dig is exhausted.

  • Step 8a (early RNAdigest) uses the PROPORTIONAL algorithm from original
    step 8a: distributes dig_total across targets proportionally.
    Both passes exist in the original and are preserved here.

  • detox genes mutate the SHARED toxins_dict in place so that toxin sigma
    is actually reduced in the environment after each tick (the bug where
    a deepcopy was discarded is fixed).

Other properties
----------------
• Column order: Tick | products | toxins | GenomeID | ParentID | …
• Both parent and child appear in df_records from the fork tick onward.
• Stop condition: cell_count == 0 only (no hard energy cutoff).
• Founder ID = 0; forks get IDs 1, 2, … .

Sigma-scale: 0σ = average, ±3σ = extreme.
"""

from __future__ import annotations
import copy
import random
from typing import Dict, List, Tuple

import pandas as pd

import core.genome as _genome_mod
from core.genome      import Genome, reset_id_counter
from core.environment import Environment
from biology.metabolism import (
    cond_all, cond_any, grow_and_cap,
    size_modifier, cell_death_probability, default_energy_cost,
)
from biology.toxins   import evaluate_toxins, generate_cellular_products
from biology.sensors  import evaluate_toxin_sensors
from biology.mutations import (
    MutationEvent, detect_mutations, repair_mutations, mutate_genome_tracked,
)


# ---------------------------------------------------------------------------
# Gene-function dispatcher  — exact port of original process_gene_functions
# ---------------------------------------------------------------------------

def _process_gene_functions(
    all_genes:        Dict[str, tuple],
    gene_list:        List[str],
    prev_status:      Dict[str, str],
    prev_expr:        Dict[str, float],
    new_expr:         Dict[str, float],
    gene_prot:        Dict[str, float],
    energy:           float,
    food:             float,
    toxins:           Dict[str, tuple],   # SHARED — mutated in place by detox
    genome:           Genome,
    support_cell_num: int,
    init_food:        float,
) -> Tuple[bool, float, float, float, Dict[str, tuple]]:
    """
    Execute each gene's biological function when protein ≥ threshold.

    RNAdigest here uses the SEQUENTIAL algorithm (original step 12):
    iterates gene targets one by one, cuts max(av, to_dig) from each until
    to_dig is exhausted.  This differs from the proportional step-8a pass.

    detox mutates `toxins` in place — pass the shared environment dict.
    """
    division_happened = False
    division_cost     = 0.0
    support_ratio     = genome.cell_count / support_cell_num

    for g, record in all_genes.items():
        thr, mode, prom, enh, size_kDa, on_cond, off_cond, func = record
        if not func:
            continue
        ftype = func[0]; val = func[1]
        if gene_prot[g] < thr:
            continue
        eff_prot = gene_prot[g]

        # ── Energy harvesting ────────────────────────────────────────────
        if ftype == "energy":
            available = food - (-3.0)
            amount    = eff_prot * val
            used      = min(available, amount)
            eff       = (0.5 + (init_food + 3.0) * (0.5 / 3.0)
                         if init_food <= 0
                         else 1.0 + init_food * (1.0 / 3.0))
            energy += used * eff
            food   -= used * support_ratio
            food    = max(min(food, 3.0), -3.0)

        # ── Autophagy / protein recycling ────────────────────────────────
        elif ftype == "process":
            total_avail = sum(
                gene_prot[t] for t in gene_list if t != g and gene_prot[t] > 0
            )
            proc_total = min(eff_prot, total_avail)
            if total_avail > 0:
                for tgt in gene_list:
                    if tgt == g or gene_prot[tgt] <= 0:
                        continue
                    share          = gene_prot[tgt] / total_avail
                    cut            = proc_total * share
                    gene_prot[tgt] = max(0.0, gene_prot[tgt] - cut)
                    energy        += cut * val

        # ── RNA digestion (sequential — original step-12 algorithm) ──────
        elif ftype == "RNAdigest":
            to_dig = eff_prot
            dig    = 0.0
            for tgt in gene_list:
                if to_dig <= 0:
                    break
                av = new_expr[tgt] - 1
                if av <= 0:
                    continue
                cut           = min(av, to_dig)
                new_expr[tgt] -= cut
                to_dig        -= cut
                dig           += cut
            energy += dig * val

        # ── Cell division ────────────────────────────────────────────────
        elif ftype == "div":
            division_cost    += val
            division_happened = True

        # ── Detoxification ───────────────────────────────────────────────
        elif ftype == "detox":
            # Mutates the SHARED toxins dict — effect persists into next tick.
            detox_power = (eff_prot * genome.cell_count) * val * support_ratio
            for name in toxins:
                sigma, (param, base_eff) = toxins[name]
                toxins[name] = (max(-3.0, sigma - detox_power), (param, base_eff))

        # ── Toxin resistance (local penalty reduction, env unchanged) ───
        elif ftype == "toxresist":
            pass   # handled in step 4b of _tick_one_genome before gene-function loop

        # ── Mutation sensing ─────────────────────────────────────────────
        elif ftype == "mutsens":
            if detect_mutations(genome.genes, genome.reference_genes, val, eff_prot):
                genome.mut_detected = True

        # ── Mutation repair ──────────────────────────────────────────────
        elif ftype == "mutrep" and genome.mut_detected:
            repair_mutations(genome.genes, genome.reference_genes, val, eff_prot)

    return division_happened, division_cost, energy, food, toxins


# ---------------------------------------------------------------------------
# Single genome tick
# ---------------------------------------------------------------------------

def _tick_one_genome(
    genome:            Genome,
    toxins_dict:       Dict[str, tuple],   # SHARED — detox mutates in place
    tox_penalties:     Dict[str, float],
    tox_levels:        Dict[str, float],
    total_toxins:      float,
    tick_food:         float,
    energy_cost:       float,
    support_cell_num:  int,
) -> Tuple[dict, bool, bool, float]:
    """
    Advance one genome by one simulation tick.
    Returns (record_dict, stop, division_happened, food_after).
    stop is True only when cell_count reaches 0.
    """
    all_genes      = genome.all_genes_tuple_dict()
    gene_list      = genome.gene_list
    prev_expr      = genome.expr_dict()
    prev_status    = genome.status_dict()
    prev_prot      = genome.protein_dict()
    deact_delay    = genome.deact_delay_dict()
    prev_expressed = genome.expressed_dict()
    protein_stability = genome.protein_stability

    energy    = genome.energy
    food      = tick_food
    init_food = food

    # 4. Toxin sensor detection
    toxin_detected = evaluate_toxin_sensors(
        gene_names=gene_list, all_genes=all_genes,
        prev_status=prev_status, prev_expr=prev_expr,
        total_toxins=total_toxins,
    )

    # 4b. toxresist: locally reduce tox_penalties for this genome.
    # Works on the COPY of tox_penalties — toxins_dict (shared env) is NOT modified.
    # Uses prev_prot/prev_status so the protein must have been active last tick.
    local_penalties = dict(tox_penalties)   # genome-local copy
    for g, (thr, mode, prom, enh, size_kDa, on_cond, off_cond, func) in all_genes.items():
        if (func and func[0] == "toxresist"
                and prev_status[g] == "active"
                and prev_prot[g] >= thr):
            reduction = prev_prot[g] * func[1]
            local_penalties = {k: max(0.0, v - reduction)
                               for k, v in local_penalties.items()}

    # 5. Energy penalty from toxins (uses genome-local penalties)
    energy -= local_penalties.get("energy", 0.0)

    # 6. Local variable dict
    local: dict = {
        "Energy": energy, "Food": food,
        "Toxin": total_toxins, "Toxin_detected": toxin_detected,
    }
    local.update(prev_status)

    # 7. Gene on/off switches
    new_expressed: Dict[str, bool] = {}
    for g, (thr, mode, prom, enh, size_kDa, on_cond, off_cond, func) in all_genes.items():
        stop_cond  = cond_any(off_cond, local)
        start_cond = cond_all(on_cond, local) and not stop_cond
        new_expressed[g] = (prev_expressed[g] and not stop_cond) or start_cond
    had_off = {g: cond_any(all_genes[g][6], local) for g in gene_list}

    # 8. Update expression levels
    new_expr: Dict[str, float] = {}
    for g, (thr, mode, prom, enh, size_kDa, on_cond, off_cond, func) in all_genes.items():
        if new_expressed[g]:
            val  = grow_and_cap(prev_expr[g], prom, enh)
            tpen = 1.0 - min(local_penalties.get("TPM", 0.0), 1.0)
            new_expr[g] = max(1, val * tpen)
        else:
            new_expr[g] = 1

    # 8a. Early RNAdigest pass — PROPORTIONAL algorithm (original step 8a)
    for g, (thr, mode, prom, enh, size_kDa, on_cond, off_cond, func) in all_genes.items():
        if func and func[0] == "RNAdigest":
            eff_prot    = prev_prot[g]
            total_avail = sum(max(0.0, new_expr[t] - 1) for t in gene_list)
            dig_total   = min(eff_prot, total_avail)
            digged      = 0.0
            if total_avail > 0:
                for tgt in gene_list:
                    avail = max(0.0, new_expr[tgt] - 1)
                    cut   = dig_total * (avail / total_avail)
                    new_expr[tgt] -= cut
                    digged        += cut
            energy += digged * func[1]

    # 9. Status update with hysteresis
    new_status: Dict[str, str]  = {}
    new_deact:  Dict[str, bool] = dict(deact_delay)
    for g, (thr, mode, prom, enh, size_kDa, on_cond, off_cond, func) in all_genes.items():
        if deact_delay[g]:
            new_status[g] = "inactive"
            new_deact[g]  = False
        elif prev_status[g] == "active":
            new_status[g] = "active"
            if had_off[g]:
                new_deact[g] = True
        else:
            new_status[g] = (
                "active"
                if (not had_off[g] and cond_all(on_cond, local) and new_expr[g] >= thr)
                else "inactive"
            )

    # 11. Protein decay + synthesis
    gene_prot: Dict[str, float] = {}
    for g in gene_list:
        base_stab    = protein_stability.get(g, 1.0)
        stab         = base_stab * size_modifier(all_genes[g][4])
        gene_prot[g] = prev_prot[g] * stab + max(0.0, prev_expr[g] - 1)

    # 12. Gene functions — pass SHARED toxins_dict (detox writes here)
    division_happened, division_cost, energy, food, toxins_dict = _process_gene_functions(
        all_genes=all_genes, gene_list=gene_list,
        prev_status=prev_status, prev_expr=prev_expr, new_expr=new_expr,
        gene_prot=gene_prot, energy=energy, food=food,
        toxins=toxins_dict, genome=genome,
        support_cell_num=support_cell_num, init_food=init_food,
    )

    # 13. Cell death — stochastic only, no hard energy cutoff
    death_prob = cell_death_probability(energy)
    current    = genome.cell_count
    if current <= 100:
        survived = sum(random.random() >= death_prob for _ in range(current))
    else:
        survived = int(current * (1.0 - death_prob))
    genome.cell_count = survived

    # 14. Division
    if division_happened:
        genome.reference_genes = {name: g.copy() for name, g in genome.genes.items()}
        genome.mut_detected    = False
        for g in gene_list:
            new_expr[g]   = 1
            new_status[g] = "inactive"
            gene_prot[g]  = 0.0
            new_deact[g]  = False
        toxin_detected    = False
        genome.cell_count = survived * 2

    # 15. Stop only on extinction
    survivors = genome.cell_count
    stop      = survivors == 0

    # 16. Final energy accounting
    energy -= sum(new_expr.values()) * energy_cost
    energy -= division_cost

    # 17. Write state back
    genome.energy = energy
    genome.apply_expr_dict(new_expr)
    genome.apply_status_dict(new_status)
    genome.apply_protein_dict(gene_prot)
    genome.apply_deact_delay_dict(new_deact)
    genome.apply_expressed_dict(new_expressed)

    food_consumed = tick_food - food   # how much this genome ate (positive = consumed)

    record = {
        "GenomeID":     genome.genome_id,
        "ParentID":     genome.parent_id,
        "Energy":       round(energy, 3),
        "CellCount":    survivors,
        "Food":         None,           # filled in after all genomes tick (shared value)
        "mut_detected": genome.mut_detected,
        "tox_detected": toxin_detected,
        **{g: round(new_expr[g], 3) for g in gene_list},
    }
    return record, stop, division_happened, food_consumed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attach_env_cols(record: dict, env_products: dict, tox_levels: dict,
                     product_names: List[str], toxin_names: List[str]) -> dict:
    """
    Write environment columns into record.

    For molecules that appear in BOTH product_names and tox_levels
    (dual-nature: e.g. Wastetoxin, CytokineX, CellProduct), we use the
    toxin sigma from tox_levels — this value has already been modified by
    detox genes this tick.  This matches original engine behaviour where
    env_products and toxins shared the same sigma variable for such molecules.

    Pure products (not in tox_levels) use env_products.
    Pure toxins (not in product_names) use tox_levels.
    """
    for name in product_names:
        if name in tox_levels:
            record[name] = round(tox_levels[name], 3)
        else:
            record[name] = round(env_products.get(name, -3.0), 3)
    for name in toxin_names:
        record[name] = round(tox_levels.get(name, -3.0), 3)
    return record


def _child_birth_record(child: Genome, tick: int,
                        env_products: dict, tox_levels: dict, food: float,
                        product_names: List[str], toxin_names: List[str]) -> dict:
    rec = {
        "Tick":         tick,
        "GenomeID":     child.genome_id,
        "ParentID":     child.parent_id,
        "Energy":       round(child.energy, 3),
        "CellCount":    child.cell_count,
        "Food":         None,   # filled in after all genomes tick (shared value)
        "mut_detected": child.mut_detected,
        "tox_detected": False,
        **{g: 1 for g in child.gene_list},
    }
    return _attach_env_cols(rec, env_products, tox_levels, product_names, toxin_names)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_simulation(
    genome:             Genome,
    environment:        Environment,
    ticks:              int   = 50,
    energy_cost               = "default",
    toxin_k:            float = 1.0,
    mutation_chance:    float = 0.0,
    n_genomes_allowed:  int   = 10,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[Genome]]:
    """
    Run the full multi-genome cell simulation.

    Parameters
    ----------
    genome             : Founding genome. Receives ID 0.
    environment        : Shared environment for all lineages.
    ticks              : Maximum simulation ticks.
    energy_cost        : Per-TPM energy cost per tick, or "default".
    toxin_k            : Global toxin scaling factor.
    mutation_chance    : Per-gene mutation probability per tick (0 = stable).
    n_genomes_allowed  : Cap on coexisting lineages. Mutagenesis suppressed
                         while cap is reached; resumes when a lineage dies.

    Returns
    -------
    df_records        : one row per (tick × live genome).
                        Column order: Tick | products | toxins |
                        GenomeID | ParentID | Energy | CellCount | Food |
                        mut_detected | tox_detected | <gene expr>.
    df_mutation_log   : one row per mutation-fixation (fork) event.
    surviving_genomes : list[Genome] alive at end of simulation.
    """
    reset_id_counter()
    genome.genome_id = 0
    genome.parent_id = None
    _genome_mod._genome_id_counter = 1   # next fork gets ID 1

    if energy_cost == "default":
        energy_cost = default_energy_cost(genome.gene_count)

    product_names: List[str] = list(environment.product_defs.keys())
    toxin_names:   List[str] = [n for n in environment.toxins
                                 if n not in environment.product_defs]

    live_genomes: Dict[int, Genome] = {genome.genome_id: genome}
    records:  List[dict] = []
    mut_log:  List[dict] = []

    for tick in range(ticks):
        env = environment

        # 1. Food regenerates once
        env.food = max(min(env.food + 1.0, 3.0), -3.0)
        tick_food = env.food

        # 2. All genomes secrete products and accumulate toxins
        toxins_dict  = env.toxins_as_dict()
        env_products = dict(env.product_levels)

        for gobj in live_genomes.values():
            prev_expr     = gobj.expr_dict()
            prev_status   = gobj.status_dict()
            TPM_sum       = sum(prev_expr.values())
            energy_spent  = TPM_sum * energy_cost
            support_ratio = gobj.cell_count / env.support_cell_num

            # Build protein dict from previous tick (stored on each Gene object)
            prev_prot = {name: gene.protein for name, gene in gobj.genes.items()}

            env_products, toxins_dict = generate_cellular_products(
                prev_expr=prev_expr, prev_status=prev_status,
                cellular_products=env.product_defs,
                env_products=env_products, toxins=toxins_dict,
                energy_spent=energy_spent, TPM_sum=TPM_sum,
                support_ratio=support_ratio,
                gene_prot=prev_prot,
            )

        # Evaluate penalties from current toxin state (before detox fires)
        tox_penalties, tox_levels = evaluate_toxins(toxins_dict, toxin_k)
        total_toxins = max(tox_levels.values()) if tox_levels else -3.0

        # 3. Tick each genome.
        # toxins_dict is shared — detox genes mutate it directly this loop.
        new_genomes: List[Genome] = []
        dead_ids:    List[int]    = []
        food_delta = 0.0
        tick_record_start = len(records)   # index of first record for this tick

        for gobj in list(live_genomes.values()):

            total_live = len(live_genomes) + len(new_genomes)
            # Mutation is allowed when:
            #   a) genome count is below the cap  (normal case), OR
            #   b) cap is reached but this genome has exactly 1 cell —
            #      the fork replaces the parent (parent.cell_count → 0 → extinct),
            #      so the total number of live genomes does not increase.
            at_cap     = (total_live >= n_genomes_allowed)
            singleton  = (gobj.cell_count == 1)
            can_mutate = mutation_chance > 0 and (not at_cap or singleton)

            # ── Immediate fork on mutation (no division required) ──────────
            # If a mutation occurs, one cell immediately separates into a new
            # child lineage.  The parent genome is restored to its reference
            # (unmutated) state so its remaining cells are unaffected.
            # The child genome carries the mutation and ticks this same turn.
            if can_mutate and gobj.cell_count > 0:
                pending = mutate_genome_tracked(gobj.genes, mutation_chance)
                if pending:
                    parent_cells_pre = gobj.cell_count
                    child = gobj.fork()   # parent loses 1 cell; child gets 1

                    # Restore parent genes to unmutated reference
                    gobj.genes = {name: g.copy()
                                  for name, g in gobj.reference_genes.items()}

                    new_genomes.append(child)

                    # Log every mutation that went into this fork
                    for ev in pending:
                        mut_log.append({
                            "Tick":            tick,
                            "ParentGenomeID":  gobj.genome_id,
                            "ParentCellCount": parent_cells_pre,
                            "ChildGenomeID":   child.genome_id,
                            "GeneName":        ev.gene_name,
                            "Attribute":       ev.attribute,
                            "ValueBefore":     ev.value_before,
                            "ValueAfter":      ev.value_after,
                        })

                    # If parent has no cells left, mark it dead immediately
                    if gobj.cell_count == 0:
                        dead_ids.append(gobj.genome_id)

                    # ── Tick the child genome immediately this same turn ───
                    c_record, c_stop, _, c_food_consumed = _tick_one_genome(
                        genome=child,
                        toxins_dict=toxins_dict,
                        tox_penalties=tox_penalties,
                        tox_levels=tox_levels,
                        total_toxins=total_toxins,
                        tick_food=tick_food,
                        energy_cost=energy_cost,
                        support_cell_num=env.support_cell_num,
                    )
                    food_delta += c_food_consumed
                    c_record["Tick"] = tick
                    _attach_env_cols(c_record, env_products, tox_levels,
                                     product_names, toxin_names)
                    records.append(c_record)
                    if c_stop:
                        dead_ids.append(child.genome_id)
                        new_genomes.remove(child)  # won't be added to live_genomes

            # ── Run this genome's tick ────────────────────────────────────
            record, stop, division_happened, food_consumed = _tick_one_genome(
                genome=gobj,
                toxins_dict=toxins_dict,    # shared — detox writes here
                tox_penalties=tox_penalties,
                tox_levels=tox_levels,
                total_toxins=total_toxins,
                tick_food=tick_food,
                energy_cost=energy_cost,
                support_cell_num=env.support_cell_num,
            )
            food_delta += food_consumed   # accumulate total consumption across all genomes

            record["Tick"] = tick
            _attach_env_cols(record, env_products, tox_levels,
                             product_names, toxin_names)
            # Only append record if genome still has cells (not already dead)
            if gobj.genome_id not in dead_ids:
                records.append(record)

            if stop and gobj.genome_id not in dead_ids:
                dead_ids.append(gobj.genome_id)

        # 4. Recompute tox_levels from post-detox toxins_dict, then sync env_products
        #    for dual-nature molecules (product + toxin) so records show detoxed sigma.
        _, tox_levels_post = evaluate_toxins(toxins_dict, toxin_k)
        # Sync env_products for dual-nature molecules to post-detox sigma
        for name in env_products:
            if name in toxins_dict:
                env_products[name] = toxins_dict[name][0]
        # Patch already-written records for this tick with post-detox toxin values
        for rec in records[tick_record_start:]:
            for name in product_names:
                if name in tox_levels_post:
                    rec[name] = round(tox_levels_post[name], 3)
            for name in toxin_names:
                if name in tox_levels_post:
                    rec[name] = round(tox_levels_post[name], 3)
        # Write post-detox state back to environment
        env.update_toxins_from_dict(toxins_dict)
        env.update_product_levels_from_dict(env_products)

        # 5. Compute shared final food and patch all records for this tick.
        #    food_delta = total consumption across ALL genomes this tick.
        #    All cells live in one environment — every genome sees the same food level.
        final_food = round(max(min(tick_food - food_delta, 3.0), -3.0), 3)
        for rec in records[tick_record_start:]:
            rec["Food"] = final_food
        env.food = final_food

        # 6. Register new genomes, remove extinct ones
        for child in new_genomes:
            live_genomes[child.genome_id] = child
        for gid in dead_ids:
            live_genomes.pop(gid, None)

        # 7. Global stop
        if not live_genomes:
            print(f"All populations extinct at tick {tick}.")
            break

    # Build output DataFrames
    df_records = pd.DataFrame(records)

    if not df_records.empty:
        env_col_order = product_names + toxin_names
        meta_cols     = ["GenomeID", "ParentID", "Energy", "CellCount", "Food",
                         "mut_detected", "tox_detected"]
        front  = ["Tick"] + [c for c in env_col_order if c in df_records.columns]
        middle = [c for c in meta_cols if c in df_records.columns]
        genes  = [c for c in df_records.columns if c not in front + middle]
        df_records = df_records[front + middle + genes]
        df_records = df_records.sort_values(["Tick", "GenomeID"]).reset_index(drop=True)

    mut_cols = [
        "Tick", "ParentGenomeID", "ParentCellCount",
        "ChildGenomeID", "GeneName", "Attribute", "ValueBefore", "ValueAfter",
    ]
    df_mut_log = (
        pd.DataFrame(mut_log, columns=mut_cols)
        if mut_log
        else pd.DataFrame(columns=mut_cols)
    )

    return df_records, df_mut_log, list(live_genomes.values())
