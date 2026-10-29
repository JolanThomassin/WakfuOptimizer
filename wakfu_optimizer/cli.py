"""Optimisation en ligne de commande.

    python -m wakfu_optimizer.cli --classe iop --niveau 245 --elements fire earth air --melee
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from .data.fetch import DataUnavailableError, GameDataFetcher
from .data.parse import load_game_data
from .engine.options import OptimizeOptions, default_min_ap, default_min_mp
from .engine.report import build_json, build_text
from .engine.solver import optimize


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Optimiseur de build Wakfu (CP-SAT)")
    p.add_argument("--classe", default="iop")
    p.add_argument("--niveau", type=int, default=245)
    p.add_argument("--elements", nargs="+", default=None, help="fire water earth air")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--melee", action="store_true")
    g.add_argument("--distance", action="store_true")
    p.add_argument("--dos", action="store_true")
    p.add_argument("--berserk", action="store_true")
    p.add_argument("--soin", action="store_true")
    p.add_argument("--offense", type=int, default=70, help="poids offensif 0-100")
    p.add_argument("--pa", type=int, default=None)
    p.add_argument("--pm", type=int, default=None)
    p.add_argument("--po", type=int, default=0)
    p.add_argument("--chasses", choices=["ideal", "none"], default="ideal")
    p.add_argument("--temps", type=float, default=30.0)
    p.add_argument("--alternatives", type=int, default=0)
    p.add_argument("--json", type=Path, help="écrire le résultat en JSON")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        bundle = GameDataFetcher().ensure()
    except DataUnavailableError as exc:
        logging.error("%s", exc)
        return 1
    data = load_game_data(bundle)
    cls = data.classes[a.classe]
    o = OptimizeOptions(
        class_key=a.classe, level=a.niveau, elements=tuple(a.elements or cls.elements),
        range="distance" if a.distance else "melee" if a.melee else cls.range,
        rear=a.dos, berserk=a.berserk, heal=a.soin, offense_weight=a.offense,
        min_ap=default_min_ap(a.niveau) if a.pa is None else a.pa,
        min_mp=default_min_mp(a.niveau) if a.pm is None else a.pm, min_range=a.po,
        shard_mode=a.chasses, time_limit=a.temps, alternatives=a.alternatives,
    )
    res = optimize(data, o, progress=lambda msg, f: logging.info("%3.0f %% %s", f * 100, msg))
    if not res.builds:
        logging.error("%s", res.message)
        return 2
    for w in res.warnings:
        logging.warning("%s", w)
    print(build_text(data, o, res.builds[0], res.totals[0], res.scores[0]))  # noqa: T201 (sortie CLI)
    for k, (sc, _t) in enumerate(zip(res.scores[1:], res.totals[1:]), start=1):
        print(f"\nAlternative {k} : score {sc:.1f} ({sc - res.scores[0]:+.1f})")  # noqa: T201
    if a.json:
        a.json.write_text(build_json(data, o, res.builds[0], res.totals[0], res.scores[0]), encoding="utf-8")
    logging.info("%s", res.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
