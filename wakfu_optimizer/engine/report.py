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


def build_text(data: GameData, opts: OptimizeOptions, build: Build, totals: Totals, score: float | None = None) -> str:
    items = data.item_by_id()
    runes = {r.id: r for r in data.runes}
    subs = {s.id: s for s in data.sublimations}
    lang = opts.lang
    cls = data.classes.get(opts.class_key)
    lines = [f"Build Wakfu — {cls.name if cls else opts.class_key} niveau {opts.level} "
             f"({', '.join(ELEMENT_FR[e] for e in opts.elements)}) — données {data.version}"]
    if score is not None:
        lines.append(f"Score : {score:.1f}")
    lines.append("")
    for slot in SLOT_ORDER:
        ch = build.slots.get(slot)
        if ch is None:
            continue
        it = items[ch.item_id]
        lines.append(f"{SLOT_FR[slot]:<13} {it.name(lang)} (niv. {it.level}, {RARITY_FR[it.rarity]})")
        for els in ch.mastery_elements:
            lines.append(f"{'':13}  maîtrise sur : {', '.join(ELEMENT_FR[e] for e in els)}")
        for els in ch.resistance_elements:
            lines.append(f"{'':13}  résistance sur : {', '.join(ELEMENT_FR[e] for e in els)}")
        if ch.shards:
            sh_txt = []
            for sh in ch.shards:
                if sh.rune_id is not None and sh.rune_id in runes:
                    r = runes[sh.rune_id]
                    sh_txt.append(f"[{COLOR_FR[sh.color]}] {r.name(lang)} niv.{sh.rune_level} (+{r.value(sh.rune_level, slot)})")
                else:
                    sh_txt.append(f"[{COLOR_FR[sh.color]}] vide")
            lines.append(f"{'':13}  châsses : " + " | ".join(sh_txt))
        if ch.sublimation_id in subs:
            lines.append(f"{'':13}  sublimation : {subs[ch.sublimation_id].name(lang)}")
        if ch.special_sublimation_id in subs:
            lines.append(f"{'':13}  sublimation spéciale : {subs[ch.special_sublimation_id].name(lang)}")
    if build.characteristics:
        lines += ["", "Caractéristiques :"]
        for key, n in sorted(build.characteristics.items()):
            branch, line = key.split(".", 1)
            lines.append(f"  {BRANCH_FR.get(branch, branch)} — {LINE_FR.get(line, line)} : {n}")
    lines += ["", "Totaux :"]
    s = totals.stats
    lines.append(f"  PV {totals.hp} | PA {s.get('ap', 0)} | PM {s.get('mp', 0)} | PW {s.get('wp', 0)} | "
                 f"Portée {s.get('range', 0)} | Critique {s.get('crit_rate', 0)} %")
    lines.append("  Maîtrises : " + ", ".join(f"{ELEMENT_FR[e]} {totals.mastery[e]}" for e in ELEMENTS)
                 + f" | Mêlée {s.get('melee_mastery', 0)} | Distance {s.get('distance_mastery', 0)}"
                 + f" | Critique {s.get('crit_mastery', 0)} | Dos {s.get('rear_mastery', 0)}"
                 + f" | Berserk {s.get('berserk_mastery', 0)} | Soin {s.get('heal_mastery', 0)}")
    lines.append("  Résistances : " + ", ".join(f"{ELEMENT_FR[e]} {totals.res_flat[e]} ({totals.res_pct[e]} %)" for e in ELEMENTS))
    lines.append(f"  Multiplicateur de dégâts moyen : ×{damage_multiplier(totals.d2):.2f}"
                 f" | PV effectifs : {totals.defense / 1e4:,.0f}".replace(",", " "))
    return "\n".join(lines)


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
