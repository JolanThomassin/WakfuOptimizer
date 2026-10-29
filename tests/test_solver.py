"""Tests du solveur CP-SAT (nécessite ortools)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("ortools")

from wakfu_optimizer.data.fetch import DataBundle  # noqa: E402
from wakfu_optimizer.data.models import PROP_EPIC, PROP_RELIC, Color, GameData, Item, Rarity, Slot  # noqa: E402
from wakfu_optimizer.data.parse import load_game_data  # noqa: E402
from wakfu_optimizer.engine.options import OptimizeOptions  # noqa: E402
from wakfu_optimizer.engine.solver import optimize  # noqa: E402
from wakfu_optimizer.engine.stats import evaluate  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "gamedata"
_ids = iter(range(900000, 999999))


def mk(slot: Slot | tuple[Slot, ...], name: str, level: int = 240, rarity: Rarity = Rarity.LEGENDARY,
       two_handed: bool = False, props: frozenset[int] = frozenset(), rm: tuple[tuple[int, int], ...] = (),
       **stats: float) -> Item:
    slots = slot if isinstance(slot, tuple) else (slot,)
    return Item(id=next(_ids), names={"fr": name}, level=level, rarity=rarity, type_id=0, type_name="test",
                slots=slots, two_handed=two_handed, stats=dict(stats), per_level={}, random_mastery=rm,
                properties=props, shard_max=4)


def base_items() -> list[Item]:
    out = []
    for s in (Slot.HEAD, Slot.NECK, Slot.CHEST, Slot.LEGS, Slot.BACK, Slot.SHOULDERS, Slot.BELT):
        out.append(mk(s, f"{s.value} A", ap=1, elem_mastery=100, hp=300, fire_res=40, water_res=40, earth_res=40, air_res=40))
        out.append(mk(s, f"{s.value} B", mp=1, elem_mastery=80, hp=400, elem_res=60))
    return out


@pytest.fixture(scope="module")
def real():  # type: ignore[no-untyped-def]
    return load_game_data(DataBundle("fixture", FIXTURES, offline=True))


def data_with(real: GameData, items: list[Item]) -> GameData:
    return GameData(version="test", items=items, runes=real.runes, sublimations=real.sublimations,
                    states=real.states, classes=real.classes, brackets=real.brackets, game=real.game)


def opts(**kw: object) -> OptimizeOptions:
    o = OptimizeOptions(level=245, elements=("fire",), min_ap=0, min_mp=0, alternatives=0, time_limit=10,
                        workers=4, exclude_shop=False)
    for k, v in kw.items():
        setattr(o, k, v)
    return o


def test_deux_mains_interdit_la_seconde_main(real) -> None:  # type: ignore[no-untyped-def]
    items = base_items() + [
        mk(Slot.FIRST_WEAPON, "Grosse hache", two_handed=True, elem_mastery=500),
        mk(Slot.FIRST_WEAPON, "Petite épée", elem_mastery=200),
        mk(Slot.SECOND_WEAPON, "Dague", elem_mastery=250),
    ]
    r = optimize(data_with(real, items), opts(offense_weight=100, shard_mode="none"))
    b = r.builds[0]
    names = {s: data_with(real, items).item_by_id()[c.item_id].name() for s, c in b.slots.items()}
    assert names[Slot.FIRST_WEAPON] == "Grosse hache"   # 500 > 200 + 250
    assert Slot.SECOND_WEAPON not in b.slots


def test_anneaux_differents_et_exclusivites(real) -> None:  # type: ignore[no-untyped-def]
    ring = (Slot.LEFT_HAND, Slot.RIGHT_HAND)
    items = base_items() + [
        mk(ring, "Anneau fort", elem_mastery=300),
        mk(ring, "Anneau fort", rarity=Rarity.MYTHICAL, elem_mastery=290),   # même modèle, autre rareté
        mk(ring, "Anneau moyen", elem_mastery=100),
        mk(Slot.HEAD, "Casque relique", rarity=Rarity.RELIC, props=frozenset({PROP_RELIC}), elem_mastery=900),
        mk(Slot.CHEST, "Plastron relique", rarity=Rarity.RELIC, props=frozenset({PROP_RELIC}), elem_mastery=900),
        mk(Slot.LEGS, "Bottes épiques", rarity=Rarity.EPIC, props=frozenset({PROP_EPIC}), elem_mastery=900),
        mk(Slot.BACK, "Cape épique", rarity=Rarity.EPIC, props=frozenset({PROP_EPIC}), elem_mastery=900),
    ]
    d = data_with(real, items)
    r = optimize(d, opts(offense_weight=100, shard_mode="none"))
    by_id = d.item_by_id()
    chosen = [by_id[c.item_id] for c in r.builds[0].slots.values()]
    rings = [i.name() for i in chosen if Slot.LEFT_HAND in i.slots]
    assert sorted(rings) == ["Anneau fort", "Anneau moyen"]
    assert sum(i.is_relic for i in chosen) == 1 and sum(i.is_epic for i in chosen) == 1


def test_solveur_et_evaluateur_coincident(real) -> None:  # type: ignore[no-untyped-def]
    items = base_items() + [
        mk(Slot.FIRST_WEAPON, "Arme", elem_mastery=200, crit_rate=10, rm=((150, 2),)),
        mk(Slot.HEAD, "Casque crit", crit_rate=20, crit_mastery=150, hp=200),
    ]
    d = data_with(real, items)
    o = opts(offense_weight=60, elements=("fire", "water"), shard_mode="ideal")
    r = optimize(d, o)
    assert r.builds, r.message
    t = evaluate(d, o, r.builds[0])
    assert t.d2 > 0 and t.defense > 0
    # au moins une rune posée
    assert any(sh.rune_id is not None for c in r.builds[0].slots.values() for sh in c.shards)


def test_mode_mes_items_respecte_les_couleurs(real) -> None:  # type: ignore[no-untyped-def]
    d = data_with(real, base_items())
    colors = {s.value: [int(Color.BLUE)] * 4 for s in Slot}
    r = optimize(d, opts(offense_weight=50, shard_mode="mine", my_colors=colors))
    runes = {x.id: x for x in real.runes}
    for c in r.builds[0].slots.values():
        for sh in c.shards:
            assert sh.color is Color.BLUE
            if sh.rune_id is not None:
                assert runes[sh.rune_id].color in (Color.BLUE, Color.WHITE)


def test_sublimation_posee_si_motif(real) -> None:  # type: ignore[no-untyped-def]
    # Influence II (motif vert-bleu-vert, +6 % crit) doit être posée si le crit compte.
    d = data_with(real, base_items())
    r = optimize(d, opts(offense_weight=100, shard_mode="ideal", crit=True, range="distance",
                                optimize_characteristics=False))
    b = r.builds[0]
    subs = [c.sublimation_id for c in b.slots.values() if c.sublimation_id]
    assert 27152 in subs
    t = evaluate(d, opts(offense_weight=100, crit=True), b)
    assert t.active_states.get(6026, 0) >= 2


def test_aucune_solution_message_clair(real) -> None:  # type: ignore[no-untyped-def]
    d = data_with(real, base_items())
    r = optimize(d, opts(min_ap=30, shard_mode="none"))
    assert not r.builds
    assert any("PA" in x for x in r.diagnostics)


def test_alternatives_par_item(real) -> None:  # type: ignore[no-untyped-def]
    from wakfu_optimizer.engine.alternatives import alternatives

    d = data_with(real, base_items())
    o = opts(offense_weight=50, shard_mode="none")
    r = optimize(d, o)
    b = r.builds[0]
    alts = alternatives(d, o, b, Slot.HEAD)
    assert alts and all(a.item.id != b.slots[Slot.HEAD].item_id for a in alts)
    assert all(a.build.slots[Slot.HEAD].item_id == a.item.id for a in alts)
    assert all(a.delta <= 1e-6 for a in alts)   # le build optimisé est déjà le meilleur


def test_jokers_limites_et_utilises(real) -> None:  # type: ignore[no-untyped-def]
    d = data_with(real, base_items())
    r = optimize(d, opts(offense_weight=100, shard_mode="ideal", max_jokers=1, optimize_characteristics=False))
    jokers = [sum(sh.color is Color.WHITE for sh in c.shards) for c in r.builds[0].slots.values()]
    assert max(jokers) <= 1 and sum(jokers) >= 1


def test_pa_au_dela_du_minimum(real) -> None:  # type: ignore[no-untyped-def]
    items = base_items() + [mk(Slot.FIRST_WEAPON, "Arme PA", ap=2, elem_mastery=150),
                            mk(Slot.FIRST_WEAPON, "Arme maîtrise", elem_mastery=170)]
    d = data_with(real, items)
    r = optimize(d, opts(offense_weight=100, shard_mode="none", min_ap=0, ap_value=10, optimize_characteristics=False))
    names = {d.item_by_id()[c.item_id].name() for c in r.builds[0].slots.values()}
    assert "Arme PA" in names
