"""Parsing d'items réels, runes, sublimations, formules et évaluateur."""

from __future__ import annotations

from pathlib import Path

import pytest

from wakfu_optimizer.data.fetch import DataBundle
from wakfu_optimizer.data.models import Color, Rarity, Slot
from wakfu_optimizer.data.parse import load_game_data, rune_curve
from wakfu_optimizer.engine.characteristics import branch_points
from wakfu_optimizer.engine.options import Build, OptimizeOptions, ShardChoice, SlotChoice
from wakfu_optimizer.engine.scoring import damage_d2, ehp_factor, flat_for_pct, res_pct
from wakfu_optimizer.engine.shards import pattern_offsets, rune_fits
from wakfu_optimizer.engine.stats import evaluate

FIXTURES = Path(__file__).parent / "fixtures" / "gamedata"


@pytest.fixture(scope="module")
def data():  # type: ignore[no-untyped-def]
    return load_game_data(DataBundle("fixture", FIXTURES, offline=True))


# --- 5 items réels (valeurs relevées dans items.json 1.93.1.62) ---------------
def test_amulette_du_bouftou(data) -> None:  # type: ignore[no-untyped-def]
    it = data.item_by_id()[2021]
    assert it.name() == "Amulette du Bouftou" and it.level == 6 and it.rarity is Rarity.UNUSUAL
    assert it.slots == (Slot.NECK,)
    assert it.stats == {"ap": 1, "hp": 6, "crit_rate": 2, "elem_mastery": 9}


def test_coiffe_primitive_elements_au_choix(data) -> None:  # type: ignore[no-untyped-def]
    it = data.item_by_id()[31837]
    assert it.level == 245 and it.slots == (Slot.HEAD,)
    assert it.stats["hp"] == 795 and it.stats["crit_mastery"] == 272 and it.stats["range"] == 1
    assert it.stats["water_res"] == 55 and it.stats["air_res"] == 55 and it.stats["earth_res"] == 55
    assert it.random_mastery == ((272, 3),)


def test_voilulette_et_griffes(data) -> None:  # type: ignore[no-untyped-def]
    v, g = data.item_by_id()[31840], data.item_by_id()[31843]
    assert v.stats["ap"] == 1 and v.stats["crit_rate"] == 6 and v.random_mastery == ((244, 2),)
    assert g.stats["mp"] == 1 and g.stats["hp"] == 760 and g.slots == (Slot.LEGS,)


def test_familier_au_niveau_50(data) -> None:  # type: ignore[no-untyped-def]
    pet = data.item_by_id()[14152]
    assert pet.slots == (Slot.PET,)
    assert pet.stats_at(245)["charac_121"] == 2 + 0.16 * 50


def test_malus_et_anneau(data) -> None:  # type: ignore[no-untyped-def]
    ring = data.item_by_id()[28320]
    assert set(ring.slots) == {Slot.LEFT_HAND, Slot.RIGHT_HAND}
    assert ring.stats["charac_121"] == -40


def test_non_equipable_ignore(data) -> None:  # type: ignore[no-untyped-def]
    assert 24130 not in data.item_by_id()


# --- runes ---------------------------------------------------------------------
def test_courbes_de_runes() -> None:
    mastery = rune_curve([[1, 0], [0, 1.5], [-16.5, 4.5], [0, 3]])
    assert mastery == (1, 3, 4, 6, 7, 10, 15, 19, 24, 30, 33)
    life = rune_curve([[4, 0], [0, 4], [-44, 12], [0, 8]])
    assert life == (4, 8, 12, 16, 20, 28, 40, 52, 64, 80, 88)
    res = rune_curve([[2, 0], [0, 2.5]])
    assert res == (2, 5, 7, 10, 12, 15, 17, 20, 22, 25, 27)


def test_runes_parsees(data) -> None:  # type: ignore[no-untyped-def]
    runes = {r.id: r for r in data.runes}
    assert 27095 not in runes  # Monocible : effet vide
    melee = runes[27097]
    assert melee.color is Color.RED and melee.stat == "melee_mastery"
    assert melee.doubled_on == {Slot.HEAD, Slot.BACK}
    assert melee.value(11, Slot.HEAD) == 66 and melee.value(11, Slot.CHEST) == 33
    assert melee.max_level_for_item(245) == 11 and melee.max_level_for_item(50) == 2
    assert runes[27109].doubled_on == {Slot.FIRST_WEAPON, Slot.HEAD}


def test_compatibilite_runes() -> None:
    from wakfu_optimizer.data.models import Rune
    r = Rune(1, {}, Color.RED, "x", (1,), frozenset(), (0,))
    assert rune_fits(r, Color.RED) and rune_fits(r, Color.WHITE) and not rune_fits(r, Color.BLUE)


# --- sublimations ----------------------------------------------------------------
def test_sublimations(data) -> None:  # type: ignore[no-untyped-def]
    subs = {s.id: s for s in data.sublimations}
    infl = subs[27152]
    assert infl.pattern == (Color.GREEN, Color.BLUE, Color.GREEN) and infl.state_level == 2
    assert data.states[6026].modeled and data.states[6026].limit == 6
    assert subs[24130].is_epic and not subs[24130].pattern
    assert 27282 not in subs  # sublimation de test filtrée


def test_motifs_avec_joker() -> None:
    G, B, R, W = Color.GREEN, Color.BLUE, Color.RED, Color.WHITE
    pat = (G, B, G)
    assert pattern_offsets([G, B, G, R], pat) == [0]
    assert pattern_offsets([R, G, B, G], pat) == [1]
    assert pattern_offsets([W, B, W, W], pat) == [0]
    assert pattern_offsets([W, W, W, W], pat) == [0, 1]
    assert pattern_offsets([G, R, G, R], pat) == []
    assert pattern_offsets([G, B], pat) == []


# --- formules ----------------------------------------------------------------------
def test_conversion_resistance() -> None:
    assert res_pct(0) == 0
    assert res_pct(100) == 20 and res_pct(311) == 50 and res_pct(1032) == 90
    assert res_pct(5000) == 90  # plafond
    assert res_pct(-100) == -25
    assert flat_for_pct(50) == 311 and flat_for_pct(90) == 1032
    assert ehp_factor(0) == 100 and ehp_factor(1032) == 1000


def test_formule_degats() -> None:
    # sans crit : multiplicateur (1 + M/100)
    assert damage_d2(100, 0, 0, 0, 0, 0) == 1.6e9 * 2
    # 100 % crit, Mc = 0 : 1,25 × (1 + M/100)
    assert damage_d2(100, 100, 0, 0, 0, 0) == 1.6e9 * 2.5
    # 100 % de dos : ×1,25 et Maîtrise Dos ajoutée
    assert damage_d2(100, 0, 0, 100, 100, 0) == 1.6e9 * 1.25 * 3
    # % dommages infligés
    assert damage_d2(0, 0, 0, 0, 0, 10) == 1_760_000_000


def test_points_de_caracteristiques(data) -> None:  # type: ignore[no-untyped-def]
    g = data.game
    assert branch_points("intelligence", 245, g) == 61 and branch_points("strength", 245, g) == 61
    assert branch_points("agility", 245, g) == 61 and branch_points("fortune", 245, g) == 61
    assert branch_points("major", 245, g) == 4 and branch_points("major", 24, g) == 0


def test_evaluateur(data) -> None:  # type: ignore[no-untyped-def]
    opts = OptimizeOptions(level=245, elements=("fire",), range="melee", crit=True)
    b = Build()
    b.slots[Slot.HEAD] = SlotChoice(Slot.HEAD, 31837, mastery_elements=[("fire", "water", "earth")],
                                    shards=[ShardChoice(Color.RED, 27097, 11), ShardChoice(Color.GREEN, 27105, 11)],
                                    sublimation_id=27152)
    b.characteristics = {"strength.melee_mastery": 40, "major.ap": 1}
    t = evaluate(data, opts, b)
    assert t.stats["ap"] == 6 + 1 + 0
    assert t.stats["melee_mastery"] == 66 + 320          # rune doublée sur casque + caracs
    assert t.mastery["fire"] == 272 and t.mastery["air"] == 0
    assert t.res_flat["fire"] == 27                       # rune feu niveau 11, non doublée sur casque
    assert t.stats["crit_rate"] == 3 + 6                  # base + Influence niveau 2
    assert t.hp == 50 + 2450 + 795
    assert t.d2 == damage_d2(272 + 386, 9, 272, 0, 0, 0)
