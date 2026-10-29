"""Point d'entrée de l'interface : python -m wakfu_optimizer.gui"""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Wakfu Optimizer")
    app.setStyle("Fusion")
    from .theme import QSS
    app.setStyleSheet(QSS)

    def excepthook(exc_type, exc, tb):  # type: ignore[no-untyped-def]
        logging.getLogger("wakfu_optimizer").error("Erreur non gérée", exc_info=(exc_type, exc, tb))
        QMessageBox.critical(None, "Erreur", "".join(traceback.format_exception_only(exc_type, exc))
                             + "\nDétails dans logs/app.log")

    sys.excepthook = excepthook
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
