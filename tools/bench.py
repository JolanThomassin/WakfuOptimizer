"""Banc d'essai du calcul : à lancer avant et après un changement du score, du modèle, des passes ou de l'élagage.

    python tools/bench.py --save avant.json          # référence : chaque scénario résolu (30 s max chacun)
    python tools/bench.py --compare avant.json       # mêmes scénarios : score, temps, statut et écarts
    python tools/bench.py --model --save m.json      # empreinte des modèles, sans résoudre (rapide) : un refactor
    python tools/bench.py --model --compare m.json   #   qui ne change rien doit la garder identique (OR-Tools)

Options : --time 30 (durée max par scénario), --full (plus de scénarios), --only cra (filtre sur le nom),
--workers 8. Avec --compare, le build de la référence est aussi réévalué avec le code actuel (colonne « réf. ») :
un écart sur cette colonne vient du score lui-même, un écart sur le nouveau build vient du solveur.
Les scores varient un peu d'un lancement à l'autre (CP-SAT multi-fils, limite de temps) : ±0,5 est du bruit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wakfu_optimizer.data.fetch import DEFAULT_CACHE_ROOT, DataBundle, GameDataFetcher  # noqa: E402
from wakfu_optimizer.data.models import GameData  # noqa: E402
from wakfu_optimizer.data.parse import load_game_data  # noqa: E402
from wakfu_optimizer.engine.archetypes import archetype_options  # noqa: E402
from wakfu_optimizer.engine.features import initial_point  # noqa: E402
from wakfu_optimizer.engine.model import BuildModel  # noqa: E402
from wakfu_optimizer.engine.options import Build, OptimizeOptions  # noqa: E402
from wakfu_optimizer.engine.scoring import gradient  # noqa: E402
from wakfu_optimizer.engine.solver import Optimizer, SolveResult  # noqa: E402
from wakfu_optimizer.engine.stats import evaluate  # noqa: E402

# (classe, niveau, archétype, réglages en plus de l'archétype)
QUICK: list[tuple[str, int, str, dict[str, Any]]] = [
    ("cra", 140, "dps_distance", {}),
    ("pandawa", 200, "tank", {}),
    ("sram", 245, "dps_rear", {}),
    ("eniripsa", 170, "heal", {}),
    ("xelor", 230, "support_debuff", {}),
    ("iop", 245, "dps_melee", {"no_subs": False}),
]
FULL = QUICK + [
    ("sacrier", 110, "berserk", {}),
    ("huppermage", 200, "dps_mixed", {}),
    ("feca", 50, "support_buff", {}),
    ("rogue", 245, "dps_distance", {}),
    ("pandawa", 65, "tank", {}),
    ("iop", 20, "dps_melee", {}),
    ("iop", 245, "dps_melee", {"no_subs": False, "forced_subs": [5077]}),
    ("iop", 245, "dps_melee", {"no_subs": False, "shard_mode": "mine",
                               "my_colors": {"HEAD": [1, 2, 3, 0], "CHEST": [3, 3, 3], "FIRST_WEAPON": [1, 1, 2, 2]}}),
    ("ecaflip", 200, "dps_melee", {"min_res_pct": 40, "char_mode": "manual",
                                   "manual_chars": {"major.ap": 1, "strength.hp": 20}}),
]


def load_data() -> GameData:
    fetcher = GameDataFetcher(cache_root=Path(os.environ.get("WAKFU_OPTIMIZER_CACHE", DEFAULT_CACHE_ROOT)))
    versions = fetcher.cached_versions()
    if not versions:
        raise SystemExit("Données Ankama absentes : python -m wakfu_optimizer.data.fetch")
    return load_game_data(DataBundle(versions[0], fetcher.cache_root / versions[0], offline=True))


def scenarios(full: bool, only: str) -> list[tuple[str, tuple[str, int, str, dict[str, Any]]]]:
    out = []
    for sc in FULL if full else QUICK:
        cls, lvl, arch, extra = sc
        name = f"{cls}-{lvl}-{arch}" + "".join(f"-{k}" for k in extra if k not in ("no_subs", "my_colors", "manual_chars"))
        if only in name:
            out.append((name, sc))
    return out


def options(data: GameData, sc: tuple[str, int, str, dict[str, Any]], seconds: float, workers: int) -> OptimizeOptions:
    cls, lvl, arch, extra = sc
    return archetype_options(data, cls, lvl, arch, time_limit=seconds, workers=workers, **extra)


def fingerprint(data: GameData, o: OptimizeOptions) -> dict[str, str]:
    """Candidats, modèle complet (objectif de la première passe compris) et gradient : rien n'est résolu."""
    cand = Optimizer(data, o)._prepare(SolveResult())   # options corrigées comme pour un vrai calcul
    bm = BuildModel(data, o, cand)
    grad = gradient(initial_point(o), o)
    bm.set_linear_objective(grad)
    h = lambda s: hashlib.sha256(s.encode()).hexdigest()[:16]  # noqa: E731
    return {"candidats": h(json.dumps([[s.value, [i.id for i in v]] for s, v in cand.items()])),
            "modèle": h(str(bm.m.Proto())),
            "gradient": h(json.dumps({k: round(v, 9) for k, v in grad.items()}, sort_keys=True))}


def solve(data: GameData, o: OptimizeOptions) -> dict[str, Any]:
    t0 = time.monotonic()
    r = Optimizer(data, o).run()
    out: dict[str, Any] = {"status": r.status, "elapsed": round(time.monotonic() - t0, 1), "score": None}
    if r.builds:
        t = r.totals[0]
        out.update(score=round(t.score, 2), build=r.builds[0].to_dict(),
                   summary=f"PA {t.stats.get('ap')} PM {t.stats.get('mp')} crit {t.stats.get('crit_rate')} % "
                           f"rés. {min(t.res_pct.values())} % PV {t.hp}")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--save", type=Path)
    p.add_argument("--compare", type=Path)
    p.add_argument("--model", action="store_true", help="empreinte des modèles, sans résoudre")
    p.add_argument("--full", action="store_true")
    p.add_argument("--only", default="")
    p.add_argument("--time", type=float, default=30.0)
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args()
    data = load_data()
    ref = json.loads(a.compare.read_text(encoding="utf-8")) if a.compare else {}
    results: dict[str, Any] = {}
    diffs = 0
    for name, sc in scenarios(a.full, a.only):
        o = options(data, sc, a.time, a.workers)
        if a.model:
            fp = results[name] = fingerprint(data, o)
            old = ref.get(name)
            bad = [k for k in fp if old and old.get(k) != fp[k]]
            diffs += bool(bad)
            print(f"{name:<44} {'DIFFÉRENT : ' + ', '.join(bad) if bad else 'identique' if old else 'ok'}", flush=True)
            continue
        r = results[name] = solve(data, o)
        line = f"{name:<44} {r['score'] if r['score'] is not None else '—':>8} {r['elapsed']:>6} s  {r['status']}"
        old = ref.get(name)
        if old:
            again = None
            if old.get("build"):   # build de la référence, évalué avec le code (et les options finales) d'aujourd'hui
                again = round(evaluate(data, o, Build.from_dict(old["build"])).score, 2)
            d = (r["score"] or 0) - (old.get("score") or 0)
            diffs += abs(d) > 0.5
            line += f"   réf. {old.get('score')} ({old.get('elapsed')} s)" + (f", réévalué {again}" if again is not None else "")
            line += f"   Δ {d:+.2f}"
        print(line, flush=True)
        if r.get("summary"):
            print(f"{'':<44} {r['summary']}", flush=True)
    if a.save:
        a.save.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"Enregistré : {a.save}")
    if a.compare:
        print(f"{diffs} scénario(s) différent(s) de la référence." if diffs else "Aucun écart notable avec la référence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
