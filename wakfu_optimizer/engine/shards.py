"""Châsses, runes et sublimations : règles de compatibilité."""

from __future__ import annotations

from collections.abc import Sequence

from ..data.models import Color, Rune, Slot, SubEffect, Sublimation
from .options import OptimizeOptions

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


def sublimation_fits(colors: Sequence[Color], sub: Sublimation) -> bool:
    return sub.is_normal and bool(pattern_offsets(colors, sub.pattern))


def static_condition(cond: str, opts: OptimizeOptions) -> bool | None:
    """True/False si la condition ne dépend que des options ; None si elle dépend de l'équipement."""
    if cond in ("", "none"):
        return True
    if cond == "melee":
        return opts.range == "melee"
    if cond == "distance":
        return opts.range == "distance"
    if cond == "berserk":
        return opts.berserk
    if cond in ("hp_high", "no_armor"):
        return opts.count_conditional
    if cond.startswith("element:"):
        return len(opts.elements) == 1 and opts.elements[0] == cond.split(":", 1)[1]
    if cond in ("two_handed", "light_weapons"):
        return None
    return False  # condition inconnue : ignorée


def condition_holds(cond: str, opts: OptimizeOptions, two_handed: bool, second_hand_used: bool) -> bool:
    s = static_condition(cond, opts)
    if s is not None:
        return s
    if cond == "two_handed":
        return two_handed
    if cond == "light_weapons":
        return not two_handed and not second_hand_used
    return False


def effect_targets(effect: SubEffect) -> tuple[str, ...]:
    return ALL_MASTERY_TARGETS if effect.stat == "all_mastery" else (effect.stat,)


def rune_level_for(rune: Rune, item_level: int) -> int:
    return rune.max_level_for_item(item_level)


def default_ideal_colors(slot: Slot, count: int) -> list[Color]:
    return [Color.RED] * count
