"""
core/genome.py

The Genome class wraps an ordered collection of Gene objects and carries
population-level state: how many cells share this genome and their energy.

Multi-lineage design
--------------------
Each Genome has a unique integer ID assigned at creation time.
The founding genome always receives ID 0 (when run_simulation calls
reset_id_counter() before creating the first genome).

When a mutation survives division, genome.fork() creates a child lineage
with a new ID, inheriting the mutated gene definitions but starting with
fresh runtime state and cell_count = 1.  The parent loses 1 cell.

Sigma-scale reminder
--------------------
energy  : 0 σ = average cellular energy
          −3 σ = lethal starvation
          +3 σ = maximal saturation
"""

from __future__ import annotations
import copy
from typing import Dict, Iterator, List, Optional

from core.gene import Gene, gene_from_tuple


# ---------------------------------------------------------------------------
# Global genome ID counter
# ---------------------------------------------------------------------------

_genome_id_counter: int = 0


def _next_id() -> int:
    global _genome_id_counter
    gid = _genome_id_counter
    _genome_id_counter += 1
    return gid


def reset_id_counter() -> None:
    """Reset the global ID counter to 0.  Call once before each simulation."""
    global _genome_id_counter
    _genome_id_counter = 0


# ---------------------------------------------------------------------------
# Genome class
# ---------------------------------------------------------------------------

class Genome:
    """
    A complete genome: an ordered mapping of gene-name → Gene, plus
    population counters for the cells that share this genome.

    Attributes
    ----------
    genome_id : int
        Unique identifier.  The founding genome always receives ID 0.
    parent_id : int | None
        ID of the genome this one was derived from (None for the founder).
    genes : dict[str, Gene]
        All genes in declaration order, keyed by name.
        This is the *live* copy — may carry mutations.
    reference_genes : dict[str, Gene]
        Deep-copy snapshot taken at genome creation or after a successful
        division.  Used by MUTSENS / MUTGUARD to detect / repair mutations.
    cell_count : int
        Number of living cells currently carrying this genome.
    energy : float  (σ units)
        Mean energy level of the cell population.
    mut_detected : bool
        True when MUTSENS found a mutation this tick.
    protein_stability : dict[str, float]
        Per-gene base stability coefficient (0 < s ≤ 1.0).
    """

    def __init__(
        self,
        genes:             Dict[str, Gene],
        cell_count:        int            = 1,
        energy:            float          = 0.0,
        protein_stability                 = None,   # float | dict | None
        parent_id:         Optional[int]  = None,
        _force_id:         Optional[int]  = None,   # internal: pin to a specific id
    ):
        self.genome_id: int           = _force_id if _force_id is not None else _next_id()
        self.parent_id: Optional[int] = parent_id

        self.genes: Dict[str, Gene]           = genes
        self.reference_genes: Dict[str, Gene] = {
            name: g.copy() for name, g in genes.items()
        }

        self.cell_count   = cell_count
        self.energy       = energy
        self.mut_detected = False

        # Normalise protein_stability into a per-gene dict
        if isinstance(protein_stability, (int, float)):
            self.protein_stability: Dict[str, float] = {
                name: float(protein_stability) for name in genes
            }
        elif isinstance(protein_stability, dict):
            self.protein_stability = {
                name: protein_stability.get(name, 1.0) for name in genes
            }
        else:
            self.protein_stability = {name: 1.0 for name in genes}

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def gene_list(self) -> List[str]:
        return list(self.genes.keys())

    @property
    def gene_count(self) -> int:
        return len(self.genes)

    def __getitem__(self, name: str) -> Gene:
        return self.genes[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.genes)

    def __len__(self) -> int:
        return len(self.genes)

    def __contains__(self, name: str) -> bool:
        return name in self.genes

    # ------------------------------------------------------------------
    # State extraction  (plain dicts for the simulation engine)
    # ------------------------------------------------------------------

    def expr_dict(self) -> Dict[str, float]:
        return {name: g.expr for name, g in self.genes.items()}

    def status_dict(self) -> Dict[str, str]:
        return {name: g.status for name, g in self.genes.items()}

    def protein_dict(self) -> Dict[str, float]:
        return {name: g.protein for name, g in self.genes.items()}

    def deact_delay_dict(self) -> Dict[str, bool]:
        return {name: g.deact_delay for name, g in self.genes.items()}

    def expressed_dict(self) -> Dict[str, bool]:
        return {name: g.expressed for name, g in self.genes.items()}

    def all_genes_tuple_dict(self) -> Dict[str, tuple]:
        """Return {name: 8-tuple} for compatibility with engine helpers."""
        return {name: g.as_tuple() for name, g in self.genes.items()}

    # ------------------------------------------------------------------
    # State restoration  (write engine output dicts back into Gene objects)
    # ------------------------------------------------------------------

    def apply_expr_dict(self, d: Dict[str, float]) -> None:
        for name, val in d.items():
            if name in self.genes:
                self.genes[name].expr = val

    def apply_status_dict(self, d: Dict[str, str]) -> None:
        for name, val in d.items():
            if name in self.genes:
                self.genes[name].status = val

    def apply_protein_dict(self, d: Dict[str, float]) -> None:
        for name, val in d.items():
            if name in self.genes:
                self.genes[name].protein = val

    def apply_deact_delay_dict(self, d: Dict[str, bool]) -> None:
        for name, val in d.items():
            if name in self.genes:
                self.genes[name].deact_delay = val

    def apply_expressed_dict(self, d: Dict[str, bool]) -> None:
        for name, val in d.items():
            if name in self.genes:
                self.genes[name].expressed = val

    # ------------------------------------------------------------------
    # Division / state reset
    # ------------------------------------------------------------------

    def reset_after_division(self) -> None:
        """
        Reset all gene runtime state to post-division defaults and
        refresh the reference genome snapshot to the current (mutated)
        gene definitions.
        """
        for g in self.genes.values():
            g.reset()
        self.reference_genes = {name: g.copy() for name, g in self.genes.items()}
        self.mut_detected = False

    # ------------------------------------------------------------------
    # Fork: create a child genome carrying a fixed mutation
    # ------------------------------------------------------------------

    def fork(self) -> "Genome":
        """
        Spawn a child genome lineage immediately upon mutation — no division needed.

        Behaviour
        ---------
        - One cell leaves the parent population and becomes the founder of the
          child lineage: self.cell_count -= 1.
        - The child inherits a deep copy of the *current* (mutated) gene
          definitions.  These become the child's live genes AND its reference
          (mutations are the new normal for the child).
        - The child's runtime gene state (expr, status, protein, …) is copied
          from the parent's current state — the cell carries over its
          regulatory state into the new lineage.
        - After fork(), the caller must restore the parent's genes to
          self.reference_genes so the remaining parent cells are unaffected.

        Returns the newly created child Genome.
        """
        # Child genes: deep copy of the mutated state
        child_genes = {name: g.copy() for name, g in self.genes.items()}
        child = Genome(
            genes             = child_genes,
            cell_count        = 1,
            energy            = self.energy,
            protein_stability = dict(self.protein_stability),
            parent_id         = self.genome_id,
        )
        # Reference = current mutated state (mutations are "normal" for child)
        child.reference_genes = {name: g.copy() for name, g in child_genes.items()}
        # Runtime state: carry over from parent (cell is mid-tick, not reset)
        # No reset here — child ticks this same turn as an independent genome.

        self.cell_count = max(0, self.cell_count - 1)
        return child

    # ------------------------------------------------------------------
    # Deep copy
    # ------------------------------------------------------------------

    def copy(self) -> "Genome":
        return copy.deepcopy(self)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        pid = f"←{self.parent_id}" if self.parent_id is not None else "founder"
        return (
            f"Genome(id={self.genome_id} [{pid}], "
            f"cells={self.cell_count}, "
            f"energy={self.energy:.2f}σ)"
        )


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def genome_from_dicts(
    receptors:         dict = None,
    metabolism:        dict = None,
    kinases:           dict = None,
    cell_cycle:        dict = None,
    division:          dict = None,
    cell_count:        int   = 1,
    energy:            float = 0.0,
    protein_stability        = None,
) -> Genome:
    """
    Build a Genome from the category-dicts used in main.py.

    Genes are added in declaration order:
        receptors → metabolism → kinases → cell_cycle → division

    Each value must be an 8-tuple:
        (threshold, mode, promoter, enhancer, size_kDa,
         on_conditions, off_conditions, function)
    """
    combined: Dict[str, tuple] = {}
    for category in (receptors, metabolism, kinases, cell_cycle, division):
        if category:
            combined.update(category)

    genes = {name: gene_from_tuple(name, rec) for name, rec in combined.items()}
    return Genome(
        genes             = genes,
        cell_count        = cell_count,
        energy            = energy,
        protein_stability = protein_stability,
    )
