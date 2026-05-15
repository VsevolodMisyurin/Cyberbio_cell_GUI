"""
gui/utils/collections.py

In-memory library of genome and environment presets.
Saved as plain Python dicts so they survive import without any GUI toolkit.
A JSON backend can replace the in-memory store without changing callers.
"""

from __future__ import annotations
import json, os
from pathlib import Path
from typing import Dict, Any

# ── Storage paths ─────────────────────────────────────────────────────────────
_DATA_DIR    = Path(os.path.expanduser("~")) / ".cell_sim"
_GENOME_FILE = _DATA_DIR / "genome_collection.json"
_ENV_FILE    = _DATA_DIR / "env_collection.json"
_CRYO_FILE   = _DATA_DIR / "cryobank.json"


def _ensure_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load(path: Path, default: dict) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return default


def _save(path: Path, data: dict):
    _ensure_dir()
    path.write_text(json.dumps(data, indent=2))


# ── Built-in genome preset ────────────────────────────────────────────────────

STABLE_GENOME_PRESET: Dict[str, Any] = {
    "receptors": {
        "ENGSENS": [
            12,
            "qual",
            4.0,
            16,
            50.0,
            [
                "DIVISION == 'inactive'"
            ],
            [
                "DIVISION == 'active'"
            ],
            False
        ],
        "FOODSENS": [
            4,
            "qual",
            2.0,
            16,
            50.0,
            [
                "Energy <= 1",
                "KINFEED == 'active'"
            ],
            [
                "Energy >= 2",
                "DIVISION == 'active'"
            ],
            [
                "secret",
                0.001
            ]
        ],
        "TOXSENS": [
            2,
            "qual",
            1.25,
            4,
            50.0,
            [
                "DIVISION == 'inactive'"
            ],
            [
                "Toxin < -2.9",
                "DIVISION == 'active'"
            ],
            [
                "toxsens",
                0.01
            ]
        ],
        "TOXNONSENS": [
            2,
            "qual",
            1.25,
            16,
            50.0,
            [
                "Energy <= -1"
            ],
            [
                "DETOXX == 'active'",
                "DIVISION == 'active'"
            ],
            [
                "toxsens",
                0.1
            ]
        ],
        "MUTSENS": [
            2,
            "qual",
            4.0,
            16,
            50.0,
            [
                "ENGSENS == 'active'"
            ],
            [
                "DIVISION == 'active'"
            ],
            [
                "mutsens",
                0.1
            ]
        ],
        "STRESSRESP": [
            2,
            "qual",
            1.25,
            16,
            50.0,
            [
                "Energy <= -1",
                "DIVISION == 'inactive'"
            ],
            [
                "Energy >= -1",
                "CDK1 == 'active'",
                "DIVISION == 'active'"
            ],
            [
                "energy",
                0.002
            ]
        ],
        "FUNACTIV": [
            4,
            "qual",
            2.0,
            16,
            50.0,
            [
                "Energy >= 0"
            ],
            [
                "Energy < 0",
                "KINSTRESS == 'active'",
                "DIVISION == 'active'"
            ],
            False
        ]
    },
    "metabolism": {
        "HARVEST": [
            2,
            "quan",
            2.0,
            16,
            50.0,
            [
                "Energy <= 1",
                "FOODSENS == 'active'"
            ],
            [
                "Energy >= 1",
                "DIVISION == 'active'"
            ],
            [
                "energy",
                0.005
            ]
        ],
        "FEED": [
            2,
            "quan",
            4.0,
            64,
            70.0,
            [
                "Energy <= 0",
                "KINFEED == 'active'"
            ],
            [
                "Energy >= 0",
                "Energy <= -2.99",
                "DIVISION == 'active'"
            ],
            [
                "energy",
                0.0015
            ]
        ],
        "SAFEED": [
            2,
            "quan",
            2.0,
            64,
            150.0,
            [
                "Energy <= -1.5"
            ],
            [
                "Energy >= -1.5",
                "DIVISION == 'active'"
            ],
            [
                "energy",
                0.005
            ]
        ],
        "RNASE": [
            2,
            "quan",
            4.0,
            16,
            150.0,
            [
                "KINSTRESS == 'active'"
            ],
            [
                "Energy >= -1.5",
                "DIVISION == 'active'"
            ],
            [
                "RNAdigest",
                0.015
            ]
        ],
        "AUTOPHAGY": [
            4,
            "quan",
            2.0,
            64,
            100.0,
            [
                "Energy >= 1.5"
            ],
            [
                "Energy <= 1.5",
                "DIVISION == 'active'"
            ],
            [
                "process",
                0.0005
            ]
        ],
        "DETOX": [
            2,
            "quan",
            2.0,
            16,
            25.0,
            [
                "Toxin_detected == True"
            ],
            [
                "DETOXX == 'active'",
                "Energy >= 0.5",
                "DIVISION == 'active'"
            ],
            [
                "detox",
                0.001
            ]
        ],
        "DETOXX": [
            2,
            "quan",
            4.0,
            64,
            15.0,
            [
                "Toxin_detected == True",
                "Toxin >= -1"
            ],
            [
                "Toxin <= -2.5",
                "CDK1 == 'active'",
                "DIVISION == 'active'"
            ],
            [
                "detox",
                0.02
            ]
        ],
        "CELLPROD": [
            2,
            "quan",
            4.0,
            64,
            50.0,
            [
                "KINFUNK == 'active'"
            ],
            [
                "Toxin > 1.5",
                "STRESSRESP == 'active'",
                "Energy <= -0.5",
                "DIVISION == 'active'"
            ],
            [
                "secret",
                0.01
            ]
        ],
        "TOXRESIST": [
            2,
            "quan",
            2.0,
            16,
            25.0,
            [
                "Toxin_detected == True"
            ],
            [
                "DETOXX == 'active'",
                "Energy >= 0.5",
                "DIVISION == 'active'"
            ],
            [
                "toxresist",
                0.001
            ]
        ]
    },
    "kinases": {
        "KINFEED": [
            3,
            "qual",
            2.0,
            4,
            50.0,
            [
                "Energy <= 1",
                "ENGSENS == 'active'"
            ],
            [
                "Energy > 0.5",
                "DIVISION == 'active'"
            ],
            False
        ],
        "KINTOX": [
            3,
            "qual",
            2.0,
            4,
            50.0,
            [
                "Toxin_detected == True"
            ],
            [
                "Toxin_detected == False",
                "DIVISION == 'active'"
            ],
            False
        ],
        "KINSTRESS": [
            2,
            "qual",
            4.0,
            16,
            150.0,
            [
                "STRESSRESP == 'active'"
            ],
            [
                "Energy > -0.5",
                "KINSTRESS == 'active'",
                "DIVISION == 'active'"
            ],
            False
        ],
        "KINFUNK": [
            3,
            "qual",
            2.0,
            4,
            50.0,
            [
                "FUNACTIV == 'active'"
            ],
            [
                "KINFUNK == 'active'",
                "STRESSRESP == 'active'",
                "DIVISION == 'active'"
            ],
            False
        ]
    },
    "cell_cycle": {
        "CDK1": [
            2,
            "qual",
            1.25,
            4,
            50.0,
            [
                "Energy >= 1.5"
            ],
            [
                "DIVISION == 'active'"
            ],
            False
        ]
    },
    "division": {
        "MUTGUARD": [
            2,
            "qual",
            4.0,
            16,
            50.0,
            [
                "DIVISION == 'inactive'"
            ],
            [
                "DIVISION == 'active'"
            ],
            [
                "mutrep",
                0.01
            ]
        ],
        "DIVISION": [
            6,
            "qual",
            2.0,
            16,
            50.0,
            [
                "CDK1 == 'active'"
            ],
            [
                "DIVISION == 'active'"
            ],
            [
                "div",
                1.0
            ]
        ]
    },
    "cellular_products": {
        "Wastetoxin": [
            "energy",
            0.005
        ],
        "CytokineX": [
            "TPMsum",
            0.0001
        ],
        "FooMol": [
            "secret:FOODSENS",
            0.0001
        ],
        "CellProduct": [
            "secret:CELLPROD",
            0.005
        ]
    },
    "cell_count": 10,
    "energy": 0.0,
    "protein_stability": 0.7,
    "name": "Def"
}

STABLE_ENV_PRESET: Dict[str, Any] = {
    "name": "Default Environment",
    "initial_food": -3.0,
    "support_cell_num": 1000,
    "ticks": 3000,
    "infinite": False,
    "toxin_k": 1.0,
    "mutation_chance": 0.0004,
    "n_genomes_allowed": 20,
    "toxins": {
        "Energotoxin": [-2, "energy", 0.2],
        "RNAtoxin":    [-2, "TPM",    0.1],
        "Wastetoxin":  [-3, "common", 0.001],
        "CytokineX":   [-3, "energy", 0.001],
        "CellProduct": [-3, "energy", 0.001],
    },
}


# ── Public API ────────────────────────────────────────────────────────────────

def load_genome_collection() -> Dict[str, dict]:
    base = {"Stable Genome (default)": STABLE_GENOME_PRESET}
    base.update(_load(_GENOME_FILE, {}))
    return base


def save_genome_to_collection(name: str, preset: dict):
    col = _load(_GENOME_FILE, {})
    preset = dict(preset)
    preset["name"] = name
    col[name] = preset
    _save(_GENOME_FILE, col)


def load_env_collection() -> Dict[str, dict]:
    base = {"Default Environment": STABLE_ENV_PRESET}
    base.update(_load(_ENV_FILE, {}))
    return base


def save_env_to_collection(name: str, preset: dict):
    col = _load(_ENV_FILE, {})
    preset = dict(preset)
    preset["name"] = name
    col[name] = preset
    _save(_ENV_FILE, col)


def genome_preset_to_genome_no_reset(preset: dict):
    """Like genome_preset_to_objects but does NOT call reset_id_counter().
    Use when creating multiple genomes sequentially (e.g. cryo injections)."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from core.genome import genome_from_dicts

    def fix_func(f):
        if f is False or f is None: return False
        if isinstance(f, (list, tuple)): return (f[0], f[1])
        return f

    def fix_cat(cat):
        return {
            name: tuple(
                fix_func(v) if i == 7 else
                list(v) if isinstance(v, list) else v
                for i, v in enumerate(rec)
            )
            for name, rec in cat.items()
        }

    genome = genome_from_dicts(
        receptors         = fix_cat(preset.get("receptors",  {})),
        metabolism        = fix_cat(preset.get("metabolism", {})),
        kinases           = fix_cat(preset.get("kinases",    {})),
        cell_cycle        = fix_cat(preset.get("cell_cycle", {})),
        division          = fix_cat(preset.get("division",   {})),
        cell_count        = preset.get("cell_count", 10),
        energy            = preset.get("energy", 0.0),
        protein_stability = preset.get("protein_stability", 0.7),
    )
    products = {
        name: tuple(v)
        for name, v in preset.get("cellular_products", {}).items()
    }
    return genome, products



def genome_to_preset(genome) -> dict:
    """
    Convert a live Genome object back to a preset dict that can be
    saved to the cryobank or genome collection.
    Reconstructs all gene categories from the genome's gene objects.
    """
    cats = {"receptors": {}, "metabolism": {}, "kinases": {},
            "cell_cycle": {}, "division": {}}

    # Categorise by gene name — use the genome's own category info if available,
    # otherwise put everything in metabolism (safe fallback).
    # We reconstruct from as_tuple() which is always complete.
    for name, gene in genome.genes.items():
        t = gene.as_tuple()
        rec = [t[0], t[1], t[2], t[3], t[4],
               list(t[5]), list(t[6]),
               list(t[7]) if t[7] else False]
        # Assign to category based on gene name heuristics
        n = name.upper()
        if any(k in n for k in ("CDK", "CYCLIN")):
            cats["cell_cycle"][name] = rec
        elif any(k in n for k in ("DIV", "MUTGUARD")):
            cats["division"][name] = rec
        elif any(k in n for k in ("KIN", "KINAS")):
            cats["kinases"][name] = rec
        elif any(k in n for k in ("SENS", "RESP", "ACTIV", "FUNACT")):
            cats["receptors"][name] = rec
        else:
            cats["metabolism"][name] = rec

    # If the genome has category metadata stored, use it
    if hasattr(genome, "_category_map"):
        cats = {"receptors": {}, "metabolism": {}, "kinases": {},
                "cell_cycle": {}, "division": {}}
        for name, cat in genome._category_map.items():
            if name in genome.genes:
                gene = genome.genes[name]
                t = gene.as_tuple()
                rec = [t[0], t[1], t[2], t[3], t[4],
                       list(t[5]), list(t[6]),
                       list(t[7]) if t[7] else False]
                cats.setdefault(cat, {})[name] = rec

    # Rebuild cellular_products from environment is not possible here;
    # we store an empty dict — caller should merge if needed.
    return {
        "name": getattr(genome, "_strain_name", f"G{genome.genome_id}"),
        "cell_count": genome.cell_count,
        "energy":     genome.energy,
        "protein_stability": (
            list(genome.protein_stability.values())[0]
            if genome.protein_stability else 0.7
        ),
        **cats,
        "cellular_products": {},
    }


def genome_preset_to_objects(preset: dict):
    """Convert a preset dict to (Genome, cellular_products_dict)."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from core.genome import genome_from_dicts, reset_id_counter

    def fix_func(f):
        if f is False or f is None:
            return False
        if isinstance(f, (list, tuple)):
            return (f[0], f[1])
        return f

    def fix_cat(cat):
        return {
            name: tuple(
                fix_func(v) if i == 7 else
                list(v) if isinstance(v, list) else v
                for i, v in enumerate(rec)
            )
            for name, rec in cat.items()
        }

    reset_id_counter()
    genome = genome_from_dicts(
        receptors         = fix_cat(preset.get("receptors",  {})),
        metabolism        = fix_cat(preset.get("metabolism", {})),
        kinases           = fix_cat(preset.get("kinases",    {})),
        cell_cycle        = fix_cat(preset.get("cell_cycle", {})),
        division          = fix_cat(preset.get("division",   {})),
        cell_count        = preset.get("cell_count", 10),
        energy            = preset.get("energy", 0.0),
        protein_stability = preset.get("protein_stability", 0.7),
    )
    products = {
        name: tuple(v)
        for name, v in preset.get("cellular_products", {}).items()
    }
    return genome, products


# ── Cryobank API ──────────────────────────────────────────────────────────────

def load_cryobank() -> Dict[str, Any]:
    """
    Returns {strain_name: entry} where entry = {
        "description": str,
        "genome_preset": dict,
        "vials": [{"cells": int, "label": str}, ...]
    }
    """
    return _load(_CRYO_FILE, {})


def save_to_cryobank(strain_name: str, description: str,
                     genome_preset: dict,
                     vials: list) -> None:
    """
    vials: list of {"cells": int, "label": str}
    """
    bank = _load(_CRYO_FILE, {})
    bank[strain_name] = {
        "description": description,
        "genome_preset": genome_preset,
        "vials": vials,
    }
    _save(_CRYO_FILE, bank)


def remove_vial_from_cryobank(strain_name: str, vial_idx: int) -> bool:
    """Remove one vial. If strain has no vials left, remove the strain."""
    bank = _load(_CRYO_FILE, {})
    if strain_name not in bank:
        return False
    vials = bank[strain_name].get("vials", [])
    if 0 <= vial_idx < len(vials):
        vials.pop(vial_idx)
    if not vials:
        del bank[strain_name]
    else:
        bank[strain_name]["vials"] = vials
    _save(_CRYO_FILE, bank)
    return True


def env_preset_to_object(preset: dict, cellular_products: dict):
    """Convert an environment preset dict to an Environment object."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from core.environment import environment_from_kwargs

    raw_toxins = preset.get("toxins", {})
    toxins = {
        name: (vals[0], (vals[1], vals[2]))
        for name, vals in raw_toxins.items()
    }
    return environment_from_kwargs(
        initial_food      = preset.get("initial_food", 0.0),
        toxins            = toxins,
        cellular_products = cellular_products,
        support_cell_num  = preset.get("support_cell_num", 1000),
    )
