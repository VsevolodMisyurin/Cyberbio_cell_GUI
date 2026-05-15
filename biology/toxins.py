"""
biology/toxins.py

Toxin effect calculations and cellular-product accumulation logic.

Sigma-scale reminder
--------------------
Toxin sigma  : −3 = absent/baseline, 0 = moderate, +3 = high concentration.
The exponential response means effects grow rapidly above 0 σ and become
negligible below −3 σ.
"""

from __future__ import annotations
import math
import numpy as np
from typing import Dict, Tuple


# ---------------------------------------------------------------------------
# Core response functions
# ---------------------------------------------------------------------------

def toxin_effect(sigma: float, base_effect: float = 0.4, k: float = 0.01) -> float:
    """
    Compute the per-tick penalty imposed by a toxin at concentration *sigma*.

    Uses an exponential (log-linear) response: effect doubles every ~0.7 σ.
    Sigma is clamped to [−8, 3] to prevent overflow.

    Parameters
    ----------
    sigma       : toxin concentration in σ units
    base_effect : coefficient scaling the effect magnitude
    k           : (unused legacy parameter, kept for signature compatibility)
    """
    clamped = max(min(sigma, 3.0), -8.0)
    return base_effect * math.exp(clamped)


def detect_effect(sigma: float, detect_effect: float = 0.05, k: float = 1.0) -> float:
    """
    Probability-like score for a toxin-sensor gene detecting a toxin.

    Returns a value that exceeds 1 when the toxin is above a detection
    threshold (triggering toxin_detected = True in the engine).

    Sigma is clamped to [−8, 8].
    """
    clamped = max(min(sigma, 8.0), -8.0)
    return (k * math.exp(clamped)) / (64.0 * detect_effect)


# ---------------------------------------------------------------------------
# Evaluate all toxins → penalties + level snapshot
# ---------------------------------------------------------------------------

def evaluate_toxins(
    toxins: Dict[str, Tuple],
    toxin_k: float = 1.0,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Compute aggregate penalties and current sigma levels for all toxins.

    Parameters
    ----------
    toxins  : {name: (sigma, (param, base_effect))}
    toxin_k : global scaling factor (legacy, currently unused in formula)

    Returns
    -------
    tox_penalties : {param: total_penalty_value}
        Keyed by affected parameter: "energy", "TPM", etc.
        "common" toxins contribute to both "energy" and "TPM".
    tox_levels    : {name: sigma}
        Current sigma for each toxin (for logging).
    """
    tox_penalties: Dict[str, float] = {}
    tox_levels:    Dict[str, float] = {}

    for name, (sigma, (param, base_eff)) in toxins.items():
        tox_levels[name] = sigma
        eff = toxin_effect(sigma, base_eff, toxin_k)
        if param == "common":
            for p in ("energy", "TPM"):
                tox_penalties[p] = tox_penalties.get(p, 0.0) + eff
        else:
            tox_penalties[param] = tox_penalties.get(param, 0.0) + eff

    return tox_penalties, tox_levels


# ---------------------------------------------------------------------------
# Cellular product secretion → environment update
# ---------------------------------------------------------------------------

def generate_cellular_products(
    prev_expr:         Dict[str, float],
    prev_status:       Dict[str, str],
    cellular_products: Dict[str, Tuple],
    env_products:      Dict[str, float],
    toxins:            Dict[str, Tuple],
    energy_spent:      float,
    TPM_sum:           float,
    support_ratio:     float,
    gene_prot:         Dict[str, float] = None,
) -> Tuple[Dict[str, float], Dict[str, Tuple]]:
    """
    Compute how much of each cellular product is secreted this tick and
    accumulate it in the shared environment.

    Product secretion modes
    -----------------------
    "energy"    : delta = coeff × energy_spent
    "TPMsum"    : delta = coeff × total_TPM
    "secret:<g>": delta = coeff × protein_level[g]  (gene g has ftype "secret")
    <gene_name> : delta = coeff × expr[gene]  (legacy: only when gene is active)

    The per-cell delta is scaled by *support_ratio*.

    Returns
    -------
    (env_products, toxins)  — both mutated in place and returned
    """
    for name, prod_def in cellular_products.items():
        # prod_def may be (mode, coeff) or (mode, coeff, energy_cost)
        mode  = prod_def[0]
        coeff = prod_def[1]
        # energy_cost is deducted from cell energy directly in _process_gene_functions
        # for "secret" mode; here we only update env.

        if mode == "energy":
            delta_per_cell = coeff * energy_spent
        elif mode == "TPMsum":
            delta_per_cell = coeff * TPM_sum
        elif mode.startswith("secret:"):
            # Secretion driven by protein level of named gene
            gene_name = mode[len("secret:"):]
            prot = (gene_prot or {}).get(gene_name, 0.0)
            delta_per_cell = coeff * prot
        elif mode in prev_status:
            delta_per_cell = (
                coeff * prev_expr[mode] if prev_status[mode] == "active" else 0.0
            )
        else:
            delta_per_cell = 0.0

        total_delta = delta_per_cell * support_ratio
        env_products[name] = env_products.get(name, -3.0) + total_delta

        if name in toxins:
            sigma, (p, b) = toxins[name]
            toxins[name] = (sigma + total_delta, (p, b))

    return env_products, toxins
