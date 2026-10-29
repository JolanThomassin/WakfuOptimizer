"""Évaluateur exact d'un build : agrégation des stats et scores.

Sert à afficher les résultats et à vérifier le solveur (les totaux doivent coïncider).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..data.models import ELEMENTS, GameData, Item, Slot
from .characteristics import BRANCH_FR, LINE_FR, char_lines
from .options import DENOUEMENT_CRIT, NEUTRAL_COMBO_STATES, SECONDARY_MASTERIES, Build, OptimizeOptions

DENOUEMENT_STATE = NEUTRAL_COMBO_STATES[1]
from .scoring import damage_d2, res_cap, defense_value, ehp_factor, log_score, res_need, res_pct, secondary_mastery
from .shards import condition_holds, effect_targets, parse_stat_condition

DISPLAY_STATS = [
    ("hp", "PV"), ("ap", "PA"), ("mp", "PM"), ("wp", "PW"), ("range", "Portée"),
    ("crit_rate", "% Critique"), ("block", "% Parade"), ("crit_mastery", "Maîtrise Critique"),
    ("melee_mastery", "Maîtrise Mêlée"), ("distance_mastery", "Maîtrise Distance"),
    ("rear_mastery", "Maîtrise Dos"), ("berserk_mastery", "Maîtrise Berserk"),
    ("heal_mastery", "Maîtrise Soin"), ("dmg_pct", "% Dommages infligés"),
    ("lock", "Tacle"), ("dodge", "Esquive"), ("initiative", "Initiative"), ("willpower", "Volonté"),
    ("control", "Contrôle"), ("crit_res", "Résistance Critique"), ("rear_res", "Résistance Dos"),
]


@dataclass
class Totals:
    stats: dict[str, int] = field(default_factory=dict)
    mastery: dict[str, int] = field(default_factory=dict)      # par élément
    res_flat: dict[str, int] = field(default_factory=dict)
    res_pct: dict[str, int] = field(default_factory=dict)
    hp: int = 0
    hp_base: int = 0
    features: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    mastery_used: int = 0
    crit_used: int = 0
    d2: int = 0
    defense: int = 0
    active_states: dict[int, int] = field(default_factory=dict)   # état -> niveau effectif
    # d'où vient chaque stat : stat -> [(origine, type, valeur, référence)] ; type : base | item | random | rune | apt | sub
    # référence (pour l'icône) : gfx de l'item, couleur de la rune, ligne d'aptitude
    sources: dict[str, list[tuple[str, str, int, str]]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def item_rune_level(item: Item, cap_level: int, rune_reqs: tuple[int, ...]) -> int:
    lvl = 0
    for i, req in enumerate(rune_reqs, start=1):
        if item.level >= req or item.scales_with_character and cap_level >= req:
            lvl = i
    return lvl


def evaluate(data: GameData, opts: OptimizeOptions, build: Build, extra_states: dict[int, int] | None = None) -> Totals:
    """`extra_states` : niveaux d'état ajoutés (pour estimer l'apport d'une sublimation)."""
    items = data.item_by_id()
    runes = data.rune_by_id()
    subs = data.sub_by_id()
    L = opts.level
    base = data.game["base"]
    cls = data.classes.get(opts.class_key)
    s: dict[str, int] = defaultdict(int)
    t = Totals()
    src: dict[str, list[tuple[str, str, int, str]]] = defaultdict(list)

    def add(stat: str, v: int, origin: str, kind: str, ref: str = "") -> None:
        if v:
            s[stat] += v
            src[stat].append((origin, kind, v, ref))

    add("ap", int(base["ap"]), "Base du personnage", "base")
    add("mp", int(base["mp"]), "Base du personnage", "base")
    add("wp", cls.base_wp if cls else int(base["wp"]), "Base du personnage", "base")
    add("crit_rate", int(base["crit_rate"]), "Base du personnage", "base")
    add("hp", int(base["hp_flat"]) + int(base["hp_per_level"]) * L, f"Base du personnage (niveau {L})", "base")
    rand_m: dict[str, int] = defaultdict(int)
    rand_r: dict[str, int] = defaultdict(int)

    two_handed = False
    second_used = False
    state_levels: dict[int, int] = defaultdict(int)
    for slot, ch in build.slots.items():
        it = items.get(ch.item_id)
        if it is None:
            t.warnings.append(f"Item {ch.item_id} introuvable")
            continue
        if slot is Slot.FIRST_WEAPON and it.two_handed:
            two_handed = True
        if slot is Slot.SECOND_WEAPON:
            second_used = True
        iname = it.name(opts.lang)
        for k, v in it.stats_at(L).items():
            add(k, int(v), iname, "item", str(it.gfx_id))
        for (v, n), els in zip(it.random_mastery, ch.mastery_elements):
            for e in list(dict.fromkeys(els))[:n]:
                rand_m[e] += v
                src[f"{e}_mastery"].append((f"{iname} (élément au choix)", "random", v, str(it.gfx_id)))
        for (v, n), els in zip(it.random_resistance, ch.resistance_elements):
            for e in list(dict.fromkeys(els))[:n]:
                rand_r[e] += v
                src[f"{e}_res"].append((f"{iname} (élément au choix)", "random", v, str(it.gfx_id)))
        for sh in ch.shards:
            if sh.rune_id is not None and sh.rune_id in runes:
                r = runes[sh.rune_id]
                add(r.stat, r.value(sh.rune_level, slot), f"{r.name(opts.lang)} niv. {sh.rune_level} ({iname})", "rune",
                    str(int(sh.color)))
        for sid in (ch.sublimation_id, ch.special_sublimation_id):
            if sid is not None and sid in subs:
                state_levels[subs[sid].state_id] += subs[sid].state_level

    for sid, lvl in (extra_states or {}).items():
        state_levels[sid] += lvl
    for cl in char_lines(data.game):
        n = build.characteristics.get(cl.key, 0)
        for stat, v in cl.per_point.items():
            add(stat, n * v, f"Aptitude {BRANCH_FR.get(cl.branch, cl.branch)} · {LINE_FR.get(cl.line, cl.line)} ({n} pt)", "apt",
                cl.line)

    later = []   # effets « si la stat X est <= / >= v » : vérifiés une fois les autres effets appliqués
    for sid, lvl in state_levels.items():
        st = data.states.get(sid)
        if st is None:
            continue
        eff_lvl = min(lvl, st.limit) if st.limit else lvl
        t.active_states[sid] = eff_lvl
        for e in st.effects:
            if parse_stat_condition(e.condition):
                later.append((st, e, eff_lvl))
            elif condition_holds(e.condition, opts, two_handed, second_used):
                for target in effect_targets(e):
                    add(target, e.value(eff_lvl, L), f"Sublimation {st.name} niv. {eff_lvl}", "sub")
    snapshot = dict(s)
    for st, e, eff_lvl in later:
        if condition_holds(e.condition, opts, two_handed, second_used, snapshot):
            for target in effect_targets(e):
                add(target, e.value(eff_lvl, L), f"Sublimation {st.name} niv. {eff_lvl}", "sub")
        elif e is st.effects[0]:
            t.warnings.append(f"{st.name} : condition non remplie ({e.condition}), sans effet.")

    if opts.neutral_combo:
        if any(s[k] > 0 for k in SECONDARY_MASTERIES):
            t.warnings.append("Combo Neutralité inactif : une maîtrise secondaire est au-dessus de 0.")
        cm = s["crit_mastery"]
        if DENOUEMENT_STATE in t.active_states and s["crit_rate"] >= DENOUEMENT_CRIT and cm:
            # Dénouement : la Maîtrise Critique est convertie en Maîtrise Élémentaire au lancement du combat
            add("elem_mastery", cm, "Dénouement (Maîtrise Critique convertie)", "sub")
            add("crit_mastery", -cm, "Dénouement (convertie en Maîtrise Élémentaire)", "sub")
    for e in ELEMENTS:
        t.mastery[e] = s["elem_mastery"] + s[f"{e}_mastery"] + rand_m[e]
        t.res_flat[e] = s["elem_res"] + s[f"{e}_res"] + rand_r[e]
        t.res_pct[e] = res_pct(t.res_flat[e])

    hp_base = s["hp"]
    t.hp = hp_base * (100 + s["hp_pct"]) // 100
    t.stats = dict(s)
    t.stats["hp"] = t.hp
    t.stats["crit_rate"] = max(-10, min(100, s["crit_rate"]))
    t.stats["block"] = min(100, s["block"])

    played = [e for e in opts.elements if e in ELEMENTS] or list(ELEMENTS)
    m = min(t.mastery[e] for e in played)
    sec = secondary_mastery(s["melee_mastery"], s["distance_mastery"], opts.range)
    mtot = m + sec + (s["berserk_mastery"] if opts.berserk else 0) + (s["heal_mastery"] if opts.heal else 0)
    t.mastery_used = mtot
    crit = max(0, min(100, s["crit_rate"])) if opts.crit else 0
    t.crit_used = crit
    t.d2 = damage_d2(mtot, crit, s["crit_mastery"] if opts.crit else 0,
                     s["rear_mastery"] if opts.rear and not opts.heal else 0,
                     opts.rear_share if opts.rear and not opts.heal else 0, s["dmg_pct"])
    gs = [ehp_factor(t.res_flat[e]) for e in ELEMENTS]
    g = min(gs)   # résistances équilibrées : la plus faible compte
    t.defense = defense_value(hp_base, s["hp_pct"], g)
    t.hp_base = hp_base
    capped = [min(t.res_flat[e], res_cap(opts)) for e in ELEMENTS]
    rear = opts.rear and not opts.heal
    t.features = {
        "mtot": float(mtot), "crit": float(crit), "crit_mastery": float(s["crit_mastery"] if opts.crit else 0),
        "rear_mastery": float(s["rear_mastery"] if rear else 0), "dmg_pct": float(s["dmg_pct"]),
        "hp": float(hp_base), "hp_pct": float(s["hp_pct"]),
        "res": float(min(capped)),
        "ap": float(s["ap"]), "mp": float(s["mp"]), "range": float(s["range"]), "wp": float(s["wp"]),
        "res_short": float(sum(max(0, res_need(opts) - t.res_flat[e]) for e in ELEMENTS)) if res_need(opts) else 0.0,
    }
    t.score = log_score(t.features, opts)
    t.sources = dict(src)
    return t
