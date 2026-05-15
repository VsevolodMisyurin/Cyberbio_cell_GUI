"""
main.py

Entry point for the cell simulation.
Define your genome and environment here, then call main().

All concentration values (energy, food, toxins) are in σ (standard deviation)
units from a biological baseline:
  −3 σ = extreme scarcity / lethal   |   0 σ = average   |   +3 σ = abundance

Usage
-----
    python main.py

Returns
-------
df_records      — per-tick expression and population data (one row per genome per tick)
df_mutation_log — mutation fixation events
final_genomes   — list of Genome objects still alive at simulation end
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from core.genome      import genome_from_dicts, reset_id_counter
from core.environment import environment_from_kwargs
from core.simulation  import run_simulation


# ============================================================
# 1.  GENOME DEFINITION
# ============================================================
#
# Gene 8-tuple format:
#   (threshold, mode, promoter, enhancer, size_kDa,
#    on_conditions, off_conditions, function)
#
# promoter  — transcription strength: "wk" | "av" | "st"
# enhancer  — expression ceiling:     "wk"→4  "av"→16  "st"→64
# function  — ("ftype", coeff) | False
#
# Condition variables available in on/off lists:
#   Energy, Food, Toxin, Toxin_detected, <GENE_NAME>
# ============================================================

receptors = {
    "ENGSENS":   (12, "qual", "st", "av", 50, ["DIVISION == 'inactive'"], ["DIVISION == 'active'"], False),
    "FOODSENS":  (4,  "qual", "av", "av", 50, ["Energy <= 1", "KINFEED == 'active'"], ["Energy >= 2", "DIVISION == 'active'"], False),
    "TOXSENS":   (2,  "qual", "wk", "wk", 50, ["DIVISION == 'inactive'"], ["Toxin < -2.9", "DIVISION == 'active'"], ("toxsens", 0.01)),
    "TOXNONSENS":(2,  "qual", "wk", "av", 50, ["Energy <= -1"], ["DETOXX == 'active'", "DIVISION == 'active'"], ("toxsens", 0.1)),
    "MUTSENS":   (2,  "qual", "st", "av", 50, ["ENGSENS == 'active'"], ["DIVISION == 'active'"], ("mutsens", 0.1)),
    "STRESSRESP":(2,  "qual", "wk", "av", 50, ["Energy <= -1", "DIVISION == 'inactive'"], ["Energy >= -1", "CDK1 == 'active'", "DIVISION == 'active'"], ("energy", 0.002)),
    "FUNACTIV":  (4,  "qual", "av", "av", 50, ["Energy >= 0"], ["Energy < 0", "KINSTRESS == 'active'", "DIVISION == 'active'"], False),
}

metabolism = {
    "HARVEST":   (2,  "quan", "av", "av", 50,  ["Energy <= 1", "FOODSENS == 'active'"], ["Energy >= 1", "DIVISION == 'active'"], ("energy", 0.005)),
    "FEED":      (2,  "quan", "st", "st", 70,  ["Energy <= 0", "KINFEED == 'active'"], ["Energy >= 0", "Energy <= -2.99", "DIVISION == 'active'"], ("energy", 0.0015)),
    "SAFEED":    (2,  "quan", "av", "st", 150, ["Energy <= -1.5"], ["Energy >= -1.5", "DIVISION == 'active'"], ("energy", 0.005)),
    "RNASE":     (2,  "quan", "st", "av", 150, ["KINSTRESS == 'active'"], ["Energy >= -1.5", "DIVISION == 'active'"], ("RNAdigest", 0.015)),
    "AUTOPHAGY": (4,  "quan", "av", "st", 100, ["Energy >= 1.5"], ["Energy <= 1.5", "DIVISION == 'active'"], ("process", 0.0005)),
    "DETOX":     (2,  "quan", "av", "av", 25,  ["Toxin_detected == True"], ["DETOXX == 'active'", "DIVISION == 'active'"], ("detox", 0.001)),
    "DETOXX":    (2,  "quan", "st", "st", 15,  ["Toxin_detected == True", "Toxin >= -1"], ["Toxin <= -2.5", "CDK1 == 'active'", "DIVISION == 'active'"], ("detox", 0.02)),
    "CELLPROD":  (2,  "quan", "st", "st", 50,  ["KINFUNK == 'active'"], ["Toxin > 1.5", "STRESSRESP == 'active'", "Energy <= -0.5", "DIVISION == 'active'"], False),
}

kinases = {
    "KINFEED":   (3,  "qual", "av", "wk", 50,  ["Energy <= 1", "ENGSENS == 'active'"], ["Energy > 0.5", "DIVISION == 'active'"], False),
    "KINTOX":    (3,  "qual", "av", "wk", 50,  ["Toxin_detected == True"], ["Toxin_detected == False", "DIVISION == 'active'"], False),
    "KINSTRESS": (2,  "qual", "st", "av", 150, ["STRESSRESP == 'active'"], ["Energy > -0.5", "KINSTRESS == 'active'", "DIVISION == 'active'"], False),
    "KINFUNK":   (3,  "qual", "av", "wk", 50,  ["FUNACTIV == 'active'"], ["KINFUNK == 'active'", "STRESSRESP == 'active'", "DIVISION == 'active'"], False),
}

cell_cycle = {
    "CDK1":      (2,  "qual", "wk", "wk", 50,  ["Energy >= 1.5"], ["DIVISION == 'active'"], False),
}

division = {
    "MUTGUARD":  (2,  "qual", "st", "av", 50,  ["DIVISION == 'inactive'"], ["DIVISION == 'active'"], ("mutrep", 0.05)),
    "DIVISION":  (6,  "qual", "av", "av", 50,  ["CDK1 == 'active'"], ["DIVISION == 'active'"], ("div", 1)),
}


# ============================================================
# 2.  ENVIRONMENT DEFINITION
# ============================================================

toxins = {
    "Energotoxin": (-2, ("energy", 0.2)),
    "RNAtoxin":    (-2, ("TPM",    0.1)),
    "Wastetoxin":  (-3, ("common", 0.001)),
    "CytokineX":   (-3, ("energy", 0.001)),
    "CellProduct": (-3, ("energy", 0.001)),
}

cellular_products = {
    "Wastetoxin":  ("energy",  0.005),
    "CytokineX":   ("TPMsum",  0.0001),
    "FooMol":      ("FOODSENS", 0.001),
    "CellProduct": ("CELLPROD", 0.03),
}


# ============================================================
# 3.  RUN
# ============================================================

def main(
    ticks:             int   = 3000,
    mutation_chance:   float = 0.0,
    n_genomes_allowed: int   = 5,
    save_csv:          bool  = False,
):
    """
    Build the founding genome, run the simulation, and return results.

    Parameters
    ----------
    ticks             : number of simulation ticks
    mutation_chance   : per-gene mutation probability per tick
                        (0.0 = completely stable, as in the original run)
    n_genomes_allowed : max number of coexisting genome lineages
    save_csv          : if True, write CSV files to runs/

    Returns
    -------
    df_records        : pd.DataFrame  — per-tick data, one row per genome
    df_mutation_log   : pd.DataFrame  — mutation fixation log
    final_genomes     : list[Genome]
    """
    reset_id_counter()   # ensure founder gets ID 0

    genome = genome_from_dicts(
        receptors         = receptors,
        metabolism        = metabolism,
        kinases           = kinases,
        cell_cycle        = cell_cycle,
        division          = division,
        cell_count        = 10,
        energy            = 0.0,       # 0 σ = average starting energy
        protein_stability = 0.7,
    )

    environment = environment_from_kwargs(
        initial_food      = -3.0,      # −3 σ = very scarce at start
        toxins            = toxins,
        cellular_products = cellular_products,
        support_cell_num  = 1000,
    )

    df_records, df_mutation_log, final_genomes = run_simulation(
        genome             = genome,
        environment        = environment,
        ticks              = ticks,
        energy_cost        = "default",
        toxin_k            = 1.0,
        mutation_chance    = mutation_chance,
        n_genomes_allowed  = n_genomes_allowed,
    )

    # ── Console summary ──────────────────────────────────────────────────
    print("=== Simulation complete ===")
    print(f"Ticks run     : {df_records['Tick'].max() + 1 if not df_records.empty else 0}")
    print(f"Lineages born : {df_records['GenomeID'].nunique() if not df_records.empty else 0}")
    print(f"Surviving     : {len(final_genomes)}")
    print(f"Mutations fixed: {len(df_mutation_log)}")
    print()
    print("--- First 15 rows (founder genome) ---")
    founder_rows = df_records[df_records["GenomeID"] == 0] if not df_records.empty else df_records
    print(founder_rows.head(15).to_string())

    if not df_mutation_log.empty:
        print()
        print("--- Mutation log ---")
        print(df_mutation_log.to_string())

    # ── Optional CSV export ───────────────────────────────────────────────
    if save_csv:
        os.makedirs("runs", exist_ok=True)
        df_records.to_csv("runs/records.csv", index=False)
        df_mutation_log.to_csv("runs/mutation_log.csv", index=False)
        df_records.to_excel("runs/records.xlsx", index=False)
        df_mutation_log.to_excel("runs/mutation_log.xlsx", index=False)
        print("\nCSV files written to runs/")

    return df_records, df_mutation_log, final_genomes


if __name__ == "__main__":
    df_records, df_mutation_log, final_genomes = main(
        ticks             = 500,
        mutation_chance   = 0.0005,
        n_genomes_allowed = 20,
        save_csv          = True,
    )
