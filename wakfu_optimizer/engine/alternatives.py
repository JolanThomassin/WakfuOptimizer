"""Remplacement d'un item d'un build : liste des items qui conviennent, comparaison, échange."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from ..data.models import ELEMENTS, PROP_EPIC_GEM, PROP_RELIC_GEM, GameData, Item, Slot
from .options import Build, OptimizeOptions, ShardChoice, SlotChoice
from .stats import Totals, evaluate, spare_elements

RINGS = (Slot.LEFT_HAND, Slot.RIGHT_HAND)


@dataclass
class Alternative:
    item: Item
    build: Build
    totals: Totals
    delta: float          # écart de score (≈ % de valeur globale)


def _random_elements(data: GameData, it: Item, opts: OptimizeOptions, totals: Totals) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
    played = [e for e in opts.elements if e in ELEMENTS] or list(ELEMENTS)
    by_m = sorted(played, key=lambda e: totals.mastery.get(e, 0)) + spare_elements(data, opts, played)
    by_r = sorted(ELEMENTS, key=lambda e: totals.res_flat.get(e, 0))
    return ([tuple(by_m[:n]) for _v, n in it.random_mastery], [tuple(by_r[:n]) for _v, n in it.random_resistance])


def swap(data: GameData, opts: OptimizeOptions, build: Build, slot: Slot, it: Item, totals: Totals) -> Build | None:
    """Build où `it` remplace l'item de `slot` (châsses et sublimation conservées)."""
    items = data.item_by_id()
    b = copy.deepcopy(build)
    old = b.slots.get(slot)
    others = [items[c.item_id] for s, c in b.slots.items() if s is not slot and c.item_id in items]
    if any(o.id == it.id for o in others):
        return None
    if slot in RINGS:
        other_ring = b.slots.get(RINGS[1] if slot is RINGS[0] else RINGS[0])
        if other_ring and items.get(other_ring.item_id) and items[other_ring.item_id].name("fr") == it.name("fr"):
            return None
    dropped: list[Slot] = []
    if it.is_relic:
        dropped += [s for s, c in b.slots.items() if s is not slot and items.get(c.item_id) and items[c.item_id].is_relic]
    if it.is_epic:
        dropped += [s for s, c in b.slots.items() if s is not slot and items.get(c.item_id) and items[c.item_id].is_epic]
    if slot is Slot.FIRST_WEAPON and it.two_handed:
        dropped.append(Slot.SECOND_WEAPON)
    if slot is Slot.SECOND_WEAPON:
        w = b.slots.get(Slot.FIRST_WEAPON)
        if w and items.get(w.item_id) and items[w.item_id].two_handed:
            return None
    for s in dropped:
        b.slots.pop(s, None)
    mel, rel = _random_elements(data, it, opts, totals)
    ch = SlotChoice(slot=slot, item_id=it.id, mastery_elements=mel, resistance_elements=rel)
    if old is not None:
        runes = data.rune_by_id()
        for sh in old.shards if it.shard_max > 0 else []:
            lvl = runes[sh.rune_id].max_level_for_item(it.level) if sh.rune_id in runes else 0
            if sh.rune_id is not None and lvl <= 0:
                lvl = 1
            ch.shards.append(ShardChoice(sh.color, sh.rune_id, lvl if sh.rune_id is not None else 0))
        ch.sublimation_id = old.sublimation_id if it.shard_max > 0 else None
        sp = old.special_sublimation_id
        if sp is not None:
            sub = data.sub_by_id().get(sp)
            fits = sub is not None and ((it.is_epic or PROP_EPIC_GEM in it.properties) if sub.is_epic
                                        else (it.is_relic or PROP_RELIC_GEM in it.properties))
            if fits:
                ch.special_sublimation_id = sp
    b.slots[slot] = ch
    return b


def alternatives(data: GameData, opts: OptimizeOptions, build: Build, slot: Slot, limit: int = 40) -> list[Alternative]:
    """Items de l'emplacement, triés par gain de score si on les met à la place de l'actuel."""
    from .solver import item_pool  # import local : évite le cycle solver -> alternatives

    base = evaluate(data, opts, build)
    pool, _ = item_pool(data, opts, rarity_filter=False, lower=True)
    current = build.slots.get(slot)
    out: list[Alternative] = []
    for it in pool.get(slot, []):
        if current is not None and it.id == current.item_id:
            continue
        if it.level < opts.level - 40 and it.type_id not in (582, 611):
            continue
        b = swap(data, opts, build, slot, it, base)
        if b is None:
            continue
        t = evaluate(data, opts, b)
        out.append(Alternative(it, b, t, t.score - base.score))
    out.sort(key=lambda a: -a.delta)
    # un seul exemplaire par nom (raretés différentes du même item) : la meilleure version
    seen: set[str] = set()
    uniq = []
    for a in out:
        n = a.item.name("fr")
        if n in seen:
            continue
        seen.add(n)
        uniq.append(a)
    return uniq[:limit]
