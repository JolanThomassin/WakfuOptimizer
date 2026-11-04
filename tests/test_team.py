"""Team Builder (engine/team.py) : équipes complètes, cohérentes, autour des personnages choisis."""

from __future__ import annotations

from pathlib import Path

import pytest

from wakfu_optimizer.data.fetch import DataBundle
from wakfu_optimizer.data.models import GameData
from wakfu_optimizer.data.parse import load_game_data
from wakfu_optimizer.engine.archetypes import class_archetypes
from wakfu_optimizer.engine.team import TRAITS, compose, team_view
from wakfu_optimizer.web.views import ROUTES

FIXTURES = Path(__file__).parent / "fixtures" / "gamedata"


@pytest.fixture(scope="module")
def data() -> GameData:
    return load_game_data(DataBundle("fixture", FIXTURES, offline=True))


def test_traits_de_classe_connus(data: GameData) -> None:
    for key, spec in data.game["classes"].items():
        assert set(spec.get("team") or []) <= set(TRAITS), key


@pytest.mark.parametrize("size", [3, 6])
def test_equipe_complete_sans_doublon(data: GameData, size: int) -> None:
    picks = [{"class": "iop", "archetype": "dps_melee"}, {"class": "cra", "archetype": "auto"}]
    teams = compose(data, picks, size)
    assert len(teams) == 3
    for team in teams:
        assert len(team) == size
        classes = [m.class_key for m in team]
        assert len(set(classes)) == size
        assert {"iop", "cra"} <= set(classes)
        iop = next(m for m in team if m.class_key == "iop")
        assert iop.archetype == "dps_melee" and iop.fixed
        cra = next(m for m in team if m.class_key == "cra")
        assert cra.archetype in class_archetypes(data, "cra")
        # membres proposés : un archétype que la classe joue d'habitude
        assert all(m.archetype in class_archetypes(data, m.class_key) for m in team if not m.fixed)


def test_equipe_de_six_equilibree(data: GameData) -> None:
    team = team_view(data, {"picks": [], "size": 6, "style": "balanced"})["teams"][0]
    assert team["roles"]["tank"] >= 1 and team["roles"]["heal"] >= 1 and team["roles"]["dps"] >= 2
    assert not team["warnings"]


def test_styles(data: GameData) -> None:
    def roles(style: str) -> dict[str, float]:
        return team_view(data, {"picks": [{"class": "sram"}], "size": 3, "style": style})["teams"][0]["roles"]
    assert roles("offense")["dps"] >= roles("defense")["dps"]
    assert roles("defense")["tank"] + roles("defense")["heal"] >= roles("offense")["tank"] + roles("offense")["heal"]


def test_route(data: GameData) -> None:
    r = ROUTES[("POST", "/api/team")](data, {}, {"picks": [{"class": "eniripsa", "archetype": "heal"}], "size": 3})
    assert r["size"] == 3 and r["teams"][0]["members"][0]["class"] == "eniripsa"
