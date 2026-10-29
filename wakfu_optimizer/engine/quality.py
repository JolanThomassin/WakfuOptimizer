"""Qualité d'un build : règles « ce build a du sens pour cet archétype » et explication du calcul.

Les mêmes règles servent aux tests (tests/test_build_quality.py : chaque classe × archétype habituel × niveau)
et à l'onglet Explication de l'interface (outil de débogage : ce que l'algorithme a privilégié et pourquoi).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..data.models import ELEMENT_FR, ELEMENTS, SLOT_FR, GameData, Slot
from .archetypes import ARCHETYPES, PANELS, apt_forced, apt_profile, class_archetypes, crit_target
from .characteristics import BRANCH_FR, LINE_FR, branch_points, char_lines
from .options import Build, OptimizeOptions, default_min_ap, default_min_mp
from .scoring import (CRIT_SHORT_PENALTY, RES_SHORT_PENALTY, crit_short, log_score, res_cap, res_need, score_parts,
                      utility_table)
from .stats import Totals

# Emplacements qu'un build complet remplit toujours (familier, monture et emblème dépendent du niveau / des filtres ;
# la seconde main peut rester vide exprès : sublimation Expert des armes légères)
CORE_SLOTS = (Slot.HEAD, Slot.NECK, Slot.CHEST, Slot.LEFT_HAND, Slot.RIGHT_HAND, Slot.LEGS, Slot.BACK,
              Slot.SHOULDERS, Slot.BELT, Slot.FIRST_WEAPON)
CRIT_MARGIN = 3        # % de critique toléré sous le palier de l'archétype
TANK_RES_PCT = 60      # % de résistance minimum (chaque élément) d'un tank
LINES_DPS_ONLY = ("strength.melee_mastery", "strength.distance_mastery", "fortune.crit_rate")


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    detail: str
    severity: str = "error"    # error : build incohérent | warn : à surveiller

    def __str__(self) -> str:
        return f"[{'OK' if self.ok else self.severity.upper()}] {self.label} : {self.detail}"


def _apt_label(key: str) -> str:
    branch, line = key.split(".", 1)
    return f"{BRANCH_FR.get(branch, branch)} · {LINE_FR.get(line, line)}"


def check_aptitudes(data: GameData, opts: OptimizeOptions, ch: dict[str, int]) -> list[Check]:
    """Aptitudes cohérentes avec l'archétype : tous les points placés, seulement des lignes du profil, et les
    incontournables (Résistance élémentaire, PA, % Critique d'un DPS, PV et Parade d'un tank, Volonté d'un débuff)."""
    out: list[Check] = []
    arch = ARCHETYPES.get(opts.archetype)
    role = arch.role if arch else "dps"
    L = opts.level

    def add(key: str, label: str, ok: bool, detail: str, severity: str = "error") -> None:
        out.append(Check(key, label, bool(ok), detail, severity))

    lines = char_lines(data.game)
    unspent = []
    for branch in data.game["characteristics"]:  # type: ignore[union-attr]
        left = branch_points(branch, L, data.game) - sum(ch.get(cl.key, 0) for cl in lines if cl.branch == branch)
        if left:
            unspent.append(f"{BRANCH_FR.get(branch, branch)} ({left})")
    add("apt_spent", "Tous les points d'aptitude placés", not unspent, "restants : " + ", ".join(unspent) if unspent else "oui")
    prof = apt_profile(opts)
    allowed = {f"{b}.{x}" for b, xs in prof.items() for x in xs}
    off = [f"{_apt_label(k)} ({n})" for k, n in ch.items() if n and k not in allowed]
    add("apt_profile", "Aptitudes cohérentes avec l'archétype", not off,
        "hors profil : " + ", ".join(off) if off else "uniquement des lignes du profil")
    if opts.apt_elem_res:
        need = min(10, branch_points("intelligence", L, data.game))
        add("apt_res", "Résistance élémentaire (Intelligence) au max", ch.get("intelligence.elem_res", 0) >= need,
            f"{ch.get('intelligence.elem_res', 0)} / {need}")
    if branch_points("major", L, data.game) >= 1:
        add("apt_major_ap", "Majeur : Point d'Action", ch.get("major.ap", 0) == 1, "pris" if ch.get("major.ap") else "absent")
    if opts.crit and opts.crit_target:
        need = min(20, branch_points("fortune", L, data.game))
        add("apt_crit", "Chance : % Coup critique au max", ch.get("fortune.crit_rate", 0) >= need,
            f"{ch.get('fortune.crit_rate', 0)} / {need}")
    if role == "tank":
        dps_lines = [f"{_apt_label(k)} ({ch[k]})" for k in LINES_DPS_ONLY if ch.get(k)]
        add("tank_apt_dps", "Tank : pas d'aptitudes de DPS", not dps_lines,
            "trouvé : " + ", ".join(dps_lines) if dps_lines else "aucune (critique, maîtrise mêlée / distance)")
        need = branch_points("strength", L, data.game)
        add("tank_apt_hp", "Tank : Force en Points de Vie", ch.get("strength.hp", 0) >= need,
            f"{ch.get('strength.hp', 0)} / {need}")
        need = min(20, branch_points("fortune", L, data.game))
        add("tank_apt_block", "Tank : % Parade au max", ch.get("fortune.block", 0) >= need, f"{ch.get('fortune.block', 0)} / {need}")
    if opts.willpower_weight >= 20:
        need = min(20, branch_points("agility", L, data.game))
        add("apt_will", "Retraits : Volonté au max", ch.get("agility.willpower", 0) >= need,
            f"{ch.get('agility.willpower', 0)} / {need}")
    return out


def check_build(data: GameData, opts: OptimizeOptions, build: Build, tot: Totals) -> list[Check]:
    """Règles qu'un build optimisé doit respecter pour avoir du sens (classe, niveau, archétype)."""
    out: list[Check] = []
    arch = ARCHETYPES.get(opts.archetype)
    role = arch.role if arch else "dps"
    s, L = tot.stats, opts.level

    def add(key: str, label: str, ok: bool, detail: str, severity: str = "error") -> None:
        out.append(Check(key, label, bool(ok), detail, severity))

    # --- équipement
    missing = [SLOT_FR[s_] for s_ in CORE_SLOTS if s_ not in build.slots]
    add("slots", "Équipement complet", not missing, "manque : " + ", ".join(missing) if missing else "tous les emplacements remplis")

    # --- PA / PM du niveau
    add("ap", "PA du niveau", s.get("ap", 0) >= default_min_ap(L), f"{s.get('ap', 0)} PA (minimum {default_min_ap(L)})")
    add("mp", "PM du niveau", s.get("mp", 0) >= default_min_mp(L), f"{s.get('mp', 0)} PM (minimum {default_min_mp(L)})")

    # --- résistances
    worst = min(tot.res_pct.values())
    if opts.res_target:
        floor = opts.res_target - opts.res_tol
        add("res", "Résistance visée", worst >= floor, f"élément le plus faible {worst} % (plancher {floor} %)")
    if role == "tank":
        add("tank_res", "Résistances de tank", worst >= TANK_RES_PCT, f"élément le plus faible {worst} % (≥ {TANK_RES_PCT} % attendu)")

    # --- aptitudes
    if opts.char_mode != "manual" and opts.optimize_characteristics:
        out += check_aptitudes(data, opts, build.characteristics)

    # --- dégâts
    if opts.crit and opts.crit_target:
        c = s.get("crit_rate", 0)
        add("crit", "Critique suffisant", c >= opts.crit_target - CRIT_MARGIN,
            f"{c} % (palier de l'archétype au niveau {L} : {opts.crit_target} %)")
    if role in ("dps", "heal") and opts.range in ("melee", "distance") and not opts.neutral_combo:
        mine, other = ("melee_mastery", "distance_mastery") if opts.range == "melee" else ("distance_mastery", "melee_mastery")
        add("range_mastery", "Maîtrise de la bonne portée", s.get(mine, 0) > max(0, s.get(other, 0)),
            f"{LINE_FR[mine]} {s.get(mine, 0)} contre {LINE_FR[other]} {s.get(other, 0)}")
    for flag, stat, lab in (("rear", "rear_mastery", "Maîtrise Dos"), ("berserk", "berserk_mastery", "Maîtrise Berserk"),
                            ("heal", "heal_mastery", "Maîtrise Soin")):
        if getattr(opts, flag) and not opts.neutral_combo:
            add(f"{flag}_mastery", f"{lab} présente", s.get(stat, 0) > 0, f"{s.get(stat, 0)}")
    return out


def failures(checks: list[Check], severity: str = "error") -> list[Check]:
    return [c for c in checks if not c.ok and c.severity == severity]


# =====================================================================  explication
FEATURE_FR = {"offense": "Dégâts", "defense": "Survie (PV effectifs)", "ap": "PA", "mp": "PM", "range": "Portée", "wp": "PW",
              "will": "Volonté (retraits)", "res_short": "Pénalité : résistance sous le plancher",
              "crit_short": "Pénalité : critique sous le palier"}


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
        ("Points de vie (fixes)", "+1 000", gain(hp=f["hp"] + 1000)),
        ("% Points de vie", "+10 %", gain(hp_pct=f["hp_pct"] + 10)),
        ("Résistance élémentaire", "+100 (4 él.)", gain(**res_plus(100))),
        ("PA", "+1", gain(ap=f["ap"] + 1)), ("PM", "+1", gain(mp=f["mp"] + 1)),
        ("Portée", "+1", gain(range=f["range"] + 1)), ("PW", "+1", gain(wp=f["wp"] + 1)),
        ("Volonté", "+10", gain(will=f["will"] + 10) if opts.willpower_weight else 0.0),
    ]
    return [{"label": lab, "unit": u, "points": p} for lab, u, p in rows]


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
         + (" ; sans sublimations" if opts.no_subs else ""), "src": src("subs")},
    ]
    # poids de chaque stat dans le score (1 point ≈ 1 % de valeur globale)
    arch_util = set(arch.utility) if arch else set()
    weights = []   # points de score par unité (1 point ≈ 1 % de valeur globale) ; 0 = ignoré
    if opts.offense_weight:
        weights.append({"stat": "dmg_pct", "label": "Dégâts", "pts": opts.offense_weight / 100, "unit": "par % de dégâts"})
    if opts.offense_weight < 100:
        weights.append({"stat": "hp", "label": "PV effectifs", "pts": (100 - opts.offense_weight) / 100, "unit": "par % de PV effectifs"})
    for k, lab in (("ap", "PA"), ("mp", "PM"), ("range", "Portée"), ("wp", "PW")):
        if util[k][0]:
            weights.append({"stat": k, "label": lab, "pts": round(100 * util[k][0], 2), "unit": f"par {lab} (max {util[k][1]})",
                            "boosted": k in arch_util})
    if opts.willpower_weight:
        weights.append({"stat": "willpower", "label": "Volonté", "pts": round(opts.willpower_weight / 100, 2), "unit": "par point"})
    if opts.crit and opts.crit_target:
        weights.append({"stat": "crit_rate", "label": "Critique sous le palier", "pts": -CRIT_SHORT_PENALTY,
                        "unit": f"par % sous {opts.crit_target} %"})
    if opts.res_target:
        weights.append({"stat": "elem_res", "label": "Résistance sous le plancher", "pts": -RES_SHORT_PENALTY,
                        "unit": "par point manquant"})
    parts = score_parts(tot.features, opts)
    score = [{"key": k, "label": FEATURE_FR.get(k, k), "points": round(v, 2)} for k, v in parts.items() if round(v, 2)]
    # aptitudes : profil de l'archétype et points placés
    prof = apt_profile(opts)
    forced = apt_forced(opts)
    ch = build.characteristics
    branches = []
    for branch in data.game["characteristics"]:  # type: ignore[union-attr]
        order = [f"{branch}.{x}" for x in prof.get(branch, [])]
        lines = [{"key": k, "label": LINE_FR.get(k.split(".")[1], k), "points": ch.get(k, 0), "in_profile": True,
                  "forced": k in forced} for k in order]
        lines += [{"key": k, "label": LINE_FR.get(k.split(".")[1], k), "points": n, "in_profile": False}
                  for k, n in ch.items() if n and k.startswith(branch + ".") and k not in order]
        branches.append({"branch": branch, "name": BRANCH_FR.get(branch, branch),
                         "total": branch_points(branch, opts.level, data.game), "lines": lines})
    checks = check_build(data, opts, build, tot)
    return {
        "archetype": {"key": opts.archetype, "name": arch.name if arch else opts.archetype, "desc": arch.desc if arch else "",
                      "recommended": opts.archetype in recs, "class_recs": [ARCHETYPES[k].name for k in recs]},
        "class": cls.name if cls else opts.class_key, "level": opts.level,
        "crit_target_level": crit_target(opts.level),
        "panels": panels, "settings": settings, "weights": weights, "score": score, "total": round(sum(parts.values()), 2),
        "marginals": _marginals(opts, tot), "aptitudes": branches,
        "manual_apt": opts.char_mode == "manual",
        "checks": [asdict(c) for c in checks],
        "elements": [ELEMENT_FR[e] for e in opts.elements if e in ELEMENTS],
        "panel_fields": {k: list(v) for k, v in PANELS.items()},
    }
