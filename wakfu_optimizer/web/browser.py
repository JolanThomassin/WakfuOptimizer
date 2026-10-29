"""Version navigateur (Pyodide, GitHub Pages) : mêmes requêtes que le serveur local, sans HTTP.

Appelé depuis ``static/worker.js``. Les données sont livrées avec le site (voir tools/build_site.py)
et le calcul tourne de façon synchrone dans le Web Worker.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..data.fetch import DataBundle
from ..data.models import GameData
from ..data.parse import load_game_data
from ..data.sources import load_crafts
from ..engine.options import Build
from .server import (CRAFTS, alternatives_view, build_view, meta, opts_from, preset_view, result_view, search,
                     sub_alternatives_view, subs_view)

DATA: GameData | None = None


def init(data_dir: str, version: str) -> None:
    global DATA
    bundle = DataBundle(version, Path(data_dir), offline=True)
    DATA = load_game_data(bundle)
    CRAFTS.update(load_crafts(bundle))


def request(method: str, path: str, body_json: str, settings_json: str) -> str:
    """Traite une requête /api/... et renvoie la réponse JSON."""
    assert DATA is not None
    d = DATA
    u = urlparse(path)
    p, q = u.path, parse_qs(u.query)
    body: dict[str, Any] = json.loads(body_json or "{}")
    out: Any
    if method == "GET" and p == "/api/meta":
        out = meta(d, json.loads(settings_json or "{}"))
    elif method == "GET" and p == "/api/preset":
        out = preset_view(d, q)
    elif method == "GET" and p == "/api/items":
        out = search(d, q)
    elif p == "/api/view":
        out = build_view(d, opts_from(body.get("opts", {}), d), Build.from_dict(body["build"]))
    elif p == "/api/alternatives":
        out = alternatives_view(d, body)
    elif p == "/api/subs":
        out = subs_view(d, body)
    elif p == "/api/sub_alternatives":
        out = sub_alternatives_view(d, body)
    else:
        out = {"error": f"requête inconnue : {method} {p}"}
    return json.dumps(out, ensure_ascii=False)


def optimize(opts_json: str, progress: Callable[[str, float], None]) -> str:
    from ..engine.solver import Optimizer

    assert DATA is not None
    opts = opts_from(json.loads(opts_json), DATA)
    try:
        r = Optimizer(DATA, opts, progress=progress).run()
        out = result_view(DATA, opts, r)
    except Exception as exc:  # noqa: BLE001 - affiché à l'utilisateur
        out = {"status": "erreur", "message": f"Erreur : {exc}", "warnings": [], "diagnostics": []}
    return json.dumps(out, ensure_ascii=False)
