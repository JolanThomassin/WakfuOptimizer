"""Qualité des builds : un build obtenu avec le seul panneau Personnage (classe, niveau, archétype) doit avoir du sens.

Trois niveaux de tests :
  * profils d'aptitudes et options d'archétype (sans solveur, toujours lancés) ;
  * scénarios clés sur les vraies données (solveur, `pytest` par défaut) : cas signalés (Crâ 140 DPS distance à 22 %
    de critique, Pandawa tank avec du critique et de la maîtrise mêlée en aptitudes) et un scénario par archétype ;
  * matrice complète (`pytest --quality=full`) : chaque classe × archétype habituel × niveau.

Les règles sont celles de engine/quality.py, affichées aussi dans l'onglet Explication du site.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from wakfu_optimizer.data.fetch import DEFAULT_CACHE_ROOT, DataBundle, GameDataFetcher
from wakfu_optimizer.data.models import GameData
from wakfu_optimizer.data.parse import load_game_data
from wakfu_optimizer.engine.archetypes import (ARCHETYPES, PANELS, apt_profile, archetype_options, class_archetypes,
                                               crit_target, preset, profile_points)
from wakfu_optimizer.engine.characteristics import branch_points, char_lines, fill_unspent
from wakfu_optimizer.engine.options import default_min_ap, default_min_mp
from wakfu_optimizer.engine.quality import check_aptitudes, check_build, explain, failures

LEVELS = (20, 50, 80, 110, 140, 170, 200, 230, 245)
QUALITY_TIME = float(os.environ.get("WAKFU_QUALITY_TIME", "30"))


@pytest.fixture(scope="session")
def data() -> GameData:
    fetcher = GameDataFetcher(cache_root=os.environ.get("WAKFU_OPTIMIZER_CACHE", DEFAULT_CACHE_ROOT))  # type: ignore[arg-type]
    versions = fetcher.cached_versions()
    if not versions:
        pytest.skip("données Ankama absentes : python -m wakfu_optimizer.data.fetch")
    return load_game_data(DataBundle(versions[0], fetcher.cache_root / versions[0], offline=True))


def all_cases(data: GameData) -> list[tuple[str, str]]:
    return [(c, a) for c in sorted(data.classes) for a in class_archetypes(data, c)]


def explain_failures(checks: list[Any]) -> str:
    return "\n".join(str(c) for c in checks)


# =====================================================================  archétypes (sans solveur)
def test_chaque_classe_a_des_archetypes_habituels(data: GameData) -> None:
    for key in data.classes:
        spec = data.game["classes"][key]  # type: ignore[index]
        assert spec.get("archetypes"), f"{key} : aucun archétype habituel dans game.yaml"
        unknown = [a for a in spec["archetypes"] if a not in ARCHETYPES]
        assert not unknown, f"{key} : archétypes inconnus {unknown}"


def test_options_crâ_dps_distance(data: GameData) -> None:
    o = archetype_options(data, "cra", 140, "dps_distance")
    assert o.range == "distance" and o.crit
    assert o.crit_target == crit_target(140) >= 30
    assert (o.min_ap, o.min_mp) == (default_min_ap(140), default_min_mp(140))
    assert o.shard_mode == "ideal" and o.no_subs and len(o.allowed_rarities) == 8   # panneau Sublimations désactivé


def test_options_tank_sans_critique(data: GameData) -> None:
    o = archetype_options(data, "pandawa", 140, "tank")
    assert not o.crit and o.crit_target == 0
    assert o.res_free and o.offense_weight == 0


def test_poids_pm_du_tank(data: GameData) -> None:
    """Un tank se place et porte : ses PM valent plus que ceux d'un DPS."""
    from wakfu_optimizer.engine.scoring import utility_table

    tank = utility_table(archetype_options(data, "pandawa", 200, "tank"))
    dps = utility_table(archetype_options(data, "pandawa", 200, "dps_melee"))
    assert tank["mp"][0] > dps["mp"][0] and tank["ap"] == dps["ap"]


def test_palier_critique_croissant() -> None:
    vals = [crit_target(L) for L in range(1, 246)]
    assert vals == sorted(vals)
    assert vals[0] >= 10 and vals[-1] == 50


def test_roublard_garde_sa_meilleure_maitrise(data: GameData) -> None:
    for a in class_archetypes(data, "rogue"):
        assert archetype_options(data, "rogue", 200, a).range == "best"


@pytest.mark.parametrize("level", LEVELS)
def test_aptitudes_rapides_coherentes(data: GameData, level: int) -> None:
    """Les aptitudes rapides de chaque archétype placent tous les points, sans ligne absurde pour le rôle."""
    for cls, arch in all_cases(data) + [("iop", a) for a in ARCHETYPES]:
        o = archetype_options(data, cls, level, arch)
        pts = preset(data, arch, cls, level)
        bad = failures(check_aptitudes(data, o, pts))
        assert not bad, f"{cls} {arch} niv. {level} :\n{explain_failures(bad)}"
        maxes = {cl.key: cl.max_points for cl in char_lines(data.game)}
        assert all(maxes[k] is None or n <= maxes[k] for k, n in pts.items())  # type: ignore[operator]


def test_profil_tank(data: GameData) -> None:
    prof = apt_profile(archetype_options(data, "pandawa", 140, "tank"))
    assert prof["strength"] == ["hp"]
    assert "crit_rate" not in prof["fortune"] and prof["fortune"][0] == "block"
    assert "ap" in prof["major"] and "elem_res" in prof["major"]


def test_profil_dps_distance(data: GameData) -> None:
    prof = apt_profile(archetype_options(data, "cra", 140, "dps_distance"))
    assert prof["strength"][0] == "distance_mastery" and "melee_mastery" not in prof["strength"]
    assert prof["fortune"][:2] == ["crit_rate", "crit_mastery"]
    assert prof["agility"][0] == "dodge"


def test_profil_suit_les_priorites_choisies(data: GameData) -> None:
    """Panneau Priorités activé : cocher Critique pour un tank ouvre la ligne % Critique (le réglage sert à quelque chose)."""
    o = archetype_options(data, "pandawa", 200, "tank", crit=True)
    assert "crit_rate" in apt_profile(o)["fortune"]
    o = archetype_options(data, "cra", 200, "dps_distance", rear=True)
    assert "rear_mastery" in apt_profile(o)["fortune"]


def test_points_restants_tank_hors_critique(data: GameData) -> None:
    """Régression : les points sans effet sur le score d'un tank partaient en % Critique (première ligne libre)."""
    o = archetype_options(data, "pandawa", 140, "tank")
    pts = fill_unspent({"fortune.block": 20, "strength.hp": 35}, 140, data.game, o.range, apt_profile(o))
    assert not pts.get("fortune.crit_rate")
    assert pts.get("fortune.crit_res") == branch_points("fortune", 140, data.game) - 20


def test_profile_points_est_le_preset(data: GameData) -> None:
    o = archetype_options(data, "eniripsa", 170, "heal")
    assert profile_points(o, data.game) == preset(data, "heal", "eniripsa", 170)


def test_panneaux_desactives_utilisent_l_archetype(data: GameData) -> None:
    """Le site envoie `panels` : un panneau désactivé ignore les valeurs du formulaire, un panneau activé les garde."""
    from wakfu_optimizer.web.server import opts_from

    sent = {"class_key": "cra", "level": 140, "elements": ["fire"], "archetype": "dps_distance", "range": "melee",
            "crit": False, "min_crit": 80, "allowed_rarities": [4], "shard_mode": "none", "offense_weight": 10}
    off = opts_from({**sent, "panels": {k: False for k in PANELS}}, data)
    assert off.range == "distance" and off.crit and off.min_crit == 0 and len(off.allowed_rarities) == 8
    assert off.shard_mode == "ideal" and off.offense_weight == 85 and off.custom_panels == ()
    on = opts_from({**sent, "panels": {k: True for k in PANELS}}, data)
    assert on.range == "melee" and not on.crit and on.min_crit == 80 and on.allowed_rarities == (4,)
    assert on.shard_mode == "none" and on.offense_weight == 85 and set(on.custom_panels) == set(PANELS)
    assert off.elements == ("fire",)   # le panneau Personnage reste celui de l'utilisateur


# =====================================================================  builds réels (solveur)
_RUNS: dict[tuple[str, int, str], Any] = {}


def run(data: GameData, cls: str, level: int, arch: str) -> tuple[Any, Any]:
    from wakfu_optimizer.engine.solver import optimize

    key = (cls, level, arch)
    if key not in _RUNS:
        o = archetype_options(data, cls, level, arch, time_limit=QUALITY_TIME)
        _RUNS[key] = (o, optimize(data, o))
    return _RUNS[key]


def assert_sensible(data: GameData, cls: str, level: int, arch: str) -> None:
    o, r = run(data, cls, level, arch)
    assert r.builds, f"{cls} {arch} niv. {level} : aucun build ({r.message})"
    checks = check_build(data, o, r.builds[0], r.totals[0])
    bad = failures(checks)
    st = r.totals[0].stats
    summary = (f"{cls} {arch} niv. {level} — PA {st.get('ap')} PM {st.get('mp')} crit {st.get('crit_rate')} % "
               f"PV {r.totals[0].hp} rés. {min(r.totals[0].res_pct.values())} % aptitudes {r.builds[0].characteristics}")
    assert not bad, f"{summary}\n{explain_failures(bad)}"


QUICK = [
    ("cra", 140, "dps_distance"),       # signalé : 22 % de critique
    ("pandawa", 140, "tank"),           # signalé : aptitudes critique / maîtrise mêlée
    ("pandawa", 140, "dps_melee"),
    ("iop", 245, "dps_melee"),
    ("sram", 200, "dps_rear"),
    ("eniripsa", 170, "heal"),
    ("xelor", 245, "support_debuff"),
    ("sacrier", 110, "berserk"),
    ("huppermage", 230, "dps_mixed"),
    ("masqueraider", 185, "support_buff"),
    ("feca", 80, "tank"),
]


@pytest.mark.quality
@pytest.mark.parametrize(("cls", "level", "arch"), QUICK, ids=[f"{c}-{lv}-{a}" for c, lv, a in QUICK])
def test_build_coherent(data: GameData, cls: str, level: int, arch: str) -> None:
    assert_sensible(data, cls, level, arch)


@pytest.mark.quality
def test_crâ_140_dps_distance_critique(data: GameData) -> None:
    o, r = run(data, "cra", 140, "dps_distance")
    t = r.totals[0]
    assert t.stats["crit_rate"] >= 30, f"{t.stats['crit_rate']} % de critique"
    assert t.stats.get("distance_mastery", 0) > 0 and r.builds[0].characteristics.get("strength.distance_mastery", 0) >= 30


@pytest.mark.quality
def test_pandawa_tank_aptitudes(data: GameData) -> None:
    o, r = run(data, "pandawa", 140, "tank")
    ch = r.builds[0].characteristics
    assert not ch.get("fortune.crit_rate") and not ch.get("strength.melee_mastery")
    assert ch.get("strength.hp") == branch_points("strength", 140, data.game)
    assert ch.get("fortune.block") == 20


@pytest.mark.quality
def test_tank_plus_solide_dps_plus_fort(data: GameData) -> None:
    """Même classe, même niveau : le tank survit mieux, le DPS frappe plus fort."""
    _, tank = run(data, "pandawa", 140, "tank")
    _, dps = run(data, "pandawa", 140, "dps_melee")
    assert tank.totals[0].defense > dps.totals[0].defense * 1.15
    assert dps.totals[0].d2 > tank.totals[0].d2 * 1.1


@pytest.mark.quality
def test_explication(data: GameData) -> None:
    o, r = run(data, "cra", 140, "dps_distance")
    x = explain(data, o, r.builds[0], r.totals[0])
    assert x["archetype"]["recommended"] and x["checks"] and x["aptitudes"]
    assert abs(x["total"] - r.totals[0].score) < 0.05
    gains = {m["label"]: m["points"] for m in x["marginals"]}
    assert gains["Maîtrise utilisée"] > 0 and gains["% Coup critique"] > 0
    assert {p["key"]: p["on"] for p in x["panels"]} == {k: False for k in PANELS}


FULL_LEVELS = (50, 110, 170, 245)


def _full_params() -> list[Any]:
    """Toutes les classes × archétypes habituels × niveaux (lu dans game.yaml, sans charger les items)."""
    from wakfu_optimizer.data.parse import load_game_yaml

    game = load_game_yaml()
    return [pytest.param(c, L, a, id=f"{c}-{L}-{a}") for c, spec in sorted(game["classes"].items())
            for a in spec.get("archetypes", []) for L in FULL_LEVELS]


@pytest.mark.quality_full
@pytest.mark.parametrize(("cls", "level", "arch"), _full_params())
def test_matrice_complete(data: GameData, cls: str, level: int, arch: str) -> None:
    assert_sensible(data, cls, level, arch)
