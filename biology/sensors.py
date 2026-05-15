"""
biology/sensors.py

Sensor evaluation: toxin detection and mutation sensing.

These are thin wrappers that centralise the logic for deciding
whether TOXSENS / MUTSENS genes successfully "fire" in a given tick.
"""

from __future__ import annotations
from typing import Dict, Tuple

from biology.toxins import detect_effect
from biology.metabolism import gene_attempts


# ---------------------------------------------------------------------------
# Toxin detection
# ---------------------------------------------------------------------------

def evaluate_toxin_sensors(
    gene_names:   list,
    all_genes:    Dict[str, tuple],
    prev_status:  Dict[str, str],
    prev_expr:    Dict[str, float],
    total_toxins: float,
) -> bool:
    """
    Check whether any active toxin-sensor gene detects the current
    toxin level this tick.

    A sensor fires when its detect_effect score exceeds 1.0.

    Parameters
    ----------
    gene_names   : ordered list of gene names
    all_genes    : {name: 8-tuple} — the full genome record
    prev_status  : {name: "active"|"inactive"} from the previous tick
    prev_expr    : {name: expression_level}
    total_toxins : max toxin sigma across all toxins (the "Toxin" variable)

    Returns
    -------
    True if at least one toxsens gene fires, False otherwise.
    """
    for g in gene_names:
        thr, mode, prom, enh, size_kDa, on_cond, off_cond, func = all_genes[g]
        if func and func[0] == "toxsens" and prev_status[g] == "active":
            sens_prob = detect_effect(
                total_toxins,
                detect_effect=func[1],
                k=prev_expr[g],
            )
            if sens_prob > 1.0:
                return True
    return False
