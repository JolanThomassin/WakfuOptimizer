"""Items candidats : filtres de l'utilisateur, élargissement si un emplacement manque d'items, élagage par dominance.

Moins de candidats = modèle plus petit et passes plus rapides. Un item n'est retiré que si d'autres items du même
groupe (relique, épique, deux mains) sont au moins aussi bons sur toutes les stats utiles pour ces options
(`item_features`). Ajouter une stat au score : l'ajouter aussi à `item_features`, sinon l'élagage peut écarter
les items qui la donnent.
"""

from __future__ import annotations

from collections import defaultdict

from ..data.models import ELEMENTS, LEVELABLE_TYPES, SLOT_FR, GameData, Item, Slot
from .options import SECONDARY_MASTERIES, OptimizeOptions
from .shards import needs_no_secondary

PER_SLOT = 40   # candidats gardés par emplacement (groupe ordinaire ; reliques, épiques, deux mains : le quart)


def bracket_of(level: int, brackets: list[tuple[int, int]]) -> tuple[int, int]:
    for lo, hi in brackets:
        if lo <= level <= hi:
            return lo, hi
    return 1, level


def no_secondary_possible(data: GameData, opts: OptimizeOptions) -> bool:
    """Une sublimation « maîtrises secondaires <= 0 » (Ambition, Dénouement…) peut être placée."""
    for sid, st in data.states.items():
        if not needs_no_secondary(st) or sid in opts.excluded_subs:
            continue
        if sid in opts.forced_subs or not opts.no_subs and (st.confirmed or not opts.confirmed_subs_only):
            return True
    return False


def item_features(it: Item, opts: OptimizeOptions, L: int, no_sec: bool = False) -> list[int]:
    """Vecteur de caractéristiques utiles (plus = mieux) pour l'élagage par dominance.
    `no_sec` : garder aussi les items aux maîtrises secondaires basses (voir no_secondary_possible)."""
    st = it.stats_at(L)
    g = lambda k: int(st.get(k, 0))  # noqa: E731
    played = opts.played_elements()
    rm_v = sum(v for v, _ in it.random_mastery)
    rm_n = max([n for _, n in it.random_mastery], default=0)
    rr_v = sum(v for v, _ in it.random_resistance)
    rr_n = max([n for _, n in it.random_resistance], default=0)
    f = [g("ap"), g("mp"), g("range"), g("wp"), g("control")]
    f += [g(k) for k in ("lock", "dodge") if opts.utility.get(k, (0, 0))[0]]   # Tacle / Esquive comptés (tank)
    if opts.offense_weight > 0:
        # maîtrise de portée : elle s'ajoute à chaque sort, quel que soit l'élément (comme la maîtrise élémentaire),
        # donc comptée dans chaque élément joué. Exact pour la dominance : min(élém.) + portée = min(élém. + portée).
        # Mixte : moitié mêlée, moitié distance (tout est doublé pour rester en entiers).
        rng, k = 0, 1
        if opts.range == "mixed":
            rng, k = g("melee_mastery") + g("distance_mastery"), 2
        elif opts.range in ("melee", "distance"):
            rng = g(f"{opts.range}_mastery")
        f += [k * (g("elem_mastery") + g(f"{e}_mastery")) + rng for e in played]
        f += [rm_v, rm_n, g("dmg_pct")]
        if no_sec:   # maîtrises secondaires à 0 ou moins : plus elles sont basses, plus on a de marge
            f.append(-sum(g(k) for k in SECONDARY_MASTERIES))
        if opts.range == "best":   # la meilleure des deux : chacune est utile
            f += [g("melee_mastery"), g("distance_mastery")]
        if opts.crit:
            f += [g("crit_rate"), g("crit_mastery")]
        if opts.rear:
            f.append(g("rear_mastery"))
        if opts.berserk:
            f.append(g("berserk_mastery"))
        if opts.heal:
            f.append(g("heal_mastery"))
    if opts.offense_weight < 100 or opts.min_res_pct > 0 or opts.res_target > 0:
        f += [g("hp"), g("hp_pct")] + [g("elem_res") + g(f"{e}_res") for e in ELEMENTS] + [rr_v, rr_n]
    if opts.min_crit > 0 and not opts.crit:
        f.append(g("crit_rate"))
    if opts.willpower_weight:
        f.append(g("willpower"))
    if opts.min_block > 0 or opts.offense_weight < 100:   # Parade : compte dans la survie
        f.append(g("block"))
    return f


def _dominates(a: list[int], b: list[int]) -> bool:
    return all(x >= y for x, y in zip(a, b)) and a != b


def item_pool(data: GameData, opts: OptimizeOptions, rarity_filter: bool = True,
              lower: bool | None = None) -> tuple[dict[Slot, list[Item]], set[int]]:
    """Items autorisés par emplacement (filtres de l'utilisateur, sans élagage)."""
    L = opts.level
    lo, _ = bracket_of(L, data.brackets)
    lower = opts.lower_brackets if lower is None else lower
    forced = set(opts.forced_ids)
    excluded = set(opts.excluded_ids) - forced
    allowed_rar = set(opts.allowed_rarities)
    pool: dict[Slot, list[Item]] = defaultdict(list)
    seen_forced: set[int] = set()
    for it in data.items:
        is_pet = it.type_id in LEVELABLE_TYPES or Slot.PET in it.slots or Slot.MOUNT in it.slots
        # familiers / montures à monter (niveau 0 à 50) : portables à tout niveau ; les autres (porte-bonheur…)
        # ont un niveau requis comme n'importe quel item
        too_high = it.level > L and it.type_id not in LEVELABLE_TYPES
        if it.id in forced:
            seen_forced.add(it.id)
            if too_high:
                continue
        else:
            if it.id in excluded or it.is_hidden:
                continue
            if is_pet and not opts.include_pet_mount:
                continue
            if too_high or not is_pet and not lower and it.level < lo:
                continue
            if rarity_filter and int(it.rarity) not in allowed_rar:
                continue
            if opts.exclude_shop and it.is_shop:
                continue
            if opts.exclude_relic and it.is_relic or opts.exclude_epic and it.is_epic:
                continue
        for s in it.slots:
            pool[s].append(it)
    return pool, seen_forced


def select_candidates(data: GameData, opts: OptimizeOptions, per_slot: int = PER_SLOT) -> tuple[dict[Slot, list[Item]], list[str]]:
    L = opts.level
    warnings: list[str] = []
    forced = set(opts.forced_ids)
    by_id = data.item_by_id()
    for fid in forced:
        it = by_id.get(fid)
        if it is None:
            warnings.append(f"Item forcé {fid} introuvable dans les données.")
        elif it.level > L and it.type_id not in LEVELABLE_TYPES:
            warnings.append(f"Item forcé « {it.name(opts.lang)} » de niveau {it.level} > {L} : ignoré.")
    pool, _ = item_pool(data, opts)
    # Trop peu d'items ordinaires (hors relique/épique) avec les filtres choisis : on élargit
    # (raretés, puis tranches inférieures) pour que chaque emplacement puisse être rempli.
    widened: dict[str, list[str]] = {}
    for slot in Slot:
        if slot is Slot.SECOND_WEAPON or slot in (Slot.PET, Slot.MOUNT) and not opts.include_pet_mount:
            continue
        need = 4 if slot in (Slot.LEFT_HAND, Slot.RIGHT_HAND) else 1 if slot in (Slot.PET, Slot.MOUNT) else 2

        def ordinary(items: list[Item]) -> int:
            return len({i.name("fr") for i in items if not (i.is_relic or i.is_epic)})

        if ordinary(pool.get(slot, [])) >= need:
            continue
        for rar, lower, why in ((False, None, "toutes raretés"), (True, True, "tranches inférieures"),
                                (False, True, "toutes raretés et tranches inférieures")):
            p2, _ = item_pool(data, opts, rarity_filter=rar, lower=lower)
            if ordinary(p2.get(slot, [])) > ordinary(pool.get(slot, [])):
                have = {i.id for i in pool.get(slot, [])}
                pool[slot] = pool.get(slot, []) + [i for i in p2[slot] if i.id not in have]
                widened.setdefault(why, []).append(SLOT_FR[slot])
                if ordinary(pool[slot]) >= need:
                    break
    for why, names in widened.items():
        warnings.append(f"Peu d'items avec vos filtres pour {', '.join(names)} : recherche élargie ({why}).")

    out: dict[Slot, list[Item]] = {}
    no_sec = no_secondary_possible(data, opts)
    for slot, items in pool.items():
        feats = {it.id: item_features(it, opts, L, no_sec) for it in items}
        keep: list[Item] = []
        # groupes comparables : reliques, épiques, deux mains, items forcés à part
        groups: dict[tuple[bool, bool, bool], list[Item]] = defaultdict(list)
        for it in items:
            groups[(it.is_relic, it.is_epic, it.two_handed)].append(it)
        need = 2 if slot in (Slot.LEFT_HAND, Slot.RIGHT_HAND) else 1
        for key, grp in groups.items():
            survivors: list[Item] = []
            for a in grp:
                if a.id in forced:
                    survivors.append(a)
                    continue
                fa = feats[a.id]
                doms = {b.name("fr") for b in grp if b.id != a.id and b.name("fr") != a.name("fr") and _dominates(feats[b.id], fa)}
                # égalité parfaite : on garde le plus petit id
                ties = [b for b in grp if b.id < a.id and feats[b.id] == fa and b.name("fr") != a.name("fr")]
                if len(doms) + len(ties) < need:
                    survivors.append(a)
            cap = per_slot if key == (False, False, False) else max(8, per_slot // 4)
            if len(survivors) > cap:
                survivors = _top_k(survivors, feats, cap, forced)
            keep.extend(survivors)
        out[slot] = keep
    return out, warnings


def _top_k(items: list[Item], feats: dict[int, list[int]], k: int, forced: set[int]) -> list[Item]:
    dims = len(next(iter(feats.values()))) if feats else 0
    mx = [max(1, max(feats[i.id][d] for i in items)) for d in range(dims)]
    score = {i.id: sum(feats[i.id][d] / mx[d] for d in range(dims)) for i in items}
    chosen = {i.id for i in items if i.id in forced}
    for d in range(dims):  # les 2 meilleurs sur chaque stat (spécialistes PA, PM...)
        for i in sorted(items, key=lambda x: -feats[x.id][d])[:2]:
            if feats[i.id][d] > 0:
                chosen.add(i.id)
    for i in sorted(items, key=lambda x: -score[x.id]):
        if len(chosen) >= k:
            break
        chosen.add(i.id)
    return [i for i in items if i.id in chosen]
