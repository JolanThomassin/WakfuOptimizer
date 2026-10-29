"""Modèle CP-SAT : choix des items, caractéristiques, couleurs de châsses, runes et sublimations.

Un seul modèle, résolu en plusieurs passes :
  1. référence offensive  (maximise les dégâts seuls)       -> D*
  2. référence défensive  (maximise les PV effectifs seuls)  -> Def*
  3. objectif final       w_off × D/D* + w_def × Def/Def*
  4. builds alternatifs   (même objectif, ensemble d'items différent)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

try:  # OR-Tools quand il est installé ; sinon (navigateur) HiGHS derrière la même API
    if os.environ.get("WAKFU_SOLVER") == "highs":
        raise ImportError
    from ortools.sat.python import cp_model
except ImportError:
    from . import milp as cp_model  # type: ignore[no-redef]

from ..data.models import (
    ELEMENTS,
    LEVELABLE_TYPES,
    PROP_EPIC_GEM,
    PROP_RELIC_GEM,
    SHARD_SLOTS,
    SLOT_FR,
    Color,
    GameData,
    Item,
    Slot,
    Sublimation,
)
from .characteristics import BRANCH_FR, branch_points, char_lines, fill_unspent
from .options import NEUTRAL_COMBO_STATES, SECONDARY_MASTERIES, Build, OptimizeOptions, ShardChoice, SlotChoice
from .scoring import flat_for_pct, gradient, res_cap, res_need, res_pct, utility_table
from .shards import effect_targets, parse_stat_condition, rune_fits, static_condition
from .stats import Totals, evaluate, spare_elements
from .sublimations import fill_empty_subs

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, float], None]
RGB = (Color.RED, Color.GREEN, Color.BLUE)
RGBW = (Color.RED, Color.GREEN, Color.BLUE, Color.WHITE)
BIG = 10**7
MAX_ITER = 8
WARM_START = cp_model.__name__.endswith("milp")   # HiGHS : point de départ construit (voir Optimizer._warm_start)
# durée max d'une passe (s) : la durée choisie est un plafond, on vise la vitesse.
# HiGHS (navigateur) a besoin de passes plus longues pour garder la même qualité.
PASS_CAP = 10.0 if WARM_START else 6.0
MAX_TIME = 600.0         # durée maximale d'un calcul (s) ; l'interface propose 1, 3 ou 6 minutes
LIN_SCALE = 10**5        # coefficients entiers de l'objectif linéaire


class Cancelled(Exception):
    pass


@dataclass
class SolveResult:
    builds: list[Build] = field(default_factory=list)
    totals: list[Totals] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    status: str = ""
    message: str = ""
    diagnostics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    ref_damage: int = 0
    ref_defense: int = 0
    candidates: int = 0


# =====================================================================  candidats
def bracket_of(level: int, brackets: list[tuple[int, int]]) -> tuple[int, int]:
    for lo, hi in brackets:
        if lo <= level <= hi:
            return lo, hi
    return 1, level


def _features(it: Item, opts: OptimizeOptions, L: int) -> list[int]:
    """Vecteur de caractéristiques utiles (plus = mieux) pour l'élagage par dominance."""
    st = it.stats_at(L)
    g = lambda k: int(st.get(k, 0))  # noqa: E731
    played = [e for e in opts.elements if e in ELEMENTS] or list(ELEMENTS)
    rm_v = sum(v for v, _ in it.random_mastery)
    rm_n = max([n for _, n in it.random_mastery], default=0)
    rr_v = sum(v for v, _ in it.random_resistance)
    rr_n = max([n for _, n in it.random_resistance], default=0)
    f = [g("ap"), g("mp"), g("range"), g("wp"), g("control")]
    if opts.offense_weight > 0:
        f += [g("elem_mastery") + g(f"{e}_mastery") for e in played]
        f += [rm_v, rm_n, g("dmg_pct")]
        if opts.neutral_combo:   # maîtrises secondaires à 0 ou moins : plus elles sont basses, plus on a de marge
            f.append(-sum(g(k) for k in SECONDARY_MASTERIES))
        elif opts.range == "mixed":
            f.append(g("melee_mastery") + g("distance_mastery"))
        elif opts.range == "best":   # la meilleure des deux : chacune est utile
            f += [g("melee_mastery"), g("distance_mastery")]
        else:
            f.append(g("melee_mastery" if opts.range == "melee" else "distance_mastery"))
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
    if opts.min_block > 0:
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
        if it.id in forced:
            seen_forced.add(it.id)
            if it.level > L and not is_pet:
                continue
        else:
            if it.id in excluded or it.is_hidden:
                continue
            if is_pet and not opts.include_pet_mount:
                continue
            if not is_pet:
                if it.level > L:
                    continue
                if not lower and it.level < lo:
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


def select_candidates(data: GameData, opts: OptimizeOptions, per_slot: int = 40) -> tuple[dict[Slot, list[Item]], list[str]]:
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
    for slot, items in pool.items():
        feats = {it.id: _features(it, opts, L) for it in items}
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


# =====================================================================  modèle
class _Acc:
    """Accumulateur d'expressions linéaires par stat, avec bornes."""

    def __init__(self) -> None:
        self.terms: dict[str, list[tuple[int, Any]]] = defaultdict(list)
        self.const: dict[str, int] = defaultdict(int)
        self.ub: dict[str, int] = defaultdict(int)
        self.lb: dict[str, int] = defaultdict(int)

    def add_const(self, stat: str, v: int) -> None:
        self.const[stat] += v
        self.ub[stat] += v
        self.lb[stat] += v

    def add_exclusive(self, stat: str, pairs: list[tuple[int, Any]]) -> None:
        """Variables 0/1 dont au plus une vaut 1."""
        pairs = [(c, v) for c, v in pairs if c]
        if not pairs:
            return
        self.terms[stat].extend(pairs)
        self.ub[stat] += max(0, max(c for c, _ in pairs))
        self.lb[stat] += min(0, min(c for c, _ in pairs))

    def add_var(self, stat: str, coef: int, var: Any, lo: int, hi: int) -> None:
        if not coef:
            return
        self.terms[stat].append((coef, var))
        self.ub[stat] += max(coef * lo, coef * hi)
        self.lb[stat] += min(coef * lo, coef * hi)

    def expr(self, stat: str) -> Any:
        return sum(c * v for c, v in self.terms.get(stat, [])) + self.const.get(stat, 0)

    def bounds(self, stat: str) -> tuple[int, int]:
        return self.lb.get(stat, 0), self.ub.get(stat, 0)


@dataclass
class _Vars:
    x: dict[tuple[int, Slot], Any] = field(default_factory=dict)
    y_m: dict[tuple[int, Slot, int, str], Any] = field(default_factory=dict)
    y_r: dict[tuple[int, Slot, int, str], Any] = field(default_factory=dict)
    color: dict[tuple[Slot, int, Color], Any] = field(default_factory=dict)
    rune: dict[tuple[Slot, int, int, int], Any] = field(default_factory=dict)     # (slot, socket, rune_id, niveau)
    sub: dict[tuple[Slot, int, int], Any] = field(default_factory=dict)           # (slot, sub_id, offset)
    special: dict[int, Any] = field(default_factory=dict)                         # sub_id épique/relique
    chars: dict[str, Any] = field(default_factory=dict)
    usage: dict[int, Any] = field(default_factory=dict)
    sockets: dict[Slot, list[Color] | int] = field(default_factory=dict)


class BuildModel:
    """Construit le modèle CP-SAT pour un jeu d'options donné."""

    def __init__(self, data: GameData, opts: OptimizeOptions, candidates: dict[Slot, list[Item]],
                 shard_mode: str | None = None, skip_constraints: Iterable[str] = ()) -> None:
        self.data, self.opts, self.cand = data, opts, candidates
        self.shard_mode = shard_mode or opts.shard_mode
        self.skip = set(skip_constraints)
        self.m = cp_model.CpModel()
        self.v = _Vars()
        self.acc = _Acc()
        self.items = {it.id: it for its in candidates.values() for it in its}
        self.L = opts.level
        self.stat_var: dict[str, Any] = {}
        self.socketed: dict[Slot, Any] = {}
        self.stat_conds: list[tuple[Any, str]] = []   # (sublimation placée, condition sur une stat totale)
        self._build()

    # ------------------------------------------------------------------ items
    def _build(self) -> None:
        m, v, acc, L, opts = self.m, self.v, self.acc, self.L, self.opts
        base = self.data.game["base"]
        cls = self.data.classes.get(opts.class_key)
        acc.add_const("ap", int(base["ap"]))
        acc.add_const("mp", int(base["mp"]))
        acc.add_const("wp", cls.base_wp if cls else int(base["wp"]))
        acc.add_const("crit_rate", int(base["crit_rate"]))
        acc.add_const("hp", int(base["hp_flat"]) + int(base["hp_per_level"]) * L)
        for stat, val in (cls.passive_stats(L) if cls else {}).items():   # passif inné de la classe
            acc.add_const(stat, val)

        by_item: dict[int, list[Any]] = defaultdict(list)
        for slot, items in self.cand.items():
            pairs_by_stat: dict[str, list[tuple[int, Any]]] = defaultdict(list)
            slot_vars = []
            for it in items:
                xv = m.NewBoolVar(f"x_{it.id}_{slot.value}")
                v.x[(it.id, slot)] = xv
                slot_vars.append(xv)
                by_item[it.id].append(xv)
                for k, val in it.stats_at(L).items():
                    if int(val):
                        pairs_by_stat[k].append((int(val), xv))
            m.AddAtMostOne(slot_vars)
            for k, pairs in pairs_by_stat.items():
                acc.add_exclusive(k, pairs)
            self._random_effects(slot, items)

        for iid, xs in by_item.items():
            u = m.NewBoolVar(f"u_{iid}")
            m.Add(sum(xs) == u)
            v.usage[iid] = u
            if iid in opts.forced_ids:
                m.Add(u == 1)
        # Anneaux : jamais deux fois le même modèle (même nom)
        rings = defaultdict(list)
        for s in (Slot.LEFT_HAND, Slot.RIGHT_HAND):
            for it in self.cand.get(s, []):
                rings[it.name("fr")].append(v.x[(it.id, s)])
        for xs in rings.values():
            if len(xs) > 1:
                m.Add(sum(xs) <= 1)
        # Symétrie des anneaux : l'anneau 1 porte l'id le plus petit
        # (on se contente d'imposer que l'anneau 1 soit rempli si l'anneau 2 l'est)
        if self.cand.get(Slot.LEFT_HAND) and self.cand.get(Slot.RIGHT_HAND):
            m.Add(self.filled(Slot.LEFT_HAND) >= self.filled(Slot.RIGHT_HAND))
        # Deux mains => pas de seconde main
        self.two_handed = sum(v.x[(it.id, Slot.FIRST_WEAPON)] for it in self.cand.get(Slot.FIRST_WEAPON, []) if it.two_handed)
        m.Add(self.two_handed + self.filled(Slot.SECOND_WEAPON) <= 1)
        # 1 relique, 1 épique
        relics = [u for iid, u in v.usage.items() if self.items[iid].is_relic]
        epics = [u for iid, u in v.usage.items() if self.items[iid].is_epic]
        if relics:
            m.Add(sum(relics) <= 1)
        if epics:
            m.Add(sum(epics) <= 1)

        self._characteristics()
        if self.shard_mode != "none":
            self._shards()
        self._sublimations()
        self._derived()

    def filled(self, slot: Slot) -> Any:
        return sum(self.v.x[(it.id, slot)] for it in self.cand.get(slot, []))

    def _random_effects(self, slot: Slot, items: list[Item]) -> None:
        m, v, acc = self.m, self.v, self.acc
        played = [e for e in self.opts.elements if e in ELEMENTS] or list(ELEMENTS)
        ub_m: dict[str, list[tuple[int, Any]]] = defaultdict(list)
        ub_r: dict[str, list[tuple[int, Any]]] = defaultdict(list)
        best_m = max([sum(val for val, _ in it.random_mastery) for it in items], default=0)
        best_r = max([sum(val for val, _ in it.random_resistance) for it in items], default=0)
        for it in items:
            xv = v.x[(it.id, slot)]
            for k, (val, n) in enumerate(it.random_mastery):
                ys = []
                for e in played:
                    y = m.NewBoolVar(f"ym_{it.id}_{slot.value}_{k}_{e}")
                    v.y_m[(it.id, slot, k, e)] = y
                    m.Add(y <= xv)
                    ys.append(y)
                    ub_m[e].append((val, y))
                m.Add(sum(ys) == min(n, len(played)) * xv)
            for k, (val, n) in enumerate(it.random_resistance):
                ys = []
                for e in ELEMENTS:
                    y = m.NewBoolVar(f"yr_{it.id}_{slot.value}_{k}_{e}")
                    v.y_r[(it.id, slot, k, e)] = y
                    m.Add(y <= xv)
                    ys.append(y)
                    ub_r[e].append((val, y))
                m.Add(sum(ys) == n * xv)
        # bornes : dans un slot, au plus un item -> on borne par le max par élément
        for e, pairs in ub_m.items():
            acc.terms[f"rand_mastery_{e}"].extend(pairs)
            acc.ub[f"rand_mastery_{e}"] += best_m
        for e, pairs in ub_r.items():
            acc.terms[f"rand_res_{e}"].extend(pairs)
            acc.ub[f"rand_res_{e}"] += best_r

    # ------------------------------------------------------- caractéristiques
    def _characteristics(self) -> None:
        if not self.opts.optimize_characteristics:
            return
        game = self.data.game
        per_branch: dict[str, list[Any]] = defaultdict(list)
        for cl in char_lines(game):
            pts = branch_points(cl.branch, self.L, game)
            hi = pts if cl.max_points is None else min(pts, cl.max_points)
            if hi <= 0:
                continue
            var = self.m.NewIntVar(0, hi, f"c_{cl.key}")
            if self.opts.char_mode == "manual":
                self.m.Add(var == max(0, min(hi, int(self.opts.manual_chars.get(cl.key, 0)))))
            elif self.opts.apt_elem_res and cl.key == "intelligence.elem_res":
                self.m.Add(var == hi)
            self.v.chars[cl.key] = var
            per_branch[cl.branch].append(var)
            for stat, val in cl.per_point.items():
                self.acc.add_var(stat, val, var, 0, hi)
        for b, vars_ in per_branch.items():
            self.m.Add(sum(vars_) <= branch_points(b, self.L, game))

    # ----------------------------------------------------------------- châsses
    def _socket_colors(self, slot: Slot) -> list[Color] | int:
        if self.shard_mode == "mine":
            return self.opts.colors_for(slot)[:4]
        return max(0, min(4, self.opts.shard_count))

    def _shards(self) -> None:
        m, v, acc = self.m, self.v, self.acc
        runes = self.data.runes
        reqs = runes[0].level_requirements if runes else ()
        for slot in SHARD_SLOTS:
            items = self.cand.get(slot, [])
            if not items:
                continue
            spec = self._socket_colors(slot)
            n = len(spec) if isinstance(spec, list) else spec
            if n <= 0:
                continue
            # classes de niveau de rune selon le niveau de l'item porté
            classes: dict[int, list[Any]] = defaultdict(list)
            for it in items:
                if it.shard_max <= 0:
                    continue
                lvl = 0
                for i, req in enumerate(reqs, start=1):
                    if it.level >= req:
                        lvl = i
                classes[max(1, lvl)].append(v.x[(it.id, slot)])
            if not classes:
                continue
            v.sockets[slot] = spec
            cls_ind = {}
            for lvl, xs in classes.items():
                q = m.NewBoolVar(f"q_{slot.value}_{lvl}")
                m.Add(q == sum(xs))
                cls_ind[lvl] = q
            self.socketed[slot] = sum(cls_ind.values())
            colors = RGBW if self.opts.max_jokers > 0 else RGB
            for j in range(n):
                if isinstance(spec, list):
                    fixed = spec[j]
                else:
                    cs = [m.NewBoolVar(f"col_{slot.value}_{j}_{c.name}") for c in colors]
                    m.AddExactlyOne(cs)
                    for c, var in zip(colors, cs):
                        v.color[(slot, j, c)] = var
                    fixed = None
                socket_vars = []
                pairs_by_stat: dict[str, list[tuple[int, Any]]] = defaultdict(list)
                for r in runes:
                    if fixed is not None and not rune_fits(r, fixed):
                        continue
                    for lvl, q in cls_ind.items():
                        z = m.NewBoolVar(f"r_{slot.value}_{j}_{r.id}_{lvl}")
                        v.rune[(slot, j, r.id, lvl)] = z
                        m.Add(z <= q)
                        if fixed is None:
                            m.Add(z <= v.color[(slot, j, r.color)] + v.color.get((slot, j, Color.WHITE), 0))
                        socket_vars.append(z)
                        pairs_by_stat[r.stat].append((r.value(lvl, slot), z))
                if socket_vars:
                    m.AddAtMostOne(socket_vars)
                for stat, pairs in pairs_by_stat.items():
                    acc.add_exclusive(stat, pairs)
            whites = [v.color[(slot, j, Color.WHITE)] for j in range(n) if (slot, j, Color.WHITE) in v.color]
            if whites:
                m.Add(sum(whites) <= max(0, self.opts.max_jokers))

    def _color_ok(self, slot: Slot, j: int, wanted: Color) -> Any | bool:
        spec = self.v.sockets.get(slot)
        if isinstance(spec, list):
            return spec[j] == Color.WHITE or spec[j] == wanted
        c = self.v.color.get((slot, j, wanted))
        w = self.v.color.get((slot, j, Color.WHITE))
        if c is None:
            return False
        return c if w is None else c + w

    # ----------------------------------------------------------- sublimations
    def _sub_allowed(self, sub: Sublimation) -> tuple[bool, list[str]]:
        if sub.state_id in self.opts.excluded_subs:
            return False, []
        st = self.data.states.get(sub.state_id)
        forced = sub.state_id in self.opts.forced_subs
        if self.opts.no_subs and not forced:
            return False, []
        if st is None or not st.modeled:
            return forced, []   # effet non chiffré : placée seulement si l'utilisateur l'impose
        useful, dynamic = False, []
        for e in st.effects:
            s = static_condition(e.condition, self.opts)
            if s is None:
                dynamic.append(e.condition)
                useful = True
            elif s:
                useful = True
        return useful or forced, dynamic

    def _apply_dynamic(self, var: Any, conds: list[str]) -> None:
        for c in conds:
            if parse_stat_condition(c):   # appliquée dans _derived, quand toutes les stats sont connues
                self.stat_conds.append((var, c))
            if c == "two_handed":
                self.m.Add(var <= self.two_handed)
            elif c == "light_weapons":
                self.m.Add(var + self.two_handed + self.filled(Slot.SECOND_WEAPON) <= 1)

    def _sublimations(self) -> None:
        m, v, acc, opts = self.m, self.v, self.acc, self.opts
        level_terms: dict[int, list[tuple[int, Any]]] = defaultdict(list)
        normal = [s for s in self.data.sublimations if s.is_normal and len(s.pattern) >= 1]
        if self.shard_mode != "none":
            for slot, spec in v.sockets.items():
                n = len(spec) if isinstance(spec, list) else spec
                slot_vars = []
                for sub in normal:
                    ok, dyn = self._sub_allowed(sub)
                    k = len(sub.pattern)
                    if not ok or k > n:
                        continue
                    for o in range(0, n - k + 1):
                        conds = [self._color_ok(slot, o + j, sub.pattern[j]) for j in range(k)]
                        if any(c is False for c in conds):
                            continue
                        w = m.NewBoolVar(f"s_{slot.value}_{sub.id}_{o}")
                        for c in conds:
                            if c is not True:
                                m.Add(w <= c)
                        self._apply_dynamic(w, dyn)
                        v.sub[(slot, sub.id, o)] = w
                        slot_vars.append(w)
                        level_terms[sub.state_id].append((sub.state_level, w))
                if slot_vars:
                    m.Add(sum(slot_vars) <= self.socketed[slot])
        # épiques / reliques : un emplacement par objet épique/relique (+ objets « gemmables »)
        epic_cap = [u for iid, u in v.usage.items() if self.items[iid].is_epic or PROP_EPIC_GEM in self.items[iid].properties]
        relic_cap = [u for iid, u in v.usage.items() if self.items[iid].is_relic or PROP_RELIC_GEM in self.items[iid].properties]
        epic_vars, relic_vars = [], []
        for sub in self.data.sublimations:
            if sub.is_normal:
                continue
            if sub.is_epic and (opts.exclude_epic or not epic_cap) or sub.is_relic and (opts.exclude_relic or not relic_cap):
                continue
            ok, dyn = self._sub_allowed(sub)
            if not ok:
                continue
            w = m.NewBoolVar(f"sp_{sub.id}")
            self._apply_dynamic(w, dyn)
            v.special[sub.id] = w
            (epic_vars if sub.is_epic else relic_vars).append(w)
            level_terms[sub.state_id].append((sub.state_level, w))
        if epic_vars:
            m.Add(sum(epic_vars) <= sum(epic_cap))
        if relic_vars:
            m.Add(sum(relic_vars) <= sum(relic_cap))
        # sublimations imposées : niveau cumulé au moins égal au niveau demandé (1 par défaut : un exemplaire)
        self.forced_missing: list[int] = []
        for sid in opts.forced_subs:
            terms = level_terms.get(sid, [])
            if terms:
                m.Add(sum(c * w for c, w in terms) >= max(1, int(opts.forced_sub_levels.get(str(sid), 1))))
            else:
                self.forced_missing.append(sid)
        # niveaux d'état cumulés, plafonnés
        for sid, terms in level_terms.items():
            st = self.data.states.get(sid)
            if st is None or not st.modeled:
                continue
            total_ub = sum(c for c, _ in terms)
            lv = m.NewIntVar(0, total_ub, f"lv_{sid}")
            m.Add(lv == sum(c * w for c, w in terms))
            cap = st.limit or total_ub
            eff = m.NewIntVar(0, min(cap, total_ub), f"lve_{sid}")
            m.AddMinEquality(eff, [lv, cap])
            for e in st.effects:
                if static_condition(e.condition, opts) is False:
                    continue
                table = [0] + [e.value(k, self.L) for k in range(1, min(cap, total_ub) + 1)]
                if not any(table):
                    continue
                val = m.NewIntVar(min(table), max(table), f"se_{sid}_{e.stat}")
                m.AddElement(eff, table, val)
                for target in effect_targets(e):
                    acc.add_var(target, 1, val, min(table), max(table))

    # ---------------------------------------------------- stats dérivées, score
    def stat(self, name: str) -> Any:
        """Variable entière égale au total d'une stat."""
        if name not in self.stat_var:
            lo, hi = self.acc.bounds(name)
            var = self.m.NewIntVar(min(lo, 0) - 10, max(hi, 0) + 10, f"S_{name}")
            self.m.Add(var == self.acc.expr(name))
            self.stat_var[name] = var
        return self.stat_var[name]

    def _derived(self) -> None:
        m, opts, acc = self.m, self.opts, self.acc
        played = [e for e in opts.elements if e in ELEMENTS] or list(ELEMENTS)
        # --- maîtrise élémentaire utile = min sur les éléments joués
        mast = []
        mlo, mhi = BIG, -BIG
        for e in ELEMENTS:
            lo = acc.lb["elem_mastery"] + acc.lb[f"{e}_mastery"]
            hi = acc.ub["elem_mastery"] + acc.ub[f"{e}_mastery"] + acc.ub[f"rand_mastery_{e}"]
            expr = acc.expr("elem_mastery") + acc.expr(f"{e}_mastery") + acc.expr(f"rand_mastery_{e}")
            if opts.neutral_combo:   # Dénouement : la Maîtrise Critique devient de la Maîtrise Élémentaire
                clo, chi = acc.bounds("crit_mastery")
                lo, hi = lo + clo, hi + chi
                expr = expr + self.stat("crit_mastery")
            var = m.NewIntVar(lo - 10, hi + 10, f"M_{e}")
            m.Add(var == expr)
            self.stat_var[f"mastery_{e}"] = var
            if e in played:
                mast.append(var)
                mlo, mhi = min(mlo, lo - 10), max(mhi, hi + 10)
        mmin = m.NewIntVar(mlo, mhi, "M_min")
        m.AddMinEquality(mmin, mast)
        mtot_expr = mmin
        if opts.berserk:
            mtot_expr += self.stat("berserk_mastery")
        if opts.heal:
            mtot_expr += self.stat("heal_mastery")
        self.mtot = m.NewIntVar(-BIG, BIG, "M_tot")
        if opts.range == "mixed":
            # moyenne mêlée / distance, arrondie à l'inférieur comme dans stats.secondary_mastery
            both = self.stat("melee_mastery") + self.stat("distance_mastery")
            m.Add(2 * self.mtot <= 2 * mtot_expr + both)
            m.Add(2 * self.mtot >= 2 * mtot_expr + both - 1)
        elif opts.range == "best":
            lo = min(acc.bounds("melee_mastery")[0], acc.bounds("distance_mastery")[0]) - 10
            hi = max(acc.bounds("melee_mastery")[1], acc.bounds("distance_mastery")[1]) + 10
            sec = m.NewIntVar(lo, hi, "M_best")
            m.AddMaxEquality(sec, [self.stat("melee_mastery"), self.stat("distance_mastery")])
            m.Add(self.mtot == mtot_expr + sec)
        else:
            m.Add(self.mtot == mtot_expr + self.stat("melee_mastery" if opts.range == "melee" else "distance_mastery"))
        # --- résistances
        self.res = {}
        for e in ELEMENTS:
            lo = acc.lb["elem_res"] + acc.lb[f"{e}_res"]
            hi = acc.ub["elem_res"] + acc.ub[f"{e}_res"] + acc.ub[f"rand_res_{e}"]
            var = m.NewIntVar(lo - 10, hi + 10, f"R_{e}")
            m.Add(var == acc.expr("elem_res") + acc.expr(f"{e}_res") + acc.expr(f"rand_res_{e}"))
            self.res[e] = var
        # --- contraintes minimales
        mins = {"ap": opts.min_ap, "mp": opts.min_mp, "range": opts.min_range, "wp": opts.min_wp,
                "crit_rate": opts.min_crit, "control": opts.min_control, "block": opts.min_block}
        self.active_mins = {}
        for stat, val in mins.items():
            if val and stat not in self.skip:
                m.Add(self.stat(stat) >= val)
                self.active_mins[stat] = val
        # sublimations « si la stat X est <= / >= v » : si on la place, la condition doit être remplie
        for var, cond in self.stat_conds:
            kind, stat, v = parse_stat_condition(cond)  # type: ignore[misc]
            lo, hi = self.acc.bounds(stat)
            if kind == "le" and hi > v:
                m.Add(self.stat(stat) <= v + (hi - v) * (1 - var))
            elif kind == "ge" and lo < v:
                m.Add(self.stat(stat) >= v - (v - lo) * (1 - var))
        if opts.neutral_combo and "neutral" not in self.skip:
            for k in SECONDARY_MASTERIES:
                m.Add(self.stat(k) <= 0)
            self.active_mins["neutral"] = 0
        maxs = {"ap": opts.max_ap, "mp": opts.max_mp, "range": opts.max_range, "wp": opts.max_wp,
                "crit_rate": opts.max_crit, "block": opts.max_block}
        for stat, val in maxs.items():
            if val and stat not in self.skip:
                m.Add(self.stat(stat) <= val)
        if opts.min_res_pct > 0 and "res" not in self.skip:
            need = flat_for_pct(opts.min_res_pct)
            for e in ELEMENTS:
                m.Add(self.res[e] >= need)
            self.active_mins["res"] = opts.min_res_pct
        self._features()

    def _features(self) -> None:
        """Variables linéaires utilisées par l'objectif (voir scoring.log_score)."""
        m, opts = self.m, self.opts
        f: dict[str, Any] = {"mtot": self.mtot}
        if opts.crit:
            t = m.NewIntVar(-BIG, 100, "T")
            m.AddMinEquality(t, [self.stat("crit_rate"), 100])
            f["crit"] = t
            f["crit_mastery"] = 0 if opts.neutral_combo else self.stat("crit_mastery")
        if opts.rear and not opts.heal:
            f["rear_mastery"] = self.stat("rear_mastery")
        f["dmg_pct"] = self.stat("dmg_pct")
        f["hp"] = self.stat("hp")
        f["hp_pct"] = self.stat("hp_pct")
        capped = []
        cap = res_cap(opts)   # au-delà du maximum voulu, la résistance ne rapporte plus rien
        for e in ELEMENTS:
            c = m.NewIntVar(-BIG, cap, f"Rc_{e}")
            m.AddMinEquality(c, [self.res[e], cap])
            capped.append(c)
        need = res_need(opts)
        if need:
            shorts = []
            for e in ELEMENTS:
                sh = m.NewIntVar(0, need + BIG, f"short_{e}")
                m.AddMaxEquality(sh, [need - self.res[e], 0])
                shorts.append(sh)
            f["res_short"] = sum(shorts)
        # moyenne des quatre résistances (plafonnées) : pas besoin d'un équilibre parfait,
        # chaque élément est tiré vers la résistance visée par la pénalité res_short
        f["res4"] = sum(capped)
        for stat, (_v, cap) in utility_table(opts).items():
            capped_u = m.NewIntVar(-100, max(0, cap), f"cap_{stat}")
            m.AddMinEquality(capped_u, [self.stat(stat), cap])
            pos = m.NewIntVar(0, max(0, cap), f"pos_{stat}")
            m.AddMaxEquality(pos, [capped_u, 0])
            f[stat] = pos
        self.feat = f

    def maximize(self, expr: Any) -> None:
        clear = getattr(self.m, "clear_objective", None) or getattr(self.m, "ClearObjective", None)
        if clear is not None:
            clear()
        self.m.Maximize(expr)

    def set_linear_objective(self, grad: dict[str, float]) -> None:
        """Objectif linéaire : somme des variables pondérées par le gradient du score."""
        terms = []
        for k, var in self.feat.items():
            g = grad.get("res", 0.0) / 4 if k == "res4" else grad.get(k, 0.0)
            c = int(round(g * LIN_SCALE))
            if c:
                terms.append(c * var)
        self.maximize(sum(terms) if terms else 0)

    # --------------------------------------------------------------- extraction
    def extract(self, solver: cp_model.CpSolver) -> Build:
        v, opts = self.v, self.opts
        val = solver.BooleanValue
        b = Build()
        runes = {r.id: r for r in self.data.runes}
        for (iid, slot), xv in v.x.items():
            if not val(xv):
                continue
            it = self.items[iid]
            ch = SlotChoice(slot=slot, item_id=iid)
            for k, (_, n) in enumerate(it.random_mastery):
                els = [e for e in ELEMENTS if (iid, slot, k, e) in v.y_m and val(v.y_m[(iid, slot, k, e)])]
                played = [e for e in opts.elements if e in ELEMENTS]
                rest = [e for e in played if e not in els] + [e for e in spare_elements(self.data, opts, played) if e not in els]
                els += rest[: max(0, n - len(els))]
                ch.mastery_elements.append(tuple(els[:n]))
            for k, (_, n) in enumerate(it.random_resistance):
                ch.resistance_elements.append(tuple(e for e in ELEMENTS if val(v.y_r[(iid, slot, k, e)])))
            spec = v.sockets.get(slot)
            n_sockets = len(spec) if isinstance(spec, list) else (spec or 0)
            for j in range(n_sockets):
                if isinstance(spec, list):
                    col = spec[j]
                else:
                    col = next((c for c in RGBW if (slot, j, c) in v.color and val(v.color[(slot, j, c)])), Color.RED)
                shard = ShardChoice(color=col)
                for (s2, j2, rid, lvl), z in v.rune.items():
                    if s2 is slot and j2 == j and val(z):
                        shard.rune_id, shard.rune_level = rid, lvl
                ch.shards.append(shard)
            for (s2, sid, _o), w in v.sub.items():
                if s2 is slot and val(w):
                    ch.sublimation_id = sid
            b.slots[slot] = ch
        # sublimations épiques / reliques : enchâssées dans l'objet correspondant
        subs = {s.id: s for s in self.data.sublimations}
        for sid, w in v.special.items():
            if not val(w):
                continue
            sub = subs[sid]
            for ch in b.slots.values():
                it = self.items[ch.item_id]
                fits = (it.is_epic or PROP_EPIC_GEM in it.properties) if sub.is_epic else (it.is_relic or PROP_RELIC_GEM in it.properties)
                if fits and ch.special_sublimation_id is None:
                    ch.special_sublimation_id = sid
                    break
        for key, var in v.chars.items():
            n = solver.Value(var)
            if n:
                b.characteristics[key] = int(n)
        _ = runes
        return b

    def add_nogood(self, build: Build) -> None:
        us = [self.v.usage[iid] for iid in build.item_ids() if iid in self.v.usage]
        if us:
            self.m.Add(sum(us) <= len(us) - 1)

    def hint(self, solver: cp_model.CpSolver) -> None:
        self.m.ClearHints()
        for xv in self.v.x.values():
            self.m.AddHint(xv, solver.BooleanValue(xv))

    def hint_from_items(self, small: BuildModel, solver: cp_model.CpSolver) -> None:
        """Indices d'un build complet et valide, à partir d'un modèle sans châsses (`small`) :
        mêmes items, aptitudes et sublimations épiques/reliques ; châsses d'une seule couleur, sans rune
        ni sublimation (sauf celles imposées, laissées libres)."""
        v, val = self.v, solver.Value
        played = [e for e in self.opts.elements if e in ELEMENTS] or list(ELEMENTS)
        m = self.m
        m.ClearHints()
        x = {k: val(small.v.x[k]) for k in v.x}
        for k, var in v.x.items():
            m.AddHint(var, x[k])
        for k, var in v.chars.items():
            if k in small.v.chars:
                m.AddHint(var, val(small.v.chars[k]))
        for (iid, slot, k, e), var in v.y_m.items():
            n = self.items[iid].random_mastery[k][1]
            m.AddHint(var, int(x[(iid, slot)] and e in played[:min(n, len(played))]))
        for (iid, slot, k, e), var in v.y_r.items():
            n = self.items[iid].random_resistance[k][1]
            m.AddHint(var, int(x[(iid, slot)] and e in ELEMENTS[:n]))
        forced = set(self.opts.forced_subs)
        subs = {s.id: s for s in self.data.sublimations}
        if not forced:   # avec des sublimations imposées, le solveur choisit les couleurs qui leur conviennent
            for (slot, j, c), var in v.color.items():
                m.AddHint(var, int(c == Color.RED))
            for var in v.rune.values():
                m.AddHint(var, 0)
        for (slot, sid, o), var in v.sub.items():
            if subs[sid].state_id not in forced:
                m.AddHint(var, 0)
        for sid, var in v.special.items():
            if sid in small.v.special:
                m.AddHint(var, val(small.v.special[sid]))


# =====================================================================  pilote
class Optimizer:
    def __init__(self, data: GameData, opts: OptimizeOptions, progress: ProgressFn | None = None,
                 cancel: threading.Event | None = None) -> None:
        self.data, self.opts = data, opts
        self.progress = progress or (lambda msg, frac: None)
        self.cancel = cancel or threading.Event()
        self._solver: cp_model.CpSolver | None = None
        self._lock = threading.Lock()

    def stop(self) -> None:
        self.cancel.set()
        with self._lock:
            if self._solver is not None:
                try:
                    self._solver.stop_search()
                except AttributeError:  # anciennes versions d'OR-Tools
                    self._solver.StopSearch()

    def _solve(self, bm: BuildModel, seconds: float) -> tuple[int, cp_model.CpSolver]:
        if self.cancel.is_set():
            raise Cancelled()
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(0.5, seconds)
        solver.parameters.num_search_workers = max(1, self.opts.workers)
        solver.parameters.random_seed = 42
        solver.parameters.relative_gap_limit = 0.001
        with self._lock:
            self._solver = solver
        status = solver.Solve(bm.m)
        with self._lock:
            self._solver = None
        if self.cancel.is_set():
            raise Cancelled()
        return status, solver

    def _res_unreachable(self, res: SolveResult, cand: dict[Slot, list[Item]], tot: Totals, t0: float,
                         budget: float) -> SolveResult:
        """Résistance visée impossible : on cherche la meilleure résistance atteignable (sur l'élément le plus faible)."""
        opts = self.opts
        self.progress("Résistance visée non atteinte : recherche du maximum possible…", 0.97)
        got = min(tot.res_pct.values())
        best = got
        try:
            probe = BuildModel(self.data, opts, cand, skip_constraints={"res"})
            if WARM_START:
                self._warm_start(probe, cand, opts, budget)
            rmin = probe.m.NewIntVar(-BIG, BIG, "Rmin_brut")
            probe.m.AddMinEquality(rmin, [probe.res[e] for e in ELEMENTS])
            probe.maximize(rmin)
            st, sv = self._solve(probe, max(5.0, min(20.0, budget - (time.monotonic() - t0))))
            if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                best = max(got, res_pct(sv.Value(rmin)))
        except Cancelled:
            pass
        res.status = "aucune solution"
        res.diagnostics = [
            f"Résistance visée {opts.res_target} % (± {opts.res_tol}) impossible avec ces réglages : au mieux {best} % "
            "sur l'élément le plus faible.",
            "Baissez la résistance minimum, autorisez plus de raretés ou les tranches inférieures, ou assouplissez "
            "les autres contraintes (PA, PM, items forcés…).",
        ]
        res.message = "Aucun build ne respecte la résistance visée — " + res.diagnostics[0]
        res.elapsed = time.monotonic() - t0
        return res

    def _warm_start(self, bm: BuildModel, cand: dict[Slot, list[Item]], opts: OptimizeOptions, budget: float) -> None:
        """HiGHS trouve mal un premier build quand il doit aussi placer châsses, runes et sublimations,
        mais améliore très vite un build qu'on lui donne. On en construit un : items choisis sans châsses,
        puis on complète le modèle entier avec ces items fixés. Les passes suivantes partent de là."""
        self.progress("Recherche d'un premier build…", 0.04)
        small = BuildModel(self.data, opts, cand, shard_mode="none")
        small.set_linear_objective(gradient(_initial_point(opts), opts))
        st, sv = self._solve(small, min(8.0, budget / 8))
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return   # infaisable ou trop lent : la passe normale s'en chargera (et le diagnostic)
        bm.hint_from_items(small, sv)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = min(6.0, budget / 10)
        solver.parameters.fix_variables_to_their_hinted_value = True
        solver.Solve(bm.m)   # en cas de succès, le build sert de point de départ (milp.CpModel.incumbent)
        bm.m.ClearHints()

    def _ticker(self, base: float, span: float, seconds: float, msg: str) -> threading.Event:
        """Fait avancer la barre de progression pendant une résolution."""
        stop = threading.Event()
        t0 = time.monotonic()

        def loop() -> None:
            while not stop.wait(0.4):
                frac = min(1.0, (time.monotonic() - t0) / max(0.5, seconds))
                self.progress(msg, base + span * frac)

        try:
            threading.Thread(target=loop, daemon=True).start()
        except RuntimeError:  # pas de fils dans le navigateur
            self.progress(msg, base)
        return stop

    def run(self) -> SolveResult:
        """Linéarisation successive : on maximise le gradient du score autour du build courant,
        on évalue exactement le build obtenu, puis on recommence autour de ce nouveau point."""
        t0 = time.monotonic()
        opts = self.opts
        res = SolveResult()
        budget = max(10.0, min(opts.time_limit, MAX_TIME))
        res.warnings.extend(opts.normalize())   # min > max, % hors bornes : corrigés et signalés
        if opts.neutral_combo:
            opts.forced_subs = tuple(dict.fromkeys(opts.forced_subs + NEUTRAL_COMBO_STATES))
            opts.excluded_subs = tuple(s for s in opts.excluded_subs if s not in NEUTRAL_COMBO_STATES)
            if opts.exclude_epic:
                res.warnings.append("Combo Neutralité : Dénouement est une sublimation épique, décochez « Exclure les épiques ».")
        self.progress("Sélection des items candidats…", 0.01)
        cand, warnings = select_candidates(self.data, opts)
        res.warnings.extend(warnings)
        res.candidates = sum(len(v) for v in cand.values())
        if opts.min_control > 0 and not opts.optimize_characteristics:
            res.warnings.append("Aucun équipement ne donne de Contrôle : activez les caractéristiques (Majeur).")
        log.info("%d items candidats (%s)", res.candidates, {s.value: len(v) for s, v in cand.items()})
        try:
            self.progress("Construction du modèle…", 0.03)
            bm = BuildModel(self.data, opts, cand)
            for sid in bm.forced_missing:
                st = self.data.states.get(sid)
                res.warnings.append(f"Sublimation imposée « {st.name if st else sid} » impossible à placer "
                                    "(pas de châsses, ou épique/relique sans objet compatible) : ignorée.")
            point = _initial_point(opts)
            if WARM_START:
                self._warm_start(bm, cand, opts, budget)
            best: tuple[float, Build, Totals] | None = None
            seen: set[tuple[Any, ...]] = set()
            # le temps est réparti entre les passes : plus de temps = chaque passe va plus loin
            per_iter = min(PASS_CAP, budget / MAX_ITER)
            status_opt = True
            stale = 0
            for it in range(MAX_ITER):
                base = 0.05 + 0.9 * it / MAX_ITER
                remaining = budget - (time.monotonic() - t0)
                if remaining < 1.0 and best is not None:
                    break
                limit = max(1.0, min(per_iter * (1.5 if it == 0 else 1.0), remaining))
                bm.set_linear_objective(gradient(point, opts))
                tick = self._ticker(base, 0.9 / MAX_ITER, limit, f"Optimisation (passe {it + 1}/{MAX_ITER})…")
                try:
                    st, sv = self._solve(bm, limit)
                    remaining = budget - (time.monotonic() - t0)
                    if best is None and st == cp_model.UNKNOWN and remaining > 1.0:
                        # machine lente (navigateur) : aucune solution encore, on continue avec le temps restant
                        self.progress("Recherche d'un premier build (machine lente)…", base)
                        st, sv = self._solve(bm, remaining)
                finally:
                    tick.set()
                if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    if best is None:
                        return self._infeasible(res, cand, st, t0)
                    break
                status_opt = status_opt and st == cp_model.OPTIMAL
                b = bm.extract(sv)
                tot = evaluate(self.data, opts, b)
                key = (tuple(sorted(b.item_ids())), tuple(sorted(b.characteristics.items())))
                log.info("passe %d : score %.2f (%s)", it + 1, tot.score, "optimal" if st == cp_model.OPTIMAL else "réalisable")
                if best is None or tot.score > best[0] + 0.25:
                    stale = 0
                else:
                    stale += 1
                if best is None or tot.score > best[0]:
                    best = (tot.score, b, tot)
                # même build qu'avant : convergé seulement si la passe a fini (sinon elle a manqué de temps)
                # deux passes sans progrès (après au moins trois passes) : on s'arrête, inutile d'attendre
                if key in seen and st == cp_model.OPTIMAL or stale >= 2 and it >= 2:
                    break
                seen.add(key)
                bm.hint(sv)
                # amortissement : on se rapproche du nouveau point sans y sauter complètement
                f = tot.features
                point = f if it == 0 else {k: 0.5 * point[k] + 0.5 * f[k] for k in point}
            assert best is not None
            out_of_time = time.monotonic() - t0 >= budget - 2
            res.status = "optimal" if status_opt else "bon build (durée max atteinte)" if out_of_time else "bon build"
            score, b, tot = best
            b, added = fill_empty_subs(self.data, opts, b)
            if opts.char_mode != "manual" and opts.optimize_characteristics:
                filled = fill_unspent(b.characteristics, opts.level, self.data.game, opts.range)
                added += [] if filled == b.characteristics else ["aptitudes"]
                b.characteristics = filled
            if added:
                tot = evaluate(self.data, opts, b)
                score = tot.score
            if opts.res_target > 0 and min(tot.res_pct.values()) < opts.res_target - opts.res_tol:
                # résistance minimum non atteinte : on n'affiche pas un build qui ne respecte pas la demande
                return self._res_unreachable(res, cand, tot, t0, budget)
            b.status = res.status
            b.solver_score = score
            res.builds.append(b)
            res.totals.append(tot)
            res.scores.append(score)
        except Cancelled:
            res.status = "annulé"
            res.message = "Calcul annulé."
            res.elapsed = time.monotonic() - t0
            return res
        res.elapsed = time.monotonic() - t0
        res.message = f"{res.status} en {res.elapsed:.1f} s ({res.candidates} items candidats)"
        self.progress("Terminé", 1.0)
        return res

    # ----------------------------------------------------------- diagnostic
    def _infeasible(self, res: SolveResult, cand: dict[Slot, list[Item]], status: int, t0: float) -> SolveResult:
        res.status = "aucune solution" if status == cp_model.INFEASIBLE else "pas de solution trouvée dans le temps imparti"
        if status != cp_model.INFEASIBLE:
            res.diagnostics = ["Le calcul n'a pas eu assez de temps : réduisez les contraintes ou relancez."]
            res.message = res.status + " — " + res.diagnostics[0]
            res.elapsed = time.monotonic() - t0
            return res
        self.progress("Recherche de la contrainte bloquante…", 0.9)
        diag: list[str] = []
        missing = [s for s in Slot if s not in (Slot.PET, Slot.MOUNT) and not cand.get(s)]
        if missing:
            diag.append("Aucun item disponible pour : " + ", ".join(s.value for s in missing))
        forced = [self.data.item_by_id().get(i) for i in self.opts.forced_ids]
        by_slot = defaultdict(list)
        for it in forced:
            if it is not None:
                by_slot[it.slots[0]].append(it.name(self.opts.lang))
        for s, names in by_slot.items():
            if len(names) > (2 if s in (Slot.LEFT_HAND, Slot.RIGHT_HAND) else 1):
                diag.append(f"Trop d'items forcés pour {s.value} : {', '.join(names)}")
        labels = {"ap": "PA", "mp": "PM", "range": "Portée", "wp": "PW", "crit_rate": "% Critique", "block": "% Parade",
                  "control": "Contrôle", "res": "% Résistance"}
        probe = BuildModel(self.data, self.opts, cand, shard_mode="none")
        for stat, val in probe.active_mins.items():
            if self.cancel.is_set():
                break
            relaxed = BuildModel(self.data, self.opts, cand, shard_mode=self.opts.shard_mode, skip_constraints={stat})
            if stat == "neutral":
                relaxed.maximize(-sum(relaxed.stat(k) for k in SECONDARY_MASTERIES))
            else:
                relaxed.maximize(relaxed.res["fire"] if stat == "res" else relaxed.stat(stat))
            try:
                st, sv = self._solve(relaxed, 4.0)
            except Cancelled:
                break
            if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                if stat == "neutral":
                    diag.append("Contrainte bloquante : combo Neutralité (maîtrises secondaires à 0 ou moins) "
                                "impossible avec les autres contraintes.")
                    continue
                best = sv.Value(relaxed.stat(stat)) if stat != "res" else None
                extra = f" (maximum atteignable avec les autres contraintes : {best})" if best is not None else ""
                diag.append(f"Contrainte bloquante : {labels.get(stat, stat)} ≥ {val}{extra}")
        if self.opts.forced_subs:
            diag.append("Vérifiez aussi les sublimations imposées (onglet Sublimations) : leurs couleurs ou "
                        "leurs conditions peuvent bloquer.")
        maxs = {"PA": self.opts.max_ap, "PM": self.opts.max_mp, "Portée": self.opts.max_range, "PW": self.opts.max_wp,
                "% Critique": self.opts.max_crit, "% Parade": self.opts.max_block}
        for lab, val in maxs.items():
            if val:
                diag.append(f"Maximum imposé : {lab} ≤ {val}")
        if not diag:
            diag.append("Combinaison de contraintes impossible : assouplissez plusieurs minimums ou autorisez les tranches inférieures.")
        res.diagnostics = diag
        res.message = res.status + " — " + " ; ".join(diag)
        res.elapsed = time.monotonic() - t0
        return res


def _initial_point(opts: OptimizeOptions) -> dict[str, float]:
    """Point de départ réaliste pour la première linéarisation."""
    L = opts.level
    return {"mtot": 8.0 * L + 100, "crit": 30.0 if opts.crit else 0.0, "crit_mastery": L / 2 if opts.crit else 0.0,
            "rear_mastery": float(L) if opts.rear else 0.0, "dmg_pct": 10.0, "hp": 25.0 * L + 50, "hp_pct": 30.0,
            "res": 3.0 * L, "ap": 0.0, "mp": 0.0, "range": 0.0, "wp": 0.0, "res_short": 0.0}


def optimize(data: GameData, opts: OptimizeOptions, progress: ProgressFn | None = None) -> SolveResult:
    return Optimizer(data, opts, progress).run()


__all__ = ["Optimizer", "SolveResult", "optimize", "select_candidates", "BuildModel", "Cancelled", "BRANCH_FR"]
