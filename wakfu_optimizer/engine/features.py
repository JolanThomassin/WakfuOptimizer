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
from .scoring import (CRIT_OVERFLOW, DECAYING, RES_CAP, WILL_CAP, WILL_FLOOR, crit_overflow, crit_short, decayed,
                      gap_bounds, res_cap, res_gap, res_gap_excess, res_need, res_pct, sec_res_counted, utility_table,
                      will_short)

if TYPE_CHECKING:
    from .model import BuildModel

BIG = 10**7         # borne « infinie » des variables entières du modèle
LIN_SCALE = 10**5   # coefficients entiers de l'objectif linéaire


def initial_point(opts: OptimizeOptions) -> dict[str, float]:
    """Point de départ réaliste pour la première linéarisation."""
    L = opts.level
    return {"mtot": 8.0 * L + 100, "crit": 30.0 if opts.crit else 0.0, "crit_mastery": L / 2 if opts.crit else 0.0,
            "rear_mastery": float(L) if opts.rear else 0.0, "dmg_pct": 10.0, "heal_mastery": 0.0, "heal_pct": 0.0, "hp": 25.0 * L + 50, "hp_pct": 30.0,
            "res": 3.0 * L, "block": 10.0, "ap": 0.0, "mp": 0.0, "range": 0.0, "wp": 0.0, "lock": 0.0, "dodge": 0.0, "crit_res": 0.0, "rear_res": 0.0, "res_short": 0.0, "res_gap": 0.0, "will": 0.0, "will_short": 0.0,
            "crit_short": 0.0, "range_neg": 0.0, "sec_res_neg": 0.0}


# =====================================================================  évaluateur (valeurs exactes)
def evaluator_features(s: dict[str, int], res_flat: dict[str, int], mtot: int, crit: int,
                       opts: OptimizeOptions) -> dict[str, float]:
    """Variables du score d'un build, à partir de ses stats totales `s` (voir stats.evaluate)."""
    capped = [min(res_flat[e], res_cap(opts)) for e in ELEMENTS]
    rear = opts.rear and not opts.heal
    util = utility_table(opts)
    out = {
        "mtot": float(mtot), "crit": float(crit), "crit_mastery": float(s["crit_mastery"] if opts.crit else 0),
        "rear_mastery": float(s["rear_mastery"] if rear else 0),
        "dmg_pct": float(s["dmg_pct"]) + crit_overflow(s["crit_rate"], opts),   # Écaflip : critique au-delà de 100 %
        "heal_mastery": float(s["heal_mastery"] if opts.heal else 0), "heal_pct": float(s["heal_pct"] if opts.heal else 0),
        "hp": float(s["hp"]), "hp_pct": float(s["hp_pct"]),
        "res": float(sum(capped) / 4), "block": float(max(0, min(100, s["block"]))),
        "ap": float(s["ap"]), "mp": float(s["mp"]), "range": float(s["range"]), "wp": float(s["wp"]),
        "lock": float(s["lock"]), "dodge": float(s["dodge"]), "crit_res": float(s["crit_res"]), "rear_res": float(s["rear_res"]),
        "will_short": will_short(s["willpower"], opts),
        "will": float(max(WILL_FLOOR, min(WILL_CAP, s["willpower"]))),
        "res_short": float(sum(max(0, res_need(opts) - res_flat[e]) for e in ELEMENTS)) if res_need(opts) else 0.0,
        "res_gap": res_gap_excess([res_flat[e] for e in ELEMENTS], opts),
        "crit_short": crit_short(s["crit_rate"], opts),
        "range_neg": float(max(0, -s["range"])),
        "sec_res_neg": float(sum(max(0, -s[k]) for k in sec_res_counted(opts))),
    }
    for k in DECAYING:   # rendement décroissant : chaque point vaut moins que le précédent
        out[k] = decayed(s[k], util[k][1])
    return out


# =====================================================================  solveur (variables linéaires)
def model_features(bm: BuildModel) -> dict[str, Any]:
    """Variables du modèle utilisées par l'objectif. `res4` = somme des 4 résistances (l'évaluateur : la moyenne)."""
    m, opts = bm.m, bm.opts
    f: dict[str, Any] = {"mtot": bm.mtot}
    if opts.crit:
        t = m.NewIntVar(-BIG, 100, "T")
        m.AddMinEquality(t, [bm.stat("crit_rate"), 100])
        f["crit"] = t
        cm = bm.stat("crit_mastery")
        f["crit_mastery"] = cm if bm.crit_conv is None else cm - bm.crit_conv   # Dénouement : convertie
        if opts.crit_target:   # palier de critique de l'archétype (voir scoring.crit_short)
            sh = m.NewIntVar(0, BIG, "crit_short")
            m.AddMaxEquality(sh, [opts.crit_target - bm.stat("crit_rate"), 0])
            f["crit_short"] = sh
    if opts.rear and not opts.heal:
        f["rear_mastery"] = bm.stat("rear_mastery")
    f["dmg_pct"] = bm.stat("dmg_pct")
    rule = CRIT_OVERFLOW.get(opts.class_key) if opts.crit else None
    if rule:   # Écaflip : critique au-delà de 100 % (plafonné) -> % DI, divisé par `per` (scoring.crit_overflow)
        per, cap = rule
        oc = m.NewIntVar(-BIG, cap, "crit_over_cap")
        m.AddMinEquality(oc, [bm.stat("crit_rate") - 100, cap])
        over = m.NewIntVar(0, cap, "crit_over")
        m.AddMaxEquality(over, [oc, 0])
        f["dmg_pct"] = (per * bm.stat("dmg_pct") + over, per)
    if opts.heal:   # soins : mtot + Maîtrise Soin, % Soins réalisés (scoring.ln_offense)
        f["heal_mastery"] = bm.stat("heal_mastery")
        f["heal_pct"] = bm.stat("heal_pct")
    f["hp"] = bm.stat("hp")
    f["hp_pct"] = bm.stat("hp_pct")
    if opts.offense_weight < 100:   # Parade : dégâts subis en moins, plafonnée à 100 %
        blk = m.NewIntVar(-BIG, 100, "block_cap")
        m.AddMinEquality(blk, [bm.stat("block"), 100])
        f["block"] = m.NewIntVar(0, 100, "block")
        m.AddMaxEquality(f["block"], [blk, 0])
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
    gap = res_gap(opts)
    if gap:
        f["res_gap"] = _gap_excess(bm, gap)
    # moyenne des quatre résistances (plafonnées) : pas besoin d'un équilibre parfait,
    # chaque élément est tiré vers la résistance visée par la pénalité res_short
    f["res4"] = sum(capped)
    if opts.willpower_weight:   # Volonté utile pour les retraits, plafonnée (voir scoring.removal_factor)
        wcap = m.NewIntVar(-BIG, WILL_CAP, "will_cap")
        m.AddMinEquality(wcap, [bm.stat("willpower"), WILL_CAP])
        wv = m.NewIntVar(WILL_FLOOR, WILL_CAP, "will")
        m.AddMaxEquality(wv, [wcap, WILL_FLOOR])
        f["will"] = wv
    if opts.will_min:   # Volonté sous le minimum de l'archétype (scoring.will_short)
        ws = m.NewIntVar(0, BIG, "will_short")
        m.AddMaxEquality(ws, [opts.will_min - bm.stat("willpower"), 0])
        f["will_short"] = ws
    neg = m.NewIntVar(0, BIG, "range_neg")   # Portée sous 0 (scoring.RANGE_NEG_PENALTY)
    m.AddMaxEquality(neg, [-bm.stat("range"), 0])
    f["range_neg"] = neg
    negs = []
    for k in sec_res_counted(opts):   # résistance critique / dos sous 0 (scoring.SEC_RES_NEG_PENALTY)
        v = m.NewIntVar(0, BIG, f"neg_{k}")
        m.AddMaxEquality(v, [-bm.stat(k), 0])
        negs.append(v)
    if negs:
        f["sec_res_neg"] = sum(negs)
    for stat, (v, cap) in utility_table(opts).items():
        if not v:
            continue
        capped_u = m.NewIntVar(-BIG, max(0, cap), f"cap_{stat}")
        m.AddMinEquality(capped_u, [bm.stat(stat), cap])
        pos = m.NewIntVar(0, max(0, cap), f"pos_{stat}")
        m.AddMaxEquality(pos, [capped_u, 0])
        f[stat] = pos
        if stat in DECAYING and cap > 0:
            # cap × decayed(pos), concave : sous chaque segment (exact en entiers, l'objectif le pousse vers le haut)
            top = round(cap * decayed(cap, cap))
            eff = m.NewIntVar(0, top, f"dec_{stat}")
            for j in range(cap):
                m.Add(eff <= round(cap * decayed(j, cap)) + (cap - j) * (pos - j))
            f[stat] = (eff, cap)   # variable et diviseur (voir linear_objective)
    return f


def _gap_excess(bm: BuildModel, gap: int) -> Any:
    """Écart entre éléments (scoring.res_gap_excess), exact : un booléen par % possible k de l'élément le plus faible.
    Chaque élément >= gap_bounds(k)[0] (donc k <= le plus faible) ; ce qui dépasse gap_bounds(k)[1] est l'excès. Le
    modèle choisit k : le plus haut possible (excès minimum), c'est-à-dire le % de l'élément le plus faible."""
    m = bm.m
    bounds = bm.res_bounds
    lo_all = int(min(b[0] for b in bounds.values()))
    hi_all = int(max(b[1] for b in bounds.values()))
    k_lo = max(0, res_pct(lo_all))
    # au-delà de RES_CAP − gap : pas de maximum ; au-delà du plus faible des maximums : k impossible
    k_hi = max(k_lo, min(RES_CAP - gap, res_pct(min(b[1] for b in bounds.values()))))
    ks = list(range(k_lo, k_hi + 1))
    z = {k: m.NewBoolVar(f"gap_k{k}") for k in ks}
    m.AddExactlyOne(list(z.values()))
    lims = {k: gap_bounds(k, gap) for k in ks}
    lo_expr = sum(max(lo_all, lims[k][0]) * z[k] for k in ks)
    hi_expr = sum(min(hi_all, hi if hi is not None else hi_all) * z[k] for k, (_, hi) in lims.items())
    out = []
    for e in ELEMENTS:
        m.Add(bm.res[e] >= lo_expr)
        ex = m.NewIntVar(0, max(0, hi_all - min(0, lo_all)), f"gap_{e}")
        m.Add(ex >= bm.res[e] - hi_expr)
        out.append(ex)
    return sum(out)


def linear_objective(feat: dict[str, Any], grad: dict[str, float]) -> Any:
    """Somme des variables du modèle pondérées par le gradient du score (coefficients entiers)."""
    terms = []
    for k, var in feat.items():
        g = grad.get("res", 0.0) / 4 if k == "res4" else grad.get(k, 0.0)
        if isinstance(var, tuple):   # (variable entière, diviseur) : variable du score = var / diviseur
            var, div = var
            g /= div
        c = int(round(g * LIN_SCALE))
        if c:
            terms.append(c * var)
    return sum(terms) if terms else 0
