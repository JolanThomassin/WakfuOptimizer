"""Tests du Build sombre (engine/combos.py) : combos de sublimations sur un build fixe, sans solveur."""

from __future__ import annotations

from pathlib import Path

import pytest

from wakfu_optimizer.data.fetch import DataBundle
from wakfu_optimizer.data.models import PROP_EPIC, Color, GameData, Item, Rarity, Slot, Sublimation
from wakfu_optimizer.data.parse import load_game_data
from wakfu_optimizer.engine.combos import ForgeParams, forge
from wakfu_optimizer.engine.options import Build, OptimizeOptions, ShardChoice, SlotChoice
from wakfu_optimizer.engine.shards import pattern_offsets
from wakfu_optimizer.engine.stats import evaluate

FIXTURES = Path(__file__).parent / "fixtures" / "gamedata"
R, G, B, W = Color.RED, Color.GREEN, Color.BLUE, Color.WHITE
SLOTS = (Slot.HEAD, Slot.NECK, Slot.CHEST, Slot.LEGS, Slot.BACK, Slot.SHOULDERS, Slot.BELT)
# états de sublimations.yaml utilisés : Influence (% critique), Dénouement (épique : Maîtrise Critique convertie si
# critique >= 40 et maîtrises secondaires <= 0), Carapace (−2 PA, +75 résistance élémentaire)
INFLUENCE, DENOUEMENT, CARAPACE, AGILITE_VITALE = 6026, 5077, 7076, 7860   # Agilité vitale : +1 PM (PV > 90 %)


def sub(sid: int, state: int, level: int, pattern: tuple[Color, ...] = (), epic: bool = False) -> Sublimation:
    return Sublimation(id=sid, names={"fr": f"#{state} {level}"}, pattern=pattern, state_id=state, state_level=level,
                       is_epic=epic, is_relic=False, rarity=5)


def item(iid: int, slot: Slot, epic: bool = False, **stats: float) -> Item:
    return Item(id=iid, names={"fr": f"{slot.value} {iid}"}, level=245, rarity=Rarity.EPIC if epic else Rarity.LEGENDARY,
                type_id=0, type_name="test", slots=(slot,), two_handed=False, stats=dict(stats), per_level={},
                properties=frozenset({PROP_EPIC}) if epic else frozenset(), shard_max=4)


@pytest.fixture(scope="module")
def data() -> GameData:
    real = load_game_data(DataBundle("fixture", FIXTURES, offline=True))
    items = [item(800 + i, s, epic=s is Slot.HEAD, crit_rate=4, crit_mastery=300, elem_mastery=200, hp=500, ap=2)
             for i, s in enumerate(SLOTS)]
    subs = [sub(1, INFLUENCE, 3, (G, B, G)), sub(2, INFLUENCE, 2, (G, B, G)), sub(3, DENOUEMENT, 1, epic=True),
            sub(4, CARAPACE, 1, (R, R, R)), sub(5, AGILITE_VITALE, 2, (B, G, B))]
    return GameData(version="test", items=items, runes=real.runes, sublimations=subs, states=real.states,
                    classes=real.classes, brackets=real.brackets, game=real.game)


def build(data: GameData, colors: tuple[Color, ...] = (G, B, G, W)) -> Build:
    return Build(slots={it.slots[0]: SlotChoice(it.slots[0], it.id, shards=[ShardChoice(c) for c in colors])
                        for it in data.items})


def opts(**kw: object) -> OptimizeOptions:
    o = OptimizeOptions(class_key="iop", level=245, elements=("fire",), crit=True, offense_weight=100, min_ap=0, min_mp=0)
    for k, v in kw.items():
        setattr(o, k, v)
    return o


def test_denouement_declenche_par_le_critique(data: GameData) -> None:
    # 7 items à 4 % de critique + 3 de base = 31 % : seule, Dénouement ne se déclenche pas (elle ne vaut rien) ;
    # avec Influence V (+15 %), elle se déclenche : le meilleur combo associe les deux, synergie positive.
    r = forge(data, opts(), build(data), ForgeParams(time_limit=20))
    best = r.combos[0]
    states = {pt.state_id: pt for pt in best.parts}
    assert DENOUEMENT in states and INFLUENCE in states
    den = states[DENOUEMENT]
    assert all(c.ok for c in den.conditions) and den.role == "Déclenchée"
    assert den.solo == pytest.approx(0) and den.marginal > 1
    assert best.synergy > 1 and best.value == pytest.approx(r.bare_value + best.gain)
    assert any(a == DENOUEMENT and b == INFLUENCE or a == INFLUENCE and b == DENOUEMENT for a, b, v in r.duos if v > 0)


def test_couleurs_respectees_et_valeur_exacte(data: GameData) -> None:
    b = build(data, colors=(G, B, G, W))
    r = forge(data, opts(), b, ForgeParams(mode="colors", time_limit=20))
    for cb in r.combos:
        assert cb.build is not None
        for slot, ch in cb.build.slots.items():
            s = next((x for x in data.sublimations if x.id == ch.sublimation_id), None)
            if s is not None:
                assert pattern_offsets([sh.color for sh in ch.shards], s.pattern), (slot, s.id)
        # posé tel quel : la valeur du build réel est celle de la recherche
        assert cb.exact == pytest.approx(cb.value)
        assert not any(pt.state_id == CARAPACE for pt in cb.parts)   # motif rouge : ne tient nulle part


def test_recolorer_pose_le_motif(data: GameData) -> None:
    b = build(data, colors=(R, R, R, W))   # aucun motif vert-bleu-vert possible sans recolorer
    r = forge(data, opts(), b, ForgeParams(mode="recolor", time_limit=20))
    best = r.combos[0]
    assert best.build is not None and best.recolored
    for slot in best.recolored:
        ch = best.build.slots[slot]
        s = next(x for x in data.sublimations if x.id == ch.sublimation_id)
        assert pattern_offsets([sh.color for sh in ch.shards], s.pattern)
    assert best.exact == pytest.approx(evaluate(data, opts(), best.build).score)


def test_garde_fou_pa(data: GameData) -> None:
    # Carapace (−2 PA) : jamais proposée si elle fait passer sous le minimum de PA du build
    b = build(data, colors=(R, R, R, W))
    ap = evaluate(data, opts(), b).stats["ap"]
    r = forge(data, opts(min_ap=ap), b, ForgeParams(mode="colors", objective="survival", time_limit=10))
    assert not any(pt.state_id == CARAPACE for cb in r.combos for pt in cb.parts)
    r = forge(data, opts(min_ap=ap), b, ForgeParams(mode="colors", objective="survival", keep_minimums=False, time_limit=10))
    assert any(pt.state_id == CARAPACE for cb in r.combos for pt in cb.parts)


def test_build_nu_sous_le_minimum_de_pm(data: GameData) -> None:
    # le build atteint ses PM grâce à Agilité vitale : sans sublimation, il est sous le minimum ; les combos proposés
    # doivent la garder (rôle Garde-fou), même si elle ne rapporte rien à elle seule
    b = build(data, colors=(B, G, B, W))
    b.slots[Slot.HEAD].sublimation_id = 5
    mp = evaluate(data, opts(), b).stats["mp"]
    r = forge(data, opts(min_mp=mp), b, ForgeParams(time_limit=10))
    assert r.combos
    for cb in r.combos:
        guard = next(pt for pt in cb.parts if pt.state_id == AGILITE_VITALE)
        assert guard.role == "Garde-fou" and cb.totals.stats["mp"] >= mp


def test_reve_sans_emplacement_reel(data: GameData) -> None:
    r = forge(data, opts(), build(data, colors=(R, R, R, W)), ForgeParams(mode="dream", time_limit=10))
    assert r.combos and all(cb.build is None for cb in r.combos)
    assert any(h.slot is None for h in r.hosts)


def test_pivot_present_dans_chaque_combo(data: GameData) -> None:
    r = forge(data, opts(), build(data), ForgeParams(pivot=DENOUEMENT, top=3, time_limit=10))
    assert r.combos and all(any(pt.state_id == DENOUEMENT for pt in cb.parts) for cb in r.combos)


def test_parametres_bornes() -> None:
    p = ForgeParams.from_dict({"base": "build", "mode": "??", "objective": "damage", "beam": 999, "time_limit": 0, "top": 0,
                               "pivot": None})
    assert (p.mode, p.objective, p.beam, p.time_limit, p.top, p.pivot) == ("colors", "damage", 64, 1.0, 1, 0)
    assert ForgeParams.from_dict({"mode": "colors"}).mode == "dream"   # corps neutre : pas de couleurs


def test_une_sublimation_par_famille(data: GameData) -> None:
    r = forge(data, opts(), build(data), ForgeParams(time_limit=10))
    for cb in r.combos:
        assert all(len(pt.placed) == 1 for pt in cb.parts)
    r = forge(data, opts(), build(data), ForgeParams(stack=True, time_limit=10))
    assert any(len(pt.placed) > 1 for cb in r.combos for pt in cb.parts)   # Influence III + II


def test_deck_building_sans_classe_ni_items() -> None:
    # vraies données : sur le corps neutre, en survie, la parade empilée déclenche Pilier (+30 % PV si parade >= 50 %)
    import os

    from wakfu_optimizer.data.fetch import DEFAULT_CACHE_ROOT, GameDataFetcher
    from wakfu_optimizer.engine.combos import Forge, neutral_body
    fetcher = GameDataFetcher(cache_root=os.environ.get("WAKFU_OPTIMIZER_CACHE", DEFAULT_CACHE_ROOT))  # type: ignore[arg-type]
    versions = fetcher.cached_versions()
    if not versions:
        pytest.skip("données Ankama absentes")
    real = load_game_data(DataBundle(versions[0], fetcher.cache_root / versions[0], offline=True))
    p = ForgeParams.from_dict({"objective": "survival", "rank": "synergy", "time_limit": 20})
    o, prepared, hosts = neutral_body(real, p)
    r = Forge(real, o, Build(), p, prepared, hosts).run()
    best = r.combos[0]
    pilier = next(pt for pt in best.parts if pt.state_id == 6707)
    assert pilier.role == "Déclenchée" and all(c.ok for c in pilier.conditions)
    assert best.synergy > 10


def test_idees_sans_doublon() -> None:
    # vraies données : le générateur de l'onglet (un bouton) trouve des combos, chacun avec d'autres familles
    import os

    from wakfu_optimizer.data.fetch import DEFAULT_CACHE_ROOT, GameDataFetcher
    from wakfu_optimizer.engine.combos import ideas
    fetcher = GameDataFetcher(cache_root=os.environ.get("WAKFU_OPTIMIZER_CACHE", DEFAULT_CACHE_ROOT))  # type: ignore[arg-type]
    versions = fetcher.cached_versions()
    if not versions:
        pytest.skip("données Ankama absentes")
    real = load_game_data(DataBundle(versions[0], fetcher.cache_root / versions[0], offline=True))
    found = ideas(real, time_per=1.0)
    fams = [frozenset(pt.state_id for pt in cb.parts) for _, _, cb in found]
    assert len(found) >= 4 and len(set(fams)) == len(fams)
    assert any(6707 in f for f in fams)   # Pilier, déclenché par la parade
