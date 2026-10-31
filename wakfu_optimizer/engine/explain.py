"""Onglet Explication : ce que l'algorithme a privilégié pour ce personnage et cet archétype, et pourquoi.

Réglages utilisés et leur origine (archétype ou panneaux), poids de chaque stat, composition du score,
valeur d'un petit gain sur chaque stat au build final, profil d'aptitudes et contrôles de qualité (quality.py).
"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from ..data.models import ELEMENT_FR, ELEMENTS, GameData
from .archetypes import (ARCHETYPES, PANELS, RES_FULL_LEVEL, Archetype, apt_forced, apt_profile, class_archetypes,
                         crit_target, res_target)
from .characteristics import BRANCH_FR, LINE_FR, branch_points, char_lines
from .options import Build, OptimizeOptions
from .quality import check_build
from .scoring import (WILL_SHORT_PENALTY, BLOCK_REDUCTION, DECAYING, CRIT_SHORT_PENALTY, RANGE_NEG_PENALTY, RES_SHORT_PENALTY, SEC_RES_NEG_PENALTY, crit_short, log_score, res_cap, res_need, score_parts,
                      decayed, heal_share, secondary_mastery, utility_table)
from .stats import Totals, evaluate

FEATURE_FR = {"offense": "Dégâts", "defense": "Survie (PV effectifs)", "ap": "PA", "mp": "PM", "range": "Portée", "wp": "PW", "lock": "Tacle", "dodge": "Esquive",
              "crit_res": "Résistance critique", "rear_res": "Résistance dos", "will_short": "Pénalité : Volonté sous le minimum",
              "will": "Volonté (retraits)", "res_short": "Pénalité : résistance sous le plancher",
              "crit_short": "Pénalité : critique sous le palier", "range_neg": "Pénalité : Portée négative",
              "sec_res_neg": "Pénalité : résistance critique / dos négative"}


def _marginals(opts: OptimizeOptions, tot: Totals) -> list[dict[str, Any]]:
    """Ce que rapporterait un petit gain sur chaque stat, au build final (points de score ; 1 point ≈ 1 % de valeur)."""
    f = dict(tot.features)
    base = log_score(f, opts)
    cap, need = res_cap(opts), res_need(opts)
    crit_raw = tot.stats.get("crit_rate", 0)

    def gain(**ch: float) -> float:
        g = dict(f)
        g.update(ch)
        return round(log_score(g, opts) - base, 2)

    def res_plus(d: int) -> dict[str, float]:
        flats = [tot.res_flat[e] + d for e in ELEMENTS]
        return {"res": sum(min(r, cap) for r in flats) / 4,
                "res_short": float(sum(max(0, need - r) for r in flats)) if need else 0.0}

    rows = [
        ("Maîtrise utilisée", "+100", gain(mtot=f["mtot"] + 100)),
        ("% Coup critique", "+1 %", gain(crit=min(100.0, f["crit"] + 1), crit_short=crit_short(crit_raw + 1, opts)) if opts.crit else 0.0),
        ("Maîtrise critique", "+100", gain(crit_mastery=f["crit_mastery"] + 100) if opts.crit else 0.0),
        ("Maîtrise dos", "+100", gain(rear_mastery=f["rear_mastery"] + 100) if opts.rear and not opts.heal else 0.0),
        ("% Dommages infligés", "+10 %", gain(dmg_pct=f["dmg_pct"] + 10)),
        ("Maîtrise soin", "+100", gain(heal_mastery=f["heal_mastery"] + 100) if opts.heal else 0.0),
        ("% Soins réalisés", "+10 %", gain(heal_pct=f["heal_pct"] + 10) if opts.heal else 0.0),
        ("Points de vie (fixes)", "+1 000", gain(hp=f["hp"] + 1000)),
        ("% Points de vie", "+10 %", gain(hp_pct=f["hp_pct"] + 10)),
        ("Résistance élémentaire", "+100 (4 él.)", gain(**res_plus(100))),
        ("% Parade", "+1 %", gain(block=min(100.0, f["block"] + 1)) if opts.offense_weight < 100 else 0.0),
        ("PA", "+1", gain(ap=f["ap"] + 1)), ("PM", "+1", gain(mp=f["mp"] + 1)),
        ("Portée", "+1", gain(range=decayed(tot.stats.get("range", 0) + 1, utility_table(opts)["range"][1]),
                              range_neg=max(0.0, f["range_neg"] - 1))), ("PW", "+1", gain(wp=f["wp"] + 1)),
        ("Tacle", "+100", gain(lock=f["lock"] + 100) if utility_table(opts)["lock"][0] else 0.0),
        ("Volonté", "+10", gain(will=f["will"] + 10) if opts.willpower_weight else 0.0),
    ]
    return [{"label": lab, "unit": u, "points": p} for lab, u, p in rows]


def _targets(opts: OptimizeOptions, arch: Archetype | None, tot: Totals) -> dict[str, Any]:
    """Objectifs du niveau : résistance visée (par élément), maîtrise de portée ajoutée à chaque élément, critique."""
    played = opts.played_elements()
    floor = opts.res_target - opts.res_tol if opts.res_target else 0
    mine = "priorities" in opts.custom_panels
    want = res_target(arch, opts.level) if arch else opts.res_target
    res = {"target": opts.res_target, "tol": opts.res_tol, "floor": floor, "mine": mine,
           "lowered": not mine and opts.res_target < want, "wanted": want,
           "full": arch.res_target if arch else opts.res_target, "full_level": RES_FULL_LEVEL,
           "scaled": bool(arch and not arch.res_free), "free": opts.res_free,
           "elements": [{"key": e, "name": ELEMENT_FR[e], "pct": tot.res_pct[e], "flat": tot.res_flat[e],
                         "ok": tot.res_pct[e] >= floor} for e in ELEMENTS]}
    st = tot.stats
    melee, dist = st.get("melee_mastery", 0), st.get("distance_mastery", 0)
    rng_val = secondary_mastery(melee, dist, opts.range)
    rng_parts = {"melee": [("melee_mastery", "Maîtrise Mêlée", melee)],
                 "distance": [("distance_mastery", "Maîtrise Distance", dist)]}.get(
        opts.range, [("melee_mastery", "Maîtrise Mêlée", melee), ("distance_mastery", "Maîtrise Distance", dist)])
    extra = [(k, lab, st.get(k, 0)) for flag, k, lab in (("berserk", "berserk_mastery", "Maîtrise Berserk"),
                                                         ("heal", "heal_mastery", "Maîtrise Soin")) if getattr(opts, flag)]
    weakest = min(tot.mastery[e] for e in played) if played else 0
    mastery = {"range": opts.range, "range_value": rng_val,
               "parts": [{"stat": k, "label": lab, "value": v} for k, lab, v in rng_parts],
               "extra": [{"stat": k, "label": lab, "value": v} for k, lab, v in extra],
               "used": tot.mastery_used, "multi": len(played) > 1,
               "elements": [{"key": e, "name": ELEMENT_FR[e], "elem": tot.mastery[e],
                             "total": tot.mastery[e] + rng_val + sum(v for _k, _l, v in extra),
                             "played": e in played, "weakest": e in played and tot.mastery[e] == weakest,
                             "rank": played.index(e) + 1 if e in played else 0}
                            for e in ELEMENTS]}
    crit = {"target": opts.crit_target, "value": st.get("crit_rate", 0)} if opts.crit and opts.crit_target else None
    return {"res": res, "mastery": mastery if opts.offense_weight else None, "crit": crit}


def explain(data: GameData, opts: OptimizeOptions, build: Build, tot: Totals) -> dict[str, Any]:
    """Ce que l'algorithme a privilégié pour ce personnage et cet archétype (onglet Explication)."""
    arch = ARCHETYPES.get(opts.archetype)
    cls = data.classes.get(opts.class_key)
    recs = class_archetypes(data, opts.class_key)
    on = set(opts.custom_panels)
    panels = [{"key": k, "name": n, "on": k in on} for k, n in
              (("priorities", "Priorités"), ("constraints", "Contraintes"), ("subs", "Châsses et sublimations"))]
    src = lambda panel: "vos réglages" if panel in on else "archétype"  # noqa: E731
    rng = {"melee": "Mêlée", "distance": "Distance", "mixed": "Mixte (moitié / moitié)", "best": "Meilleure des deux (passif)"}
    secondary = [lab for flag, lab in (("crit", "Critique"), ("rear", f"Dos ({opts.rear_share} % des coups)"),
                                       ("berserk", "Berserk"), ("heal", "Soin")) if getattr(opts, flag)]
    util = utility_table(opts)
    settings = [
        {"label": "Portée", "value": rng.get(opts.range, opts.range), "src": src("priorities")},
        {"label": "Maîtrises secondaires", "value": ", ".join(secondary) or "aucune", "src": src("priorities")},
        {"label": "Résistance visée", "value": (f"{opts.res_target} % ± {opts.res_tol} (−{RES_SHORT_PENALTY:g} point par point "
                                                 f"de résistance sous le plancher)" + (" ; compte encore au-delà" if opts.res_free else ""))
         if opts.res_target else "aucune", "src": src("priorities")},
        {"label": "Minimums", "value": ", ".join(f"{v} {lab}" for v, lab in ((opts.min_ap, "PA"), (opts.min_mp, "PM"),
                                                                           (opts.min_range, "PO"), (opts.min_wp, "PW"),
                                                                           (opts.min_crit, "% crit"), (opts.min_block, "% parade")) if v)
         or "aucun", "src": src("constraints")},
        {"label": "Châsses", "value": {"ideal": f"idéales ({opts.shard_count} par item, {opts.max_jokers} joker max)",
                                       "mine": "mes couleurs", "none": "ignorées"}.get(opts.shard_mode, opts.shard_mode)
         + (" ; sans sublimations" if opts.no_subs else " ; sublimations confirmées seulement" if opts.confirmed_subs_only
            else ""), "src": src("subs")},
    ]
    # poids de chaque stat dans le score (1 point ≈ 1 % de valeur globale)
    arch_util = set(arch.utility) if arch else set()
    focus = {k for k, _ in arch.focus} if arch else set()
    weights = []   # points de score par unité (1 point ≈ 1 % de valeur globale) ; en vert : stat privilégiée par l'archétype
    h = heal_share(opts)
    if opts.offense_weight and h < 1:
        weights.append({"stat": "dmg_pct", "label": "Dégâts", "pts": round(opts.offense_weight * (1 - h) / 100, 2),
                        "unit": "par % de dégâts en plus", "boosted": arch is not None and arch.role == "dps"})
    if opts.offense_weight and h > 0:
        weights.append({"stat": "heal_mastery", "label": "Soins", "pts": round(opts.offense_weight * h / 100, 2),
                        "unit": "par % de soins en plus", "boosted": arch is not None and arch.role == "heal"})
    if opts.offense_weight < 100:
        d = round((100 - opts.offense_weight) / 100, 2)
        weights.append({"stat": "hp", "label": "PV", "pts": d, "unit": "par % de PV en plus", "boosted": "hp" in focus})
        weights.append({"stat": "elem_res", "label": "Résistances", "pts": d,
                        "unit": "par % de dégâts subis en moins" + (" (même au-delà de la cible)" if opts.res_free else
                                                                    f" (jusqu'à {opts.res_target} %)"),
                        "boosted": "elem_res" in focus})
        weights.append({"stat": "block", "label": "Parade", "pts": round(d * 100 * BLOCK_REDUCTION / 100, 2),
                        "unit": f"par % de Parade (un coup paré : {round(100 * BLOCK_REDUCTION)} % de dégâts en moins ; "
                                "un peu plus quand la Parade est déjà haute)", "boosted": "block" in focus})
    for k, lab in (("ap", "PA"), ("mp", "PM"), ("range", "Portée"), ("wp", "PW")):
        if util[k][0]:
            unit = (f"pour le 1er point de {lab}, puis de moins en moins (max {util[k][1]})" if k in DECAYING
                    else f"par {lab} (max {util[k][1]})")
            weights.append({"stat": k, "label": lab, "pts": round(100 * util[k][0], 2), "unit": unit,
                            "boosted": k in arch_util or k in focus})
    for k, lab in (("lock", "Tacle"), ("dodge", "Esquive")):   # par 100 points : ces stats se comptent en centaines
        if util[k][0]:
            weights.append({"stat": k, "label": lab, "pts": round(1e4 * util[k][0], 2), "unit": f"par 100 de {lab} (max {util[k][1]})",
                            "boosted": True})
    for k, lab in (("crit_res", "Rés. critique"), ("rear_res", "Rés. dos")):
        if util[k][0]:
            weights.append({"stat": k, "label": lab, "pts": round(100 * util[k][0], 2), "unit": f"par point de {lab} (max {util[k][1]})",
                            "boosted": True})
            weights.append({"stat": k, "label": f"{lab} < 0", "pts": -SEC_RES_NEG_PENALTY, "unit": f"malus par point de {lab} sous 0"})
    if opts.will_min:
        weights.append({"stat": "willpower", "label": f"Volonté < {opts.will_min}", "pts": -WILL_SHORT_PENALTY,
                        "unit": "malus par point de Volonté sous le minimum (retraits PA / PM subis)"})
    if util["range"][0] == 0:
        weights.append({"stat": "range", "label": "Portée < 0", "pts": -RANGE_NEG_PENALTY, "unit": "malus par PO sous 0"})
    if opts.willpower_weight:
        weights.append({"stat": "willpower", "label": "Volonté", "pts": round(opts.willpower_weight / 100, 2),
                        "unit": "par point (retraits PA / PM " + ("subis)" if arch and arch.role == "tank" else "infligés)"),
                        "boosted": "willpower" in focus or bool(arch and arch.role == "tank")})
    if opts.crit and opts.crit_target:
        weights.append({"stat": "crit_rate", "label": f"Critique < {opts.crit_target} %", "pts": -CRIT_SHORT_PENALTY,
                        "unit": f"malus par % de critique sous {opts.crit_target} %"})
    if opts.res_target:
        floor = opts.res_target - opts.res_tol
        weights.append({"stat": "elem_res", "label": f"Résistance < {floor} %", "pts": -RES_SHORT_PENALTY,
                        "unit": f"malus par point de résistance manquant pour atteindre {floor} % sur un élément"})
    parts = score_parts(tot.features, opts)
    score = [{"key": k, "label": FEATURE_FR.get(k, k), "points": round(v, 2)} for k, v in parts.items() if round(v, 2)]
    # aptitudes : profil de l'archétype et points placés
    prof = apt_profile(opts)
    forced = apt_forced(opts)
    ch = build.characteristics
    branches = []
    all_lines = char_lines(data.game)

    def line_gain(key: str) -> float:
        """Points de score d'un point de plus dans cette ligne, au build final."""
        b2 = replace(build, characteristics={**ch, key: ch.get(key, 0) + 1})
        return round(evaluate(data, opts, b2).score - tot.score, 2)

    for branch in data.game["characteristics"]:  # type: ignore[union-attr]
        order = [f"{branch}.{x}" for x in prof.get(branch, [])]
        others = [cl.key for cl in all_lines if cl.branch == branch and cl.key not in order]
        maxes = {cl.key: cl.max_points for cl in all_lines}
        lines = [{"key": k, "line": k.split(".")[1], "label": LINE_FR.get(k.split(".")[1], k), "points": ch.get(k, 0),
                  "in_profile": k in order, "forced": k in forced, "gain": line_gain(k),
                  "full": maxes.get(k) is not None and ch.get(k, 0) >= maxes[k]}  # type: ignore[operator]
                 for k in order + others]
        branches.append({"branch": branch, "name": BRANCH_FR.get(branch, branch),
                         "total": branch_points(branch, opts.level, data.game), "lines": lines})
    checks = check_build(data, opts, build, tot)
    return {
        "archetype": {"key": opts.archetype, "name": arch.name if arch else opts.archetype, "desc": arch.desc if arch else "",
                      "recommended": opts.archetype in recs,
                      "focus": [{"stat": k, "label": lab} for k, lab in (arch.focus if arch else ())]},
        "class": cls.name if cls else opts.class_key, "level": opts.level,
        "crit_target_level": crit_target(opts.level),
        "panels": panels, "settings": settings, "weights": weights, "score": score, "total": round(sum(parts.values()), 2),
        "marginals": _marginals(opts, tot), "aptitudes": branches, "targets": _targets(opts, arch, tot),
        "manual_apt": opts.char_mode == "manual",
        "checks": [asdict(c) for c in checks],
        "elements": [ELEMENT_FR[e] for e in opts.elements if e in ELEMENTS],
        "element_keys": [e for e in opts.elements if e in ELEMENTS],
        "panel_fields": {k: list(v) for k, v in PANELS.items()},
    }
