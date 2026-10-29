"""Variables du score (scoring.FEATURES) : leur calcul exact (évaluateur) et leur version linéaire (solveur).

Le score est une fonction non linéaire de ces variables (scoring.score_parts). Le solveur la linéarise autour du
build courant : il maximise  Σ gradient[k] × variable[k]  (linear_objective), puis l'évaluateur recalcule le score
exact du build obtenu, et on recommence (solver.Optimizer.run).

Les deux côtés de chaque variable sont ici, l'un sous l'autre. Ajouter ou changer une variable du score :
  1. scoring.FEATURES (pas du gradient) et scoring.score_parts (ce qu'elle rapporte) ;
  2. evaluator_features (valeur exacte d'un build) ;
  3. model_features (variable du modèle, mêmes plafonds que l'évaluateur) ;
  4. initial_point (valeur réaliste pour la première linéarisation) ;
  5. candidates.item_features si une stat d'item devient utile (sinon l'élagage écarte les items qui la donnent).
tests/test_features.py vérifie que ces listes coïncident.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..data.models import ELEMENTS
from .options import OptimizeOptions
from .scoring import WILL_CAP, WILL_FLOOR, crit_short, res_cap, res_need, utility_table

if TYPE_CHECKING:
    from .model import BuildModel

BIG = 10**7         # borne « infinie » des variables entières du modèle
LIN_SCALE = 10**5   # coefficients entiers de l'objectif linéaire


def initial_point(opts: OptimizeOptions) -> dict[str, float]:
    """Point de départ réaliste pour la première linéarisation."""
    L = opts.level
    return {"mtot": 8.0 * L + 100, "crit": 30.0 if opts.crit else 0.0, "crit_mastery": L / 2 if opts.crit else 0.0,
            "rear_mastery": float(L) if opts.rear else 0.0, "dmg_pct": 10.0, "hp": 25.0 * L + 50, "hp_pct": 30.0,
            "res": 3.0 * L, "ap": 0.0, "mp": 0.0, "range": 0.0, "wp": 0.0, "res_short": 0.0, "will": 0.0,
            "crit_short": 0.0, "range_neg": 0.0}


# =====================================================================  évaluateur (valeurs exactes)
def evaluator_features(s: dict[str, int], res_flat: dict[str, int], mtot: int, crit: int,
                       opts: OptimizeOptions) -> dict[str, float]:
    """Variables du score d'un build, à partir de ses stats totales `s` (voir stats.evaluate)."""
    capped = [min(res_flat[e], res_cap(opts)) for e in ELEMENTS]
    rear = opts.rear and not opts.heal
    return {
        "mtot": float(mtot), "crit": float(crit), "crit_mastery": float(s["crit_mastery"] if opts.crit else 0),
        "rear_mastery": float(s["rear_mastery"] if rear else 0), "dmg_pct": float(s["dmg_pct"]),
        "hp": float(s["hp"]), "hp_pct": float(s["hp_pct"]),
        "res": float(sum(capped) / 4),
        "ap": float(s["ap"]), "mp": float(s["mp"]), "range": float(s["range"]), "wp": float(s["wp"]),
        "will": float(max(WILL_FLOOR, min(WILL_CAP, s["willpower"]))),
        "res_short": float(sum(max(0, res_need(opts) - res_flat[e]) for e in ELEMENTS)) if res_need(opts) else 0.0,
        "crit_short": crit_short(s["crit_rate"], opts),
        "range_neg": float(max(0, -s["range"])),
    }


# =====================================================================  solveur (variables linéaires)
def model_features(bm: BuildModel) -> dict[str, Any]:
    """Variables du modèle utilisées par l'objectif. `res4` = somme des 4 résistances (l'évaluateur : la moyenne)."""
    m, opts = bm.m, bm.opts
    f: dict[str, Any] = {"mtot": bm.mtot}
    if opts.crit:
        t = m.NewIntVar(-BIG, 100, "T")
        m.AddMinEquality(t, [bm.stat("crit_rate"), 100])
        f["crit"] = t
        f["crit_mastery"] = 0 if opts.neutral_combo else bm.stat("crit_mastery")
        if opts.crit_target:   # palier de critique de l'archétype (voir scoring.crit_short)
            sh = m.NewIntVar(0, BIG, "crit_short")
            m.AddMaxEquality(sh, [opts.crit_target - bm.stat("crit_rate"), 0])
            f["crit_short"] = sh
    if opts.rear and not opts.heal:
        f["rear_mastery"] = bm.stat("rear_mastery")
    f["dmg_pct"] = bm.stat("dmg_pct")
    f["hp"] = bm.stat("hp")
    f["hp_pct"] = bm.stat("hp_pct")
    capped = []
    cap = res_cap(opts)   # au-delà du maximum voulu, la résistance ne rapporte plus rien
    for e in ELEMENTS:
        c = m.NewIntVar(-BIG, cap, f"Rc_{e}")
        m.AddMinEquality(c, [bm.res[e], cap])
        capped.append(c)
    need = res_need(opts)
    if need:
        shorts = []
        for e in ELEMENTS:
            sh = m.NewIntVar(0, need + BIG, f"short_{e}")
            m.AddMaxEquality(sh, [need - bm.res[e], 0])
            shorts.append(sh)
        f["res_short"] = sum(shorts)
    # moyenne des quatre résistances (plafonnées) : pas besoin d'un équilibre parfait,
    # chaque élément est tiré vers la résistance visée par la pénalité res_short
    f["res4"] = sum(capped)
    if opts.willpower_weight:   # Volonté utile pour les retraits, plafonnée (voir scoring.removal_factor)
        wcap = m.NewIntVar(-BIG, WILL_CAP, "will_cap")
        m.AddMinEquality(wcap, [bm.stat("willpower"), WILL_CAP])
        wv = m.NewIntVar(WILL_FLOOR, WILL_CAP, "will")
        m.AddMaxEquality(wv, [wcap, WILL_FLOOR])
        f["will"] = wv
    neg = m.NewIntVar(0, BIG, "range_neg")   # Portée sous 0 (scoring.RANGE_NEG_PENALTY)
    m.AddMaxEquality(neg, [-bm.stat("range"), 0])
    f["range_neg"] = neg
    for stat, (_v, cap) in utility_table(opts).items():
        capped_u = m.NewIntVar(-100, max(0, cap), f"cap_{stat}")
        m.AddMinEquality(capped_u, [bm.stat(stat), cap])
        pos = m.NewIntVar(0, max(0, cap), f"pos_{stat}")
        m.AddMaxEquality(pos, [capped_u, 0])
        f[stat] = pos
    return f


def linear_objective(feat: dict[str, Any], grad: dict[str, float]) -> Any:
    """Somme des variables du modèle pondérées par le gradient du score (coefficients entiers)."""
    terms = []
    for k, var in feat.items():
        g = grad.get("res", 0.0) / 4 if k == "res4" else grad.get(k, 0.0)
        c = int(round(g * LIN_SCALE))
        if c:
            terms.append(c * var)
    return sum(terms) if terms else 0
