"""Build sombre (onglet debug) : combos de sublimations sur un build dont les items ne bougent pas.

Seules les sublimations changent : on part du build sans aucune sublimation et on cherche les ensembles qui rapportent
le plus ENSEMBLE. Une sublimation à condition (Dénouement, Mesure, Pilier, Inflexible…) ne vaut souvent rien seule et
beaucoup à côté de celle qui remplit sa condition : un glouton sublimation par sublimation ne les trouve pas.

Recherche, bornée en temps (`ForgeParams.time_limit`) :
  1. solo : chaque sublimation seule sur le build nu ;
  2. duos : chaque paire de familles (au plus haut niveau d'une sublimation) -> synergie = duo − solo A − solo B ;
  3. faisceau : à partir du vide (ou du pivot) et des meilleurs duos, on ajoute une sublimation à la fois et on garde
     les `beam` meilleurs combos à chaque profondeur ;
  4. descente locale sur les meilleurs : retirer, ajouter ou remplacer une sublimation tant que ça rapporte.
Puis on retire le poids mort (sublimation dont le retrait ne coûte rien : condition non remplie, plafond atteint) et
on garde des combos assez différents les uns des autres (`diversity`).

Les évaluations sont exactes (stats.evaluate, niveaux d'états ajoutés au build nu) et mémorisées par niveaux d'états :
deux combos qui donnent les mêmes niveaux ont la même valeur.

Emplacements (`mode`) :
  colors  : motif dans les couleurs actuelles des châsses (le jaune sert de joker) ; épiques / reliques dans les items
            qui les acceptent. Le combo se pose tel quel sur le build.
  recolor : n'importe quel item à 3 châsses ou plus. À l'application, les châsses sont recolorées et les runes
            replacées (la meilleure rune de la couleur dans une châsse restée vide) : la valeur exacte est recalculée.
  dream   : théorique, toutes les châsses sans contrainte de couleur, une épique et une relique même sans item pour les
            porter. Ne s'applique pas au build.
"""

from __future__ import annotations

import copy
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..data.models import PROP_EPIC_GEM, PROP_RELIC_GEM, SHARD_SLOTS, Color, GameData, Slot, Sublimation
from .options import SECONDARY_MASTERIES, Build, OptimizeOptions, ShardChoice
from .scoring import ln_damage, ln_defense
from .shards import COND_FR, STAT_COND_FR, color_matches, needs_stats, parse_stat_condition, pattern_offsets, rune_fits, static_condition
from .stats import Totals, evaluate, item_rune_level, prepare

MODES = ("colors", "recolor", "dream")
OBJECTIVES = ("score", "damage", "survival")
INVALID = 1000.0     # malus d'un combo qui passe sous les PA / PM minimums (garde-fou) : jamais proposé
# recolor : coût estimé d'un item recoloré, en part de la valeur moyenne d'une rune du build. Les runes sont replacées
# (la meilleure de la couleur dans une châsse libérée) : mesuré sur de vrais builds, le coût réel est d'environ 10 %.
RECOLOR_COST = 0.1
EPS = 1e-6


@dataclass
class ForgeParams:
    mode: str = "colors"           # colors | recolor | dream (voir en tête)
    objective: str = "score"       # score | damage (dégâts seuls) | survival (PV effectifs seuls)
    epic: bool = True
    relic: bool = True
    pivot: int = 0                 # id d'état présent dans chaque combo (0 : aucun)
    beam: int = 16                 # combos gardés à chaque profondeur du faisceau
    time_limit: float = 10.0
    top: int = 6                   # combos proposés
    diversity: int = 3             # familles différentes au minimum entre deux combos proposés
    keep_minimums: bool = True     # PA / PM jamais sous les minimums (ou sous ceux du build actuel s'ils sont plus bas)
    confirmed_only: bool = False   # seulement les sublimations confirmées (sublimations.yaml)
    conditional: bool = True       # compter les conditions « PV > 90 % », « sans armure »

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ForgeParams":
        p = ForgeParams()
        for k, v in d.items():
            if hasattr(p, k) and v is not None:
                setattr(p, k, type(getattr(p, k))(v))
        p.mode = p.mode if p.mode in MODES else "colors"
        p.objective = p.objective if p.objective in OBJECTIVES else "score"
        p.beam = max(2, min(64, p.beam))
        p.time_limit = max(1.0, min(60.0, p.time_limit))
        p.top = max(1, min(12, p.top))
        p.diversity = max(1, min(4, p.diversity))
        return p


@dataclass(frozen=True)
class Host:
    """Un emplacement de sublimation : les châsses d'un item, ou son emplacement épique / relique."""

    slot: Slot | None              # None : emplacement théorique (mode dream)
    kinds: frozenset[str]          # normal | epic | relic
    colors: tuple[Color, ...] = ()


@dataclass(frozen=True)
class Piece:
    sub: Sublimation
    kind: str                      # normal | epic | relic
    mask: int                      # hôtes possibles (bits)
    fit: int                       # parmi eux, ceux dont les couleurs vont déjà (recolor : à essayer d'abord)


@dataclass
class Condition:
    label: str
    value: int
    threshold: int
    ok: bool
    margin: int


@dataclass
class Part:
    """Une famille de sublimations (un état) dans un combo."""

    state_id: int
    kind: str
    level: int
    limit: int
    placed: list[tuple[Sublimation, Host]]
    solo: float                    # valeur de la famille seule (au même niveau) sur le build nu
    marginal: float                # ce que coûte son retrait du combo
    role: str
    conditions: list[Condition] = field(default_factory=list)
    guard: bool = False            # sans elle, le combo passe sous les PA / PM minimums


@dataclass
class Combo:
    pieces: tuple[int, ...]
    value: float                   # objectif (avec garde-fous) sur le build nu + combo
    gain: float                    # value − valeur du build nu
    synergy: float                 # gain − somme des solos de ses familles
    totals: Totals
    parts: list[Part]
    name: str
    build: Build | None = None     # combo posé sur le build (None en mode dream)
    exact: float | None = None     # valeur du build posé (recolor : runes replacées)
    recolored: list[Slot] = field(default_factory=list)
    runes_changed: list[tuple[Slot, str, str]] = field(default_factory=list)   # (emplacement, avant, après)


@dataclass
class ForgeResult:
    params: ForgeParams
    bare: Totals                   # build sans aucune sublimation
    current: Totals                # build tel qu'il est (sublimations de l'optimiseur)
    bare_value: float
    current_value: float
    combos: list[Combo]
    solo: list[tuple[int, float]]                       # (état, gain seul au meilleur niveau)
    matrix_states: list[int]
    matrix: list[list[float | None]]                    # synergies des duos
    duos: list[tuple[int, int, float]]                  # duos les plus (et les moins) complices : (état, état, synergie)
    hosts: list[Host]
    n_pieces: int
    evals: int
    elapsed: float
    timed_out: bool
    phases: list[tuple[str, float, int]]                # (phase, secondes, évaluations)
    messages: list[str] = field(default_factory=list)


def strip_subs(build: Build) -> Build:
    b = copy.deepcopy(build)
    for ch in b.slots.values():
        ch.sublimation_id = None
        ch.special_sublimation_id = None
    return b


def _special_kinds(data: GameData, item_id: int) -> set[str]:
    it = data.item_by_id().get(item_id)
    if it is None:
        return set()
    out = set()
    if it.is_epic or PROP_EPIC_GEM in it.properties:
        out.add("epic")
    if it.is_relic or PROP_RELIC_GEM in it.properties:
        out.add("relic")
    return out


def hosts_of(data: GameData, build: Build, mode: str) -> list[Host]:
    out: list[Host] = []
    for slot, ch in build.slots.items():
        if ch.item_id not in data.item_by_id():
            continue
        cols = tuple(sh.color for sh in ch.shards)
        if len(cols) >= 3 or mode == "dream" and slot in SHARD_SLOTS:
            out.append(Host(slot, frozenset({"normal"}), cols))
        if mode != "dream" and (kinds := _special_kinds(data, ch.item_id)):
            out.append(Host(slot, frozenset(kinds)))
    if mode == "dream":
        out += [Host(None, frozenset({"epic"})), Host(None, frozenset({"relic"}))]
    return out


class Forge:
    def __init__(self, data: GameData, opts: OptimizeOptions, build: Build, params: ForgeParams) -> None:
        self.data, self.p = data, params
        self.opts = copy.copy(opts)
        self.opts.count_conditional = params.conditional
        self.t0 = time.monotonic()
        self.deadline = self.t0 + params.time_limit
        self.timed_out = False
        self.bare = strip_subs(build)
        self.prepared = prepare(data, self.opts, self.bare)   # items, runes, aptitudes : calculés une fois
        self.hosts = hosts_of(data, build, params.mode)
        self.pieces = self._pieces()
        self.memo: dict[tuple[tuple[int, int], ...], tuple[float, float, Totals]] = {}   # niveaux -> (valeur, brute, totaux)
        self.feas: dict[tuple[int, ...], tuple[list[int], int] | None] = {}   # combo -> (hôtes, châsses à recolorer)
        self.best_rune: dict[tuple[Slot, Color], int | None] = {}
        self.sigs: dict[tuple[int, ...], frozenset[int]] = {}
        self.evals = 0
        self.current = evaluate(data, self.opts, build)
        self.ap_floor = min(opts.min_ap, int(self.current.stats.get("ap", 0)))
        self.mp_floor = min(opts.min_mp, int(self.current.stats.get("mp", 0)))
        _, self.v0, self.bare_totals = self.evaluate(())   # base des gains : valeur brute (le build nu peut manquer de PA)
        self.current_value = self.raw(self.current)
        self.recolor_cost = self._rune_cost() if params.mode == "recolor" else 0.0

    # ------------------------------------------------------------------ catalogue
    def _pieces(self) -> list[Piece]:
        p, opts = self.p, self.opts
        out: list[Piece] = []
        seen: set[tuple[int, int, int]] = set()
        for sub in self.data.sublimations:
            st = self.data.states.get(sub.state_id)
            if st is None or not st.modeled or sub.state_id in opts.excluded_subs and sub.state_id != p.pivot:
                continue
            if p.confirmed_only and not st.confirmed and sub.state_id != p.pivot:
                continue
            if not any(static_condition(e.condition, opts) is not False for e in st.effects):
                continue
            kind = "epic" if sub.is_epic else "relic" if sub.is_relic else "normal"
            if sub.state_id != p.pivot and (kind == "epic" and not p.epic or kind == "relic" and not p.relic):
                continue
            if kind == "normal" and not sub.pattern:
                continue
            mask = fit = 0
            for i, h in enumerate(self.hosts):
                if kind not in h.kinds:
                    continue
                fits = kind != "normal" or bool(pattern_offsets(h.colors, sub.pattern))
                if p.mode == "colors" and not fits or kind == "normal" and p.mode == "recolor" and len(h.colors) < len(sub.pattern):
                    continue
                mask |= 1 << i
                fit |= (1 << i) if fits else 0
            key = (sub.state_id, sub.state_level, mask)   # même état, même niveau, mêmes hôtes : un seul exemplaire
            if mask and key not in seen:
                seen.add(key)
                out.append(Piece(sub, kind, mask, fit))
        return out

    # ------------------------------------------------------------------ évaluation
    def time_left(self) -> bool:
        if time.monotonic() > self.deadline:
            self.timed_out = True
        return not self.timed_out

    def objective(self, t: Totals) -> float:
        """Objectif avec garde-fous : un combo sous les PA / PM minimums n'est jamais proposé."""
        v = self.raw(t)
        if self.p.keep_minimums:
            short = max(0, self.ap_floor - int(t.stats.get("ap", 0))) + max(0, self.mp_floor - int(t.stats.get("mp", 0)))
            if short:
                v -= INVALID + 100 * short
        return v

    def raw(self, t: Totals) -> float:
        """Objectif seul (score, dégâts ou survie), sans garde-fous : pour les gains, solos et synergies affichés."""
        f, o = t.features, self.opts
        if self.p.objective == "damage":
            rear = o.rear and not o.heal
            v = 100 * ln_damage(f["mtot"], f["crit"], f["crit_mastery"], f["rear_mastery"],
                                float(o.rear_share) if rear else 0.0, f["dmg_pct"])
        elif self.p.objective == "survival":
            v = 100 * ln_defense(f["hp"], f["hp_pct"], f["res"], f.get("block", 0.0))
        else:
            v = t.score
        return v

    def levels(self, combo: tuple[int, ...]) -> dict[int, int]:
        out: dict[int, int] = defaultdict(int)
        for i in combo:
            out[self.pieces[i].sub.state_id] += self.pieces[i].sub.state_level
        return out

    def key(self, combo: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
        return tuple(sorted(self.levels(combo).items()))

    def evaluate(self, combo: tuple[int, ...]) -> tuple[float, float, Totals]:
        """(valeur avec garde-fous, valeur brute, totaux) du build nu + combo."""
        k = self.key(combo)
        hit = self.memo.get(k)
        if hit is None:
            t = evaluate(self.data, self.opts, self.bare, extra_states=dict(k), prepared=self.prepared)
            self.evals += 1
            hit = self.memo[k] = (self.objective(t), self.raw(t), t)
        return hit

    def gain(self, combo: tuple[int, ...]) -> float:
        """Gain brut face au build nu (sans garde-fous ni coût des recolorations)."""
        return self.evaluate(combo)[1] - self.v0

    def valid(self, combo: tuple[int, ...]) -> bool:
        v, r, _ = self.evaluate(combo)
        return v > r - INVALID / 2

    def value(self, combo: tuple[int, ...]) -> float:
        """Objectif du combo ; recolor : moins une estimation du coût des runes déplacées par item recoloré."""
        v = self.evaluate(combo)[0]
        if self.recolor_cost and (fit := self._fit(combo)) is not None:
            v -= self.recolor_cost * fit[1]
        return v

    def _rune_cost(self) -> float:
        """Coût estimé de la recoloration d'un item : RECOLOR_COST × valeur moyenne d'une rune du build."""
        b = copy.deepcopy(self.bare)
        n = 0
        for ch in b.slots.values():
            for sh in ch.shards:
                n += sh.rune_id is not None
                sh.rune_id = None
        if not n:
            return 0.0
        return RECOLOR_COST * max(0.0, (self.v0 - self.raw(evaluate(self.data, self.opts, b))) / n)

    # ------------------------------------------------------------------ placement
    def assign(self, combo: tuple[int, ...]) -> list[int] | None:
        """Hôte de chaque sublimation du combo (couplage biparti), ou None si le combo ne tient pas sur le build."""
        fit = self._fit(combo)
        return fit[0] if fit else None

    def _fit(self, combo: tuple[int, ...]) -> tuple[list[int], int] | None:
        if combo in self.feas:
            return self.feas[combo]
        out: tuple[list[int], int] | None = None
        if all(not (st := self.data.states.get(s)) or not st.limit or lv <= st.limit for s, lv in self.levels(combo).items()):
            n = len(self.hosts)
            owner = [-1] * n

            def place(k: int, seen: list[bool]) -> bool:
                pc = self.pieces[combo[k]]
                for first in (True, False):   # d'abord les hôtes dont les couleurs vont déjà
                    for h in range(n):
                        if (pc.fit if first else pc.mask & ~pc.fit) >> h & 1 and not seen[h]:
                            seen[h] = True
                            if owner[h] < 0 or place(owner[h], seen):
                                owner[h] = k
                                return True
                return False

            if all(place(k, [False] * n) for k in range(len(combo))):
                hosts = [-1] * len(combo)
                for h, k in enumerate(owner):
                    if k >= 0:
                        hosts[k] = h
                out = (hosts, sum(not self.pieces[i].fit >> h & 1 for i, h in zip(combo, hosts)))
        self.feas[combo] = out
        return out

    def feasible(self, combo: tuple[int, ...]) -> bool:
        return self.assign(combo) is not None

    # ------------------------------------------------------------------ recherche
    def run(self) -> ForgeResult:
        phases: list[tuple[str, float, int]] = []
        messages: list[str] = []
        clock: list[float] = [time.monotonic(), float(self.evals)]

        def phase(name: str) -> None:
            now = time.monotonic()
            phases.append((name, now - clock[0], int(self.evals - clock[1])))
            clock[:] = [now, float(self.evals)]

        # 1. solo
        solo: dict[int, float] = {}
        for i in range(len(self.pieces)):
            if self.feasible((i,)):
                solo[i] = self.gain((i,))
        rep: dict[int, int] = {}   # état -> pièce de plus haut niveau (la meilleure à niveau égal)
        for i in solo:
            s = self.pieces[i].sub
            j = rep.get(s.state_id)
            if j is None or (s.state_level, solo[i]) > (self.pieces[j].sub.state_level, solo[j]):
                rep[s.state_id] = i
        fam_solo = {s: max(v for i, v in solo.items() if self.pieces[i].sub.state_id == s) for s in rep}
        phase("Solo")

        # 2. duos
        fams = sorted(rep, key=lambda s: -fam_solo[s])
        duo: dict[tuple[int, int], float] = {}
        duo_value: dict[tuple[int, ...], float] = {}
        for x, a in enumerate(fams):
            if not self.time_left():
                break
            for b in fams[x + 1:]:
                c = tuple(sorted((rep[a], rep[b])))
                if self.feasible(c):
                    duo_value[c] = self.value(c)
                    duo[(a, b)] = duo[(b, a)] = self.gain(c) - solo[rep[a]] - solo[rep[b]]
        phase("Duos")

        pivot = self.p.pivot if self.p.pivot in rep else 0
        if self.p.pivot and not pivot:
            messages.append("Le pivot ne tient pas sur ce build (couleurs, emplacement ou options) : recherche sans pivot.")
        # familles utiles : celles qui rapportent seules ou en duo, et toujours celles à condition sur les stats du build
        # (Dénouement, Mesure, Pilier…) : il leur faut parfois deux autres sublimations pour se déclencher
        conditional = {s for s in fams if any(needs_stats(e.condition) for e in self.data.states[s].effects)}
        # garde-fou : celles qui donnent des PA / PM (le build nu peut être sous le minimum si l'optimiseur l'atteignait
        # avec une sublimation ; elles ne rapportent rien à l'objectif, mais rendent les combos possibles)
        guards = {s for s in fams if self.p.keep_minimums
                  and any(e.stat in ("ap", "mp") and max(e.values) > 0 for e in self.data.states[s].effects)}
        useful = {s for s in fams if fam_solo[s] > 0.01 or any(duo.get((s, b), 0) > 0.01 for b in fams)}
        useful |= conditional | guards | ({pivot} - {0})
        cand = [i for i in solo if self.pieces[i].sub.state_id in useful]
        def has_pivot(c: tuple[int, ...]) -> bool:
            return not pivot or any(self.pieces[i].sub.state_id == pivot for i in c)

        # 3. faisceau
        pool: dict[tuple[tuple[int, int], ...], tuple[int, ...]] = {}

        def remember(c: tuple[int, ...]) -> None:
            k = self.key(c)
            if k not in pool or (self.value(c), -len(c)) > (self.value(pool[k]), -len(pool[k])):
                pool[k] = c

        seeds: list[tuple[int, ...]] = [(i,) for i in cand if self.pieces[i].sub.state_id == pivot] if pivot else [()]
        duos = [c for c in duo_value if has_pivot(c) and all(i in cand for i in c)]
        seeds += sorted(duos, key=lambda c: -duo_value[c])[: self.p.beam // 2]
        syn = sorted(duos, key=lambda c: -duo.get((self.pieces[c[0]].sub.state_id, self.pieces[c[1]].sub.state_id), 0))
        seeds += syn[: self.p.beam // 2]
        frontier = list(dict.fromkeys(seeds))
        for c in frontier:
            remember(c)
        tried: set[tuple[int, ...]] = set(frontier)
        while frontier and self.time_left():
            nxt: dict[tuple[tuple[int, int], ...], tuple[int, ...]] = {}
            for c in frontier:
                if not self.time_left():
                    break
                for i in cand:
                    n = tuple(sorted(c + (i,)))
                    if n in tried:
                        continue
                    tried.add(n)
                    if not self.feasible(n):
                        continue
                    k = self.key(n)
                    if k not in nxt or (self.value(n), -len(n)) > (self.value(nxt[k]), -len(nxt[k])):
                        nxt[k] = n
            ranked = sorted(nxt.values(), key=lambda c: -self.value(c))
            for c in ranked:
                remember(c)
            frontier = []
            per_set: dict[frozenset[int], int] = defaultdict(int)   # au plus 2 variantes de niveaux par ensemble de familles
            for c in ranked:
                fs = frozenset(self.levels(c))
                if per_set[fs] < 2:
                    per_set[fs] += 1
                    frontier.append(c)
                if len(frontier) >= self.p.beam:
                    break
            # places réservées : les 2 meilleurs combos avec chaque famille à condition, même s'ils ne rapportent pas
            # encore (Dénouement attend le critique que les profondeurs suivantes apporteront)
            for fam in conditional & useful:
                extra = [c for c in ranked if c not in frontier and any(self.pieces[i].sub.state_id == fam for i in c)]
                frontier += extra[:2]
        phase("Faisceau")

        # 4. descente locale (première amélioration trouvée : retirer, ajouter, puis remplacer une sublimation), depuis
        # les meilleurs combos assez différents ; puis recherche locale itérée tant qu'elle trouve mieux : on retire 2 ou 3
        # sublimations d'un des meilleurs combos et on redescend (sortir d'un optimum local)
        def descend(c: tuple[int, ...]) -> tuple[int, ...]:
            improved = True
            while improved and self.time_left():
                improved, bv = False, self.value(c)
                moves = [c[:k] + c[k + 1:] for k in range(len(c))] + [c + (i,) for i in cand]
                moves += [c[:k] + c[k + 1:] + (i,) for k in range(len(c)) for i in cand if i != c[k]]
                for idx, m in enumerate(moves):
                    if idx % 64 == 0 and not self.time_left():
                        break
                    m = tuple(sorted(m))
                    if m != c and has_pivot(m) and self.feasible(m) and self.value(m) > bv + EPS:
                        c, improved = m, True
                        remember(c)
                        break
            return c

        best_first = [c for c in sorted(pool.values(), key=lambda c: -self.value(c)) if has_pivot(c)]
        elite = [descend(c) for c in self._diverse(best_first[:150], self.p.top + 2)]
        rng = random.Random(len(self.pieces))   # déterministe : mêmes réglages, mêmes combos (hors limite de temps)
        best_v = max((self.value(c) for c in elite), default=self.v0)
        stale = 0
        reserve = self.t0 + 0.85 * self.p.time_limit   # le reste du temps : sélection et analyse des combos
        while elite and stale < 4 * self.p.beam and time.monotonic() < reserve:
            kept = list(rng.choice(elite))
            for _ in range(min(len(kept), rng.randint(2, 3))):
                kept.pop(rng.randrange(len(kept)))
            found = descend(tuple(sorted(kept)))
            v = self.value(found)
            if v > best_v + EPS:
                best_v, stale = v, 0
                elite = sorted(elite + [found], key=lambda x: -self.value(x))[: self.p.top + 2]
            else:
                stale += 1
        phase("Descente")

        # 5. sélection : poids mort retiré, combos assez différents
        ranked = [c for c in sorted(pool.values(), key=lambda c: -self.value(c))
                  if has_pivot(c) and self.valid(c)][:400]
        finals: list[Combo] = []
        # recolor : la recherche n'estime que le coût des runes déplacées ; on pose deux fois plus de combos et on
        # garde les meilleurs à la valeur exacte
        pruned: list[tuple[int, ...]] = []
        for c in ranked[: 40 * self.p.top]:
            if len(pruned) >= 3 * self.p.top and not self.time_left():
                break
            pruned.append(self._prune(c, has_pivot))
        pruned = list(dict.fromkeys(pruned))
        pruned.sort(key=lambda c: -self.value(c))
        picked = self._diverse(pruned, self.p.top * (2 if self.p.mode == "recolor" else 1),
                               keep=lambda c: self.gain(c) > 0.01 or bool(pivot))
        for c in picked:
            if self.p.mode == "recolor" and not self.time_left() and len(finals) >= self.p.top:
                break
            finals.append(self._analyse(c, fam_solo))
        if self.p.mode == "recolor":   # une fois les runes replacées, un combo peut ne plus rien rapporter
            finals = [x for x in finals if x.exact is None or x.exact - self.v0 > 0.01]
            finals.sort(key=lambda x: -(x.exact if x.exact is not None else x.value))
            del finals[self.p.top:]
        self._names(finals, pivot)
        phase("Analyse")

        mstates = list(dict.fromkeys([pt.state_id for cb in finals for pt in cb.parts] + fams))[:12]
        matrix = [[None if a == b else duo.get((a, b)) for b in mstates] for a in mstates]
        pairs = sorted(((a, b, v) for (a, b), v in duo.items() if a < b), key=lambda x: -x[2])
        best_duos = [x for x in pairs[:6] if x[2] > 0.05] + [x for x in pairs[-4:] if x[2] < -0.05][::-1]
        if not self.pieces:
            messages.append("Aucune sublimation ne tient sur ce build (pas de châsses, ou toutes exclues).")
        return ForgeResult(
            params=self.p, bare=self.bare_totals, current=self.current, bare_value=self.v0, current_value=self.current_value,
            combos=finals, solo=sorted(fam_solo.items(), key=lambda kv: -kv[1]), matrix_states=mstates, matrix=matrix, duos=best_duos,
            hosts=self.hosts, n_pieces=len(self.pieces), evals=self.evals, elapsed=time.monotonic() - self.t0,
            timed_out=self.timed_out, phases=phases, messages=messages)

    def _prune(self, combo: tuple[int, ...], has_pivot: Any) -> tuple[int, ...]:
        """Retire les sublimations dont le retrait ne coûte rien (condition non remplie, plafond, niveau perdu)."""
        changed = True
        while changed:
            changed = False
            v = self.value(combo)
            for k in range(len(combo)):
                c = combo[:k] + combo[k + 1:]
                if has_pivot(c) and self.value(c) >= v - EPS:
                    combo, changed = c, True
                    break
        return combo

    def _signature(self, c: tuple[int, ...]) -> frozenset[int]:
        """Familles qui comptent dans le combo : leur retrait coûte plus que 0,5 point (et 3 % du gain). Les appoints
        minuscules (Évasion I ou Interception I dans la dernière châsse libre) ne font pas un combo différent."""
        if c not in self.sigs:
            _, v, _ = self.evaluate(c)
            floor = max(0.5, 0.03 * (v - self.v0))
            fams = set(self.levels(c))
            self.sigs[c] = frozenset(s for s in fams if v - self.evaluate(tuple(i for i in c if self.pieces[i].sub.state_id != s))[1] > floor)
        return self.sigs[c]

    def _distance(self, a: tuple[int, ...], b: tuple[int, ...]) -> int:
        sa, sb = self._signature(a), self._signature(b)
        d = len(sa ^ sb)
        if d or sa != sb:
            return d
        if abs(self.value(a) - self.value(b)) < EPS:   # mêmes familles, même valeur : un niveau qui ne sert à rien
            return 0
        la, lb = self.levels(a), self.levels(b)
        return 1 if any(la.get(s) != lb.get(s) for s in sa) else 0   # mêmes familles à d'autres niveaux : variante proche

    def _diverse(self, combos: list[tuple[int, ...]], n: int, keep: Any = lambda c: True) -> list[tuple[int, ...]]:
        """Les meilleurs combos assez différents les uns des autres (familles qui comptent, voir _signature) ; s'il en
        manque, on assouplit l'écart demandé, jusqu'à une famille ou un niveau d'écart. Rangés par valeur."""
        out: list[tuple[int, ...]] = []
        for d in range(self.p.diversity, 0, -1):
            for c in combos:
                if len(out) >= n:
                    break
                if c not in out and keep(c) and all(self._distance(c, o) >= d and self.key(c) != self.key(o) for o in out):
                    out.append(c)
            if len(out) >= n:
                break
        return sorted(out, key=lambda c: -self.value(c))

    # ------------------------------------------------------------------ analyse d'un combo
    def _analyse(self, combo: tuple[int, ...], fam_solo: dict[int, float]) -> Combo:
        _, v, t = self.evaluate(combo)
        by_state: dict[int, list[int]] = defaultdict(list)
        for k, i in enumerate(combo):
            by_state[self.pieces[i].sub.state_id].append(k)
        assign = self.assign(combo) or [-1] * len(combo)
        parts: list[Part] = []
        for sid, ks in by_state.items():
            st = self.data.states[sid]
            alone = tuple(combo[k] for k in ks)
            rest = tuple(i for k, i in enumerate(combo) if k not in ks)
            solo = self.gain(alone)   # valeurs brutes : effet des états seul (ni garde-fous, ni coût des recolorations)
            marginal = v - self.evaluate(rest)[1]
            parts.append(Part(
                state_id=sid, kind=self.pieces[combo[ks[0]]].kind, level=sum(self.pieces[combo[k]].sub.state_level for k in ks),
                limit=st.limit, placed=[(self.pieces[combo[k]].sub, self.hosts[assign[k]]) for k in ks],
                solo=solo, marginal=marginal, role="", conditions=self._conditions(sid, t), guard=not self.valid(rest)))
        # Le score est logarithmique : dans un combo, chaque sublimation vaut moins que seule (rendement décroissant).
        # Les rôles se lisent par rapport au rendement typique du combo (médiane de marginal / solo).
        ratios = sorted(pt.marginal / pt.solo for pt in parts if pt.solo > 0.5)
        typical = ratios[len(ratios) // 2] if ratios else 1.0
        top = max((pt.marginal for pt in parts), default=0)
        for pt in parts:
            expected = typical * pt.solo
            thr = max(0.5, 0.25 * abs(pt.marginal))
            if pt.guard:
                pt.role = "Garde-fou"
            elif pt.solo < -0.05:
                pt.role = "Sacrifice"
            elif pt.marginal > pt.solo + thr:
                pt.role = "Déclenchée" if pt.conditions else "Catalyseur"
            elif pt.marginal < 0.5 * expected - 0.1:
                pt.role = "Plafonnée"
            else:
                pt.role = "Pilier" if pt.marginal >= top - EPS else "Appoint"
        parts.sort(key=lambda pt: -pt.marginal)
        gain = v - self.v0
        cb = Combo(pieces=combo, value=v, gain=gain, synergy=gain - sum(pt.solo for pt in parts), totals=t, parts=parts, name="")
        if self.p.mode != "dream":
            self._materialize(cb, assign)
        return cb

    def _names(self, combos: list[Combo], pivot: int) -> None:
        """Nom d'un combo : ses deux familles qui comptent le plus (le pivot d'abord). Deux combos du même nom : on ajoute
        au suivant ce qui le distingue du premier (une famille en plus, sinon un niveau qui change), sans répéter un nom."""
        def name(sid: int) -> str:
            return self.data.state_name(sid, self.opts.lang)

        seen: dict[str, dict[int, int]] = {}   # nom de base -> familles (et niveaux) du premier combo de ce nom
        used: set[str] = set()
        for cb in combos:
            order = sorted(cb.parts, key=lambda pt: (pt.state_id != pivot, -pt.marginal))
            base = " × ".join(name(pt.state_id) for pt in order[:2]) or "—"
            first = seen.setdefault(base, {pt.state_id: pt.level for pt in cb.parts})
            tags = [name(pt.state_id) for pt in order[2:] if pt.state_id not in first]
            tags += [f"{name(pt.state_id)} {pt.level}" for pt in order if first.get(pt.state_id, pt.level) != pt.level]
            labels = [base] + [f"{base} · {t}" for t in tags] + [f"{base} · {', '.join(tags[:k])}" for k in range(2, len(tags) + 1)]
            cb.name = next((x for x in labels if x not in used), "")
            n = 2
            while not cb.name or cb.name in used:
                cb.name, n = f"{labels[-1]} ({n})", n + 1
            used.add(cb.name)

    def _conditions(self, sid: int, t: Totals) -> list[Condition]:
        out: list[Condition] = []
        seen: set[str] = set()
        for e in self.data.states[sid].effects:
            if not needs_stats(e.condition):
                continue
            for c in e.condition.split("&"):
                if c in seen:
                    continue
                seen.add(c)
                sc = parse_stat_condition(c)
                if sc is not None:
                    kind, stat, thr = sc
                    cur = int(t.raw.get(stat, 0))
                    ok = cur <= thr if kind == "le" else cur >= thr
                    out.append(Condition(f"{STAT_COND_FR.get(stat, stat)} {'≤' if kind == 'le' else '≥'} {thr}", cur, thr, ok,
                                         thr - cur if kind == "le" else cur - thr))
                elif c == "no_secondary":
                    cur = max(int(t.raw.get(k, 0)) for k in SECONDARY_MASTERIES)
                    out.append(Condition(COND_FR[c], cur, 0, cur <= 0, -cur))
        return out

    # ------------------------------------------------------------------ pose sur le build
    def _materialize(self, cb: Combo, assign: list[int]) -> None:
        b = copy.deepcopy(self.bare)
        todo: list[tuple[Slot, Sublimation]] = []
        for k, i in enumerate(cb.pieces):
            pc, h = self.pieces[i], self.hosts[assign[k]]
            if h.slot is None:
                return
            ch = b.slots[h.slot]
            if pc.kind == "normal":
                ch.sublimation_id = pc.sub.id
                if not pattern_offsets([sh.color for sh in ch.shards], pc.sub.pattern):
                    todo.append((h.slot, pc.sub))
            else:
                ch.special_sublimation_id = pc.sub.id
        for slot, sub in todo:
            cb.runes_changed += self._recolor(b, slot, sub.pattern)
            cb.recolored.append(slot)
        cb.build = b
        cb.exact = self.raw(evaluate(self.data, self.opts, b))

    def _recolor(self, b: Build, slot: Slot, pattern: tuple[Color, ...]) -> list[tuple[Slot, str, str]]:
        """Recolore le moins de châsses possible pour que le motif tienne, puis replace les runes de l'item, châsse par
        châsse (les colorées d'abord, le joker ensuite) : la rune de l'item qui rapporte le plus, ou la meilleure rune de la
        couleur si aucune ne vaut mieux. Renvoie les runes changées (avant, après)."""
        ch = b.slots[slot]
        runes = self.data.rune_by_id()
        cols = [sh.color for sh in ch.shards]
        k = len(pattern)
        o = min(range(len(cols) - k + 1), key=lambda o: sum(not color_matches(cols[o + j], pattern[j]) for j in range(k)))
        for j in range(k):
            if not color_matches(cols[o + j], pattern[j]):
                cols[o + j] = pattern[j]
        old = [(sh.rune_id, sh.rune_level) for sh in ch.shards if sh.rune_id in runes]
        before = sorted(runes[r].name(self.opts.lang) for r, _ in old)
        it = self.data.item_by_id()[ch.item_id]
        reqs = self.data.runes[0].level_requirements if self.data.runes else ()
        lvl = max((lv for _, lv in old), default=item_rune_level(it, self.opts.level, reqs))
        ch.shards = new = [ShardChoice(c) for c in cols]
        left = list(old)

        def score_with(sh: ShardChoice, rune: tuple[int, int]) -> float:
            sh.rune_id, sh.rune_level = rune
            return self.raw(evaluate(self.data, self.opts, b))

        for sh in sorted(new, key=lambda s: s.color == Color.WHITE):
            options = list(dict.fromkeys(r for r in left if rune_fits(runes[r[0]], sh.color)))
            if lvl:
                key = (slot, sh.color)   # meilleure rune neuve de la couleur pour cet item : cherchée une fois
                if key not in self.best_rune:
                    scored = [(score_with(sh, (r.id, lvl)), r.id) for r in self.data.runes if rune_fits(r, sh.color)]
                    self.best_rune[key] = max(scored)[1] if scored else None
                if (fresh := self.best_rune[key]) is not None:
                    options.append((fresh, lvl))
            if not options:
                sh.rune_id = None
                continue
            pick = max(options, key=lambda r: score_with(sh, r))
            sh.rune_id, sh.rune_level = pick
            if pick in left:
                left.remove(pick)
        after = sorted(runes[sh.rune_id].name(self.opts.lang) for sh in new if sh.rune_id in runes)
        return [(slot, ", ".join(before), ", ".join(after))] if before != after else []


def forge(data: GameData, opts: OptimizeOptions, build: Build, params: ForgeParams) -> ForgeResult:
    return Forge(data, opts, build, params).run()
