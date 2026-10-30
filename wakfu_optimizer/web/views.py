"""Réponses JSON de l'interface (/api/...), communes au serveur local (server.py) et au navigateur (browser.py).

Ajouter une requête : une fonction `(données, paramètres d'URL, corps JSON) -> réponse` dans ROUTES, en bas du
fichier ; elle marche alors dans les deux versions, sans toucher à server.py ni à browser.py. Les requêtes de
calcul (optimize, job, cancel, reload) et /api/meta (réglages enregistrés) restent propres à chaque version.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..data.models import (
    COLOR_FR,
    ELEMENT_FR,
    ELEMENTS,
    PROP_EPIC_GEM,
    PROP_RELIC_GEM,
    RARITY_COLOR,
    RARITY_FR,
    SLOT_FR,
    GameData,
    Item,
    Rarity,
    Slot,
)
from ..data.sources import Crafts, craft_of, wiki_url
from ..engine.alternatives import alternatives
from ..engine.archetypes import (ARCHETYPES, PANELS, apply_archetype, archetype_options, class_archetypes, meta_archetypes, preset,
                                 profile_desc)
from ..engine.characteristics import BRANCH_FR, LINE_FR, char_lines
from ..engine.combos import ForgeParams, Host, forge
from ..engine.explain import explain
from ..engine.options import Build, OptimizeOptions, default_min_ap, default_min_mp
from ..engine.report import SLOT_ORDER, build_json, build_text
from ..engine.scoring import damage_multiplier, removal_factor
from ..engine.stats import Totals, evaluate, rescore
from ..engine.weights import weights_view
from ..engine.sublimations import SubFamily, build_levels, catalog, condition_failed, sub_alternatives


STAT_LABEL = {
    "hp": "PV", "ap": "PA", "mp": "PM", "wp": "PW", "range": "Portée", "crit_rate": "% Critique",
    "block": "% Parade", "crit_mastery": "Maîtrise critique", "melee_mastery": "Maîtrise mêlée",
    "distance_mastery": "Maîtrise distance", "rear_mastery": "Maîtrise dos", "berserk_mastery": "Maîtrise berserk",
    "heal_mastery": "Maîtrise soin", "dmg_pct": "% Dommages infligés", "lock": "Tacle", "dodge": "Esquive",
    "initiative": "Initiative", "willpower": "Volonté", "control": "Contrôle", "crit_res": "Résistance critique",
    "rear_res": "Résistance dos", "elem_mastery": "Maîtrise élémentaire", "elem_res": "Résistance élémentaire",
    "hp_pct": "% PV", "wisdom": "Sagesse", "prospecting": "Prospection", "heal_pct": "% Soins réalisés",
    "armor_given_pct": "% Armure donnée", "armor_received_pct": "% Armure reçue", "indirect_pct": "% Dommages indirects",
}
for _e in ELEMENTS:
    STAT_LABEL[f"{_e}_mastery"] = f"Maîtrise {ELEMENT_FR[_e]}"
    STAT_LABEL[f"{_e}_res"] = f"Résistance {ELEMENT_FR[_e]}"

ITEM_STATS = ["ap", "mp", "wp", "range", "hp", "hp_pct", "crit_rate", "block", "elem_mastery", "fire_mastery",
              "water_mastery", "earth_mastery", "air_mastery", "melee_mastery", "distance_mastery", "crit_mastery",
              "rear_mastery", "berserk_mastery", "heal_mastery", "dmg_pct", "elem_res", "fire_res", "water_res",
              "earth_res", "air_res", "lock", "dodge", "initiative", "willpower", "control", "crit_res", "rear_res",
              "wisdom", "prospecting"]

# Lignes du comparatif (ordre d'affichage)
COMPARE = ["hp", "ap", "mp", "wp", "range", "crit_rate", "block", "crit_mastery", "melee_mastery", "distance_mastery",
           "rear_mastery", "berserk_mastery", "heal_mastery", "dmg_pct", "lock", "dodge", "initiative", "willpower"]


CRAFTS: Crafts = {}  # recettes des items équipables (voir data/sources.py)



# =====================================================================  sérialisation
def opts_from(d: dict[str, Any], data: GameData) -> OptimizeOptions:
    """Options envoyées par l'interface. `panels` dit quels panneaux sont activés : les champs d'un panneau désactivé
    (et toujours les poids du calcul) prennent les valeurs de l'archétype (voir engine/archetypes.py)."""
    o = OptimizeOptions.from_dict(d)
    o.alternatives = 0
    o.target = "single"
    panels = d.get("panels")
    on = tuple(k for k in PANELS if not isinstance(panels, dict) or panels.get(k))
    o.custom_panels = on
    return apply_archetype(o, data, tuple(k for k in PANELS if k not in on))


def item_brief(data: GameData, it: Item, lang: str, level: int) -> dict[str, Any]:
    st = it.stats_at(level)
    return {
        "id": it.id, "name": it.name(lang), "level": it.level, "gfx": it.gfx_id, "type": it.type_name,
        "rarity": int(it.rarity), "rarity_name": RARITY_FR[it.rarity], "color": RARITY_COLOR[it.rarity],
        "two_handed": it.two_handed, "special_effect": it.has_special_effect,
        "stats": [{"stat": k, "label": STAT_LABEL.get(k, k), "value": int(st[k])} for k in ITEM_STATS if int(st.get(k, 0))],
        "rand_mastery": [{"value": v, "n": n} for v, n in it.random_mastery],
        "rand_res": [{"value": v, "n": n} for v, n in it.random_resistance],
        "craft": craft_of(CRAFTS, it.id, lang), "shop": it.is_shop, "wiki": wiki_url(it.names),
        "can_epic": it.is_epic or PROP_EPIC_GEM in it.properties, "can_relic": it.is_relic or PROP_RELIC_GEM in it.properties,
    }


def breakdown(t: Totals) -> dict[str, dict[str, Any]]:
    """Détail de chaque stat affichée : ce qui l'augmente ou la baisse (items, runes, aptitudes, sublimations)."""
    def lines(*stats: str) -> list[dict[str, Any]]:
        out = [{"src": o, "kind": k, "value": v, "ref": r} for st in stats for o, k, v, r in t.sources.get(st, [])]
        return sorted(out, key=lambda x: -x["value"])

    out: dict[str, dict[str, Any]] = {}
    for st in set(t.sources) | set(t.stats):
        out[st] = {"label": STAT_LABEL.get(st, st), "total": int(t.stats.get(st, 0)), "lines": lines(st)}
    for e in ELEMENTS:   # maîtrise / résistance d'un élément = élémentaire + élément + aléatoire
        out[f"{e}_mastery"] = {"label": f"Maîtrise {ELEMENT_FR[e]}", "total": t.mastery[e],
                               "lines": lines("elem_mastery", f"{e}_mastery")}
        out[f"{e}_res"] = {"label": f"Résistance {ELEMENT_FR[e]}", "total": t.res_flat[e],
                           "lines": lines("elem_res", f"{e}_res"), "note": f"= {t.res_pct[e]} % de réduction"}
    flat = sum(x["value"] for x in out.get("hp", {}).get("lines", []))
    pct = int(t.stats.get("hp_pct", 0))
    if pct:   # PV = PV fixes × (1 + %PV)
        out["hp"]["lines"].append({"src": f"Bonus de {pct} % PV (voir % PV)", "kind": "pct", "value": t.hp - flat})
    return out


def build_view(data: GameData, opts: OptimizeOptions, build: Build, t: Totals | None = None) -> dict[str, Any]:
    t = t or evaluate(data, opts, build)
    items = data.item_by_id()
    runes, subs = data.rune_by_id(), data.sub_by_id()
    lang = opts.lang
    cards = []
    for slot in SLOT_ORDER:
        ch = build.slots.get(slot)
        if ch is None or ch.item_id not in items:
            continue
        it = items[ch.item_id]
        c = item_brief(data, it, lang, opts.level)
        c["slot"], c["slot_name"] = slot.value, SLOT_FR[slot]
        c["rand_mastery"] = [{"value": v, "n": n, "els": list(els)} for (v, n), els in
                             zip(it.random_mastery, ch.mastery_elements or [()] * len(it.random_mastery))]
        c["rand_res"] = [{"value": v, "n": n, "els": list(els)} for (v, n), els in
                         zip(it.random_resistance, ch.resistance_elements or [()] * len(it.random_resistance))]
        shards = []
        for sh in ch.shards:
            r = runes.get(sh.rune_id) if sh.rune_id is not None else None
            shards.append({"color": int(sh.color), "color_name": COLOR_FR[sh.color],
                           "rune": r.name(lang) if r else None, "stat": r.stat if r else None,
                           "label": STAT_LABEL.get(r.stat, r.stat) if r else None,
                           "value": r.value(sh.rune_level, slot) if r else 0, "level": sh.rune_level})
        c["shards"] = shards
        for key, sid in (("sub", ch.sublimation_id), ("special", ch.special_sublimation_id)):
            if sid in subs:
                st = data.states.get(subs[sid].state_id)
                c[key] = {"id": sid, "state": subs[sid].state_id, "name": subs[sid].name(lang),
                          "desc": st.description if st else "", "modeled": bool(st and st.modeled),
                          "pattern": [int(x) for x in subs[sid].pattern]}
        it_special = it.is_epic or it.is_relic or PROP_EPIC_GEM in it.properties or PROP_RELIC_GEM in it.properties
        c["can_special"] = it_special
        c["forced"] = it.id in opts.forced_ids
        cards.append(c)
    s = t.stats
    active = []
    raw = build_levels(data, build)
    for sid, lvl in t.active_states.items():
        st = data.states.get(sid)
        if st:
            active.append({"name": data.state_name(sid, lang), "level": lvl, "desc": st.description, "limit": st.limit,
                           "raw": raw.get(sid, lvl), "modeled": st.modeled})
    cp = data.classes.get(opts.class_key)
    passive = None
    if cp and cp.passive_name:
        passive = {"name": cp.passive_name, "desc": cp.passive_desc,
                   "stats": [{"stat": k, "label": STAT_LABEL.get(k, k), "value": v} for k, v in cp.passive_stats(opts.level).items()]}
    return {
        "passive": passive,
        "removal": round(removal_factor(t.stats.get("willpower", 0)), 2) if opts.willpower_weight else None,
        "class": {"key": opts.class_key, "name": cp.name if cp else opts.class_key},
        "level": opts.level, "elements": list(opts.elements),
        "score": round(t.score, 2), "mastery_used": t.mastery_used, "damage": round(damage_multiplier(t.d2), 2), "ehp": round(t.defense / 1e4),
        "hp": t.hp, "mastery": t.mastery, "res_flat": t.res_flat, "res_pct": t.res_pct,
        "stats": {k: int(v) for k, v in s.items()}, "active": active, "items": cards, "breakdown": breakdown(t),
        "build": build.to_dict(), "text": build_text(data, opts, build, t, t.score),
        "json": build_json(data, opts, build, t, t.score),
    }


def compare(a: Totals, b: Totals, opts: OptimizeOptions) -> list[dict[str, Any]]:
    rows = []
    played = opts.played_elements()

    def add(label: str, stat: str, x: float, y: float, nd: int = 0, **change: dict[str, int]) -> None:
        """`change` : ce qui change dans les stats de `a` pour cette ligne seule (voir stats.rescore) ; sans : pas
        d'écart de score par ligne (Score, Dégâts)."""
        x, y = (round(x, nd), round(y, nd)) if nd else (int(x), int(y))
        if x != y:
            pts = round(rescore(a, opts, **change) - a.score, 1) if change else None
            rows.append({"label": label, "stat": stat, "old": x, "new": y, "diff": round(y - x, nd) if nd else y - x,
                         "score": pts})

    add("Score", "score", a.score, b.score, 1)
    add("Dégâts (×)", "dmg_pct", damage_multiplier(a.d2), damage_multiplier(b.d2), 2)
    for e in played:
        add(f"Maîtrise {ELEMENT_FR[e]}", e, a.mastery[e], b.mastery[e], mastery={e: b.mastery[e]})
    for e in ELEMENTS:
        add(f"Résistance {ELEMENT_FR[e]}", e, a.res_flat[e], b.res_flat[e], res_flat={e: b.res_flat[e]})
    for k in COMPARE:
        # PV : PV de base et % PV ensemble (la ligne montre les PV finaux)
        keys = ("hp", "hp_pct") if k == "hp" else (k,)
        add(STAT_LABEL.get(k, k), k, a.stats.get(k, 0), b.stats.get(k, 0),
            stats={x: b.raw.get(x, 0) for x in keys})
    return rows


def result_view(data: GameData, opts: OptimizeOptions, r: Any) -> dict[str, Any]:
    """Résultat d'un calcul (SolveResult) pour l'interface."""
    out: dict[str, Any] = {"status": r.status, "message": r.message, "warnings": r.warnings,
                           "diagnostics": r.diagnostics, "elapsed": round(r.elapsed, 1)}
    if r.builds:
        out["view"] = build_view(data, opts, r.builds[0], r.totals[0])
        out["explain"] = explain(data, opts, r.builds[0], r.totals[0])
    return out


def meta(d: GameData, settings: dict[str, Any]) -> dict[str, Any]:
    levels = sorted({hi for _lo, hi in d.brackets}, reverse=True)
    return {
        "version": d.version, "items": len(d.items),
        "classes": [{"key": k, "name": c.name, "elements": list(c.elements), "range": c.range, "role": c.role,
                     "rear": c.rear, "berserk": c.berserk, "archetypes": class_archetypes(d, k)}
                    for k, c in sorted(d.classes.items(), key=lambda kv: kv[1].name)],
        "archetypes": meta_archetypes(levels),
        "levels": [{"level": lv, "min_ap": default_min_ap(lv), "min_mp": default_min_mp(lv)} for lv in levels],
        "elements": [{"key": e, "name": ELEMENT_FR[e]} for e in ELEMENTS],
        "rarities": [{"id": int(r), "name": RARITY_FR[r], "color": RARITY_COLOR[r]} for r in Rarity],
        "slots": [{"key": s.value, "name": SLOT_FR[s]} for s in Slot],
        "settings": settings, "defaults": json.loads(OptimizeOptions().to_json()),
        "aptitudes": aptitudes(d),
    }


def preset_view(d: GameData, q: dict[str, list[str]]) -> dict[str, Any]:
    """Aptitudes rapides d'un archétype pour une classe et un niveau, avec leur description."""
    cls = q.get("cls", ["iop"])[0]
    cls = cls if cls in d.classes else next(iter(d.classes))
    level = int(q.get("level", ["245"])[0])
    arch = q.get("name", [""])[0]
    o = archetype_options(d, cls, level, arch or None)
    return {"points": preset(d, o.archetype, cls, level), "desc": profile_desc(o)}


def aptitudes(d: GameData) -> list[dict[str, Any]]:
    spec = d.game["characteristics"]
    out = []
    for branch, b in spec.items():  # type: ignore[union-attr]
        lines = [{"key": cl.key, "line": cl.line, "label": LINE_FR.get(cl.line, cl.line), "max": cl.max_points}
                 for cl in char_lines(d.game) if cl.branch == branch]
        out.append({"branch": branch, "name": BRANCH_FR.get(branch, branch), "offset": int(b.get("offset", 0)),
                    "lines": lines})
    return out


def search(d: GameData, q: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Items par nom et / ou par filtres (emplacement, rareté, tranche de niveau) ; ids = liste précise."""
    text = q.get("q", [""])[0].strip().lower()
    ids = [int(x) for x in q.get("ids", [""])[0].split(",") if x.isdigit()]
    level = int(q.get("level", ["245"])[0])
    lang = q.get("lang", ["fr"])[0]
    slot = q.get("slot", [""])[0]
    rars = {int(x) for x in q.get("rarity", [""])[0].split(",") if x.isdigit()}
    bracket = q.get("bracket", ["0"])[0] == "1"
    limit = min(300, int(q.get("limit", ["80"])[0] or 80))
    by_id = d.item_by_id()
    if ids:
        return [dict(item_brief(d, by_id[i], lang, level), slot_name=SLOT_FR[by_id[i].slots[0]] if by_id[i].slots else "")
                for i in ids if i in by_id]
    if len(text) < 2 and not slot:
        return []
    lo = next((a for a, b in d.brackets if a <= level <= b), 1) if bracket else 0
    found = [it for it in d.items
             if not it.is_hidden and (it.level <= level or it.scales_with_character)
             and (not bracket or it.level >= lo or it.scales_with_character)
             and (not slot or any(s.value == slot for s in it.slots))
             and (not rars or int(it.rarity) in rars)
             and (len(text) < 2 or text in it.name(lang).lower())]
    found.sort(key=lambda it: (-it.level, -int(it.rarity), it.name(lang)))
    out = []
    for it in found[:limit]:
        b = item_brief(d, it, lang, level)
        b["slot_name"] = SLOT_FR[it.slots[0]] if it.slots else ""
        out.append(b)
    return out


def family_json(d: GameData, f: SubFamily, lang: str) -> dict[str, Any]:
    return {"state": f.state_id, "name": d.state_name(f.state_id, lang), "desc": f.desc, "limit": f.limit, "kind": f.kind,
            "modeled": f.modeled, "applicable": f.applicable, "in_build": f.in_build, "gain": f.gain,
            "same_levels": f.same_levels, "confirmed": f.confirmed,
            "levels": [{"id": s.id, "name": s.name(lang), "level": s.state_level, "gfx": s.gfx_id,
                        "pattern": [int(x) for x in s.pattern]} for s in f.subs]}


def subs_view(d: GameData, body: dict[str, Any]) -> list[dict[str, Any]]:
    """Catalogue des sublimations (onglet Sublimations), avec leur apport sur le build affiché."""
    opts = opts_from(body.get("opts", {}), d)
    build = Build.from_dict(body["build"]) if body.get("build") else None
    return [family_json(d, f, opts.lang) for f in catalog(d, opts, build)]


def sub_alternatives_view(d: GameData, body: dict[str, Any]) -> dict[str, Any]:
    opts = opts_from(body.get("opts", {}), d)
    build = Build.from_dict(body["build"])
    slot = Slot(body["slot"])
    special = bool(body.get("special"))
    base = evaluate(d, opts, build)
    options, other_colors = sub_alternatives(d, opts, build, slot, special)
    out = []
    for o in options:
        st = d.states.get(o.sub.state_id) if o.sub else None
        out.append({"id": o.sub.id if o.sub else None, "name": o.sub.name(opts.lang) if o.sub else "Aucune sublimation",
                    "desc": st.description if st else "", "modeled": bool(st and st.modeled),
                    "inactive": bool(st and condition_failed(o.totals, st.name)),
                    "pattern": [int(x) for x in o.sub.pattern] if o.sub else [], "delta": o.delta,
                    "build": o.build.to_dict(), "compare": compare(base, o.totals, opts)})
    return {"slot": slot.value, "slot_name": SLOT_FR[slot], "special": special, "items": out,
            "other_colors": other_colors}


def alternatives_view(d: GameData, body: dict[str, Any]) -> dict[str, Any]:
    opts = opts_from(body.get("opts", {}), d)
    build = Build.from_dict(body["build"])
    slot = Slot(body["slot"])
    base = evaluate(d, opts, build)
    out = []
    for a in alternatives(d, opts, build, slot):
        b = item_brief(d, a.item, opts.lang, opts.level)
        b.update(delta=round(a.delta, 2), build=a.build.to_dict(), compare=compare(base, a.totals, opts),
                 dropped=[SLOT_FR[s] for s in build.slots if s not in a.build.slots])
        out.append(b)
    return {"slot": slot.value, "slot_name": SLOT_FR[slot], "items": out}


def weights_route(d: GameData, body: dict[str, Any]) -> dict[str, Any]:
    """Onglet Poids : poids de l'archétype et poids utilisés (avec ceux modifiés par l'utilisateur)."""
    o = dict(body.get("opts", {}))
    opts = opts_from(o, d)
    default = opts_from({**o, "custom_weights": {}}, d)
    out = weights_view(default, opts)
    out["archetype"] = ARCHETYPES[opts.archetype].name
    return out


def forge_view(d: GameData, body: dict[str, Any]) -> dict[str, Any]:
    """Onglet Build sombre (debug) : combos de sublimations sur le build affiché (voir engine/combos.py)."""
    opts = opts_from(body.get("opts", {}), d)
    p = ForgeParams.from_dict(body.get("params", {}))
    r = forge(d, opts, Build.from_dict(body["build"]), p)
    lang, items, build = opts.lang, d.item_by_id(), Build.from_dict(body["build"])

    def host(h: Host) -> dict[str, Any]:
        ch = build.slots.get(h.slot) if h.slot else None
        it = items.get(ch.item_id) if ch else None
        special = "normal" not in h.kinds
        name = SLOT_FR[h.slot] if h.slot else ("Emplacement épique (théorique)" if "epic" in h.kinds else "Emplacement relique (théorique)")
        return {"slot": h.slot.value if h.slot else None, "slot_name": name, "special": special,
                "item": it.name(lang) if it else None, "gfx": it.gfx_id if it else None, "colors": [int(c) for c in h.colors]}

    def state(sid: int) -> dict[str, Any]:
        st = d.states.get(sid)
        sub = next((s for s in d.sublimations if s.state_id == sid), None)
        return {"state": sid, "name": d.state_name(sid, lang), "desc": st.description if st else "",
                "kind": "epic" if sub and sub.is_epic else "relic" if sub and sub.is_relic else "normal",
                "gfx": sub.gfx_id if sub else 0, "confirmed": bool(st and st.confirmed)}

    combos = []
    for cb in r.combos:
        final = cb.exact if cb.exact is not None else cb.value
        parts = [dict(state(pt.state_id), level=pt.level, limit=pt.limit, solo=round(pt.solo, 2), marginal=round(pt.marginal, 2),
                      role=pt.role, conditions=[{"label": c.label, "value": c.value, "threshold": c.threshold, "ok": c.ok,
                                                 "margin": c.margin} for c in pt.conditions],
                      subs=[{"id": s.id, "name": s.name(lang), "gfx": s.gfx_id, "level": s.state_level,
                             "pattern": [int(x) for x in s.pattern], "host": host(h),
                             "recolored": h.slot in cb.recolored and not s.is_epic and not s.is_relic} for s, h in pt.placed])
                 for pt in cb.parts]
        t = cb.totals
        combos.append({
            "name": cb.name, "gain": round(cb.gain, 2), "synergy": round(cb.synergy, 2), "value": round(final, 2),
            "estimate": round(cb.value, 2), "vs_current": round(final - r.current_value, 2),
            "score": round(t.score, 2), "damage": round(damage_multiplier(t.d2), 3), "ehp": round(t.defense / 1e4),
            "stats": {k: int(t.stats.get(k, 0)) for k in ("ap", "mp", "wp", "range", "crit_rate", "block", "dmg_pct", "willpower")},
            "mastery_used": t.mastery_used, "hp": t.hp,
            "parts": parts, "compare": compare(r.bare, t, opts),
            "build": cb.build.to_dict() if cb.build else None,
            "recolored": [SLOT_FR[s] for s in cb.recolored],
            "runes_changed": [{"slot_name": SLOT_FR[s], "before": a, "after": b} for s, a, b in cb.runes_changed],
            "forced": {str(pt.state_id): pt.level for pt in cb.parts},
        })
    hosts = r.hosts
    return {
        "params": {"mode": p.mode, "objective": p.objective},
        "bare": round(r.bare_value, 2), "current": round(r.current_value, 2),
        "bare_score": round(r.bare.score, 2), "current_score": round(r.current.score, 2),
        "combos": combos,
        "solo": [dict(state(s), gain=round(v, 2)) for s, v in r.solo[:16]],
        "matrix": {"states": [state(s) for s in r.matrix_states],
                   "cells": [[None if v is None else round(v, 2) for v in row] for row in r.matrix]},
        "duos": [{"a": state(a), "b": state(b), "synergy": round(v, 2)} for a, b, v in r.duos],
        "search": {"evals": r.evals, "elapsed": round(r.elapsed, 2), "timed_out": r.timed_out, "pieces": r.n_pieces,
                   "hosts": sum("normal" in h.kinds for h in hosts), "specials": sum("normal" not in h.kinds for h in hosts),
                   "phases": [{"name": n, "time": round(sec, 2), "evals": e} for n, sec, e in r.phases]},
        "messages": r.messages,
    }


def view_route(d: GameData, body: dict[str, Any]) -> dict[str, Any]:
    return build_view(d, opts_from(body.get("opts", {}), d), Build.from_dict(body["build"]))


# =====================================================================  requêtes
Route = Callable[[GameData, dict[str, list[str]], dict[str, Any]], Any]
ROUTES: dict[tuple[str, str], Route] = {
    ("GET", "/api/preset"): lambda d, q, body: preset_view(d, q),
    ("GET", "/api/items"): lambda d, q, body: search(d, q),
    ("POST", "/api/view"): lambda d, q, body: view_route(d, body),
    ("POST", "/api/weights"): lambda d, q, body: weights_route(d, body),
    ("POST", "/api/alternatives"): lambda d, q, body: alternatives_view(d, body),
    ("POST", "/api/subs"): lambda d, q, body: subs_view(d, body),
    ("POST", "/api/sub_alternatives"): lambda d, q, body: sub_alternatives_view(d, body),
    ("POST", "/api/forge"): lambda d, q, body: forge_view(d, body),
}
