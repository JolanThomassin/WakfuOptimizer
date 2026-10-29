"""Tests du remplaçant HiGHS de CP-SAT (utilisé par la version navigateur)."""

from __future__ import annotations

import pytest

pytest.importorskip("highspy")

from wakfu_optimizer.engine import milp  # noqa: E402


def solve(m: milp.CpModel) -> milp.CpSolver:
    s = milp.CpSolver()
    assert s.Solve(m) == milp.OPTIMAL
    return s


def test_min_max_element() -> None:
    m = milp.CpModel()
    x = m.NewIntVar(0, 10, "x")
    y = m.NewIntVar(0, 10, "y")
    lo = m.NewIntVar(-100, 100, "lo")
    hi = m.NewIntVar(-100, 100, "hi")
    m.AddMinEquality(lo, [x, y, 7])
    m.AddMaxEquality(hi, [x, y])
    m.Add(x + y == 12)
    m.Add(x >= 9)
    v = m.NewIntVar(0, 100, "v")
    m.AddElement(y, [5, 40, 20, 30], v)
    m.Maximize(lo + v)
    s = solve(m)
    # x = 9..10, y = 2..3 ; v = table[y] -> y = 3 (30), lo = min(9, 3, 7) = 3
    assert (s.Value(x), s.Value(y), s.Value(lo), s.Value(hi), s.Value(v)) == (9, 3, 3, 9, 30)


def test_infaisable() -> None:
    m = milp.CpModel()
    bs = [m.NewBoolVar(f"b{i}") for i in range(3)]
    m.AddExactlyOne(bs)
    m.Add(sum(bs) >= 2)
    assert milp.CpSolver().Solve(m) == milp.INFEASIBLE
