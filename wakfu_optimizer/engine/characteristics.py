"""Points de caractéristiques (Intelligence, Force, Agilité, Chance, Majeur)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BRANCH_FR = {"intelligence": "Intelligence", "strength": "Force", "agility": "Agilité",
             "fortune": "Chance", "major": "Majeur"}
LINE_FR = {
    "hp_pct": "% Points de Vie", "elem_res": "Résistance Élémentaire", "barrier": "Barrière",
    "heals_received_pct": "% Soins reçus", "armor_hp_pct": "% Points de Vie en Armure",
    "elem_mastery": "Maîtrise Élémentaire", "melee_mastery": "Maîtrise Mêlée", "distance_mastery": "Maîtrise Distance",
    "hp": "Points de Vie", "lock": "Tacle", "dodge": "Esquive", "initiative": "Initiative",
    "lock_dodge": "Tacle et Esquive", "willpower": "Volonté", "crit_rate": "% Coup critique", "block": "% Parade",
    "crit_mastery": "Maîtrise Critique", "rear_mastery": "Maîtrise Dos", "berserk_mastery": "Maîtrise Berserk",
    "heal_mastery": "Maîtrise Soin", "rear_res": "Résistance Dos", "crit_res": "Résistance Critique",
    "ap": "Point d'Action", "mp": "Point de Mouvement et dégâts", "range": "Portée et dégâts", "wp": "Point de Wakfu",
    "armor_given_pct": "% Armure donnée", "dmg_pct": "% Dommages infligés", "heal_pct": "% Soins réalisés",
    "indirect_pct": "% Dommages indirects",
}


@dataclass(frozen=True)
class CharLine:
    key: str                  # "branche.ligne"
    branch: str
    line: str
    per_point: dict[str, int]
    max_points: int | None


def branch_points(branch: str, level: int, game: dict[str, Any]) -> int:
    """Nombre de points disponibles dans une branche pour un niveau donné."""
    if branch == "major":
        return max(0, min((level + 25) // 50, 4))
    offset = int(game["characteristics"][branch].get("offset", 0))
    return max(0, (level + offset) // 4)


def char_lines(game: dict[str, Any]) -> list[CharLine]:
    out: list[CharLine] = []
    for branch, spec in game["characteristics"].items():
        for line, ls in spec["lines"].items():
            out.append(CharLine(f"{branch}.{line}", branch, line,
                                {k: int(v) for k, v in ls["per_point"].items()},
                                None if ls.get("max") is None else int(ls["max"])))
    return out


def characteristic_stats(points: dict[str, int], game: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for cl in char_lines(game):
        n = points.get(cl.key, 0)
        if n:
            for stat, v in cl.per_point.items():
                out[stat] = out.get(stat, 0) + n * v
    return out


# Répartitions « rapides » habituelles des joueurs. Pour chaque branche, les lignes sont remplies
# dans l'ordre (jusqu'à `max` points, ou jusqu'au plafond de la ligne) ; la dernière prend le reste.
PRESETS: dict[str, dict[str, object]] = {
    "distance": {"name": "Distance", "desc": "Résistance élémentaire puis % PV ; Maîtrise distance au max puis élémentaire ; "
                 "Esquive ; % Critique au max puis Maîtrise critique ; Majeur PA, PM, % Dommages, Portée.",
                 "lines": {"intelligence": [("elem_res", None), ("hp_pct", None)],
                           "strength": [("distance_mastery", None), ("elem_mastery", None)],
                           "agility": [("dodge", None)],
                           "fortune": [("crit_rate", None), ("crit_mastery", None)],
                           "major": [("ap", None), ("mp", None), ("dmg_pct", None), ("range", None)]}},
    "melee": {"name": "Mêlée", "desc": "Résistance élémentaire puis % PV ; Maîtrise mêlée au max puis élémentaire ; "
              "Tacle ; % Critique au max puis Maîtrise critique ; Majeur PA, PM, % Dommages, PW.",
              "lines": {"intelligence": [("elem_res", None), ("hp_pct", None)],
                        "strength": [("melee_mastery", None), ("elem_mastery", None)],
                        "agility": [("lock", None)],
                        "fortune": [("crit_rate", None), ("crit_mastery", None)],
                        "major": [("ap", None), ("mp", None), ("dmg_pct", None), ("wp", None)]}},
    "elemental": {"name": "Élémentaire", "desc": "Résistance élémentaire puis % PV ; tout en Maîtrise élémentaire ; "
                  "Tacle et Esquive ; % Critique au max puis Maîtrise critique ; Majeur PA, PM, % Dommages, Portée.",
                  "lines": {"intelligence": [("elem_res", None), ("hp_pct", None)],
                            "strength": [("elem_mastery", None)],
                            "agility": [("lock_dodge", None)],
                            "fortune": [("crit_rate", None), ("crit_mastery", None)],
                            "major": [("ap", None), ("mp", None), ("dmg_pct", None), ("range", None)]}},
    "tank": {"name": "Tank", "desc": "Résistance élémentaire puis % PV ; tout en Points de vie ; Tacle ; "
             "% Parade, Résistances critique et dos au max ; Majeur PA, PM, Résistance élémentaire, % Dommages.",
             "lines": {"intelligence": [("elem_res", None), ("hp_pct", None)],
                       "strength": [("hp", None)],
                       "agility": [("lock", None)],
                       "fortune": [("block", None), ("crit_res", None), ("rear_res", None), ("crit_mastery", None)],
                       "major": [("ap", None), ("mp", None), ("elem_res", None), ("dmg_pct", None)]}},
    "heal": {"name": "Soin", "desc": "Résistance élémentaire puis % PV ; tout en Maîtrise élémentaire ; Esquive ; "
             "% Critique au max puis Maîtrise soin ; Majeur PA, PM, % Soins réalisés, Portée.",
             "lines": {"intelligence": [("elem_res", None), ("hp_pct", None)],
                       "strength": [("elem_mastery", None)],
                       "agility": [("dodge", None)],
                       "fortune": [("crit_rate", None), ("heal_mastery", None)],
                       "major": [("ap", None), ("mp", None), ("heal_pct", None), ("range", None)]}},
}


def preset_points(name: str, level: int, game: dict[str, Any]) -> dict[str, int]:
    """Points de caractéristiques d'un preset rapide pour un niveau donné."""
    spec = PRESETS[name]["lines"]
    maxes = {cl.key: cl.max_points for cl in char_lines(game)}
    out: dict[str, int] = {}
    for branch, lines in spec.items():  # type: ignore[union-attr]
        left = branch_points(branch, level, game)
        for line, cap in lines:
            key = f"{branch}.{line}"
            if key not in maxes or left <= 0:
                continue
            lim = [left] + [x for x in (maxes[key], cap) if x is not None]
            n = min(lim)
            if n > 0:
                out[key] = n
                left -= n
    return out
