"""Interface web locale : petit serveur HTTP (bibliothèque standard) + page HTML/JS.

    python -m wakfu_optimizer.web          -> ouvre le navigateur sur http://127.0.0.1:<port>
"""

from __future__ import annotations

import json
import logging
import mimetypes
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..data.fetch import DEFAULT_CACHE_ROOT, GameDataFetcher
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
from ..data.parse import load_game_data
from ..data.sources import Crafts, load_crafts, wiki_url
from ..engine.alternatives import alternatives
from ..engine.archetypes import (PANELS, apply_archetype, archetype_options, class_archetypes, meta_archetypes, preset,
                                 profile_desc)
from ..engine.characteristics import BRANCH_FR, LINE_FR, char_lines
from ..engine.options import Build, OptimizeOptions, default_min_ap, default_min_mp
from ..engine.quality import explain
from ..engine.report import SLOT_ORDER, build_json, build_text
from ..engine.scoring import damage_multiplier, removal_factor
from ..engine.stats import Totals, evaluate
from ..engine.sublimations import SubFamily, build_levels, catalog, condition_failed, sub_alternatives

log = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parent / "static"
ASSETS = Path(__file__).resolve().parents[1] / "gui" / "assets"
ICON_DIR = DEFAULT_CACHE_ROOT / "icons"
APP_DIR = Path(__file__).resolve().parents[2]
LAST_SETTINGS = APP_DIR / "presets" / "_dernier.json"

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


# =====================================================================  état
class State:
    def __init__(self) -> None:
        self.data: GameData | None = None
        self.error = ""
        self.loading = True
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def load(self, force: bool = False) -> None:
        self.loading = True
        try:
            bundle = GameDataFetcher().ensure(force=force)
            self.data = load_game_data(bundle)
            CRAFTS.clear()
            CRAFTS.update(load_crafts(bundle, {it.id for it in self.data.items}))
            self.error = ""
        except Exception as exc:  # noqa: BLE001 - affiché à l'utilisateur
            log.exception("Chargement des données")
            self.error = f"Données indisponibles : {exc}"
        finally:
            self.loading = False


STATE = State()


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
        "craft": CRAFTS.get(it.id), "shop": it.is_shop, "wiki": wiki_url(it.names),
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
            active.append({"name": st.name, "level": lvl, "desc": st.description, "limit": st.limit,
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
    played = [e for e in opts.elements if e in ELEMENTS] or list(ELEMENTS)

    def add(label: str, stat: str, x: float, y: float, nd: int = 0) -> None:
        x, y = (round(x, nd), round(y, nd)) if nd else (int(x), int(y))
        if x != y:
            rows.append({"label": label, "stat": stat, "old": x, "new": y, "diff": round(y - x, nd) if nd else y - x})

    add("Score", "score", a.score, b.score, 1)
    add("Dégâts (×)", "dmg_pct", damage_multiplier(a.d2), damage_multiplier(b.d2), 2)
    add("PV effectifs", "hp", a.defense / 1e4, b.defense / 1e4)
    for e in played:
        add(f"Maîtrise {ELEMENT_FR[e]}", e, a.mastery[e], b.mastery[e])
    for e in ELEMENTS:
        add(f"Résistance {ELEMENT_FR[e]}", e, a.res_flat[e], b.res_flat[e])
    for k in COMPARE:
        add(STAT_LABEL.get(k, k), k, a.stats.get(k, 0), b.stats.get(k, 0))
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
        "archetypes": meta_archetypes(),
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
    return {"state": f.state_id, "name": f.name, "desc": f.desc, "limit": f.limit, "kind": f.kind,
            "modeled": f.modeled, "applicable": f.applicable, "in_build": f.in_build, "gain": f.gain,
            "same_levels": f.same_levels,
            "levels": [{"id": s.id, "name": s.name(lang), "level": s.state_level,
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


# =====================================================================  optimisation (tâches)
def start_job(opts: OptimizeOptions) -> str:
    from ..engine.solver import Optimizer

    jid = uuid.uuid4().hex[:10]
    job: dict[str, Any] = {"progress": 0.0, "msg": "Démarrage…", "done": False, "result": None, "t0": time.monotonic()}

    def progress(msg: str, frac: float) -> None:
        job["msg"], job["progress"] = msg, max(job["progress"], frac)

    assert STATE.data is not None
    opt = Optimizer(STATE.data, opts, progress=progress)
    job["optimizer"] = opt

    def run() -> None:
        try:
            r = opt.run()
            job["result"] = result_view(STATE.data, opts, r)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            log.exception("Optimisation")
            job["result"] = {"status": "erreur", "message": f"Erreur : {exc}", "warnings": [], "diagnostics": []}
        finally:
            job["done"] = True
            job["progress"] = 1.0

    with STATE.lock:
        STATE.jobs = {k: v for k, v in STATE.jobs.items() if not v["done"]}
        STATE.jobs[jid] = job
    threading.Thread(target=run, daemon=True).start()
    return jid


# =====================================================================  HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "WakfuOptimizer/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # silence
        log.debug(fmt, *args)

    def _send(self, code: int, body: bytes, ctype: str, cache: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _file(self, path: Path, cache: bool = False) -> None:
        if not path.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype, cache)

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    # ------------------------------------------------------------------ GET
    def do_GET(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        p = u.path
        try:
            if p in ("/", "/index.html"):
                return self._file(STATIC / "index.html")
            if p.startswith("/static/"):
                return self._file(STATIC / p[len("/static/"):].replace("..", ""))
            if p.startswith("/assets/"):
                return self._file(ASSETS / p[len("/assets/"):].replace("..", ""))
            if p.startswith("/icon/"):
                return self._item_icon(p[len("/icon/"):].removesuffix(".png"))
            if p == "/api/meta":
                return self._json(self._meta())
            if p == "/api/job":
                jid = parse_qs(u.query).get("id", [""])[0]
                job = STATE.jobs.get(jid)
                if job is None:
                    return self._json({"error": "tâche inconnue"}, 404)
                return self._json({"progress": job["progress"], "msg": job["msg"], "done": job["done"],
                                   "elapsed": round(time.monotonic() - job["t0"], 1), "result": job["result"]})
            if p == "/api/preset":
                q = parse_qs(u.query)
                if STATE.data is None:
                    return self._json({"error": "données non chargées"}, 503)
                return self._json(preset_view(STATE.data, q))
            if p == "/api/items":
                return self._json(search(STATE.data, parse_qs(u.query)) if STATE.data else [])
            return self._send(404, b"not found", "text/plain")
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as exc:  # noqa: BLE001
            log.exception("GET %s", p)
            return self._json({"error": str(exc)}, 500)

    def _item_icon(self, gfx: str) -> None:
        if not gfx.isdigit():
            return self._send(404, b"", "text/plain")
        path = ICON_DIR / f"{gfx}.png"
        if not path.is_file():
            try:
                with urllib.request.urlopen(f"https://static.ankama.com/wakfu/portal/game/item/115/{gfx}.png", timeout=8) as r:
                    raw = r.read()
                ICON_DIR.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            except OSError:
                return self._send(404, b"", "text/plain")
        return self._file(path, cache=True)

    def _meta(self) -> dict[str, Any]:
        d = STATE.data
        if d is None:
            return {"loading": STATE.loading, "error": STATE.error}
        settings: dict[str, Any] = {}
        try:
            if LAST_SETTINGS.is_file():
                settings = json.loads(LAST_SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            settings = {}
        return meta(d, settings)

    # ------------------------------------------------------------------ POST
    def do_POST(self) -> None:  # noqa: N802
        p = urlparse(self.path).path
        try:
            body = self._body()
            d = STATE.data
            if p == "/api/reload":
                threading.Thread(target=STATE.load, kwargs={"force": True}, daemon=True).start()
                STATE.data = None
                return self._json({"ok": True})
            if d is None:
                return self._json({"error": "données non chargées"}, 503)
            if p == "/api/optimize":
                opts = opts_from(body.get("opts", {}), d)
                try:
                    LAST_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
                    LAST_SETTINGS.write_text(opts.to_json(), encoding="utf-8")
                except OSError:
                    pass
                return self._json({"job": start_job(opts)})
            if p == "/api/cancel":
                job = STATE.jobs.get(body.get("job", ""))
                if job is not None:
                    job["optimizer"].stop()
                return self._json({"ok": True})
            if p == "/api/view":
                opts = opts_from(body.get("opts", {}), d)
                return self._json(build_view(d, opts, Build.from_dict(body["build"])))
            if p == "/api/alternatives":
                return self._json(alternatives_view(d, body))
            if p == "/api/subs":
                return self._json(subs_view(d, body))
            if p == "/api/sub_alternatives":
                return self._json(sub_alternatives_view(d, body))
            return self._send(404, b"not found", "text/plain")
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as exc:  # noqa: BLE001
            log.exception("POST %s", p)
            return self._json({"error": str(exc)}, 500)


def serve(port: int = 0, open_browser: bool = True) -> None:
    threading.Thread(target=STATE.load, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    log.info("Interface : %s", url)
    print(f"Wakfu Optimizer : {url}", flush=True)  # noqa: T201
    if open_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    httpd.serve_forever()
