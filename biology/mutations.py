"""
biology/mutations.py

Mutagenesis and mutation-repair logic.

Mutable gene attributes
-----------------------
Each tick, a gene that passes the mutation_chance roll has ONE randomly
chosen attribute altered:

  threshold    : ±1 (integer)
  promoter     : numeric multiplier × uniform(0.9, 1.1),
                 clamped to valid values [1.25, 2.0, 4.0] (nearest)
  enhancer     : numeric cap × uniform(0.9, 1.1),
                 clamped to valid values [4, 16, 64] (nearest)
  func_coeff   : function coefficient × uniform(0.8, 1.25)
                 NOTE: energy_cost field (index 1 when ftype=="secret_cost")
                 must NOT mutate — only the secretion coefficient mutates.
  cond_value   : one numeric literal inside a random on/off condition
                 is multiplied by uniform(0.9, 1.1), rounded to 2 d.p.
  size_kda     : protein size × uniform(0.9, 1.1), clamped to [1, 1000] kDa.

MUTGUARD is excluded from all mutagenesis.
energy_cost (for "secret" function) must NOT mutate.
"""

from __future__ import annotations
import re
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from core.gene import Gene, EXCLUDED_FROM_MUTAGENESIS


# ── Constants ─────────────────────────────────────────────────────────────────

_COEFF_MUTABLE_FTYPES = frozenset({
    "energy", "process", "RNAdigest",
    "detox", "toxresist", "mutsens", "mutrep", "toxsens", "secret",
})

# Promoter valid values and their snap-to-nearest logic
_PROMOTER_VALS = [1.25, 2.0, 4.0]
_ENHANCER_VALS = [4.0, 16.0, 64.0]

def _snap(val: float, choices: list) -> float:
    """Snap val to nearest value in choices."""
    return min(choices, key=lambda c: abs(c - val))

_COEFF_MUT_LOW  = 0.8
_COEFF_MUT_HIGH = 1.25

_COND_MUT_LOW   = 0.9     # ±10 % for condition values and size_kDa
_COND_MUT_HIGH  = 1.1

# Regex: matches an optional leading minus + digits + optional decimal part.
# Excludes pure integers that look like gene-status comparisons (e.g. == 'active').
_NUM_RE = re.compile(r'-?\d+(?:\.\d+)')


# ── MutationEvent ─────────────────────────────────────────────────────────────

@dataclass
class MutationEvent:
    """Describes a single gene-attribute change caused by mutagenesis."""
    gene_name    : str
    attribute    : str
    value_before : object
    value_after  : object


# ── Condition-value helpers ────────────────────────────────────────────────────

def _find_numeric_conditions(conditions: List[str]) -> List[Tuple[int, str]]:
    """
    Return [(index_in_list, condition_string)] for every condition that
    contains at least one numeric literal.
    """
    return [
        (i, cond)
        for i, cond in enumerate(conditions)
        if _NUM_RE.search(cond)
    ]


def _mutate_condition_value(cond: str) -> Tuple[str, str, str]:
    """
    Pick one numeric literal in *cond* at random, multiply by
    uniform(_COND_MUT_LOW, _COND_MUT_HIGH), round to 2 decimal places.

    Returns (new_condition_string, old_value_str, new_value_str).
    """
    matches = list(_NUM_RE.finditer(cond))
    m       = random.choice(matches)
    old_val = float(m.group())
    new_val = round(old_val * random.uniform(_COND_MUT_LOW, _COND_MUT_HIGH), 2)
    new_cond = cond[:m.start()] + str(new_val) + cond[m.end():]
    return new_cond, m.group(), str(new_val)


# ── Core mutator ──────────────────────────────────────────────────────────────

def _mutate_gene_inplace(gene: Gene) -> Optional[MutationEvent]:
    """
    Randomly alter one attribute of *gene* in place.
    Returns a MutationEvent if something changed, None otherwise.
    """
    if gene.name in EXCLUDED_FROM_MUTAGENESIS:
        return None

    # Build pool of available mutation types
    choices = ["threshold", "promoter", "enhancer"]

    has_mutable_coeff = (
        gene.function is not False
        and gene.function[0] in _COEFF_MUTABLE_FTYPES
    )
    if has_mutable_coeff:
        choices.append("func_coeff")

    # Condition-value mutations: pool all conditions that contain numbers
    on_eligible  = _find_numeric_conditions(gene.on_conditions)
    off_eligible = _find_numeric_conditions(gene.off_conditions)
    if on_eligible or off_eligible:
        choices.append("cond_value")

    # size_kDa is always mutable
    choices.append("size_kda")

    mut_type = random.choice(choices)

    # ── threshold ─────────────────────────────────────────────────────────────
    if mut_type == "threshold":
        before = gene.threshold
        gene.threshold = max(1, before + random.choice((-1, 1)))
        after = gene.threshold

    # ── promoter (continuous numeric multiplier) ─────────────────────────────────
    elif mut_type == "promoter":
        before = gene.promoter
        if isinstance(gene.promoter, str):
            cur = {"wk": 1.25, "av": 2.0, "st": 4.0}.get(gene.promoter, 2.0)
        else:
            try:    cur = float(gene.promoter)
            except: cur = 2.0
        # Continuous mutation: multiply by uniform(0.9, 1.1), no hard clamp
        new_val = cur * random.uniform(_COND_MUT_LOW, _COND_MUT_HIGH)
        gene.promoter = round(max(0.01, new_val), 4)  # only keep positive
        after = gene.promoter

    # ── enhancer (continuous numeric cap) ─────────────────────────────────────
    elif mut_type == "enhancer":
        before = gene.enhancer
        if isinstance(gene.enhancer, str):
            cur = {"wk": 4.0, "av": 16.0, "st": 64.0}.get(gene.enhancer, 16.0)
        else:
            try:    cur = float(gene.enhancer)
            except: cur = 16.0
        # Continuous mutation: multiply by uniform(0.9, 1.1), no hard clamp
        new_val = cur * random.uniform(_COND_MUT_LOW, _COND_MUT_HIGH)
        gene.enhancer = round(max(0.01, new_val), 4)  # only keep positive
        after = gene.enhancer

    # ── func_coeff ────────────────────────────────────────────────────────────
    elif mut_type == "func_coeff":
        func = gene.function
        ftype = func[0]
        if ftype == "secret":
            # secret function: (ftype, secretion_coeff, energy_cost)
            # Only the secretion_coeff mutates; energy_cost is fixed.
            sec_coeff = func[1]
            energy_cost = func[2] if len(func) > 2 else 0.005
            before    = sec_coeff
            new_coeff = sec_coeff * random.uniform(_COEFF_MUT_LOW, _COEFF_MUT_HIGH)
            gene.function = (ftype, new_coeff, energy_cost)
            after = new_coeff
        else:
            coeff = func[1]
            before    = coeff
            new_coeff = coeff * random.uniform(_COEFF_MUT_LOW, _COEFF_MUT_HIGH)
            gene.function = (ftype, new_coeff)
            after = new_coeff

    # ── cond_value ────────────────────────────────────────────────────────────
    elif mut_type == "cond_value":
        # Pick randomly from on or off conditions (weighted by count)
        pool: List[Tuple[str, List[str], int]] = []   # (side, list_ref, idx)
        for idx, _ in on_eligible:
            pool.append(("on_cond", gene.on_conditions, idx))
        for idx, _ in off_eligible:
            pool.append(("off_cond", gene.off_conditions, idx))

        side, cond_list, idx = random.choice(pool)
        old_cond = cond_list[idx]
        new_cond, old_val, new_val = _mutate_condition_value(old_cond)
        cond_list[idx] = new_cond
        before = f"{side}[{idx}] …{old_val}…"
        after  = f"{side}[{idx}] …{new_val}…"

    # ── size_kda ──────────────────────────────────────────────────────────────
    else:  # size_kda
        before = gene.size_kDa
        new_size = gene.size_kDa * random.uniform(_COND_MUT_LOW, _COND_MUT_HIGH)
        gene.size_kDa = round(max(1.0, min(1000.0, new_size)), 1)
        after = gene.size_kDa

    # For numeric attributes, avoid false-equal due to float precision
    if mut_type in ("promoter", "enhancer", "func_coeff", "size_kda"):
        try:
            if abs(float(before) - float(after)) < 1e-9:
                return None
        except (TypeError, ValueError):
            if before == after:
                return None
    else:
        if before == after:
            return None
    return MutationEvent(gene.name, mut_type, before, after)


# ── Genome-level mutagenesis — tracked ────────────────────────────────────────

def mutate_genome_tracked(
    genes: Dict[str, Gene],
    mutation_chance: float,
) -> List[MutationEvent]:
    """
    Independently test each gene for mutation with probability *mutation_chance*.
    Mutates *genes* in place; returns a list of MutationEvent for every change.
    """
    events: List[MutationEvent] = []
    for gene in genes.values():
        if random.random() < mutation_chance:
            ev = _mutate_gene_inplace(gene)
            if ev is not None:
                events.append(ev)
    return events


# ── Genome-level mutagenesis — silent ─────────────────────────────────────────

def mutate_genome(genes: Dict[str, Gene], mutation_chance: float) -> None:
    """Mutate genes in place without tracking events."""
    for gene in genes.values():
        if random.random() < mutation_chance:
            _mutate_gene_inplace(gene)


# ── Legacy tuple helper ───────────────────────────────────────────────────────

def mutate_gene_tuple(gene_record: tuple) -> tuple:
    thr, mode, prom, enh, size_kDa, on_cond, off_cond, func = gene_record
    choice = random.choice(("threshold", "promoter", "enhancer"))
    if choice == "threshold":
        thr = max(1, thr + random.choice((-1, 1)))
    elif choice == "promoter":
        prom = random.choice(("wk", "av", "st"))
    else:
        enh = random.choice(("wk", "av", "st"))
    return (thr, mode, prom, enh, size_kDa, on_cond, off_cond, func)


# ── Mutation detection — MUTSENS ──────────────────────────────────────────────

def detect_mutations(
    current_genes:   Dict[str, Gene],
    reference_genes: Dict[str, Gene],
    sens_chance:     float,
    eff_prot:        float,
) -> bool:
    from biology.metabolism import gene_attempts
    attempts = gene_attempts(eff_prot)
    for _ in range(attempts):
        for name, ref_gene in reference_genes.items():
            if name in current_genes:
                if current_genes[name] != ref_gene and random.random() < sens_chance:
                    return True
    return False


# ── Mutation repair — MUTGUARD ────────────────────────────────────────────────

def repair_mutations(
    current_genes:   Dict[str, Gene],
    reference_genes: Dict[str, Gene],
    rep_chance:      float,
    eff_prot:        float,
) -> None:
    from biology.metabolism import gene_attempts
    attempts = gene_attempts(eff_prot)
    for _ in range(attempts):
        for name, ref_gene in reference_genes.items():
            if name not in current_genes:
                continue
            if current_genes[name] != ref_gene:
                if random.random() < rep_chance:
                    current_genes[name] = ref_gene.copy()
                elif random.random() < rep_chance:
                    _mutate_gene_inplace(current_genes[name])
