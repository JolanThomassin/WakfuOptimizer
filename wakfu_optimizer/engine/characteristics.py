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


# Où mettre les points qui ne changent pas le score (surtout l'Agilité), comme le font les joueurs
DEFAULT_LINES = {"melee": ["agility.lock"], "distance": ["agility.dodge"], "mixed": ["agility.lock_dodge"]}


def fill_unspent(points: dict[str, int], level: int, game: dict[str, Any], range_kind: str,
                 profile: dict[str, list[str]] | None = None) -> dict[str, int]:
    """Répartit les points restants de chaque branche : lignes du profil de l'archétype dans l'ordre
    (voir archetypes.apt_profile), sinon ligne habituelle d'abord, puis la première ligne libre."""
    out = dict(points)
    lines = char_lines(game)
    for branch in game["characteristics"]:
        left = branch_points(branch, level, game) - sum(out.get(cl.key, 0) for cl in lines if cl.branch == branch)
        if left <= 0:
            continue
        mine = [cl for cl in lines if cl.branch == branch]
        if profile is not None and profile.get(branch):
            first = [f"{branch}.{x}" for x in profile[branch]]
        else:
            first = DEFAULT_LINES.get(range_kind, [])
        order = [cl for k in first for cl in mine if cl.key == k] + mine
        for cl in order:
            room = left if cl.max_points is None else cl.max_points - out.get(cl.key, 0)
            n = max(0, min(left, room))
            if n:
                out[cl.key] = out.get(cl.key, 0) + n
                left -= n
            if not left:
                break
    return out


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
