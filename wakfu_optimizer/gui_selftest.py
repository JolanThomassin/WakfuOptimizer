"""Test automatique de l'interface (hors écran) : charge les données, optimise, capture la fenêtre.

    python -m wakfu_optimizer.gui_selftest    -> logs/gui_selftest.png
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    if os.name == "nt":
        os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from .gui.theme import QSS
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.resize(1500, 950)
    win.show()
    t0 = time.monotonic()
    state = {"phase": "load", "ok": False}

    def tick() -> None:
        if state["phase"] == "load":
            if win.data is not None and win.go.isEnabled():
                win.time_limit.setValue(45)
                win.alts.setValue(1)
                state["phase"] = "solve"
                win.start()
        elif state["phase"] == "solve":
            if win.solve_worker is None and win.tabs.count() > 0:
                LOG_DIR.mkdir(exist_ok=True)
                win.grab().save(str(LOG_DIR / "gui_selftest.png"))
                print("GUI OK :", win.msg.text()[:300])  # noqa: T201
                state["ok"] = True
                app.quit()
            elif win.solve_worker is None and "aucune" in win.msg.text():
                print("GUI : pas de solution :", win.msg.text())  # noqa: T201
                app.quit()
        if time.monotonic() - t0 > 240:
            print("GUI : délai dépassé", state["phase"], win.msg.text())  # noqa: T201
            app.quit()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(300)
    app.exec()
    win.save_settings = lambda: None  # type: ignore[method-assign]
    win.close()
    return 0 if state["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
