"""Gestion des sublimations : catalogue avec l'apport estimé pour un build, et remplacement sur un item."""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass, field

from ..data.models import PROP_EPIC_GEM, PROP_RELIC_GEM, GameData, Item, Slot, Sublimation
from .options import Build, OptimizeOptions
from .shards import pattern_offsets, static_condition
from .stats import Totals, evaluate


@dataclass
class SubFamily:
    """Toutes les sublimations qui donnent le même état (niveaux I, II, III...)."""

    state_id: int
    name: str
    desc: str
    limit: int
    kind: str                      # normal | epic | relic
    modeled: bool                  # effet chiffré par l'optimiseur
    applicable: bool               # ses conditions sont compatibles avec les options
    subs: list[Sublimation] = field(default_factory=list)
    same_levels: bool = False      # tous les niveaux donnent les mêmes effets (le niveau ne sert qu'au cumul max)
    in_build: int = 0              # niveau cumulé dans le build
    gain: float | None = None      # gain de score si on l'ajoute au build (niveau max)


def _kind(sub: Sublimation) -> str:
    return "epic" if sub.is_epic else "relic" if sub.is_relic else "normal"


def _applicable(data: GameData, opts: OptimizeOptions, state_id: int) -> tuple[bool, bool]:
    st = data.states.get(state_id)
    if st is None or not st.modeled:
        return False, True
    return True, any(static_condition(e.condition, opts) is not False for e in st.effects)


def build_levels(data: GameData, build: Build) -> dict[int, int]:
    subs = data.sub_by_id()
    out: dict[int, int] = defaultdict(int)
    for ch in build.slots.values():
        for sid in (ch.sublimation_id, ch.special_sublimation_id):
            if sid in subs:
                out[subs[sid].state_id] += subs[sid].state_level
    return out


def catalog(data: GameData, opts: OptimizeOptions, build: Build | None = None) -> list[SubFamily]:
    """Familles de sublimations, avec l'apport de chacune sur `build` (s'il est donné), les plus utiles d'abord."""
    fams: dict[int, SubFamily] = {}
    for sub in data.sublimations:
        if sub.is_normal and not sub.pattern:
            continue
        f = fams.get(sub.state_id)
        if f is None:
            st = data.states.get(sub.state_id)
            modeled, ok = _applicable(data, opts, sub.state_id)
            top = (st.limit or 5) if st else 1
            same = bool(st and st.effects and top > 1
                        and all(len(set(e.values[:top])) == 1 for e in st.effects))
            f = fams[sub.state_id] = SubFamily(
                state_id=sub.state_id, name=(st.name if st and st.name else sub.name(opts.lang)),
                desc=st.description if st else "", limit=st.limit if st else 0, kind=_kind(sub),
                modeled=modeled, applicable=ok, same_levels=same)
        f.subs.append(sub)
    base: Totals | None = None
    levels: dict[int, int] = {}
    if build is not None:
        base = evaluate(data, opts, build)
        levels = build_levels(data, build)
    for f in fams.values():
        f.subs.sort(key=lambda s: (s.state_level, s.id))
        f.in_build = levels.get(f.state_id, 0)
        if base is not None and build is not None and f.modeled and f.applicable:
            top = max(s.state_level for s in f.subs)
            t = evaluate(data, opts, build, extra_states={f.state_id: top})
            f.gain = round(t.score - base.score, 2)
    return sorted(fams.values(), key=lambda f: (-(f.gain if f.gain is not None else -1e9) if f.applicable else 1e9,
                                                not f.modeled, f.name))


@dataclass
class SubOption:
    sub: Sublimation | None        # None = retirer la sublimation
    build: Build
    totals: Totals
    delta: float


def _special_fits(it: Item, sub: Sublimation) -> bool:
    if sub.is_epic:
        return it.is_epic or PROP_EPIC_GEM in it.properties
    return it.is_relic or PROP_RELIC_GEM in it.properties


def sub_alternatives(data: GameData, opts: OptimizeOptions, build: Build, slot: Slot,
                     special: bool = False) -> tuple[list[SubOption], int]:
    """Sublimations possibles sur l'item de `slot`, triées par gain de score.

    Sublimation normale : seulement celles dont le motif tient dans les couleurs des châsses actuelles
    (le jaune sert de joker). Renvoie aussi le nombre de sublimations écartées faute de bonnes couleurs.
    """
    base = evaluate(data, opts, build)
    ch = build.slots.get(slot)
    it = data.item_by_id().get(ch.item_id) if ch else None
    if ch is None or it is None:
        return [], 0
    colors = [sh.color for sh in ch.shards]
    current = ch.special_sublimation_id if special else ch.sublimation_id
    taken = {c.special_sublimation_id for s, c in build.slots.items() if s is not slot} if special else set()
    out: list[SubOption] = []
    seen: set[tuple[int, int]] = set()   # (état, niveau) : une seule entrée par niveau
    misfit: set[tuple[int, int]] = set()
    cur_sub = data.sub_by_id().get(current) if current is not None else None
    if cur_sub is not None:
        seen.add((cur_sub.state_id, cur_sub.state_level))

    def add(sub: Sublimation | None) -> None:
        b = copy.deepcopy(build)
        if special:
            b.slots[slot].special_sublimation_id = sub.id if sub else None
        else:
            b.slots[slot].sublimation_id = sub.id if sub else None
        t = evaluate(data, opts, b)
        out.append(SubOption(sub, b, t, round(t.score - base.score, 2)))

    if current is not None:
        add(None)
    for sub in data.sublimations:
        if sub.id == current or sub.state_id in opts.excluded_subs or sub.id in taken:
            continue
        if special:
            if sub.is_normal or not _special_fits(it, sub):
                continue
        elif not sub.is_normal or not sub.pattern:
            continue
        key = (sub.state_id, sub.state_level)
        if key in seen:
            continue
        if not special and not pattern_offsets(colors, sub.pattern):
            misfit.add(key)
            continue
        seen.add(key)
        add(sub)
    other_colors = len({s for s, _ in misfit} - {s for s, _ in seen})   # par famille, pas par niveau
    out.sort(key=lambda o: -o.delta)
    return out, other_colors


def condition_failed(t: Totals, state_name: str) -> bool:
    """Sublimation « si la stat X est <= / >= v » posée alors que la condition n'est pas remplie (sans effet)."""
    return any(w.startswith(f"{state_name} :") and "condition non remplie" in w for w in t.warnings)


def fill_empty_subs(data: GameData, opts: OptimizeOptions, build: Build) -> tuple[Build, list[str]]:
    """Emplacements de sublimation restés vides (épique, relique, châsses) : on y met la meilleure sublimation
    chiffrée qui ne fait rien perdre. Le solveur les laisse vides quand aucune ne lui rapporte, mais autant en avoir une."""
    if opts.no_subs:
        return build, []
    added: list[str] = []
    for slot in list(build.slots):
        for special in (True, False):
            ch = build.slots[slot]
            if (ch.special_sublimation_id if special else ch.sublimation_id) is not None:
                continue
            if not special and not ch.shards:
                continue
            options, _ = sub_alternatives(data, opts, build, slot, special)
            usable = [o for o in options if o.sub is not None and o.delta >= -1e-6
                      and (st := data.states.get(o.sub.state_id)) is not None and st.modeled
                      and not condition_failed(o.totals, st.name)]
            if usable:
                best = usable[0]   # triées par gain décroissant
                build = best.build
                assert best.sub is not None
                added.append(best.sub.name(opts.lang))
    return build, added
