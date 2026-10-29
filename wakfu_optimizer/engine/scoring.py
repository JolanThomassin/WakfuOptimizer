"""Formules de jeu, en arithmétique entière (identiques dans le solveur et l'évaluateur).

Dégâts (wakfu.wiki.gg, Wakfu Calc) :
    dégâts = base × (1 + M/100) × orientation × crit × (1 + %DI/100) × (1 − %rés/100)
    crit = ×1,25 sur la base ; la Maîtrise Critique s'ajoute aux maîtrises en cas de critique ;
    dos = ×1,25 et la Maîtrise Dos s'ajoute.

Espérance d'un coup (t = taux critique entre 0 et 1, Mc = Maîtrise Critique) :
    E(M) = (1 − t)(1 + M/100) + t × 1,25 × (1 + (M + Mc)/100)
En entier, avec T = taux critique en % (0..100) :
    E4(M) = 400 × (100 + M) + T × ((100 + M) + 5 × Mc)      = 40 000 × E(M)
Avec une part p (%) de frappes de dos (R = Maîtrise Dos) :
    D1 = 4 × (100 − p) × E4(M) + 5 × p × E4(M + R)          = 1,6e7 × [(1−p)E(M) + 1,25 p E(M+R)]
    D2 = D1 × (100 + %DI)                                    = 1,6e9 × multiplicateur moyen

Survie : PV effectifs = PV × 100 / (100 − %rés).
    G(rés) = floor(10000 / (100 − %rés))     (100 sans résistance, 1000 à 90 %)
    Def = PV × (100 + %PV) × G               = 1e4 × PV effectifs
"""

from __future__ import annotations

import math
from functools import lru_cache

RES_CAP = 90
RES_TABLE_MIN = -1000      # bornes de la table de conversion résistance fixe -> %
RES_TABLE_MAX = 4000

D2_SCALE = 1.6e9           # D2 / D2_SCALE = multiplicateur de dégâts moyen
DEF_SCALE = 1e4            # Def / DEF_SCALE = PV effectifs (moyens ou minimum)


def res_pct(flat: int) -> int:
    """% de réduction pour une résistance fixe : floor(100 × (1 − 0,8^(rés/100))), plafonné à 90."""
    flat = max(RES_TABLE_MIN, min(RES_TABLE_MAX, int(flat)))
    pct = math.floor(100 * (1 - 0.8 ** (flat / 100)) + 1e-9)
    return min(RES_CAP, pct)


def ehp_factor(flat: int) -> int:
    """G(rés) = floor(10000 / (100 − %rés))."""
    return 10000 // (100 - res_pct(flat))


@lru_cache(maxsize=None)
def ehp_table() -> tuple[int, ...]:
    """Table G indexée par rés − RES_TABLE_MIN (pour AddElement du solveur)."""
    return tuple(ehp_factor(r) for r in range(RES_TABLE_MIN, RES_TABLE_MAX + 1))


@lru_cache(maxsize=None)
def pct_table() -> tuple[int, ...]:
    return tuple(res_pct(r) for r in range(RES_TABLE_MIN, RES_TABLE_MAX + 1))


def flat_for_pct(pct: int) -> int:
    """Plus petite résistance fixe donnant au moins `pct` %."""
    if pct <= 0:
        return RES_TABLE_MIN
    pct = min(pct, RES_CAP)
    lo, hi = 0, RES_TABLE_MAX
    while lo < hi:
        mid = (lo + hi) // 2
        if res_pct(mid) >= pct:
            hi = mid
        else:
            lo = mid + 1
    return lo


def e4(mastery: int, crit_pct: int, crit_mastery: int) -> int:
    t = max(0, min(100, crit_pct))
    return 400 * (100 + mastery) + t * ((100 + mastery) + 5 * crit_mastery)


def damage_d2(mastery: int, crit_pct: int, crit_mastery: int, rear_mastery: int,
              rear_share: int, dmg_pct: int) -> int:
    p = max(0, min(100, rear_share))
    d1 = 4 * (100 - p) * e4(mastery, crit_pct, crit_mastery) + 5 * p * e4(mastery + rear_mastery, crit_pct, crit_mastery)
    return d1 * max(0, 100 + dmg_pct)


def damage_multiplier(d2: int) -> float:
    return d2 / D2_SCALE


def utility_bonus(stats: dict[str, int], opts: object) -> int:
    """Bonus de score (en points × 1e5) pour PA/PM/PO/PW, plafonnés. Identique au solveur."""
    total = 0
    for stat, vk, ck in (("ap", "ap_value", "ap_cap"), ("mp", "mp_value", "mp_cap"),
                         ("range", "range_value", "range_cap"), ("wp", "wp_value", "wp_cap")):
        v = int(getattr(opts, vk, 0))
        if v:
            total += v * max(0, min(int(stats.get(stat, 0)), int(getattr(opts, ck, 0))))
    return total * 100000


def defense_value(hp_base: int, hp_pct: int, ehp_g: int) -> int:
    return hp_base * max(0, 100 + hp_pct) * ehp_g


# =====================================================================  score logarithmique
# Le solveur maximise   w_off × ln(dégâts) + w_def × ln(PV effectifs) + 100 × utilité
# (w_off + w_def = 100). 1 point de score ≈ 1 % de valeur globale : +1 % de dégâts vaut w_off / 100.
LN_RES = -math.log(0.8) / 100         # ln(PV effectifs) gagné par point de résistance fixe
RES_CAP_FLAT = 1032                   # résistance fixe donnant 90 % (au-delà : inutile)

# Valeur automatique (fraction de la valeur globale) de chaque PA/PM/PO/PW, jusqu'au plafond.
UTILITY = {"ap": (0.06, 14), "mp": (0.025, 6), "wp": (0.005, 12)}
RANGE_UTILITY = {"distance": (0.03, 6), "melee": (0.005, 4), "mixed": (0.025, 5), "best": (0.025, 5)}
# Pénalité (points de score) par point de résistance fixe manquant sous la résistance visée, par élément :
# assez forte pour que la cible soit atteinte dès que possible, sans rendre le calcul infaisable sinon.
RES_SHORT_PENALTY = 1.0   # par point de résistance fixe sous le plancher (cible − écart) : à éviter absolument


def utility_table(opts: object) -> dict[str, tuple[float, int]]:
    out = dict(UTILITY)
    out["range"] = RANGE_UTILITY.get(str(getattr(opts, "range", "melee")), RANGE_UTILITY["melee"])
    return out


def ln_damage(mtot: float, crit: float, crit_mastery: float, rear_mastery: float, rear_share: float,
              dmg_pct: float) -> float:
    t = max(0.0, min(100.0, crit)) / 100
    p = max(0.0, min(100.0, rear_share)) / 100

    def e(m: float) -> float:
        return (1 - t) * (1 + m / 100) + t * 1.25 * (1 + (m + crit_mastery) / 100)

    b = (1 - p) * e(mtot) + 1.25 * p * e(mtot + rear_mastery)
    return math.log(max(1e-3, b)) + math.log(max(1.0, 100 + dmg_pct))


def ln_defense(hp: float, hp_pct: float, res: float) -> float:
    return math.log(max(1.0, hp)) + math.log(max(1.0, 100 + hp_pct)) + LN_RES * min(res, RES_CAP_FLAT)


FEATURES = ("mtot", "crit", "crit_mastery", "rear_mastery", "dmg_pct", "hp", "hp_pct", "res", "ap", "mp", "range", "wp",
            "res_short")


def log_score(f: dict[str, float], opts: object) -> float:
    w_off = max(0, min(100, int(getattr(opts, "offense_weight", 70))))
    s = 0.0
    if w_off:
        rear = bool(getattr(opts, "rear", False)) and not getattr(opts, "heal", False)
        s += w_off * ln_damage(f["mtot"], f["crit"], f["crit_mastery"], f["rear_mastery"],
                               float(getattr(opts, "rear_share", 0)) if rear else 0.0, f["dmg_pct"])
    if w_off < 100:
        s += (100 - w_off) * ln_defense(f["hp"], f["hp_pct"], f["res"])
    for k, (v, cap) in utility_table(opts).items():
        s += 100 * v * max(0.0, min(float(f.get(k, 0)), cap))
    s -= RES_SHORT_PENALTY * f.get("res_short", 0.0)
    return s


def secondary_mastery(melee: int, distance: int, rng: str) -> int:
    """Maîtrise de portée utile : mêlée, distance, ou moyenne des deux (classes « mixtes »)."""
    if rng == "mixed":
        return (melee + distance) // 2
    if rng == "best":
        return max(melee, distance)
    return melee if rng == "melee" else distance


def res_cap(opts: object) -> int:
    """Résistance fixe au-delà de laquelle la résistance ne rapporte plus rien : le plancher (cible − écart).
    Partout dans l'écart, le score est donc le même : aucune stat sacrifiée pour se rapprocher de la cible."""
    t = int(getattr(opts, "res_target", 0) or 0)
    if not 0 < t < 90 or getattr(opts, "res_free", False):
        return RES_CAP_FLAT
    floor = t - int(getattr(opts, "res_tol", 5) or 0)
    return min(RES_CAP_FLAT, flat_for_pct(floor)) if floor > 0 else 0


def res_need(opts: object) -> int:
    """Plancher par élément : cible − écart max. Au-dessus, aucune pénalité ; en dessous, pénalité forte."""
    t = int(getattr(opts, "res_target", 0) or 0)
    floor = t - int(getattr(opts, "res_tol", 5) or 0)
    return flat_for_pct(floor) if t > 0 and floor > 0 else 0


def gradient(f: dict[str, float], opts: object) -> dict[str, float]:
    """Dérivées partielles du score (différences centrées)."""
    out = {}
    for k in FEATURES:
        h = 0.5 if k in ("crit", "ap", "mp", "range", "wp", "dmg_pct", "hp_pct") else 5.0
        if k in ("ap", "mp", "range", "wp"):
            out[k] = 100 * utility_table(opts)[k][0]   # plafond géré dans le modèle
            continue
        a, b = dict(f), dict(f)
        a[k] += h
        b[k] -= h
        out[k] = (log_score(a, opts) - log_score(b, opts)) / (2 * h)
    return out
