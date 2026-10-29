"""Conversion des JSON du CDN en modèles internes."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from .actions_map import STATIC_DIR, ActionMapping, EffectKind, load_actions_map
from .fetch import DataBundle
from .models import (
    ClassProfile,
    Color,
    GameData,
    Item,
    POSITION_ID,
    Rarity,
    Rune,
    Slot,
    SubEffect,
    Sublimation,
    SubState,
)

log = logging.getLogger(__name__)

_POSITION_SLOTS: dict[str, tuple[Slot, ...]] = {
    "HEAD": (Slot.HEAD,), "NECK": (Slot.NECK,), "CHEST": (Slot.CHEST,),
    "LEFT_HAND": (Slot.LEFT_HAND,), "RIGHT_HAND": (Slot.RIGHT_HAND,),
    "LEGS": (Slot.LEGS,), "BACK": (Slot.BACK,), "SHOULDERS": (Slot.SHOULDERS,),
    "BELT": (Slot.BELT,), "FIRST_WEAPON": (Slot.FIRST_WEAPON,),
    "SECOND_WEAPON": (Slot.SECOND_WEAPON,), "ACCESSORY": (Slot.ACCESSORY,),
    "PET": (Slot.PET,), "MOUNT": (Slot.MOUNT,),
}
_ID_TO_SLOT = {v: k for k, v in POSITION_ID.items()}


def _names(entry: dict[str, Any]) -> dict[str, str]:
    title = entry.get("title") or {}
    return {k: str(v) for k, v in title.items() if v}


def _clean_type_name(title: str) -> str:
    # « Anneau{[~1]?x:} » -> « Anneau »
    out, depth = [], 0
    for ch in title:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out).strip()


def parse_effects(
    effects: list[dict[str, Any]], mapping: dict[int, ActionMapping]
) -> tuple[dict[str, float], dict[str, float], list[tuple[int, int]], list[tuple[int, int]], bool]:
    """equipEffects -> (stats fixes, stats par niveau, maîtrises aléatoires, résistances aléatoires, effet spécial)."""
    stats: dict[str, float] = defaultdict(float)
    per_level: dict[str, float] = defaultdict(float)
    rand_m: list[tuple[int, int]] = []
    rand_r: list[tuple[int, int]] = []
    special = False
    for eff in effects:
        d = eff["effect"]["definition"]
        aid = int(d["actionId"])
        p = [float(x) for x in d.get("params", [])]
        m = mapping.get(aid)
        if m is None:
            log.debug("actionId %s inconnu, ignoré", aid)
            continue
        base = p[0] if p else 0.0
        lvl = p[1] if len(p) > 1 else 0.0
        if m.kind is EffectKind.FLAT:
            stats[m.stat] += m.sign * base
            if lvl:
                per_level[m.stat] += m.sign * lvl
        elif m.kind is EffectKind.RANDOM_ELEMENTS:
            count = int(p[m.count_param or 2]) if len(p) > (m.count_param or 2) else 1
            target = rand_m if m.stat == "random_mastery" else rand_r
            target.append((int(base), max(1, min(4, count))))
        elif m.kind is EffectKind.CHARAC_PARAM:
            charac = int(p[m.charac_param or 4]) if len(p) > (m.charac_param or 4) else 0
            name = (m.characs or {}).get(charac, f"charac_{charac}")
            stats[name] += m.sign * base
            if lvl:
                per_level[name] += m.sign * lvl
        elif m.kind is EffectKind.STATE:
            special = True
    return dict(stats), dict(per_level), rand_m, rand_r, special


def parse_items(raw_items: list[dict[str, Any]], equipment_types: list[dict[str, Any]],
                mapping: dict[int, ActionMapping]) -> list[Item]:
    types: dict[int, tuple[tuple[Slot, ...], bool, str]] = {}
    for t in equipment_types:
        d = t["definition"]
        slots: list[Slot] = []
        for pos in d.get("equipmentPositions", []):
            slots.extend(_POSITION_SLOTS.get(pos, ()))
        if not slots:
            continue  # costumes, etc.
        two_handed = "SECOND_WEAPON" in d.get("equipmentDisabledPositions", [])
        types[int(d["id"])] = (tuple(slots), two_handed, _clean_type_name((t.get("title") or {}).get("fr", "")))
    items: list[Item] = []
    for entry in raw_items:
        d = entry["definition"]["item"]
        bp = d["baseParameters"]
        tinfo = types.get(int(bp["itemTypeId"]))
        if tinfo is None:
            continue
        stats, per_level, rm, rr, special = parse_effects(entry["definition"].get("equipEffects", []), mapping)
        if not stats and not per_level and not rm and not rr:
            continue  # aucune statistique : apparat, outils...
        items.append(Item(
            id=int(d["id"]), names=_names(entry), level=int(d.get("level", 0)),
            rarity=Rarity(int(bp.get("rarity", 0))), type_id=int(bp["itemTypeId"]), type_name=tinfo[2],
            slots=tinfo[0], two_handed=tinfo[1], stats=stats, per_level=per_level,
            random_mastery=tuple(rm), random_resistance=tuple(rr),
            properties=frozenset(int(x) for x in d.get("properties", [])),
            gfx_id=int((d.get("graphicParameters") or {}).get("gfxId", 0)),
            shard_max=int(bp.get("maximumShardSlotNumber", 0)), set_id=int(bp.get("itemSetId", 0)),
            has_special_effect=special,
        ))
    return items


def rune_curve(effects: list[list[float]], levels: int = 11) -> tuple[int, ...]:
    """Valeurs par niveau d'une rune.

    Les runes ont 4 segments [base, par_niveau] (niveaux 1 | 2-5 | 6-9 | 10-11)
    ou 2 segments (niveau 1 | 2-11). Bornes déduites et recoupées avec WakForge.
    """
    if len(effects) >= 4:
        bounds = [(1, 1), (2, 5), (6, 9), (10, levels)]
    elif len(effects) == 2:
        bounds = [(1, 1), (2, levels)]
    else:
        bounds = [(1, levels)]
    out: list[int] = []
    for lvl in range(1, levels + 1):
        for (lo, hi), (base, step) in zip(bounds, effects):
            if lo <= lvl <= hi:
                out.append(int(base + step * lvl))
                break
    return tuple(out)


def parse_runes(raw_items: list[dict[str, Any]], mapping: dict[int, ActionMapping]) -> list[Rune]:
    runes: list[Rune] = []
    for entry in raw_items:
        d = entry["definition"]["item"]
        sp = d.get("shardsParameters")
        if not sp:
            continue
        effs = [e["effect"]["definition"] for e in entry["definition"].get("equipEffects", [])]
        if not effs:
            continue
        m = mapping.get(int(effs[0]["actionId"]))
        if m is None or m.kind is not EffectKind.FLAT:
            continue  # runes obsolètes (effet vide)
        reqs = tuple(int(x) for x in sp.get("shardLevelRequirement", []))
        curve = rune_curve([[float(e["params"][0]), float(e["params"][1])] for e in effs], levels=len(reqs) or 11)
        runes.append(Rune(
            id=int(d["id"]), names=_names(entry), color=Color(int(sp["color"])), stat=m.stat,
            values=curve,
            doubled_on=frozenset(_ID_TO_SLOT[p] for p in sp.get("doubleBonusPosition", []) if p in _ID_TO_SLOT),
            level_requirements=reqs,
        ))
    return runes


def load_states(path: Path = STATIC_DIR / "sublimations.yaml") -> dict[int, SubState]:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[int, SubState] = {}
    for sid, e in (raw.get("states") or {}).items():
        effects = tuple(
            SubEffect(stat=str(x["stat"]), values=tuple(int(v) for v in x["values"]),
                      mode=str(x.get("mode", "flat")), condition=str(x.get("condition", "none")))
            for x in e.get("effects", [])
        )
        out[int(sid)] = SubState(id=int(sid), name=str(e.get("name", "")), description=str(e.get("desc", "")),
                                 limit=int(e.get("limit", 0)), effects=effects)
    return out


def parse_sublimations(raw_items: list[dict[str, Any]], states: dict[int, SubState]) -> tuple[list[Sublimation], dict[int, SubState]]:
    subs: list[Sublimation] = []
    max_level: dict[int, int] = defaultdict(int)
    for entry in raw_items:
        d = entry["definition"]["item"]
        sp = d.get("sublimationParameters")
        if not sp:
            continue
        st = [e["effect"]["definition"]["params"] for e in entry["definition"].get("equipEffects", [])
              if int(e["effect"]["definition"]["actionId"]) == 304]
        if not st:
            continue
        sid, lvl = int(st[0][0]), max(1, int(st[0][2]) if len(st[0]) > 2 else 1)
        if "test" in (entry.get("title") or {}).get("fr", "").lower():
            continue  # sublimations de test laissées dans les données
        subs.append(Sublimation(
            id=int(d["id"]), names=_names(entry),
            pattern=tuple(Color(int(c)) for c in sp.get("slotColorPattern", [])),
            state_id=sid, state_level=lvl, is_epic=bool(sp.get("isEpic")), is_relic=bool(sp.get("isRelic")),
            rarity=int(d["baseParameters"].get("rarity", 0)),
        ))
        max_level[sid] = max(max_level[sid], lvl)
    # États inconnus du YAML (nouvelle sublimation) : nom tiré de l'item, non modélisé.
    merged = dict(states)
    for s in subs:
        if s.state_id not in merged:
            merged[s.state_id] = SubState(s.state_id, s.name().rsplit(" ", 1)[0], "(description inconnue)", 0)
    # Cumul max par défaut : niveau max de la sublimation (I/II/III) si non renseigné.
    for sid, st in list(merged.items()):
        if st.limit <= 0:
            merged[sid] = SubState(st.id, st.name, st.description, max_level.get(sid, 1) or 1, st.effects)
    return subs, merged


def load_game_yaml(path: Path = STATIC_DIR / "game.yaml") -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def parse_classes(game: dict[str, Any]) -> dict[str, ClassProfile]:
    return {
        k: ClassProfile(key=k, name=str(v["fr"]), elements=tuple(v["elements"]), range=str(v.get("range", "melee")),
                        role=str(v.get("role", "dps")), rear=bool(v.get("rear", False)),
                        berserk=bool(v.get("berserk", False)), base_wp=int(v.get("base_wp", 6)))
        for k, v in game["classes"].items()
    }


def load_game_data(bundle: DataBundle) -> GameData:
    """Charge et convertit toutes les données nécessaires à l'optimiseur."""
    mapping = load_actions_map()
    raw_items: list[dict[str, Any]] = bundle.load("items")  # type: ignore[assignment]
    eq_types: list[dict[str, Any]] = bundle.load("equipmentItemTypes")  # type: ignore[assignment]
    items = parse_items(raw_items, eq_types, mapping)
    runes = parse_runes(raw_items, mapping)
    subs, states = parse_sublimations(raw_items, load_states())
    game = load_game_yaml()
    log.info("Données %s : %d items équipables, %d runes, %d sublimations", bundle.version, len(items), len(runes), len(subs))
    return GameData(
        version=bundle.version, items=items, runes=runes, sublimations=subs, states=states,
        classes=parse_classes(game), brackets=[(int(a), int(b)) for a, b in game["brackets"]], game=game,
    )
