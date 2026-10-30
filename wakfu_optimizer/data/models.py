"""Modèles internes : items, runes, sublimations, profils de classe."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

ELEMENTS: tuple[str, ...] = ("fire", "water", "earth", "air")
ELEMENT_FR = {"fire": "Feu", "water": "Eau", "earth": "Terre", "air": "Air"}


class Slot(str, Enum):
    """Emplacements physiques du personnage (les deux anneaux sont distincts)."""

    HEAD = "HEAD"
    NECK = "NECK"
    CHEST = "CHEST"
    LEFT_HAND = "LEFT_HAND"
    RIGHT_HAND = "RIGHT_HAND"
    LEGS = "LEGS"
    BACK = "BACK"
    SHOULDERS = "SHOULDERS"
    BELT = "BELT"
    FIRST_WEAPON = "FIRST_WEAPON"
    SECOND_WEAPON = "SECOND_WEAPON"
    ACCESSORY = "ACCESSORY"
    PET = "PET"
    MOUNT = "MOUNT"


SLOT_FR: dict[Slot, str] = {
    Slot.HEAD: "Casque", Slot.NECK: "Amulette", Slot.CHEST: "Plastron",
    Slot.LEFT_HAND: "Anneau 1", Slot.RIGHT_HAND: "Anneau 2", Slot.LEGS: "Bottes",
    Slot.BACK: "Cape", Slot.SHOULDERS: "Épaulettes", Slot.BELT: "Ceinture",
    Slot.FIRST_WEAPON: "Arme", Slot.SECOND_WEAPON: "Seconde main",
    Slot.ACCESSORY: "Emblème", Slot.PET: "Familier", Slot.MOUNT: "Monture",
}

# Identifiants numériques des positions (utilisés par shardsParameters.doubleBonusPosition).
POSITION_ID: dict[Slot, int] = {
    Slot.HEAD: 0, Slot.SHOULDERS: 3, Slot.NECK: 4, Slot.CHEST: 5,
    Slot.LEFT_HAND: 7, Slot.RIGHT_HAND: 8, Slot.BELT: 10, Slot.LEGS: 12,
    Slot.BACK: 13, Slot.FIRST_WEAPON: 15,
}

# Emplacements pouvant porter des châsses.
SHARD_SLOTS: tuple[Slot, ...] = (
    Slot.HEAD, Slot.NECK, Slot.CHEST, Slot.LEFT_HAND, Slot.RIGHT_HAND, Slot.LEGS,
    Slot.BACK, Slot.SHOULDERS, Slot.BELT, Slot.FIRST_WEAPON, Slot.SECOND_WEAPON,
)


class Rarity(int, Enum):
    COMMON = 0
    UNUSUAL = 1
    RARE = 2
    MYTHICAL = 3
    LEGENDARY = 4
    RELIC = 5
    SOUVENIR = 6
    EPIC = 7


RARITY_FR = {
    Rarity.COMMON: "Commun", Rarity.UNUSUAL: "Inhabituel", Rarity.RARE: "Rare",
    Rarity.MYTHICAL: "Mythique", Rarity.LEGENDARY: "Légendaire", Rarity.RELIC: "Relique",
    Rarity.SOUVENIR: "Souvenir", Rarity.EPIC: "Épique",
}
RARITY_COLOR = {
    Rarity.COMMON: "#9a9a9a", Rarity.UNUSUAL: "#cfcfcf", Rarity.RARE: "#00c46f",
    Rarity.MYTHICAL: "#ff902d", Rarity.LEGENDARY: "#e8c547", Rarity.RELIC: "#ff73df",
    Rarity.SOUVENIR: "#8dc6e3", Rarity.EPIC: "#ff5c9d",
}


class Color(int, Enum):
    """Couleurs de châsses (codes du CDN)."""

    WHITE = 0
    RED = 1
    GREEN = 2
    BLUE = 3


# La châsse « blanche » des données est la châsse joker, affichée en JAUNE (dorée) en jeu.
COLOR_FR = {Color.WHITE: "Jaune (joker)", Color.RED: "Rouge", Color.GREEN: "Verte", Color.BLUE: "Bleue"}

# Propriétés d'items (itemProperties.json)
PROP_SHOP = 7
PROP_RELIC = 8            # EXCLUSIVE_EQUIPMENT_ITEM
PROP_EPIC = 12            # EXCLUSIVE_EQUIPMENT_ITEM_2
PROP_EPIC_GEM = 19        # ajoute un slot de sublimation épique
PROP_RELIC_GEM = 20       # ajoute un slot de sublimation relique
PROP_HIDDEN = (23, 24)    # exclus des listes / de l'encyclopédie

LEVELABLE_TYPES = frozenset({582, 611})  # familiers, montures
PET_MAX_LEVEL = 50

StatDict = dict[str, float]


@dataclass(frozen=True)
class Item:
    id: int
    names: dict[str, str]
    level: int
    rarity: Rarity
    type_id: int
    type_name: str
    slots: tuple[Slot, ...]
    two_handed: bool
    stats: StatDict                       # valeurs fixes (params[0])
    per_level: StatDict                   # params[1] (familiers, items Makabra)
    random_mastery: tuple[tuple[int, int], ...] = ()     # (valeur, nb éléments)
    random_resistance: tuple[tuple[int, int], ...] = ()
    properties: frozenset[int] = frozenset()
    gfx_id: int = 0
    shard_max: int = 0
    set_id: int = 0
    has_special_effect: bool = False      # effet « applique un état » non chiffré

    def name(self, lang: str = "fr") -> str:
        return self.names.get(lang) or self.names.get("fr") or f"#{self.id}"

    @property
    def is_relic(self) -> bool:
        return PROP_RELIC in self.properties

    @property
    def is_epic(self) -> bool:
        return PROP_EPIC in self.properties

    @property
    def is_shop(self) -> bool:
        return PROP_SHOP in self.properties

    @property
    def is_hidden(self) -> bool:
        return any(p in self.properties for p in PROP_HIDDEN)

    @property
    def scales_with_character(self) -> bool:
        """Items de niveau 0-1 dont les stats suivent le niveau du personnage."""
        return self.level <= 1 and bool(self.per_level) and self.type_id not in LEVELABLE_TYPES

    def stats_at(self, character_level: int) -> StatDict:
        """Stats effectives (familiers au niveau 50, items Makabra au niveau du perso)."""
        if not self.per_level:
            return dict(self.stats)
        if self.type_id in LEVELABLE_TYPES:
            lvl = PET_MAX_LEVEL
        elif self.scales_with_character:
            lvl = character_level
        else:
            lvl = self.level
        out = dict(self.stats)
        for k, v in self.per_level.items():
            out[k] = out.get(k, 0) + v * lvl
        return {k: float(int(v)) for k, v in out.items()}

    def icon_url(self) -> str:
        return f"https://static.ankama.com/wakfu/portal/game/item/64/{self.gfx_id}.png"


@dataclass(frozen=True)
class Rune:
    id: int
    names: dict[str, str]
    color: Color
    stat: str
    values: tuple[int, ...]              # valeur pour les niveaux 1..11
    doubled_on: frozenset[Slot]
    level_requirements: tuple[int, ...]  # niveau d'item minimal par niveau de rune

    def name(self, lang: str = "fr") -> str:
        return self.names.get(lang) or self.names.get("fr") or f"#{self.id}"

    def max_level_for_item(self, item_level: int) -> int:
        lvl = 0
        for i, req in enumerate(self.level_requirements, start=1):
            if item_level >= req:
                lvl = i
        return min(lvl, len(self.values))

    def value(self, level: int, slot: Slot | None = None) -> int:
        if level <= 0:
            return 0
        v = self.values[min(level, len(self.values)) - 1]
        return v * 2 if slot is not None and slot in self.doubled_on else v


@dataclass(frozen=True)
class SubEffect:
    stat: str
    values: tuple[int, ...]   # par niveau d'état (1..N)
    mode: str                 # flat | pct_level
    condition: str            # voir sublimations.yaml

    def value(self, state_level: int, character_level: int) -> int:
        if state_level <= 0 or not self.values:
            return 0
        v = self.values[min(state_level, len(self.values)) - 1]
        if self.mode == "pct_level":
            return int(v * character_level / 100)
        return int(v)


@dataclass(frozen=True)
class SubState:
    """État appliqué par une ou plusieurs sublimations (niveaux I, II, III...)."""

    id: int
    name: str
    description: str
    limit: int
    effects: tuple[SubEffect, ...] = ()
    confirmed: bool = False   # description, niveaux et effets vérifiés à la main (sinon grisée dans l'interface)

    @property
    def modeled(self) -> bool:
        return bool(self.effects)


@dataclass(frozen=True)
class Sublimation:
    id: int
    names: dict[str, str]
    pattern: tuple[Color, ...]   # vide pour épique/relique
    state_id: int
    state_level: int
    is_epic: bool
    is_relic: bool
    rarity: int
    gfx_id: int = 0             # icône (parchemin I / II / III, ou image propre des épiques et reliques)

    def name(self, lang: str = "fr") -> str:
        return self.names.get(lang) or self.names.get("fr") or f"#{self.id}"

    @property
    def is_normal(self) -> bool:
        return not (self.is_epic or self.is_relic)


@dataclass(frozen=True)
class ClassProfile:
    key: str
    name: str
    elements: tuple[str, ...]
    range: str                   # melee | distance | mixed | best
    role: str                    # dps | heal | tank | support
    rear: bool = False
    berserk: bool = False
    base_wp: int = 6
    passive_name: str = ""       # passif inné (toujours actif)
    passive_desc: str = ""
    passive_effects: tuple[tuple[str, int, str], ...] = ()   # (stat, valeur, flat | pct_level)

    def passive_stats(self, level: int) -> dict[str, int]:
        out: dict[str, int] = {}
        for stat, v, mode in self.passive_effects:
            out[stat] = out.get(stat, 0) + (v * level // 100 if mode == "pct_level" else v)
        return out


@dataclass
class GameData:
    version: str
    items: list[Item]
    runes: list[Rune]
    sublimations: list[Sublimation]
    states: dict[int, SubState]
    classes: dict[str, ClassProfile]
    brackets: list[tuple[int, int]]
    game: dict[str, object] = field(default_factory=dict)

    _cache: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    def item_by_id(self) -> dict[int, Item]:
        if "items" not in self._cache:
            self._cache["items"] = {i.id: i for i in self.items}
        return self._cache["items"]  # type: ignore[return-value]

    def rune_by_id(self) -> dict[int, Rune]:
        if "runes" not in self._cache:
            self._cache["runes"] = {r.id: r for r in self.runes}
        return self._cache["runes"]  # type: ignore[return-value]

    def sub_by_id(self) -> dict[int, Sublimation]:
        if "subs" not in self._cache:
            self._cache["subs"] = {s.id: s for s in self.sublimations}
        return self._cache["subs"]  # type: ignore[return-value]

    def state_name(self, state_id: int, lang: str = "fr") -> str:
        """Nom d'un état de sublimation : en français celui de sublimations.yaml, sinon celui de la sublimation (sans « II »)."""
        st = self.states.get(state_id)
        fr = st.name if st else f"#{state_id}"
        if lang == "fr":
            return fr
        if "state_subs" not in self._cache:
            self._cache["state_subs"] = {s.state_id: s for s in self.sublimations}
        subs: dict[int, Sublimation] = self._cache["state_subs"]  # type: ignore[assignment]
        sub = subs.get(state_id)
        return re.sub(r"\s+[IVX]+$", "", sub.name(lang)) if sub else fr
