"""Construit la version statique (GitHub Pages) : l'interface web + le moteur Python exécuté par Pyodide.

    python tools/build_site.py --out _site

Le CDN Ankama n'autorise pas les requêtes depuis un autre site (pas de CORS) : les données nécessaires
sont donc allégées et copiées dans le site. Le workflow .github/workflows/pages.yml relance ce script
chaque jour pour suivre les patchs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wakfu_optimizer.data.fetch import DataBundle, GameDataFetcher  # noqa: E402
from wakfu_optimizer.data.parse import load_game_data  # noqa: E402
from wakfu_optimizer.data.sources import dump_crafts, load_crafts  # noqa: E402

PKG = ROOT / "wakfu_optimizer"
WEB = PKG / "web"
# Fichiers du paquet utiles au navigateur (pas d'interface Qt ni de serveur HTTP lancé)
PY_FILES = ["__init__.py", "data/*.py", "data/static/*.yaml", "engine/*.py", "web/__init__.py",
            "web/views.py", "web/browser.py"]
DATA_FILES = ["items.json", "equipmentItemTypes.json", "sources.json"]


def slim_item(entry: dict[str, Any]) -> dict[str, Any]:
    """Ne garde que ce que lit data/parse.py."""
    d = entry["definition"]
    it = dict(d["item"])
    it.pop("useParameters", None)
    if "graphicParameters" in it:
        it["graphicParameters"] = {"gfxId": it["graphicParameters"].get("gfxId", 0)}
    effects = [{"effect": {"definition": {"actionId": e["effect"]["definition"]["actionId"],
                                          "params": e["effect"]["definition"].get("params", [])}}}
               for e in d.get("equipEffects", [])]
    return {"definition": {"item": it, "equipEffects": effects}, "title": entry.get("title") or {}}


def package_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for pattern in PY_FILES:
            for f in sorted(PKG.glob(pattern)):
                z.write(f, Path("wakfu_optimizer") / f.relative_to(PKG))
    return buf.getvalue()


def build(out: Path, force: bool) -> None:
    bundle = GameDataFetcher().ensure(force=force)
    if out.exists():
        shutil.rmtree(out)
    data_dir = out / "data" / bundle.version
    data_dir.mkdir(parents=True)
    items = [slim_item(e) for e in bundle.load("items")]  # type: ignore[union-attr]
    (data_dir / "items.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.copyfile(bundle.path("equipmentItemTypes"), data_dir / "equipmentItemTypes.json")
    # contrôle : les données allégées donnent exactement le même résultat
    full, slim = load_game_data(bundle), load_game_data(DataBundle(bundle.version, data_dir, offline=True))
    if full.items != slim.items or full.runes != slim.runes or full.sublimations != slim.sublimations:
        raise SystemExit("Les données allégées diffèrent des données complètes : vérifier slim_item().")
    crafts = load_crafts(bundle, {it.id for it in full.items})
    (data_dir / "sources.json").write_text(dump_crafts(crafts), encoding="utf-8")

    py = package_zip()
    py_name = f"py/wakfu_optimizer-{hashlib.sha256(py).hexdigest()[:10]}.zip"
    (out / "py").mkdir()
    (out / py_name).write_bytes(py)

    shutil.copytree(WEB / "static", out / "static")
    for f in ("bridge.js", "worker.js"):
        shutil.copyfile(WEB / "pages" / f, out / "static" / f)
    shutil.copytree(PKG / "gui" / "assets", out / "assets")
    html = (WEB / "static" / "index.html").read_text(encoding="utf-8")
    first = '<script src="static/js/core.js"></script>'
    if first not in html:
        raise SystemExit("index.html : balise static/js/core.js introuvable")
    # change dès qu'un fichier du site change : le navigateur ne garde pas d'anciens scripts en cache
    h = hashlib.sha256(py)
    for f in sorted(p for p in (out / "static").rglob("*") if p.is_file()):
        h.update(f.read_bytes())
    stamp = h.hexdigest()[:10]
    html = html.replace('href="static/style.css"', f'href="static/style.css?v={stamp}"')
    html = html.replace(first, '<script src="static/bridge.js"></script>\n' + first)   # avant l'interface
    html = re.sub(r'<script src="static/([^"?]+)"></script>', rf'<script src="static/\1?v={stamp}"></script>', html)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "build.json").write_text(json.dumps({"version": bundle.version, "data": f"data/{bundle.version}/",
                                                "files": DATA_FILES, "py": py_name}), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"Site généré dans {out} : données {bundle.version}, {len(full.items)} items, {size / 1e6:.1f} Mo")  # noqa: T201


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--force", action="store_true", help="retélécharger les données Ankama")
    a = p.parse_args()
    build(a.out.resolve(), a.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
