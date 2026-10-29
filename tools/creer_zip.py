"""Crée une archive à envoyer à un ami (sans environnement Python, cache, logs ni réglages perso).

    python tools/creer_zip.py      -> wakfu_optimizer_partage.zip à côté du dossier du projet
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "wakfu_optimizer_partage.zip"
SKIP_DIRS = {".venv", "_site", "logs", "reports", "__pycache__", ".pytest_cache", ".claude", ".git", "wakfu_optimizer.egg-info"}
SKIP_FILES = {".shortcut_done", "_dernier.json"}


def keep(p: Path) -> bool:
    rel = p.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    if rel.parts[:2] == ("data", "cache"):
        return False
    return p.name not in SKIP_FILES and p.suffix != ".pyc"


def main() -> None:
    files = [p for p in ROOT.rglob("*") if p.is_file() and keep(p)]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, Path("wakfu_optimizer") / p.relative_to(ROOT))
    print(f"{OUT} ({len(files)} fichiers, {OUT.stat().st_size // 1024} Ko)")  # noqa: T201


if __name__ == "__main__":
    main()
