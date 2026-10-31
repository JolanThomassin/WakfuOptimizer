"""Évaluateur exact d'un build : agrégation des stats et scores.

Sert à afficher les résultats et à vérifier le solveur (les totaux doivent coïncider).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..data.models import ELEMENTS, GameData, Item, Slot, SubEffect, SubState
from .characteristics import BRANCH_FR, LINE_FR, char_lines
from .features import evaluator_features
from .options import Build, OptimizeOptions
from .scoring import damage_d2, defense_value, ehp_factor, elem_mastery_used, log_score, res_pct, secondary_mastery
from .shards import CRIT_TO_ELEM, condition_holds, condition_label, effect_targets, needs_stats, parse_stat_condition

DISPLAY_STATS = [
    ("hp", "PV"), ("ap", "PA"), ("mp", "PM"), ("wp", "PW"), ("range", "Portée"),
    ("crit_rate", "% Critique"), ("block", "% Parade"), ("crit_mastery", "Maîtrise Critique"),
    ("melee_mastery", "Maîtrise Mêlée"), ("distance_mastery", "Maîtrise Distance"),
    ("rear_mastery", "Maîtrise Dos"), ("berserk_mastery", "Maîtrise Berserk"),
    ("heal_mastery", "Maîtrise Soin"), ("dmg_pct", "% Dommages infligés"),
    ("lock", "Tacle"), ("dodge", "Esquive"), ("initiative", "Initiative"), ("willpower", "Volonté"),
    ("control", "Contrôle"), ("crit_res", "Résistance Critique"), ("rear_res", "Résistance Dos"),
]


def spare_elements(data: GameData, opts: OptimizeOptions, played: list[str]) -> list[str]:
    """Éléments « en trop » d'une maîtrise sur N éléments : ceux de la classe d'abord (elle a des sorts dans ces
    éléments), puis les autres. Ex. Crâ mono Feu, maîtrise sur 3 éléments : Feu + Air + Terre, jamais Eau."""
    cls = data.classes.get(opts.class_key)
    mine = [e for e in (cls.elements if cls else ()) if e in ELEMENTS and e not in played]
    return mine + [e for e in ELEMENTS if e not in played and e not in mine]


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
    raw: dict[str, int] = field(default_factory=dict)   # stats avant plafonds (PV de base, % critique brut) : rescore


def item_rune_level(item: Item, cap_level: int, rune_reqs: tuple[int, ...]) -> int:
    lvl = 0
    for i, req in enumerate(rune_reqs, start=1):
        if item.level >= req or item.scales_with_character and cap_level >= req:
            lvl = i
    return lvl


@dataclass
class Prepared:
    """Ce qui ne dépend pas des sublimations : base, passif, items, runes et aptitudes (voir prepare)."""

    stats: dict[str, int]
    sources: dict[str, list[tuple[str, str, int, str]]]
    rand_m: dict[str, int]
    rand_r: dict[str, int]
    two_handed: bool
    second_used: bool
    state_levels: dict[int, int]     # niveaux d'états des sublimations posées sur le build
    warnings: list[str]


def prepare(data: GameData, opts: OptimizeOptions, build: Build) -> Prepared:
    """Première moitié d'evaluate : à calculer une fois pour évaluer beaucoup de jeux de sublimations sur les mêmes items
    (onglet Build sombre, engine/combos.py)."""
    items = data.item_by_id()
    runes = data.rune_by_id()
    subs = data.sub_by_id()
    L = opts.level
    base = data.game["base"]
    cls = data.classes.get(opts.class_key)
    s: dict[str, int] = defaultdict(int)
    warnings: list[str] = []
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
    for stat, v in (cls.passive_stats(L) if cls else {}).items():
        add(stat, v, f"Passif de classe : {cls.passive_name}", "passive", opts.class_key)  # type: ignore[union-attr]
    rand_m: dict[str, int] = defaultdict(int)
    rand_r: dict[str, int] = defaultdict(int)

    two_handed = False
    second_used = False
    state_levels: dict[int, int] = defaultdict(int)
    for slot, ch in build.slots.items():
        it = items.get(ch.item_id)
        if it is None:
            warnings.append(f"Item {ch.item_id} introuvable")
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

    for cl in char_lines(data.game):
        n = build.characteristics.get(cl.key, 0)
        for stat, v in cl.per_point.items():
            add(stat, n * v, f"Aptitude {BRANCH_FR.get(cl.branch, cl.branch)} · {LINE_FR.get(cl.line, cl.line)} ({n} pt)", "apt",
                cl.line)
    return Prepared(dict(s), dict(src), dict(rand_m), dict(rand_r), two_handed, second_used, dict(state_levels), warnings)


def evaluate(data: GameData, opts: OptimizeOptions, build: Build, extra_states: dict[int, int] | None = None,
             prepared: Prepared | None = None) -> Totals:
    """`extra_states` : niveaux d'état ajoutés (pour estimer l'apport d'une sublimation). `prepared` : prepare() du même
    build (même items, runes et aptitudes ; les sublimations du build sont celles de prepare)."""
    p = prepared or prepare(data, opts, build)
    L = opts.level
    s: dict[str, int] = defaultdict(int, p.stats)
    src: dict[str, list[tuple[str, str, int, str]]] = defaultdict(list, {k: list(v) for k, v in p.sources.items()})
    t = Totals(warnings=list(p.warnings))
    rand_m: dict[str, int] = defaultdict(int, p.rand_m)
    rand_r: dict[str, int] = defaultdict(int, p.rand_r)
    two_handed, second_used = p.two_handed, p.second_used
    state_levels: dict[int, int] = defaultdict(int, p.state_levels)

    def add(stat: str, v: int, origin: str, kind: str, ref: str = "") -> None:
        if v:
            s[stat] += v
            src[stat].append((origin, kind, v, ref))

    for sid, lvl in (extra_states or {}).items():
        state_levels[sid] += lvl

    # Effets conditionnés par les stats du build, vérifiés une fois les autres effets appliqués : d'abord
    # « maîtrises secondaires <= 0 » (Ambition, Neutralité…), puis « si la stat X est <= / >= v » (épiques).
    mid: list[tuple[SubState, SubEffect, int]] = []
    later: list[tuple[SubState, SubEffect, int]] = []
    convert: list[str] = []   # Dénouement actif

    def apply(st: SubState, e: SubEffect, eff_lvl: int) -> None:
        if e.stat == CRIT_TO_ELEM:
            convert.append(st.name)
            return
        for target in effect_targets(e):
            add(target, e.value(eff_lvl, L), f"Sublimation {data.state_name(st.id, opts.lang)} niv. {eff_lvl}", "sub")

    for sid, lvl in state_levels.items():
        st = data.states.get(sid)
        if st is None:
            continue
        eff_lvl = min(lvl, st.limit) if st.limit else lvl
        t.active_states[sid] = eff_lvl
        for e in st.effects:
            if needs_stats(e.condition):
                (later if any(parse_stat_condition(c) for c in e.condition.split("&")) else mid).append((st, e, eff_lvl))
            elif condition_holds(e.condition, opts, two_handed, second_used):
                apply(st, e, eff_lvl)
    for group in (mid, later):
        snapshot = dict(s)
        for st, e, eff_lvl in group:
            if condition_holds(e.condition, opts, two_handed, second_used, snapshot):
                apply(st, e, eff_lvl)
            elif e is st.effects[0]:
                t.warnings.append(f"{st.name} : condition non remplie ({condition_label(e.condition)}), sans effet.")
    cm = s["crit_mastery"]
    if convert and cm > 0:   # Dénouement : la Maîtrise Critique est convertie en Maîtrise Élémentaire au lancement du combat
        add("elem_mastery", cm, f"{convert[0]} (Maîtrise Critique convertie)", "sub")
        add("crit_mastery", -cm, f"{convert[0]} (convertie en Maîtrise Élémentaire)", "sub")
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

    mtot, crit = _mastery_crit(s, t.mastery, opts)
    t.mastery_used = mtot + (s["heal_mastery"] if opts.heal else 0)
    t.crit_used = crit
    t.d2 = damage_d2(t.mastery_used, crit, s["crit_mastery"] if opts.crit else 0,
                     s["rear_mastery"] if opts.rear and not opts.heal else 0,
                     opts.rear_share if opts.rear and not opts.heal else 0, s["dmg_pct"])
    gs = [ehp_factor(t.res_flat[e]) for e in ELEMENTS]
    g = sum(gs) // 4   # moyenne des quatre éléments
    t.defense = defense_value(hp_base, s["hp_pct"], g)
    t.hp_base = hp_base
    t.features = evaluator_features(s, t.res_flat, mtot, crit, opts)
    t.score = log_score(t.features, opts)
    t.sources = dict(src)
    t.raw = dict(s)
    return t


def _mastery_crit(s: dict[str, int], mastery: dict[str, int], opts: OptimizeOptions) -> tuple[int, int]:
    """Maîtrise des dégâts (élémentaire + portée + berserk ; les soins y ajoutent la Maîtrise Soin) et % critique compté."""
    m = elem_mastery_used([(mastery[e], w) for e, w in opts.element_weights()])
    sec = secondary_mastery(s["melee_mastery"], s["distance_mastery"], opts.range)
    mtot = m + sec + (s["berserk_mastery"] if opts.berserk else 0)
    return mtot, max(0, min(100, s["crit_rate"])) if opts.crit else 0


def rescore(t: Totals, opts: OptimizeOptions, stats: dict[str, int] | None = None,
            mastery: dict[str, int] | None = None, res_flat: dict[str, int] | None = None) -> float:
    """Score de `t` si seules quelques stats (brutes), maîtrises ou résistances par élément changeaient :
    ce que rapporte une ligne de la comparaison d'items, toutes choses égales par ailleurs."""
    s = defaultdict(int, t.raw)
    s.update(stats or {})
    m = {**t.mastery, **(mastery or {})}
    r = {**t.res_flat, **(res_flat or {})}
    mtot, crit = _mastery_crit(s, m, opts)
    return log_score(evaluator_features(s, r, mtot, crit, opts), opts)
