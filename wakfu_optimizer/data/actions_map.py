"""Chargement et validation de static/actions_map.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

STATIC_DIR = Path(__file__).resolve().parent / "static"
ACTIONS_MAP_PATH = STATIC_DIR / "actions_map.yaml"


class EffectKind(str, Enum):
    FLAT = "flat"                        # valeur fixe sur une stat
    RANDOM_ELEMENTS = "random_elements"  # N éléments au choix du joueur
    CHARAC_PARAM = "charac_param"        # stat donnée par un paramètre
    STATE = "state"                      # applique un état (effet spécial)
    IGNORE = "ignore"                    # sans intérêt pour le build


@dataclass(frozen=True)
class ActionMapping:
    action_id: int
    stat: str
    sign: int
    kind: EffectKind
    label: str
    count_param: int | None = None
    charac_param: int | None = None
    characs: dict[int, str] | None = None
    todo: str | None = None


class ActionsMapError(ValueError):
    """Le fichier YAML est mal formé."""


def load_actions_map(path: Path = ACTIONS_MAP_PATH) -> dict[int, ActionMapping]:
    """Lit la table actionId -> ActionMapping et vérifie sa cohérence."""
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("actions"), dict):
        raise ActionsMapError(f"{path} : clé racine 'actions' manquante")
    result: dict[int, ActionMapping] = {}
    for key, entry in raw["actions"].items():
        if not isinstance(key, int) or not isinstance(entry, dict):
            raise ActionsMapError(f"{path} : entrée invalide {key!r}")
        try:
            kind = EffectKind(entry.get("kind", "flat"))
        except ValueError as exc:
            raise ActionsMapError(f"actionId {key} : kind inconnu {entry.get('kind')!r}") from exc
        sign = int(entry.get("sign", 0 if kind is EffectKind.IGNORE else 1))
        if kind is not EffectKind.IGNORE and sign not in (1, -1):
            raise ActionsMapError(f"actionId {key} : sign doit valoir 1 ou -1")
        if "stat" not in entry:
            raise ActionsMapError(f"actionId {key} : champ 'stat' manquant")
        characs = entry.get("characs")
        result[key] = ActionMapping(
            action_id=key,
            stat=str(entry["stat"]),
            sign=sign,
            kind=kind,
            label=str(entry.get("fr", "")),
            count_param=entry.get("count_param"),
            charac_param=entry.get("charac_param"),
            characs={int(k): str(v) for k, v in characs.items()} if characs else None,
            todo=entry.get("todo"),
        )
    return result
