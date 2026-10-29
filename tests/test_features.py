"""Variables du score : mêmes noms partout (scoring.FEATURES, évaluateur, modèle, point de départ, gradient).

Voir engine/features.py : ajouter une variable du score demande de toucher ces cinq endroits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wakfu_optimizer.data.fetch import DataBundle
from wakfu_optimizer.data.models import GameData
from wakfu_optimizer.data.parse import load_game_data
from wakfu_optimizer.engine.archetypes import ARCHETYPES
from wakfu_optimizer.engine.features import initial_point
from wakfu_optimizer.engine.options import Build, OptimizeOptions
from wakfu_optimizer.engine.scoring import FEATURES, gradient, score_parts
from wakfu_optimizer.engine.stats import evaluate

FIXTURES = Path(__file__).parent / "fixtures" / "gamedata"


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_game_data(DataBundle("fixture", FIXTURES, offline=True))


def variants() -> list[OptimizeOptions]:
    out = [OptimizeOptions(), OptimizeOptions(crit=False, rear=True, heal=True, willpower_weight=40, crit_target=30)]
    out += [OptimizeOptions(archetype=k, offense_weight=a.offense, willpower_weight=a.will, crit=a.crit)
            for k, a in ARCHETYPES.items()]
    return out


def test_point_de_depart_et_gradient() -> None:
    for o in variants():
        p = initial_point(o)
        assert set(p) == set(FEATURES)
        assert set(gradient(p, o)) == set(FEATURES)
        score_parts(p, o)   # toutes les variables lues par le score existent


def test_evaluateur(data: GameData) -> None:
    for o in variants():
        assert set(evaluate(data, o, Build()).features) == set(FEATURES)


def test_modele(data: GameData) -> None:
    pytest.importorskip("ortools")
    from wakfu_optimizer.engine.candidates import select_candidates
    from wakfu_optimizer.engine.model import BuildModel

    for o in variants():
        cand, _ = select_candidates(data, o)
        feat = BuildModel(data, o, cand, shard_mode="none").feat
        unknown = set(feat) - set(FEATURES) - {"res4"}   # res4 : somme des 4 résistances (évaluateur : moyenne)
        assert not unknown, f"variables du modèle absentes de scoring.FEATURES : {unknown}"
