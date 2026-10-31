"""Pilote de l'optimisation : linéarisation successive du score sur le modèle CP-SAT (model.BuildModel).

    candidats (candidates.py) -> modèle (model.py) -> passes : maximiser le gradient du score autour du build
    courant (features.py), évaluer exactement le build obtenu (stats.evaluate), recommencer autour de ce point
    -> finitions (sublimations vides, points d'aptitude restants) -> résultat.

Si la résistance visée n'est pas atteinte : passe de rattrapage (plancher strict), puis, pour une cible
d'archétype, nouveau calcul avec la cible abaissée au maximum atteignable. Sans solution : diagnostic
(contrainte bloquante), en bas du fichier.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..data.models import ELEMENTS, GameData, Item, Slot
from .archetypes import apt_profile
from .backend import WARM_START, cp_model
from .candidates import select_candidates
from .characteristics import fill_unspent
from .features import BIG, initial_point
from .model import BuildModel
from .options import Build, OptimizeOptions, default_min_mp
from .scoring import gradient, res_need, res_pct
from .shards import CRIT_TO_ELEM, condition_label, needs_stats
from .stats import Totals, evaluate
from .sublimations import fill_empty_subs

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, float], None]
MAX_ITER = 8
# durée max d'une passe (s) : la durée choisie est un plafond, on vise la vitesse.
# HiGHS (navigateur) a besoin de passes plus longues pour garder la même qualité.
PASS_CAP = 10.0 if WARM_START else 6.0
MAX_TIME = 600.0         # durée maximale d'un calcul (s) ; l'interface propose 1, 3 ou 6 minutes
COMBO_SHARE = 0.4        # part du temps donnée à la variante « Dénouement imposé » (voir _combo_states)
OK = (cp_model.OPTIMAL, cp_model.FEASIBLE)
Scored = tuple[float, Build, Totals]   # (score exact, build, totaux)


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


@dataclass
class _Search:
    """État de la linéarisation successive (Optimizer._passes)."""
    point: dict[str, float]             # point de linéarisation (variables du score)
    best: Scored | None = None
    best_ok: Scored | None = None       # meilleur build qui respecte la résistance visée
    optimal: bool = True                # toutes les passes ont fini (statut OPTIMAL)
    status: int = cp_model.UNKNOWN      # statut de la dernière passe


class Optimizer:
    def __init__(self, data: GameData, opts: OptimizeOptions, progress: ProgressFn | None = None,
                 cancel: threading.Event | None = None) -> None:
        self.data, self.opts = data, opts
        self.progress = progress or (lambda msg, frac: None)
        self.cancel = cancel or threading.Event()
        self._solver: cp_model.CpSolver | None = None
        self._relaxed = False   # résistance visée de l'archétype déjà abaissée au maximum atteignable
        self._mins_relaxed = False   # PM / PO minimums de l'archétype déjà ramenés à ceux du niveau (_relax_mins)
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

    def _relax_mins(self) -> str:
        """Aucun build : si les PM / PO minimums viennent de l'archétype (panneau Contraintes désactivé) et dépassent
        ceux du niveau, on les ramène à ceux du niveau (un Eliotrope soigneur 65 ne trouve pas 1 PO). Renvoie l'avertissement (vide : rien changé)."""
        opts = self.opts
        if "constraints" in opts.custom_panels or self._mins_relaxed:
            return ""
        self._mins_relaxed = True
        level_mp = default_min_mp(opts.level)
        dropped = [f"{v} {lab}" for v, lab, base in ((opts.min_mp, "PM", level_mp), (opts.min_range, "PO", 0)) if v > base]
        if not dropped:
            return ""
        opts.min_mp, opts.min_range = min(opts.min_mp, level_mp), 0
        return (f"Minimums de l'archétype ({', '.join(dropped)}) impossibles au niveau {opts.level} : "
                "ramenés à ceux du niveau.")

    def _res_ok(self, t: Totals) -> bool:
        """Résistance visée respectée : élément le plus faible au-dessus du plancher (cible − écart)."""
        opts = self.opts
        return opts.res_target <= 0 or min(t.res_pct.values()) >= opts.res_target - opts.res_tol

    # ================================================================  calcul
    def run(self) -> SolveResult:
        t0 = time.monotonic()
        opts = self.opts
        res = SolveResult()
        budget = max(10.0, min(opts.time_limit, MAX_TIME))
        cand = self._prepare(res)
        try:
            self.progress("Construction du modèle…", 0.03)
            bm = BuildModel(self.data, opts, cand)
            for sid in bm.forced_missing:
                st = self.data.states.get(sid)
                res.warnings.append(f"Sublimation imposée « {st.name if st else sid} » impossible à placer "
                                    "(pas de châsses, ou épique/relique sans objet compatible) : ignorée.")
            for iid, sid in bm.item_sub_missing:
                st, it = self.data.states.get(sid), self.data.item_by_id().get(iid)
                res.warnings.append(f"Sublimation « {st.name if st else sid} » impossible à poser sur "
                                    f"« {it.name(opts.lang) if it else iid} » (châsses, ou item ni épique ni relique) : "
                                    "placée ailleurs si possible.")
            combo = self._combo_states()
            if WARM_START:
                self._warm_start(bm, cand, opts, budget)
            s = self._passes(bm, t0, budget * (1 - COMBO_SHARE), (0.05, 0.55)) if combo else self._passes(bm, t0, budget)
            if s.best is None:
                note = self._relax_mins() if s.status == cp_model.INFEASIBLE else ""
                if note:
                    again = self.run()
                    again.warnings.insert(0, note)
                    return again
                return self._infeasible(res, cand, s.status, t0)
            if combo:
                bm, s = self._combo_pass(bm, s, cand, combo, t0, budget)
            out_of_time = time.monotonic() - t0 >= budget - 2
            res.status = "optimal" if s.optimal else "bon build (durée max atteinte)" if out_of_time else "bon build"
            best = s.best
            if not self._res_ok(best[2]):
                best_ok = s.best_ok
                if best_ok is None:   # aucune passe au-dessus du plancher : une dernière passe qui l'impose
                    best_ok = self._floor_pass(bm, s.point, budget, t0)
                if best_ok is not None:
                    best = best_ok
            score, b, tot = self._finish(best[1])
            if not self._res_ok(tot):
                return self._res_fallback(res, cand, tot, t0, budget)
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

    def _prepare(self, res: SolveResult) -> dict[Slot, list[Item]]:
        """Options corrigées (changements signalés dans `res.warnings`) et items candidats."""
        opts = self.opts
        res.warnings.extend(opts.normalize())   # min > max, % hors bornes : corrigés et signalés
        if opts.offense_weight <= 0:   # tank : imposer une sublimation de dégâts à conditions déforme tout le build
            for sid in opts.forced_subs:
                st = self.data.states.get(sid)
                if st and any(e.stat in (CRIT_TO_ELEM, "crit_rate", "dmg_pct") and needs_stats(e.condition) for e in st.effects):
                    res.warnings.append(f"Sublimation imposée « {st.name} » : sans intérêt pour cet archétype (dégâts "
                                        f"ignorés), mais ses conditions ({condition_label(st.effects[0].condition)}) "
                                        "s'imposent au build. Retirez-la dans l'onglet Sublimations.")
        self.progress("Sélection des items candidats…", 0.01)
        cand, warnings = select_candidates(self.data, opts)
        res.warnings.extend(warnings)
        res.candidates = sum(len(v) for v in cand.values())
        if opts.min_control > 0 and not opts.optimize_characteristics:
            res.warnings.append("Aucun équipement ne donne de Contrôle : activez les caractéristiques (Majeur).")
        log.info("%d items candidats (%s)", res.candidates, {s.value: len(v) for s, v in cand.items()})
        return cand

    def _passes(self, bm: BuildModel, t0: float, budget: float, bar: tuple[float, float] = (0.05, 0.9)) -> _Search:
        """Linéarisation successive : on maximise le gradient du score autour du build courant,
        on évalue exactement le build obtenu, puis on recommence autour de ce nouveau point.
        `bar` : début et étendue de la barre de progression."""
        opts = self.opts
        s = _Search(point=initial_point(opts))
        seen: set[tuple[Any, ...]] = set()
        # le temps est réparti entre les passes : plus de temps = chaque passe va plus loin
        per_iter = min(PASS_CAP, budget / MAX_ITER)
        stale = 0
        for it in range(MAX_ITER):
            base = bar[0] + bar[1] * it / MAX_ITER
            remaining = budget - (time.monotonic() - t0)
            if remaining < 1.0 and s.best is not None:
                break
            limit = max(1.0, min(per_iter * (1.5 if it == 0 else 1.0), remaining))
            bm.set_linear_objective(gradient(s.point, opts))
            tick = self._ticker(base, bar[1] / MAX_ITER, limit, f"Optimisation (passe {it + 1}/{MAX_ITER})…")
            try:
                st, sv = self._solve(bm, limit)
                remaining = budget - (time.monotonic() - t0)
                if s.best is None and st == cp_model.UNKNOWN and remaining > 1.0:
                    # machine lente (navigateur) : aucune solution encore, on continue avec le temps restant
                    self.progress("Recherche d'un premier build (machine lente)…", base)
                    st, sv = self._solve(bm, remaining)
            finally:
                tick.set()
            s.status = st
            if st not in OK:
                break   # sans aucun build : diagnostic (voir run)
            s.optimal = s.optimal and st == cp_model.OPTIMAL
            b = bm.extract(sv)
            tot = evaluate(self.data, opts, b)
            key = (tuple(sorted(b.item_ids())), tuple(sorted(b.characteristics.items())))
            log.info("passe %d : score %.2f (%s)", it + 1, tot.score, "optimal" if st == cp_model.OPTIMAL else "réalisable")
            if s.best is None or tot.score > s.best[0] + 0.25:
                stale = 0
            else:
                stale += 1
            if s.best is None or tot.score > s.best[0]:
                s.best = (tot.score, b, tot)
            # la résistance visée n'est qu'une pénalité pendant les passes : on garde aussi le meilleur build qui la respecte
            if self._res_ok(tot) and (s.best_ok is None or tot.score > s.best_ok[0]):
                s.best_ok = (tot.score, b, tot)
            # même build qu'avant : convergé seulement si la passe a fini (sinon elle a manqué de temps)
            # deux passes sans progrès (après au moins trois passes) : on s'arrête, inutile d'attendre
            if key in seen and st == cp_model.OPTIMAL or stale >= 2 and it >= 2:
                break
            seen.add(key)
            bm.hint(sv)
            # amortissement : on se rapproche du nouveau point sans y sauter complètement
            f = tot.features
            s.point = f if it == 0 else {k: 0.5 * s.point[k] + 0.5 * f[k] for k in s.point}
        return s

    def _combo_states(self) -> tuple[int, ...]:
        """Sublimations à conversion (Dénouement) utilisables et non imposées. Leur intérêt n'apparaît qu'une fois tout
        le build basculé (maîtrises secondaires à 0, beaucoup de Maîtrise Critique) : les passes, qui avancent
        autour du build courant, ne les trouvent pas seules. On essaie donc aussi une variante qui les impose."""
        o = self.opts
        if o.no_subs or o.offense_weight <= 0:
            return ()
        out = []
        for sub in self.data.sublimations:
            st = self.data.states.get(sub.state_id)
            if (st is None or sub.state_id in out or sub.state_id in o.forced_subs or sub.state_id in o.excluded_subs
                    or not any(e.stat == CRIT_TO_ELEM for e in st.effects)
                    or o.confirmed_subs_only and not st.confirmed
                    or sub.is_epic and o.exclude_epic or sub.is_relic and o.exclude_relic):
                continue
            out.append(sub.state_id)
        return tuple(out)

    def _combo_pass(self, bm: BuildModel, s: _Search, cand: dict[Slot, list[Item]], combo: tuple[int, ...],
                    t0: float, budget: float) -> tuple[BuildModel, _Search]:
        """Variante avec la sublimation à conversion imposée ; on garde la meilleure des deux recherches."""
        best = s.best
        if best is None or any(sid in best[2].active_states for sid in combo):
            return bm, s   # déjà choisie par les passes
        self.progress("Variante avec Dénouement…", 0.6)
        opts2 = dataclasses.replace(self.opts, forced_subs=self.opts.forced_subs + combo[:1])
        bm2 = BuildModel(self.data, opts2, cand)
        s2 = self._passes(bm2, t0, budget, (0.6, 0.35))
        if s2.best is not None and s2.best[0] > best[0]:
            log.info("variante %s retenue : %.2f > %.2f", combo[0], s2.best[0], best[0])
            return bm2, s2
        return bm, s

    def _warm_start(self, bm: BuildModel, cand: dict[Slot, list[Item]], opts: OptimizeOptions, budget: float) -> None:
        """HiGHS trouve mal un premier build quand il doit aussi placer châsses, runes et sublimations,
        mais améliore très vite un build qu'on lui donne. On en construit un : items choisis sans châsses,
        puis on complète le modèle entier avec ces items fixés. Les passes suivantes partent de là."""
        self.progress("Recherche d'un premier build…", 0.04)
        small = BuildModel(self.data, opts, cand, shard_mode="none")
        small.set_linear_objective(gradient(initial_point(opts), opts))
        st, sv = self._solve(small, min(8.0, budget / 8))
        if st not in OK:
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

    def _finish(self, b: Build) -> tuple[float, Build, Totals]:
        """Sublimations des châsses restées vides et points d'aptitude sans effet, dans l'ordre du profil."""
        opts = self.opts
        b, added = fill_empty_subs(self.data, opts, b)
        if opts.char_mode != "manual" and opts.optimize_characteristics:
            filled = fill_unspent(b.characteristics, opts.level, self.data.game, opts.range, apt_profile(opts))
            added += [] if filled == b.characteristics else ["aptitudes"]
            b.characteristics = filled
        tot = evaluate(self.data, opts, b)
        return tot.score, b, tot

    def _floor_pass(self, bm: BuildModel, point: dict[str, float], budget: float, t0: float) -> Scored | None:
        """Passe avec la résistance visée imposée (plancher strict sur chaque élément)."""
        need = res_need(self.opts)
        if not need:
            return None
        self.progress("Résistance visée : passe de rattrapage…", 0.95)
        for e in ELEMENTS:
            bm.m.Add(bm.res[e] >= need)
        bm.set_linear_objective(gradient(point, self.opts))
        st, sv = self._solve(bm, max(5.0, min(20.0, budget - (time.monotonic() - t0))))
        if st not in OK:
            return None
        b = bm.extract(sv)
        tot = evaluate(self.data, self.opts, b)
        return tot.score, b, tot

    # ================================================================  résistance visée hors d'atteinte
    def _res_fallback(self, res: SolveResult, cand: dict[Slot, list[Item]], tot: Totals, t0: float,
                      budget: float) -> SolveResult:
        opts = self.opts
        if "priorities" not in opts.custom_panels and not self._relaxed:
            # cible de l'archétype (pas la vôtre) hors d'atteinte à ce niveau : on vise le maximum possible
            wanted = opts.res_target
            best_pct = self._max_res(cand, tot, t0, budget)
            self._relaxed = True
            opts.res_target = max(0, best_pct)
            opts.res_tol = min(opts.res_tol, opts.res_target)
            again = self.run()
            again.warnings.insert(0, f"Résistance visée par l'archétype ({wanted} %) impossible au niveau {opts.level} : "
                                     f"visée abaissée à {opts.res_target} %, le maximum atteignable.")
            return again
        # résistance visée (la vôtre) non atteinte : on n'affiche pas un build qui ne respecte pas la demande
        return self._res_unreachable(res, cand, tot, t0, budget)

    def _max_res(self, cand: dict[Slot, list[Item]], tot: Totals, t0: float, budget: float) -> int:
        """Meilleure résistance (%) atteignable sur l'élément le plus faible, avec les autres contraintes."""
        self.progress("Résistance visée non atteinte : recherche du maximum possible…", 0.97)
        best = min(tot.res_pct.values())
        try:
            probe = BuildModel(self.data, self.opts, cand, skip_constraints={"res"})
            if WARM_START:
                self._warm_start(probe, cand, self.opts, budget)
            rmin = probe.m.NewIntVar(-BIG, BIG, "Rmin_brut")
            probe.m.AddMinEquality(rmin, [probe.res[e] for e in ELEMENTS])
            probe.maximize(rmin)
            st, sv = self._solve(probe, max(5.0, min(20.0, budget - (time.monotonic() - t0))))
            if st in OK:
                best = max(best, res_pct(sv.Value(rmin)))
        except Cancelled:
            pass
        return best

    def _res_unreachable(self, res: SolveResult, cand: dict[Slot, list[Item]], tot: Totals, t0: float,
                         budget: float) -> SolveResult:
        """Résistance visée impossible : on cherche la meilleure résistance atteignable (sur l'élément le plus faible)."""
        opts = self.opts
        best = self._max_res(cand, tot, t0, budget)
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

    # ================================================================  diagnostic (aucune solution)
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
            relaxed.maximize(relaxed.res["fire"] if stat == "res" else relaxed.stat(stat))
            try:
                st, sv = self._solve(relaxed, 4.0)
            except Cancelled:
                break
            if st in OK:
                best = sv.Value(relaxed.stat(stat)) if stat != "res" else None
                extra = f" (maximum atteignable avec les autres contraintes : {best})" if best is not None else ""
                diag.append(f"Contrainte bloquante : {labels.get(stat, stat)} ≥ {val}{extra}")
        if self.opts.forced_subs:
            diag.append("Vérifiez aussi les sublimations imposées (onglet Sublimations) : leurs couleurs ou "
                        "leurs conditions (ex. maîtrises secondaires à 0 ou moins, % critique) peuvent bloquer.")
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


def optimize(data: GameData, opts: OptimizeOptions, progress: ProgressFn | None = None) -> SolveResult:
    return Optimizer(data, opts, progress).run()


__all__ = ["Optimizer", "SolveResult", "optimize", "Cancelled"]
