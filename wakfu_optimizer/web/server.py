"""Interface web locale : petit serveur HTTP (bibliothèque standard) + page HTML/JS (static/).

    python -m wakfu_optimizer.web          -> ouvre le navigateur sur http://127.0.0.1:<port>

Les réponses JSON sont dans views.py ; ici : fichiers, données, calculs en tâche de fond (start_job).
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
from ..data.models import GameData
from ..data.parse import load_game_data
from ..data.sources import load_crafts
from ..engine.options import OptimizeOptions
from .views import CRAFTS, ROUTES, meta, opts_from, result_view

log = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parent / "static"
ASSETS = Path(__file__).resolve().parents[1] / "gui" / "assets"
ICON_DIR = DEFAULT_CACHE_ROOT / "icons"
APP_DIR = Path(__file__).resolve().parents[2]
LAST_SETTINGS = APP_DIR / "presets" / "_dernier.json"


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

    def _route(self, method: str, p: str, q: dict[str, list[str]], body: dict[str, Any]) -> None:
        """Requêtes communes avec la version navigateur (views.ROUTES)."""
        route = ROUTES.get((method, p))
        if route is None:
            return self._send(404, b"not found", "text/plain")
        if STATE.data is None:
            return self._json({"error": "données non chargées"}, 503)
        return self._json(route(STATE.data, q, body))

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
            if p == "/api/items" and STATE.data is None:
                return self._json([])
            return self._route("GET", p, parse_qs(u.query), {})
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
            return self._route("POST", p, {}, body)
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
