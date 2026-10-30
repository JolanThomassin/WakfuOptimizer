"""Modèle CP-SAT d'un build : items, aptitudes, couleurs de châsses, runes, sublimations, stats dérivées.

`BuildModel` construit les variables et les contraintes ; l'objectif (linéaire) est posé par le pilote
(solver.Optimizer) avec `set_linear_objective`, à partir des variables du score (features.model_features).

Sections : items -> aptitudes -> châsses / runes -> sublimations -> stats dérivées et contraintes (_derived)
-> extraction d'un build et indices (warm start). Chaque stat totale est une expression linéaire accumulée
dans `_Acc` (bornes comprises) ; `stat(nom)` en fait une variable entière.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ..data.models import ELEMENTS, PROP_EPIC_GEM, PROP_RELIC_GEM, SHARD_SLOTS, Color, GameData, Item, Slot, Sublimation
from .archetypes import apt_forced, apt_profile, profile_keys
from .backend import cp_model
from .characteristics import branch_points, char_lines
from .features import BIG, linear_objective, model_features
from .options import SECONDARY_MASTERIES, Build, OptimizeOptions, ShardChoice, SlotChoice
from .scoring import flat_for_pct
from .shards import CRIT_TO_ELEM, effect_targets, parse_stat_condition, rune_fits, static_condition
from .stats import spare_elements

RGB = (Color.RED, Color.GREEN, Color.BLUE)
RGBW = (Color.RED, Color.GREEN, Color.BLUE, Color.WHITE)


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
        self.convert: Any = None    # Dénouement placé (0/1) : Maîtrise Critique convertie en Maîtrise Élémentaire
        self.crit_conv: Any = None  # Maîtrise Critique convertie
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
        played = self.opts.played_elements()
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
        manual = self.opts.char_mode == "manual"
        allowed = profile_keys(self.opts)   # lignes qui ont un sens pour l'archétype (voir archetypes.apt_profile)
        forced = apt_forced(self.opts)      # lignes au maximum d'office (PA en Majeur, % Critique d'un DPS…)
        # points des lignes imposées : au maximum, dans l'ordre du profil, tant que la branche en a (bas niveau)
        maxes = {cl.key: cl.max_points for cl in char_lines(game)}
        forced_pts: dict[str, int] = {}
        for branch, lines in apt_profile(self.opts).items():
            left = branch_points(branch, self.L, game)
            for key in (f"{branch}.{line}" for line in lines):
                if key in forced and key in maxes:
                    mx = maxes[key]
                    forced_pts[key] = n = left if mx is None else min(left, mx)
                    left -= n
        per_branch: dict[str, list[Any]] = defaultdict(list)
        for cl in char_lines(game):
            pts = branch_points(cl.branch, self.L, game)
            hi = pts if cl.max_points is None else min(pts, cl.max_points)
            if hi <= 0 or not manual and cl.key not in allowed:
                continue
            var = self.m.NewIntVar(0, hi, f"c_{cl.key}")
            if manual:
                self.m.Add(var == max(0, min(hi, int(self.opts.manual_chars.get(cl.key, 0)))))
            elif cl.key in forced_pts:
                self.m.Add(var == min(hi, forced_pts[cl.key]))
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
        if self.opts.confirmed_subs_only and not forced and not (st and st.confirmed):
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
        for c in (part for cond in conds for part in cond.split("&")):
            if parse_stat_condition(c):   # appliquée dans _derived, quand toutes les stats sont connues
                self.stat_conds.append((var, c))
            if c == "no_secondary":   # maîtrises secondaires <= 0 si on la place (Neutralité, Ambition, Dénouement…)
                self.stat_conds += [(var, f"stat_le:{k}:0") for k in SECONDARY_MASTERIES]
            if c == "two_handed":
                self.m.Add(var <= self.two_handed)
            elif c == "light_weapons":
                self.m.Add(var + self.two_handed + self.filled(Slot.SECOND_WEAPON) <= 1)

    def _item_subs(self) -> None:
        """Sublimations à poser sur un item forcé (onglet Items) : normale dans ses châsses, épique / relique dans
        l'item s'il peut la recevoir. `item_sub_missing` : (item, état) impossibles, signalés et ignorés."""
        m, v = self.m, self.v
        subs = {s.id: s for s in self.data.sublimations}
        self.item_sub_missing: list[tuple[int, int]] = []
        for key, states in self.opts.forced_item_subs.items():
            iid = int(key)
            it = self.items.get(iid)
            places = [(slot, x) for (i, slot), x in v.x.items() if i == iid]
            if it is None or not places:
                continue
            for sid in states:
                kinds = [s for s in self.data.sublimations if s.state_id == sid]
                if any(s.is_normal for s in kinds):
                    for slot, x in places:   # posée dans l'emplacement où l'item finit (anneaux : l'un ou l'autre)
                        ws = [w for (s2, sub_id, _o), w in v.sub.items() if s2 is slot and subs[sub_id].state_id == sid]
                        if not ws:
                            self.item_sub_missing.append((iid, sid))
                            break
                        m.Add(sum(ws) >= x)
                    continue
                fits = any((it.is_epic or PROP_EPIC_GEM in it.properties) if s.is_epic
                           else (it.is_relic or PROP_RELIC_GEM in it.properties) for s in kinds)
                if not fits or not any(s.id in v.special for s in kinds):
                    self.item_sub_missing.append((iid, sid))

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
        self._item_subs()
        # niveau cumulé jamais au-delà du maximum de l'état (niveaux perdus), sauf si l'utilisateur en impose plus
        imposed = {sid for states in opts.forced_item_subs.values() for sid in states}
        for sid, terms in level_terms.items():
            st = self.data.states.get(sid)
            if st is not None and st.limit and sid not in imposed and sum(c for c, _ in terms) > st.limit:
                m.Add(sum(c * w for c, w in terms) <= max(st.limit, int(opts.forced_sub_levels.get(str(sid), 1))))
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
                if e.stat == CRIT_TO_ELEM:   # Dénouement : conversion faite dans _derived
                    self.convert = eff
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
        weights = dict(opts.element_weights())
        self._crit_conversion()
        # --- maîtrise élémentaire utile : moitié min, moitié moyenne pondérée (scoring.elem_mastery_used)
        mast = []
        mlo, mhi = BIG, -BIG
        for e in ELEMENTS:
            lo = acc.lb["elem_mastery"] + acc.lb[f"{e}_mastery"]
            hi = acc.ub["elem_mastery"] + acc.ub[f"{e}_mastery"] + acc.ub[f"rand_mastery_{e}"]
            expr = acc.expr("elem_mastery") + acc.expr(f"{e}_mastery") + acc.expr(f"rand_mastery_{e}")
            if self.crit_conv is not None:   # Dénouement : la Maîtrise Critique devient de la Maîtrise Élémentaire
                hi += max(0, acc.bounds("crit_mastery")[1])
                expr = expr + self.crit_conv
            var = m.NewIntVar(lo - 10, hi + 10, f"M_{e}")
            m.Add(var == expr)
            self.stat_var[f"mastery_{e}"] = var
            if e in weights:
                mast.append(var)
                mlo, mhi = min(mlo, lo - 10), max(mhi, hi + 10)
        mmin = m.NewIntVar(mlo, mhi, "M_min")
        m.AddMinEquality(mmin, mast)
        w = sum(weights.values())
        if w > 1:
            melem = m.NewIntVar(mlo, mhi, "M_elem")
            num = w * mmin + sum(p * self.stat_var[f"mastery_{e}"] for e, p in weights.items())
            m.Add(2 * w * melem <= num)
            m.Add(2 * w * melem >= num - (2 * w - 1))
            mtot_expr = melem
        else:
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
        self.feat = model_features(self)   # variables du score (objectif)

    def _crit_conversion(self) -> None:
        """Dénouement placé : crit_conv = Maîtrise Critique (si positive), sinon 0."""
        if self.convert is None:
            return
        m = self.m
        hi = max(0, self.acc.bounds("crit_mastery")[1]) + 10
        pos = m.NewIntVar(0, hi, "crit_m_pos")
        m.AddMaxEquality(pos, [self.stat("crit_mastery"), 0])
        conv = m.NewIntVar(0, hi, "crit_conv")
        m.Add(conv <= pos)
        m.Add(conv <= hi * self.convert)
        m.Add(conv >= pos - hi * (1 - self.convert))
        self.crit_conv = conv

    def maximize(self, expr: Any) -> None:
        clear = getattr(self.m, "clear_objective", None) or getattr(self.m, "ClearObjective", None)
        if clear is not None:
            clear()
        self.m.Maximize(expr)

    def set_linear_objective(self, grad: dict[str, float]) -> None:
        """Objectif linéaire : somme des variables du score pondérées par le gradient du score."""
        self.maximize(linear_objective(self.feat, grad))

    # --------------------------------------------------------------- extraction
    def extract(self, solver: cp_model.CpSolver) -> Build:
        v, opts = self.v, self.opts
        val = solver.BooleanValue
        b = Build()
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
            wanted = [ch for ch in b.slots.values()   # d'abord l'item forcé qui doit la porter (onglet Items)
                      if sub.state_id in self.opts.forced_item_subs.get(str(ch.item_id), [])]
            for ch in wanted + list(b.slots.values()):
                it = self.items[ch.item_id]
                fits = (it.is_epic or PROP_EPIC_GEM in it.properties) if sub.is_epic else (it.is_relic or PROP_RELIC_GEM in it.properties)
                if fits and ch.special_sublimation_id is None:
                    ch.special_sublimation_id = sid
                    break
        for key, var in v.chars.items():
            n = solver.Value(var)
            if n:
                b.characteristics[key] = int(n)
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
        played = self.opts.played_elements()
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
