"""Poids du calcul (onglet Poids) : ceux de l'archétype, que l'utilisateur peut remplacer (OptimizeOptions.custom_weights).

Les poids sont affichés et saisis en points de score (1 point ≈ 1 % de valeur globale) par unité de stat, l'unité
étant 1 point (PA, PM…) ou 100 points (Tacle, Esquive). En interne, l'utilité est une fraction de la valeur globale
par point de stat (scoring.utility_table) : conversion ici, dans les deux sens.

custom_weights : {"offense_weight": 30, "willpower_weight": 0, "will_min": 10, "crit_target": 40,
                  "utility.<stat>": [points par unité, maximum]}
"""

from __future__ import annotations

from typing import Any

from .options import OptimizeOptions
from .scoring import (BLOCK_REDUCTION, CRIT_SHORT_PENALTY, DECAYING, RANGE_NEG_PENALTY, RES_SHORT_PENALTY,
                      SEC_RES_NEG_PENALTY, WILL_SHORT_PENALTY, utility_table)

# Utilités affichées : (stat, libellé, taille de l'unité, description)
UTILITY_ROWS: tuple[tuple[str, str, int, str], ...] = (
    ("ap", "PA", 1, "Chaque PA au-delà du minimum, jusqu'au maximum."),
    ("mp", "PM", 1, "Se placer, se dégager, porter."),
    ("range", "Portée", 1, "Le 1er point vaut le poids indiqué, chaque point suivant un peu moins."),
    ("wp", "PW", 1, "Points de Wakfu."),
    ("lock", "Tacle", 100, "Retenir les ennemis au contact (par 100 de Tacle)."),
    ("dodge", "Esquive", 100, "Se dégager du contact (par 100 d'Esquive)."),
    ("crit_res", "Résistance critique", 1, "Moins de dégâts subis sur les coups critiques."),
    ("rear_res", "Résistance dos", 1, "Moins de dégâts subis de dos."),
)
SCALARS = ("offense_weight", "willpower_weight", "will_min", "crit_target")   # entiers de 0 à 100


def apply_custom_weights(opts: OptimizeOptions) -> None:
    """Remplace les poids de l'archétype par ceux saisis dans l'onglet Poids (appelé après apply_archetype)."""
    units = {stat: unit for stat, _l, unit, _d in UTILITY_ROWS}
    util = {k: list(v) for k, v in (opts.utility or {}).items()}
    for key, val in (opts.custom_weights or {}).items():
        try:
            if key in SCALARS:
                setattr(opts, key, max(0, min(100, int(val))))
            elif key.startswith("utility.") and key[8:] in units:
                pts, cap = val
                util[key[8:]] = [max(0.0, float(pts)) / (100 * units[key[8:]]), max(0, int(cap))]
        except (TypeError, ValueError):
            continue   # saisie invalide : poids de l'archétype
    opts.utility = util
    if not opts.crit:
        opts.crit_target = 0


def weights_view(default: OptimizeOptions, opts: OptimizeOptions) -> dict[str, Any]:
    """Poids de l'archétype (`default`) et poids utilisés (`opts`, avec ceux de l'utilisateur), pour l'interface."""
    du, ou = utility_table(default), utility_table(opts)
    rows = []
    for stat, label, unit, desc in UTILITY_ROWS:
        rows.append({"key": f"utility.{stat}", "stat": stat, "label": label, "unit": unit, "desc": desc,
                     "decaying": stat in DECAYING,
                     "pts": round(100 * unit * ou[stat][0], 2), "cap": int(ou[stat][1]),
                     "def_pts": round(100 * unit * du[stat][0], 2), "def_cap": int(du[stat][1])})
    return {
        "offense": {"value": opts.offense_weight, "default": default.offense_weight},
        "block_reduction": BLOCK_REDUCTION,
        "utility": rows,
        "will": {"weight": opts.willpower_weight, "def_weight": default.willpower_weight,
                 "min": opts.will_min, "def_min": default.will_min, "penalty": WILL_SHORT_PENALTY},
        "crit": {"enabled": opts.crit, "target": opts.crit_target, "def_target": default.crit_target,
                 "penalty": CRIT_SHORT_PENALTY},
        "fixed": [
            {"stat": "range", "label": "Portée sous 0", "pts": -RANGE_NEG_PENALTY, "unit": "par PO sous 0 (tous les archétypes)"},
            {"stat": "rear_res", "label": "Résistance critique / dos sous 0", "pts": -SEC_RES_NEG_PENALTY,
             "unit": "par point sous 0, quand ces résistances ont un poids (tank)"},
            {"stat": "elem_res", "label": "Résistance sous le plancher", "pts": -RES_SHORT_PENALTY,
             "unit": "par point de résistance fixe sous la résistance visée moins l'écart"},
        ],
        "custom": sorted((opts.custom_weights or {}).keys()),
    }
