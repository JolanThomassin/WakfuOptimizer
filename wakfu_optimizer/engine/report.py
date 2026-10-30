"""Export texte / JSON d'un build."""

from __future__ import annotations

import json
from typing import Any

from ..data.models import COLOR_FR, ELEMENT_FR, ELEMENTS, RARITY_FR, SLOT_FR, GameData, Slot
from .characteristics import BRANCH_FR, LINE_FR
from .options import Build, OptimizeOptions
from .scoring import damage_multiplier
from .stats import DISPLAY_STATS, Totals

SLOT_ORDER = list(Slot)


def describe_item_stats(data: GameData, item_id: int, lang: str, level: int, limit: int = 8) -> str:
    it = data.item_by_id().get(item_id)
    if it is None:
        return ""
    labels = dict(DISPLAY_STATS)
    labels.update({"elem_mastery": "Maîtrise élém.", "elem_res": "Rés. élém."})
    for e in ELEMENTS:
        labels[f"{e}_mastery"] = f"Maîtrise {ELEMENT_FR[e]}"
        labels[f"{e}_res"] = f"Rés. {ELEMENT_FR[e]}"
    parts = []
    st = it.stats_at(level)
    for k in ("ap", "mp", "wp", "range", "hp", "crit_rate", "elem_mastery", "melee_mastery", "distance_mastery",
              "crit_mastery", "rear_mastery", "berserk_mastery", "heal_mastery", "elem_res", "block"):
        if st.get(k):
            parts.append(f"{int(st[k]):+d} {labels.get(k, k)}")
    for v, n in it.random_mastery:
        parts.append(f"+{v} Maîtrise ×{n} élém.")
    for v, n in it.random_resistance:
        parts.append(f"+{v} Rés. ×{n} élém.")
    return ", ".join(parts[:limit])


SITE_URL = "https://jolanthomassin.github.io/WakfuOptimizer/"
WIDTH = 64


def _n(v: float) -> str:
    """Nombre au format français : 12 345."""
    return f"{int(round(v)):,}".replace(",", " ")


def _title(text: str) -> str:
    return f"── {text} " + "─" * max(3, WIDTH - len(text) - 4)


def build_text(data: GameData, opts: OptimizeOptions, build: Build, totals: Totals, score: float | None = None) -> str:
    """Build lisible en texte brut (à coller sur Discord, un forum, ou à enregistrer en .txt)."""
    items = data.item_by_id()
    runes = {r.id: r for r in data.runes}
    subs = {s.id: s for s in data.sublimations}
    lang = opts.lang
    cls = data.classes.get(opts.class_key)
    s = totals.stats
    els = " / ".join(ELEMENT_FR[e] for e in opts.elements)
    L: list[str] = ["═" * WIDTH, f"  BUILD WAKFU · {cls.name if cls else opts.class_key} niveau {opts.level} · {els}", "═" * WIDTH]
    L.append(f"  PV {_n(totals.hp)}   PA {s.get('ap', 0)}   PM {s.get('mp', 0)}   PW {s.get('wp', 0)}   "
             f"PO {s.get('range', 0)}   Critique {s.get('crit_rate', 0)} %   Parade {s.get('block', 0)} %")
    head = f"  Dégâts ×{damage_multiplier(totals.d2):.2f}   PV effectifs {_n(totals.defense / 1e4)}".replace(".", ",")
    L.append(head + (f"   Score {score:.1f}".replace(".", ",") if score is not None else ""))

    L += ["", _title("Maîtrises")]
    L.append("  " + "   ".join(f"{ELEMENT_FR[e]} {_n(totals.mastery[e])}" for e in ELEMENTS))
    sec = [("Mêlée", "melee_mastery"), ("Distance", "distance_mastery"), ("Critique", "crit_mastery"), ("Dos", "rear_mastery"),
           ("Berserk", "berserk_mastery"), ("Soin", "heal_mastery")]
    L.append("  " + "   ".join(f"{lab} {_n(s.get(k, 0))}" for lab, k in sec if s.get(k, 0)) or "  (aucune maîtrise secondaire)")
    L.append(f"  Dommages infligés {s.get('dmg_pct', 0)} %")
    L += ["", _title("Résistances")]
    L.append("  " + "   ".join(f"{ELEMENT_FR[e]} {totals.res_pct[e]} % ({totals.res_flat[e]})" for e in ELEMENTS))
    other = [("Tacle", "lock"), ("Esquive", "dodge"), ("Initiative", "initiative"), ("Volonté", "willpower"),
             ("Rés. critique", "crit_res"), ("Rés. dos", "rear_res")]
    L.append("  " + "   ".join(f"{lab} {_n(s.get(k, 0))}" for lab, k in other))

    L += ["", _title("Équipement")]
    pad = 14
    for slot in SLOT_ORDER:
        ch = build.slots.get(slot)
        if ch is None or ch.item_id not in items:
            continue
        it = items[ch.item_id]
        L.append(f"  {SLOT_FR[slot]:<{pad}}{it.name(lang)}  (niv. {it.level}, {RARITY_FR[it.rarity]})")
        ind = " " * (pad + 2)
        for el in ch.mastery_elements:
            L.append(f"{ind}Maîtrise au choix : {', '.join(ELEMENT_FR[e] for e in el)}")
        for el in ch.resistance_elements:
            L.append(f"{ind}Résistance au choix : {', '.join(ELEMENT_FR[e] for e in el)}")
        if ch.shards:
            parts = []
            for sh in ch.shards:
                r = runes.get(sh.rune_id) if sh.rune_id is not None else None
                parts.append(f"[{COLOR_FR[sh.color].split(' ')[0]}] " + (f"{r.name(lang)} niv. {sh.rune_level} (+{r.value(sh.rune_level, slot)})" if r else "vide"))
            L.append(f"{ind}Châsses : " + parts[0])
            L += [f"{ind}          {p}" for p in parts[1:]]
        if ch.sublimation_id in subs:
            L.append(f"{ind}Sublimation : {subs[ch.sublimation_id].name(lang)}")
        if ch.special_sublimation_id in subs:
            L.append(f"{ind}Sublimation épique / relique : {subs[ch.special_sublimation_id].name(lang)}")

    if totals.active_states:
        L += ["", _title("Sublimations actives")]
        for sid, lvl in totals.active_states.items():
            st = data.states.get(sid)
            if st:
                L.append(f"  {st.name} niv. {lvl}" + (f"/{st.limit}" if st.limit else ""))

    if build.characteristics:
        L += ["", _title("Aptitudes")]
        by_branch: dict[str, list[str]] = {}
        for key, n in build.characteristics.items():
            if n:
                branch, line = key.split(".", 1)
                by_branch.setdefault(branch, []).append(f"{LINE_FR.get(line, line)} {n}")
        for branch in ("intelligence", "strength", "agility", "fortune", "major"):
            if branch in by_branch:
                L.append(f"  {BRANCH_FR.get(branch, branch) + ' :':<15} " + " · ".join(by_branch[branch]))

    L += ["", "─" * WIDTH, f"  Généré avec Wakfu Optimizer · {SITE_URL}", f"  Données du jeu {data.version}"]
    return "\n".join(L)


def build_json(data: GameData, opts: OptimizeOptions, build: Build, totals: Totals, score: float | None = None) -> str:
    items = data.item_by_id()
    out: dict[str, Any] = {
        "version_donnees": data.version,
        "options": json.loads(opts.to_json()),
        "score": score,
        "build": build.to_dict(),
        "items": {s.value: {"id": c.item_id, "nom": items[c.item_id].name(opts.lang)} for s, c in build.slots.items()},
        "totaux": {
            "stats": totals.stats, "maitrises": totals.mastery, "resistances": totals.res_flat,
            "resistances_pct": totals.res_pct, "pv": totals.hp,
            "multiplicateur_degats": round(damage_multiplier(totals.d2), 4), "pv_effectifs": round(totals.defense / 1e4),
        },
    }
    return json.dumps(out, indent=2, ensure_ascii=False)
