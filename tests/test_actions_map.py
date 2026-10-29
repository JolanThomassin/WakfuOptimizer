"""Tests de la table actionId -> stat et de l'explorateur."""

from __future__ import annotations

from pathlib import Path

from wakfu_optimizer.data.actions_map import EffectKind, load_actions_map
from wakfu_optimizer.data.explore import collect_usage, explore
from wakfu_optimizer.data.fetch import DataBundle

FIXTURES = Path(__file__).parent / "fixtures" / "gamedata"

# Les 66 actionId utilisés par les équipements dans la version 1.93.1.62.
ACTION_IDS_1_93_1_62 = {
    20, 21, 26, 31, 39, 40, 41, 56, 57, 71, 80, 82, 83, 84, 85, 90, 96, 97, 98, 100,
    120, 122, 123, 124, 125, 130, 132, 149, 150, 160, 161, 162, 166, 168, 171, 172,
    173, 174, 175, 176, 177, 180, 181, 183, 185, 191, 192, 304, 400, 875, 876, 988,
    999, 1020, 1052, 1053, 1055, 1056, 1059, 1060, 1061, 1062, 1063, 1068, 1069, 2001,
}
# Effets « Perte » / « Deboost » de actions.json : doivent être négatifs.
MALUS_IDS = {21, 40, 56, 57, 90, 96, 97, 98, 100, 130, 132, 161, 168, 172, 174, 176,
             181, 192, 876, 1056, 1059, 1060, 1061, 1062, 1063}


def test_table_couvre_tous_les_actionid_de_la_version() -> None:
    mapping = load_actions_map()
    assert ACTION_IDS_1_93_1_62 <= set(mapping)


def test_malus_negatifs_bonus_positifs() -> None:
    mapping = load_actions_map()
    for aid, m in mapping.items():
        if m.kind is EffectKind.IGNORE:
            continue
        expected = -1 if aid in MALUS_IDS else 1
        assert m.sign == expected, f"actionId {aid} ({m.label}) : signe {m.sign}"


def test_elements_aleatoires() -> None:
    mapping = load_actions_map()
    assert mapping[1068].kind is EffectKind.RANDOM_ELEMENTS and mapping[1068].count_param == 2
    assert mapping[1069].kind is EffectKind.RANDOM_ELEMENTS


def _bundle() -> DataBundle:
    return DataBundle("fixture", FIXTURES, offline=True)


def test_collect_usage_ignore_les_non_equipables() -> None:
    b = _bundle()
    usage = collect_usage(b.load("items"), b.load("equipmentItemTypes"), b.load("actions"))  # type: ignore[arg-type]
    assert 304 not in usage  # seul le parchemin (type 812) l'utilise
    assert usage[20].count == 4 and usage[1068].count == 3
    assert usage[39].per_level_count == 0  # familier : dépendance au niveau attendue
    assert usage[20].example == (2021, "Amulette du Bouftou", [6, 0, 1, 0, 0, 0])


def test_explore_signale_les_actionid_inconnus(tmp_path: Path) -> None:
    report, unmapped = explore(_bundle(), load_actions_map(), tmp_path)
    assert unmapped == [9999]
    text = report.read_text(encoding="utf-8")
    assert "**NON MAPPÉ**" in text and "| 20 | Boost : Point de vie (PV) | hp | + |" in text
