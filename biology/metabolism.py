"""
biology/metabolism.py

Pure mathematical helpers related to protein stability, energy costs,
and cellular function execution.

All energy / food / toxin values are in σ (standard deviation) units:
  0 σ = baseline average; ±3 σ = extreme states.
"""

from __future__ import annotations
import math
import numpy as np
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Protein size → stability modifier
# ---------------------------------------------------------------------------

def size_modifier(size_kDa: float) -> float:
    """
    Return a stability multiplier based on protein size.

    Proteins ≥ 150 kDa degrade 4× faster than proteins ≤ 10 kDa.
    Linear interpolation between the two extremes.

        size_kDa ≤  10  →  1.00  (most stable)
        size_kDa ≥ 150  →  0.25  (degrades 4× faster)
    """
    if size_kDa <= 10:
        return 1.0
    if size_kDa >= 150:
        return 0.25
    return 0.25 + (150.0 - size_kDa) / 140.0


# ---------------------------------------------------------------------------
# Expression growth
# ---------------------------------------------------------------------------

# Numeric promoter/enhancer defaults (used for legacy string values)
_PROMOTER_MULT = {"wk": 1.25, "av": 2.0, "st": 4.0}
_ENHANCER_CAP  = {"wk":  4.0, "av": 16.0, "st": 64.0}


def grow_and_cap(expr: float, promoter, enhancer) -> float:
    """
    Increase expression level according to promoter multiplier and cap it
    at the enhancer ceiling.

    Promoter is now a numeric multiplier:
      1.25  (formerly "wk")  →  expr × 1.25
      2.0   (formerly "av")  →  expr × 2.0
      4.0   (formerly "st")  →  expr × 4.0
    Legacy string values "wk"/"av"/"st" are still accepted.

    Enhancer is now a numeric cap:
      4     (formerly "wk")  →  cap at 4
      16    (formerly "av")  →  cap at 16
      64    (formerly "st")  →  cap at 64
    Legacy string values "wk"/"av"/"st" are still accepted.
    """
    # Resolve promoter: numeric multiplier or legacy string
    if isinstance(promoter, str):
        mult = _PROMOTER_MULT.get(promoter, 2.0)
    else:
        mult = float(promoter)

    # Resolve enhancer: numeric cap or legacy string
    if isinstance(enhancer, str):
        cap = _ENHANCER_CAP.get(enhancer, 64.0)
    else:
        cap = float(enhancer)

    return min(expr * mult, cap)


# ---------------------------------------------------------------------------
# Protein attempt count
# ---------------------------------------------------------------------------

def gene_attempts(expr: float = 12) -> int:
    """
    Number of attempts a protein has to perform its stochastic function
    per tick.  Scales with expression level.
    """
    return 3 + int(expr // 12)


# ---------------------------------------------------------------------------
# Cell death
# ---------------------------------------------------------------------------

def cell_death_probability(energy: float) -> float:
    """
    Logistic function: probability of a single cell dying this tick given
    its current energy level (σ units).

    Death risk is negligible for |energy| < ~2 σ and approaches 1 when
    energy reaches −3 σ (starvation) or highly positive values are sustained.
    """
    x, k, x0 = abs(energy), 3.0, 3.5
    return 1.0 / (1.0 + math.exp(-k * (x - x0)))


# ---------------------------------------------------------------------------
# Energy cost helpers
# ---------------------------------------------------------------------------

def default_energy_cost(n_genes: int) -> float:
    """
    Default per-tick energy cost per unit of TPM expression.
    Scales inversely with genome size so that larger genomes don't
    automatically starve cells.
    """
    return 1.0 / (n_genes * 16)


# ---------------------------------------------------------------------------
# Condition evaluators
# ---------------------------------------------------------------------------

def cond_all(conditions: List[str], local_vars: dict) -> bool:
    """Return True only if ALL conditions evaluate to True."""
    return all(eval(c, {}, local_vars) for c in conditions)


def cond_any(conditions: List[str], local_vars: dict) -> bool:
    """Return True if ANY condition evaluates to True."""
    return any(eval(c, {}, local_vars) for c in conditions)
