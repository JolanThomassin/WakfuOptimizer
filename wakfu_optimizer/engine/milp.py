"""Sous-ensemble de l'API CP-SAT (``ortools.sat.python.cp_model``) résolu par HiGHS (``highspy``).

OR-Tools n'existe pas dans le navigateur (Pyodide) ; HiGHS, si. Seules les méthodes utilisées par
``solver.py`` sont fournies. Les contraintes non linéaires (min, max, élément) sont linéarisées
avec des variables binaires et des grands M calculés à partir des bornes des variables.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import highspy  # type: ignore[import-untyped]
import numpy as np

UNKNOWN, MODEL_INVALID, FEASIBLE, INFEASIBLE, OPTIMAL = 0, 1, 2, 3, 4


# =====================================================================  expressions
class LinearExpr:
    """Expression linéaire paresseuse : ``sum()`` sur des milliers de termes reste en O(n)."""

    __slots__ = ()

    def __add__(self, o: Any) -> LinearExpr:
        return _Sum(self, o, 1)

    __radd__ = __add__

    def __sub__(self, o: Any) -> LinearExpr:
        return _Sum(self, o, -1)

    def __rsub__(self, o: Any) -> LinearExpr:
        return _Sum(_Scale(self, -1), o, 1)

    def __mul__(self, c: Any) -> LinearExpr:
        if isinstance(c, LinearExpr):
            raise TypeError("produit de deux expressions : non linéaire")
        return _Scale(self, c)

    __rmul__ = __mul__

    def __neg__(self) -> LinearExpr:
        return _Scale(self, -1)

    def __le__(self, o: Any) -> _Bounded:
        return _Bounded(self - o, None, 0)

    def __ge__(self, o: Any) -> _Bounded:
        return _Bounded(self - o, 0, None)

    def __eq__(self, o: Any) -> _Bounded:  # type: ignore[override]
        return _Bounded(self - o, 0, 0, pair=(self, o))

    __hash__ = object.__hash__


class IntVar(LinearExpr):
    __slots__ = ("index", "name")

    def __init__(self, index: int, name: str) -> None:
        self.index, self.name = index, name

    def __repr__(self) -> str:
        return self.name


class _Sum(LinearExpr):
    __slots__ = ("a", "b", "sign")

    def __init__(self, a: Any, b: Any, sign: int) -> None:
        self.a, self.b, self.sign = a, b, sign


class _Scale(LinearExpr):
    __slots__ = ("e", "c")

    def __init__(self, e: Any, c: Any) -> None:
        self.e, self.c = e, c


class _Bounded:
    """Contrainte ``lo <= expr <= hi`` (renvoyée par <=, >=, ==)."""

    def __init__(self, expr: LinearExpr, lo: float | None, hi: float | None, pair: tuple[Any, Any] | None = None) -> None:
        self.expr, self.lo, self.hi, self.pair = expr, lo, hi, pair

    def __bool__(self) -> bool:  # ``x == y`` hors d'un Add (ex. ``in``) : comparaison d'identité
        if self.pair is not None:
            return self.pair[0] is self.pair[1]
        raise TypeError("contrainte utilisée comme booléen")


def flatten(e: Any) -> tuple[dict[int, float], float]:
    coefs: dict[int, float] = {}
    const = 0.0
    stack: list[tuple[Any, float]] = [(e, 1.0)]
    while stack:
        x, c = stack.pop()
        if isinstance(x, IntVar):
            coefs[x.index] = coefs.get(x.index, 0.0) + c
        elif isinstance(x, _Sum):
            stack.append((x.a, c))
            stack.append((x.b, c * x.sign))
        elif isinstance(x, _Scale):
            stack.append((x.e, c * x.c))
        elif isinstance(x, (int, float, np.integer, np.floating)):
            const += float(c * x)
        else:
            raise TypeError(f"terme inattendu : {x!r}")
    return {k: v for k, v in coefs.items() if v}, const


# =====================================================================  modèle
class CpModel:
    def __init__(self) -> None:
        self.lb: list[float] = []
        self.ub: list[float] = []
        self.names: list[str] = []
        self.rows: list[tuple[dict[int, float], float, float]] = []
        self.objective: dict[int, float] = {}
        self.hints: dict[int, float] = {}
        self.incumbent: np.ndarray | None = None   # dernière solution trouvée (point de départ suivant)

    # ------------------------------------------------------------ variables
    def NewIntVar(self, lo: int, hi: int, name: str) -> IntVar:  # noqa: N802
        self.lb.append(float(lo))
        self.ub.append(float(hi))
        self.names.append(name)
        return IntVar(len(self.lb) - 1, name)

    def NewBoolVar(self, name: str) -> IntVar:  # noqa: N802
        return self.NewIntVar(0, 1, name)

    def bounds(self, e: Any) -> tuple[float, float]:
        coefs, const = flatten(e)
        lo = hi = const
        for i, c in coefs.items():
            a, b = c * self.lb[i], c * self.ub[i]
            lo += min(a, b)
            hi += max(a, b)
        return lo, hi

    # ---------------------------------------------------------- contraintes
    def _row(self, e: Any, lo: float | None, hi: float | None) -> None:
        coefs, const = flatten(e)
        lo_ = -np.inf if lo is None else lo - const
        hi_ = np.inf if hi is None else hi - const
        if not coefs:
            if lo_ > 1e-9 or hi_ < -1e-9:
                self.rows.append(({}, lo_, hi_))  # contrainte constante fausse : modèle infaisable
            return
        if len(coefs) == 1:  # borne simple : on resserre la variable
            (i, c), = coefs.items()
            a, b = (lo_ / c, hi_ / c) if c > 0 else (hi_ / c, lo_ / c)
            self.lb[i] = max(self.lb[i], np.ceil(a - 1e-9))
            self.ub[i] = min(self.ub[i], np.floor(b + 1e-9))
            return
        self.rows.append((coefs, lo_, hi_))

    def Add(self, ct: _Bounded | bool) -> None:  # noqa: N802
        if isinstance(ct, bool):
            if not ct:
                self.rows.append(({}, 1.0, 1.0))
            return
        self._row(ct.expr, ct.lo, ct.hi)

    def AddAtMostOne(self, xs: list[Any]) -> None:  # noqa: N802
        if xs:
            self._row(sum(xs), None, 1)

    def AddExactlyOne(self, xs: list[Any]) -> None:  # noqa: N802
        self._row(sum(xs), 1, 1)

    def AddMinEquality(self, target: IntVar, args: list[Any]) -> None:  # noqa: N802
        self._extremum(target, args, sign=1)

    def AddMaxEquality(self, target: IntVar, args: list[Any]) -> None:  # noqa: N802
        self._extremum(target, args, sign=-1)

    def _extremum(self, target: IntVar, args: list[Any], sign: int) -> None:
        """target = min(args) (sign=1) ou max(args) (sign=-1), via min(-args) pour le max."""
        terms = [sign * a for a in args]
        t = sign * target
        bnds = [self.bounds(a) for a in terms]
        floor_ = min(lo for lo, _ in bnds)        # borne inférieure du minimum
        ceil_ = min(hi for _, hi in bnds)         # borne supérieure du minimum
        # arguments jamais minimaux : leur borne basse dépasse la borne haute du minimum
        live = [(a, b) for a, b in zip(terms, bnds) if b[0] <= ceil_]
        lo_t, hi_t = (floor_, ceil_) if sign == 1 else (-ceil_, -floor_)
        self.lb[target.index] = max(self.lb[target.index], np.ceil(lo_t - 1e-9))
        self.ub[target.index] = min(self.ub[target.index], np.floor(hi_t + 1e-9))
        for a in terms:
            self._row(t - a, None, 0)             # t <= a_i
        if len(live) == 1:
            self._row(t - live[0][0], 0, 0)
            return
        sel = []
        for a, (_lo, hi) in live:
            b = self.NewBoolVar("sel")
            big = hi - floor_
            self._row(t - a - big * b, -big, None)  # b = 1  =>  t >= a_i
            sel.append(b)
        self._row(sum(sel), 1, 1)

    def AddElement(self, index: IntVar, table: list[int], target: IntVar) -> None:  # noqa: N802
        lo = max(0, int(self.lb[index.index]))
        hi = min(len(table) - 1, int(self.ub[index.index]))
        ks = range(lo, hi + 1)
        es = [self.NewBoolVar(f"el_{k}") for k in ks]
        self._row(sum(es), 1, 1)
        self._row(index - sum(k * e for k, e in zip(ks, es)), 0, 0)
        self._row(target - sum(table[k] * e for k, e in zip(ks, es)), 0, 0)

    # ------------------------------------------------------------- objectif
    def Maximize(self, e: Any) -> None:  # noqa: N802
        self.objective, _ = flatten(e)

    def ClearObjective(self) -> None:  # noqa: N802
        self.objective = {}

    clear_objective = ClearObjective

    def AddHint(self, var: IntVar, value: Any) -> None:  # noqa: N802
        self.hints[var.index] = float(value)

    def ClearHints(self) -> None:  # noqa: N802
        self.hints = {}

    # ----------------------------------------------------------- conversion
    def to_highs(self) -> highspy.HighsLp:
        n = len(self.lb)
        lp = highspy.HighsLp()
        lp.num_col_, lp.num_row_ = n, len(self.rows)
        cost = np.zeros(n)
        for i, c in self.objective.items():
            cost[i] = c
        lp.col_cost_ = cost
        lp.col_lower_ = np.array(self.lb, dtype=float)
        lp.col_upper_ = np.array(self.ub, dtype=float)
        lp.row_lower_ = np.array([lo for _, lo, _ in self.rows], dtype=float)
        lp.row_upper_ = np.array([hi for _, _, hi in self.rows], dtype=float)
        start: list[int] = [0]
        index: list[int] = []
        value: list[float] = []
        for coefs, _, _ in self.rows:
            index.extend(coefs.keys())
            value.extend(coefs.values())
            start.append(len(index))
        a = lp.a_matrix_
        a.format_ = highspy.MatrixFormat.kRowwise
        a.num_row_, a.num_col_ = lp.num_row_, n
        a.start_ = np.array(start, dtype=np.int32)
        a.index_ = np.array(index, dtype=np.int32)
        a.value_ = np.array(value, dtype=float)
        lp.integrality_ = [highspy.HighsVarType.kInteger] * n
        lp.sense_ = highspy.ObjSense.kMaximize
        return lp


# =====================================================================  solveur
class CpSolver:
    def __init__(self) -> None:
        self.parameters = SimpleNamespace(max_time_in_seconds=10.0, num_search_workers=1, random_seed=0,
                                          relative_gap_limit=1e-4, fix_variables_to_their_hinted_value=False)
        self._values: np.ndarray = np.zeros(0)
        self._highs: highspy.Highs | None = None
        self.wall_time = 0.0

    def Solve(self, model: CpModel) -> int:  # noqa: N802
        t0 = time.monotonic()
        h = highspy.Highs()
        self._highs = h
        h.setOptionValue("output_flag", False)
        h.setOptionValue("time_limit", float(self.parameters.max_time_in_seconds))
        h.setOptionValue("mip_rel_gap", float(self.parameters.relative_gap_limit))
        h.setOptionValue("random_seed", int(self.parameters.random_seed))
        lp = model.to_highs()
        fix = bool(self.parameters.fix_variables_to_their_hinted_value) and model.hints
        if fix:
            lo, hi = np.array(lp.col_lower_), np.array(lp.col_upper_)
            for i, v in model.hints.items():
                lo[i] = hi[i] = v
            lp.col_lower_, lp.col_upper_ = lo, hi
        h.passModel(lp)
        # Point de départ : le dernier build trouvé sur ce modèle (seul l'objectif change d'une passe à l'autre).
        # HiGHS trouve mal une première solution (châsses, runes, sublimations) mais améliore vite une solution donnée.
        if not fix and model.incumbent is not None and len(model.incumbent) == len(model.lb):
            sol = highspy.HighsSolution()
            sol.col_value = model.incumbent
            sol.value_valid = True
            h.setSolution(sol)
        h.run()
        self.wall_time = time.monotonic() - t0
        status = h.getModelStatus()
        has_sol = h.getInfo().primal_solution_status == 2
        if has_sol:
            self._values = np.round(np.array(h.getSolution().col_value))
            model.incumbent = self._values.copy()
        if status == highspy.HighsModelStatus.kOptimal:
            return OPTIMAL
        if status == highspy.HighsModelStatus.kInfeasible:
            return INFEASIBLE
        return FEASIBLE if has_sol else UNKNOWN

    def Value(self, e: Any) -> int:  # noqa: N802
        coefs, const = flatten(e)
        return int(round(const + sum(c * self._values[i] for i, c in coefs.items())))

    def BooleanValue(self, e: Any) -> bool:  # noqa: N802
        return bool(self.Value(e))

    def stop_search(self) -> None:
        pass  # HiGHS tourne dans le même fil : l'annulation est gérée par l'appelant

    StopSearch = stop_search
