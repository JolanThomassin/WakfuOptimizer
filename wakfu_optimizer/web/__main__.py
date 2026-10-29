"""Point d'entrée : python -m wakfu_optimizer.web [--port N] [--no-browser]"""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .server import serve

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    a = p.parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    serve(a.port, open_browser=not a.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
