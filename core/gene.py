"""
core/gene.py

A single gene record. All values are stored as attributes but the class
remains fully compatible with the original tuple representation:
    (threshold, mode, promoter, enhancer, size_kDa,
     on_conditions, off_conditions, function)

Sigma-scale reminder
---------------------
Energy, food, and toxin concentrations are expressed in standard deviations
from a baseline.  0 σ = average; −2 σ = scarcity / low energy; +2 σ = abundance.
Gene conditions use these sigma values directly.
"""

from __future__ import annotations
import copy
from typing import Optional, Tuple, List


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROMOTER_LEVELS = ("wk", "av", "st")
ENHANCER_LEVELS = ("wk", "av", "st")
ENHANCER_CAP    = {"wk": 4, "av": 16, "st": 64}

# Genes that are never subject to random mutagenesis
EXCLUDED_FROM_MUTAGENESIS: frozenset[str] = frozenset({"MUTGUARD"})


# ---------------------------------------------------------------------------
# Gene class
# ---------------------------------------------------------------------------

class Gene:
    """
    Represents a single gene with its regulatory and functional parameters.

    Parameters
    ----------
    name : str
        Unique identifier of the gene (e.g. "ENGSENS", "HARVEST").
    threshold : int
        Minimum protein level required to execute the gene's function.
    mode : str
        Expression mode — currently always "qual" or "quan" (qualitative /
        quantitative); kept for forward compatibility.
    promoter : str
        Transcription strength: "wk" | "av" | "st".
        Controls how fast expression level grows each active tick.
    enhancer : str
        Maximum expression cap: "wk" → 4, "av" → 16, "st" → 64.
    size_kDa : float
        Protein size in kilodaltons.  Larger proteins degrade faster
        (see biology/metabolism.py :: size_modifier).
    on_conditions : list[str]
        Boolean expressions (evaluated against the cell's local variables)
        that ALL must be True to activate the gene.
    off_conditions : list[str]
        Boolean expressions; ANY being True suppresses / deactivates the gene.
    function : tuple | False
        The biological function executed when protein >= threshold.
        Format: ("ftype", coefficient) or False for regulatory-only genes.
        Supported ftypes: "energy", "process", "RNAdigest", "div",
                          "detox", "mutsens", "mutrep", "toxsens", "div".
    """

    __slots__ = (
        "name", "threshold", "mode", "promoter", "enhancer",
        "size_kDa", "on_conditions", "off_conditions", "function",
        # runtime state — reset on division / initialisation
        "expr",       # current expression level (TPM-like integer)
        "status",     # "active" | "inactive"
        "protein",    # accumulated protein level (float)
        "deact_delay",# hysteresis flag: one-tick delay before deactivation
        "expressed",  # was the gene expressed last tick?
    )

    def __init__(
        self,
        name: str,
        threshold: int,
        mode: str,
        promoter: str,
        enhancer: str,
        size_kDa: float,
        on_conditions: List[str],
        off_conditions: List[str],
        function,
    ):
        self.name          = name
        self.threshold     = threshold
        self.mode          = mode
        self.promoter      = promoter
        self.enhancer      = enhancer
        self.size_kDa      = size_kDa
        self.on_conditions = list(on_conditions)
        self.off_conditions= list(off_conditions)
        self.function      = function

        # initialise runtime state
        self.reset()

    # ------------------------------------------------------------------
    # Runtime state helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset to freshly-initialised (post-division) state."""
        self.expr        = 1
        self.status      = "inactive"
        self.protein     = 0.0
        self.deact_delay = False
        self.expressed   = False

    # ------------------------------------------------------------------
    # Tuple compatibility (for passing into legacy functions if needed)
    # ------------------------------------------------------------------

    def as_tuple(self) -> tuple:
        """Return the original 8-tuple representation."""
        return (
            self.threshold, self.mode, self.promoter, self.enhancer,
            self.size_kDa, self.on_conditions, self.off_conditions,
            self.function,
        )

    # ------------------------------------------------------------------
    # Expression growth
    # ------------------------------------------------------------------

    def grow_expression(self, tox_tpm_penalty: float = 0.0) -> None:
        """
        Increase expression level according to promoter strength and cap
        it at the enhancer ceiling.  Applies TPM toxin penalty afterward.
        Called only when the gene is in expressed state.
        """
        raw = (
            self.expr + 1          if self.promoter == "wk" else
            self.expr * 2          if self.promoter == "av" else
            self.expr * 4          if self.promoter == "st" else
            self.expr
        )
        cap = ENHANCER_CAP.get(self.enhancer, 64)
        tpen = 1.0 - min(tox_tpm_penalty, 1.0)
        self.expr = max(1, min(raw, cap) * tpen)

    # ------------------------------------------------------------------
    # Protein dynamics
    # ------------------------------------------------------------------

    def update_protein(self, base_stability: float) -> None:
        """
        Decay existing protein (stability × size modifier) then add
        newly synthesised protein from the previous expression level.

        Proteins ≥ 150 kDa degrade 4× faster than proteins ≤ 10 kDa.
        """
        from biology.metabolism import size_modifier  # local import avoids cycles
        stab    = base_stability * size_modifier(self.size_kDa)
        decayed = self.protein * stab
        added   = max(0.0, self.expr - 1)
        self.protein = decayed + added

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def mutate(self) -> None:
        """
        Randomly alter threshold, promoter, or enhancer (in-place).
        Genes listed in EXCLUDED_FROM_MUTAGENESIS are silently skipped.
        """
        import random
        if self.name in EXCLUDED_FROM_MUTAGENESIS:
            return
        choice = random.choice(["threshold", "promoter", "enhancer"])
        if choice == "threshold":
            self.threshold = max(1, self.threshold + random.choice([-1, 1]))
        elif choice == "promoter":
            self.promoter  = random.choice(list(PROMOTER_LEVELS))
        else:
            self.enhancer  = random.choice(list(ENHANCER_LEVELS))

    # ------------------------------------------------------------------
    # Deep copy
    # ------------------------------------------------------------------

    def copy(self) -> "Gene":
        return copy.deepcopy(self)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Gene({self.name!r}, thr={self.threshold}, "
            f"prom={self.promoter}, enh={self.enhancer}, "
            f"expr={self.expr:.1f}, status={self.status})"
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, Gene):
            return NotImplemented
        return self.as_tuple() == other.as_tuple()


# ---------------------------------------------------------------------------
# Factory: build a Gene from a raw tuple (original format)
# ---------------------------------------------------------------------------

def gene_from_tuple(name: str, record: tuple) -> Gene:
    """
    Construct a Gene from the original 8-element tuple used in stable_genome.py.

    Example
    -------
    gene_from_tuple("ENGSENS",
        (12, "qual", "st", "av", 50,
         ["DIVISION == 'inactive'"], ["DIVISION == 'active'"], False))
    """
    thr, mode, prom, enh, size_kDa, on_cond, off_cond, func = record
    return Gene(name, thr, mode, prom, enh, size_kDa, on_cond, off_cond, func)
