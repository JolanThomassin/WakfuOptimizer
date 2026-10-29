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
from .views import CRAFTS, ROUTES, meta, opts_from, result_view

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
    route = ROUTES.get((method, p))
    if method == "GET" and p == "/api/meta":
        out = meta(d, json.loads(settings_json or "{}"))
    elif route is not None:
        out = route(d, q, body)
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
