"""Châsses, runes et sublimations : règles de compatibilité."""

from __future__ import annotations

from collections.abc import Sequence

from ..data.models import Color, Rune, SubEffect, SubState
from .options import SECONDARY_MASTERIES, OptimizeOptions

# Effet spécial de Dénouement : la Maîtrise Critique est convertie en Maîtrise Élémentaire (model._derived, stats.evaluate).
CRIT_TO_ELEM = "crit_to_elem"
# Stats regroupées par « Toutes les maîtrises ».
ALL_MASTERY_TARGETS = ("elem_mastery", "melee_mastery", "distance_mastery", "berserk_mastery",
                       "rear_mastery", "crit_mastery", "heal_mastery")


def rune_fits(rune: Rune, socket: Color) -> bool:
    """Une rune va dans une châsse de sa couleur ou dans une blanche."""
    return socket == Color.WHITE or socket == rune.color


def color_matches(socket: Color, wanted: Color) -> bool:
    """Pour les motifs de sublimation, la châsse blanche sert de joker."""
    return socket == Color.WHITE or socket == wanted


def pattern_offsets(colors: Sequence[Color], pattern: Sequence[Color]) -> list[int]:
    """Positions de départ où le motif apparaît sur des châsses consécutives."""
    n, k = len(colors), len(pattern)
    return [o for o in range(0, n - k + 1)
            if all(color_matches(colors[o + j], pattern[j]) for j in range(k))]


def static_condition(cond: str, opts: OptimizeOptions) -> bool | None:
    """True/False si la condition ne dépend que des options ; None si elle dépend de l'équipement.
    « a&b » : les deux conditions à la fois."""
    if "&" in cond:
        parts = [static_condition(c, opts) for c in cond.split("&")]
        return False if False in parts else None if None in parts else True
    if cond in ("", "none"):
        return True
    if cond == "melee":
        return opts.range in ("melee", "mixed", "best")
    if cond == "distance":
        return opts.range in ("distance", "mixed", "best")
    if cond == "berserk":
        return opts.berserk
    if cond in ("hp_high", "no_armor"):
        return opts.count_conditional
    if cond.startswith("element:"):
        return len(opts.elements) == 1 and opts.elements[0] == cond.split(":", 1)[1]
    if cond in ("two_handed", "light_weapons", "no_secondary") or cond.startswith(("stat_le:", "stat_ge:")):
        return None
    return False  # condition inconnue : ignorée


def parse_stat_condition(cond: str) -> tuple[str, str, int] | None:
    """« stat_le:ap:10 » -> ("le", "ap", 10)."""
    if not cond.startswith(("stat_le:", "stat_ge:")):
        return None
    kind, stat, v = cond.split(":")
    return kind[5:], stat, int(v)


def needs_stats(cond: str) -> bool:
    """La condition porte sur les stats totales du build (vérifiée une fois les autres effets comptés)."""
    return any(c == "no_secondary" or parse_stat_condition(c) for c in cond.split("&"))


def needs_no_secondary(st: SubState | None) -> bool:
    """État dont un effet demande des maîtrises secondaires <= 0 (Neutralité, Ambition, Dénouement…)."""
    return st is not None and any("no_secondary" in e.condition.split("&") for e in st.effects)


COND_FR = {"no_secondary": "maîtrises secondaires ≤ 0", "two_handed": "arme à deux mains",
           "light_weapons": "ni bouclier, ni dague, ni arme à deux mains"}
STAT_COND_FR = {"crit_rate": "% Critique", "ap": "PA", "block": "% Parade", "range": "Portée"}


def condition_label(cond: str) -> str:
    out = []
    for c in cond.split("&"):
        sc = parse_stat_condition(c)
        out.append(f"{STAT_COND_FR.get(sc[1], sc[1])} {'≤' if sc[0] == 'le' else '≥'} {sc[2]}" if sc else COND_FR.get(c, c))
    return " et ".join(out)


def condition_holds(cond: str, opts: OptimizeOptions, two_handed: bool, second_hand_used: bool,
                    stats: dict[str, int] | None = None) -> bool:
    if "&" in cond:
        return all(condition_holds(c, opts, two_handed, second_hand_used, stats) for c in cond.split("&"))
    s = static_condition(cond, opts)
    if s is not None:
        return s
    sc = parse_stat_condition(cond)
    if sc is not None:
        kind, stat, v = sc
        cur = (stats or {}).get(stat, 0)
        return cur <= v if kind == "le" else cur >= v
    if cond == "no_secondary":
        return all((stats or {}).get(k, 0) <= 0 for k in SECONDARY_MASTERIES)
    if cond == "two_handed":
        return two_handed
    if cond == "light_weapons":
        return not two_handed and not second_hand_used
    return False


def effect_targets(effect: SubEffect) -> tuple[str, ...]:
    return ALL_MASTERY_TARGETS if effect.stat == "all_mastery" else (effect.stat,)
