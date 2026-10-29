"""Paramètres d'une optimisation et structure d'un build résultat."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from ..data.models import Color, Rarity, Slot


DENOUEMENT_CRIT = 40     # % critique requis par Dénouement
NEUTRAL_COMBO_STATES = (6931, 5077)   # Neutralité, Dénouement (id d'état)
# Maîtrises « secondaires » qui doivent rester <= 0 (la Maîtrise Critique est convertie par Dénouement)
SECONDARY_MASTERIES = ("melee_mastery", "distance_mastery", "rear_mastery", "berserk_mastery", "heal_mastery")


def default_min_ap(level: int) -> int:
    return 11 if level >= 171 else 10 if level >= 96 else 8 if level >= 36 else 6


def default_min_mp(level: int) -> int:
    return 5 if level >= 200 else 4 if level >= 51 else 3


@dataclass
class OptimizeOptions:
    # --- Personnage
    class_key: str = "iop"
    level: int = 245
    elements: tuple[str, ...] = ("fire", "earth", "air")
    lang: str = "fr"
    # --- Priorités
    range: str = "melee"                 # melee | distance | mixed (moitié mêlée, moitié distance)
    target: str = "single"               # single | area (sans effet : n'existe plus sur l'équipement)
    crit: bool = True
    rear: bool = False
    rear_share: int = 50                 # % des frappes de dos si « rear »
    berserk: bool = False
    heal: bool = False
    offense_weight: int = 85             # 0..100 ; défense = 100 - offense (fixe : la défense passe par res_target)
    res_target: int = 50                 # % de résistance visé sur chaque élément ; au-delà, elle ne rapporte plus rien
    res_tol: int = 5                     # écart max sous la cible (%) : dans l'écart, aucun malus de score
    res_free: bool = False               # tank : la résistance continue de compter au-delà du plancher
    archetype: str = ""                  # archétype choisi dans l'interface (tank, dps_melee…), pour mémoire
    res_max: int = 90                    # obsolète (remplacé par res_target / res_tol)
    balance_res: bool = True             # obsolète : les résistances sont toujours équilibrées (gardé pour les anciens réglages)
    count_conditional: bool = True       # sublimations « PV > 90 % », « sans armure »
    # Combo Neutralité + Dénouement : maîtrises secondaires <= 0, >= 40 % critique, Maîtrise Critique convertie
    # en Maîtrise Élémentaire (Dénouement) ; Neutralité, Ambition, Prétention s'activent.
    neutral_combo: bool = False
    # Valeur (en points de score) de chaque PA/PM/PO/PW, au-delà des minimums, jusqu'aux plafonds.
    ap_value: int = 6
    mp_value: int = 4
    range_value: int = 1
    wp_value: int = 1
    ap_cap: int = 14
    mp_cap: int = 6
    range_cap: int = 6
    wp_cap: int = 12
    # --- Contraintes
    min_ap: int = 11
    min_mp: int = 5
    min_range: int = 0
    min_wp: int = 0
    min_crit: int = 0
    min_control: int = 0
    min_block: int = 0
    min_res_pct: int = 0                 # résistance minimale (%) sur chaque élément (contrainte stricte)
    # maximums (0 = pas de maximum)
    max_ap: int = 0
    max_mp: int = 0
    max_range: int = 0
    max_wp: int = 0
    max_crit: int = 0
    max_block: int = 0
    allowed_rarities: tuple[int, ...] = tuple(int(r) for r in Rarity)
    lower_brackets: bool = False
    exclude_relic: bool = False
    exclude_epic: bool = False
    exclude_shop: bool = True
    include_pet_mount: bool = True
    optimize_characteristics: bool = True
    char_mode: str = "auto"               # auto (le solveur choisit) | manual (aptitudes saisies)
    apt_elem_res: bool = True             # auto : Résistance élémentaire (Intelligence) toujours au max, comme la plupart des joueurs
    manual_chars: dict[str, int] = field(default_factory=dict)   # "branche.ligne" -> points
    excluded_ids: tuple[int, ...] = ()
    forced_ids: tuple[int, ...] = ()
    forced_subs: tuple[int, ...] = ()     # sublimations imposées (id d'état : n'importe quel niveau)
    excluded_subs: tuple[int, ...] = ()   # sublimations interdites (id d'état)
    forced_sub_levels: dict[str, int] = field(default_factory=dict)   # id d'état -> niveau minimum imposé
    no_subs: bool = False                 # aucune sublimation, sauf celles imposées
    # --- Châsses
    shard_mode: str = "ideal"            # ideal | mine | none
    shard_count: int = 4
    max_jokers: int = 1                  # châsses jaunes (joker) max par item en mode idéal
    my_colors: dict[str, list[int]] = field(default_factory=dict)   # Slot.value -> codes couleur
    # --- Calcul
    alternatives: int = 3
    time_limit: float = 180.0
    workers: int = 8

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "OptimizeOptions":
        o = OptimizeOptions()
        for k, v in d.items():
            if hasattr(o, k):
                if isinstance(getattr(o, k), tuple) and isinstance(v, list):
                    v = tuple(v)
                setattr(o, k, v)
        return o

    def normalize(self) -> list[str]:
        """Corrige les réglages incohérents (min > max, % hors 0..100) et renvoie ce qui a été changé."""
        out: list[str] = []
        for stat, label, cap in (("ap", "PA", None), ("mp", "PM", None), ("range", "PO", None), ("wp", "PW", None),
                                 ("crit", "% Critique", 100), ("block", "% Parade", 100)):
            lo, hi = f"min_{stat}", f"max_{stat}"
            for k in (lo, hi):
                v = max(0, int(getattr(self, k)))
                setattr(self, k, min(v, cap) if cap else v)
            if getattr(self, hi) and getattr(self, lo) > getattr(self, hi):
                out.append(f"{label} : minimum {getattr(self, lo)} > maximum {getattr(self, hi)}, "
                           f"minimum ramené à {getattr(self, hi)}.")
                setattr(self, lo, getattr(self, hi))
        self.res_target = max(0, min(90, int(self.res_target)))
        self.res_tol = max(0, min(self.res_target, int(self.res_tol)))
        self.min_res_pct = max(0, min(90, int(self.min_res_pct)))
        self.rear_share = max(0, min(100, int(self.rear_share)))
        self.forced_sub_levels = {str(k): max(1, int(v)) for k, v in self.forced_sub_levels.items()
                                  if int(k) in self.forced_subs}
        if self.neutral_combo:
            self.crit = True
            self.rear = self.berserk = self.heal = False   # ces maîtrises sont à 0 ou moins
            if self.min_crit < DENOUEMENT_CRIT:
                self.min_crit = DENOUEMENT_CRIT
            if self.max_crit and self.max_crit < DENOUEMENT_CRIT:
                out.append(f"Combo Neutralité : il faut au moins {DENOUEMENT_CRIT} % critique, maximum retiré.")
                self.max_crit = 0
        return out

    def colors_for(self, slot: Slot) -> list[Color]:
        return [Color(c) for c in self.my_colors.get(slot.value, [])]


@dataclass
class ShardChoice:
    color: Color
    rune_id: int | None = None
    rune_level: int = 0


@dataclass
class SlotChoice:
    slot: Slot
    item_id: int
    mastery_elements: list[tuple[str, ...]] = field(default_factory=list)     # par effet aléatoire
    resistance_elements: list[tuple[str, ...]] = field(default_factory=list)
    shards: list[ShardChoice] = field(default_factory=list)
    sublimation_id: int | None = None
    special_sublimation_id: int | None = None   # épique / relique enchâssée dans cet item


@dataclass
class Build:
    slots: dict[Slot, SlotChoice] = field(default_factory=dict)
    characteristics: dict[str, int] = field(default_factory=dict)   # "branche.ligne" -> points
    solver_score: float = 0.0
    status: str = ""

    def item_ids(self) -> list[int]:
        return [c.item_id for c in self.slots.values()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slots": {
                s.value: {
                    "item_id": c.item_id,
                    "mastery_elements": [list(x) for x in c.mastery_elements],
                    "resistance_elements": [list(x) for x in c.resistance_elements],
                    "shards": [{"color": int(sh.color), "rune_id": sh.rune_id, "rune_level": sh.rune_level} for sh in c.shards],
                    "sublimation_id": c.sublimation_id,
                    "special_sublimation_id": c.special_sublimation_id,
                } for s, c in self.slots.items()
            },
            "characteristics": dict(self.characteristics),
            "status": self.status,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Build":
        b = Build(characteristics={k: int(v) for k, v in d.get("characteristics", {}).items()}, status=d.get("status", ""))
        for s, c in d.get("slots", {}).items():
            slot = Slot(s)
            b.slots[slot] = SlotChoice(
                slot=slot, item_id=int(c["item_id"]),
                mastery_elements=[tuple(x) for x in c.get("mastery_elements", [])],
                resistance_elements=[tuple(x) for x in c.get("resistance_elements", [])],
                shards=[ShardChoice(Color(int(x["color"])), x.get("rune_id"), int(x.get("rune_level", 0))) for x in c.get("shards", [])],
                sublimation_id=c.get("sublimation_id"), special_sublimation_id=c.get("special_sublimation_id"),
            )
        return b
