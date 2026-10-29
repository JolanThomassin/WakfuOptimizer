"""Solveur utilisé : OR-Tools CP-SAT quand il est installé, sinon HiGHS (navigateur) derrière la même API (milp.py).

`WAKFU_SOLVER=highs` force HiGHS hors navigateur (pour tester la version en ligne : `WAKFU_SOLVER=highs pytest`).
"""

from __future__ import annotations

import os

try:
    if os.environ.get("WAKFU_SOLVER") == "highs":
        raise ImportError
    from ortools.sat.python import cp_model
except ImportError:
    from . import milp as cp_model  # type: ignore[no-redef]

# HiGHS trouve mal un premier build seul : on lui en construit un (voir Optimizer._warm_start)
WARM_START = cp_model.__name__.endswith("milp")

__all__ = ["cp_model", "WARM_START"]
