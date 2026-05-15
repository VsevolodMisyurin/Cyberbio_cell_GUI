"""
core/environment.py

The Environment holds everything that lives *outside* individual cells:
food concentration, toxin sigmas, and secreted cellular products.

Sigma-scale reminder
--------------------
All concentrations are expressed in standard deviations from a baseline:

  food    :  −3 σ = extreme scarcity   |  0 σ = average  |  +3 σ = abundance
  toxins  :  −3 σ = absent / baseline  |  0 σ = moderate effect  |  +3 σ = high
  products:  same convention as toxins

This representation makes sigmoid / exponential response functions
mathematically convenient and physically interpretable.
"""

from __future__ import annotations
import copy
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Toxin descriptor
# ---------------------------------------------------------------------------

class Toxin:
    """
    One toxin species present in the environment.

    Attributes
    ----------
    name   : str   – identifier, e.g. "Energotoxin"
    sigma  : float – current concentration in σ units
    param  : str   – which cellular parameter is penalised:
                     "energy" | "TPM" | "RNAdigest" | "common"
                     ("common" applies to both energy and TPM)
    base_effect : float
                 – scaling coefficient passed to toxin_effect()
    """

    __slots__ = ("name", "sigma", "param", "base_effect")

    def __init__(self, name: str, sigma: float, param: str, base_effect: float):
        self.name        = name
        self.sigma       = sigma
        self.param       = param
        self.base_effect = base_effect

    # ------------------------------------------------------------------
    # Compatibility with original dict format
    # ------------------------------------------------------------------

    def as_tuple(self) -> Tuple[float, Tuple[str, float]]:
        """Return (sigma, (param, base_effect)) — the engine's native format."""
        return (self.sigma, (self.param, self.base_effect))

    @classmethod
    def from_tuple(cls, name: str, record: tuple) -> "Toxin":
        """
        Build from the original dict value:
            "Energotoxin": (-2, ("energy", 0.2))
        """
        sigma, (param, base_effect) = record
        return cls(name, sigma, param, base_effect)

    def copy(self) -> "Toxin":
        return copy.deepcopy(self)

    def __repr__(self) -> str:
        return f"Toxin({self.name!r}, σ={self.sigma:.2f}, param={self.param!r})"


# ---------------------------------------------------------------------------
# Environment class
# ---------------------------------------------------------------------------

class Environment:
    """
    Shared extracellular milieu in which all cells live.

    Attributes
    ----------
    food : float  (σ units)
        Nutrient concentration.  Regenerates every tick (capped at +3 σ).
        Cells deplete it via HARVEST / FEED / SAFEED genes.

    toxins : dict[str, Toxin]
        All toxin species currently in the environment.

    products : dict[str, float]
        Cellular secretion levels (σ units).  Products that are also listed
        in *toxins* update those toxin sigmas each tick.

    support_cell_num : int
        Carrying capacity — the total number of cells the environment can
        support.  Used to compute the support_ratio = cell_count / capacity,
        which scales nutrient depletion and product accumulation.
    """

    def __init__(
        self,
        initial_food: float         = 0.0,
        toxins: Dict[str, tuple]    = None,
        cellular_products: Dict[str, tuple] = None,
        support_cell_num: int       = 1000,
    ):
        # Food (σ units; 0 = average, −3 = severe scarcity, +3 = abundance)
        self.food: float            = max(min(initial_food, 3.0), -3.0)
        self.support_cell_num: int  = support_cell_num

        # Toxins
        self.toxins: Dict[str, Toxin] = {}
        if toxins:
            for name, record in toxins.items():
                self.toxins[name] = Toxin.from_tuple(name, record)

        # Cellular products (secreted molecules tracked in environment)
        # product_defs stores (mode, coeff) — used by the engine each tick
        self.product_defs: Dict[str, Tuple[str, float]] = dict(cellular_products or {})
        # product_levels starts at −3 σ (absent)
        self.product_levels: Dict[str, float] = {
            name: -3.0 for name in self.product_defs
        }

    # ------------------------------------------------------------------
    # Tick-level food regeneration
    # ------------------------------------------------------------------

    def regenerate_food(self) -> None:
        """
        Food regenerates by +1 σ per tick, capped at +3 σ.
        Called at the *start* of each simulation tick, before cells act.
        """
        self.food = min(self.food + 1.0, 3.0)
        self.food = max(self.food, -3.0)

    # ------------------------------------------------------------------
    # Engine-format dict converters
    # ------------------------------------------------------------------

    def toxins_as_dict(self) -> Dict[str, Tuple]:
        """Return {name: (sigma, (param, base_effect))} for engine compatibility."""
        return {name: t.as_tuple() for name, t in self.toxins.items()}

    def update_toxins_from_dict(self, d: Dict[str, Tuple]) -> None:
        """Absorb engine output back into Toxin objects."""
        for name, (sigma, (param, base_effect)) in d.items():
            if name in self.toxins:
                self.toxins[name].sigma       = sigma
                self.toxins[name].param       = param
                self.toxins[name].base_effect = base_effect
            else:
                self.toxins[name] = Toxin(name, sigma, param, base_effect)

    def update_product_levels_from_dict(self, d: Dict[str, float]) -> None:
        """Absorb engine-computed product levels."""
        self.product_levels.update(d)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def max_toxin_sigma(self) -> float:
        """Worst-case (highest) toxin sigma — used as the single 'Toxin' value."""
        if not self.toxins:
            return -3.0
        return max(t.sigma for t in self.toxins.values())

    # ------------------------------------------------------------------
    # Deep copy
    # ------------------------------------------------------------------

    def copy(self) -> "Environment":
        return copy.deepcopy(self)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        tox_summary = ", ".join(
            f"{n}={t.sigma:.2f}σ" for n, t in self.toxins.items()
        )
        return (
            f"Environment(food={self.food:.2f}σ, "
            f"capacity={self.support_cell_num}, "
            f"toxins=[{tox_summary}])"
        )


# ---------------------------------------------------------------------------
# Factory helper — build from the stable_genome.py keyword args
# ---------------------------------------------------------------------------

def environment_from_kwargs(
    initial_food: float           = 0.0,
    toxins: Dict[str, tuple]      = None,
    cellular_products: Dict       = None,
    support_cell_num: int         = 1000,
) -> Environment:
    return Environment(
        initial_food      = initial_food,
        toxins            = toxins,
        cellular_products = cellular_products,
        support_cell_num  = support_cell_num,
    )
