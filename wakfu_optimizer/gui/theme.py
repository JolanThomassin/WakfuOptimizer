"""Thème sombre et icônes (statistiques, châsses, classes).

Icônes : WakfuAssets (https://github.com/Tmktahu/WakfuAssets), issues du jeu Wakfu (© Ankama).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from ..data.models import Color

ASSETS = Path(__file__).resolve().parent / "assets"

BG = "#14131c"
PANEL = "#1d1b28"
CARD = "#252333"
CARD_HI = "#2e2b40"
BORDER = "#34314a"
TEXT = "#e8e6f0"
MUTED = "#9a96b0"
ACCENT = "#e0a83a"
GOOD = "#7ad97a"
BAD = "#ff6b6b"

ELEMENT_COLOR = {"fire": "#ff8a3d", "water": "#4cc3ff", "earth": "#a5c94b", "air": "#c58cff"}

QSS = f"""
* {{ color: {TEXT}; font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#sidebar, QScrollArea#sidebarScroll, QScrollArea#sidebarScroll > QWidget > QWidget {{ background: {PANEL}; }}
QGroupBox {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; margin-top: 18px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {ACCENT}; font-weight: 600; font-size: 11pt; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#statCard {{ background: {CARD_HI}; border-radius: 8px; }}
QFrame#itemCard {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#itemCard:hover {{ border: 1px solid {ACCENT}; }}
QLabel#title {{ font-size: 15pt; font-weight: 700; font-family: Georgia, serif; }}
QLabel#section {{ font-size: 13pt; font-weight: 700; font-family: Georgia, serif; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#big {{ font-size: 13pt; font-weight: 700; }}
QComboBox, QSpinBox, QLineEdit {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px; min-height: 22px; }}
QComboBox:hover, QSpinBox:hover, QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {BORDER}; selection-background-color: {CARD_HI}; outline: 0; }}
QPushButton {{ background: {CARD_HI}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#primary {{ background: {ACCENT}; color: #1a1408; font-weight: 700; font-size: 12pt; border: none; border-radius: 8px; }}
QPushButton#primary:hover {{ background: #f0bb52; }}
QPushButton#primary:disabled {{ background: #6b5a35; color: #2a2414; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator {{ border: 1px solid {BORDER}; border-radius: 4px; background: {CARD_HI}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QRadioButton::indicator {{ border: 1px solid {BORDER}; border-radius: 8px; background: {CARD_HI}; }}
QRadioButton::indicator:checked {{ background: {ACCENT}; border: 3px solid {CARD_HI}; }}
QSlider::groove:horizontal {{ height: 6px; background: {CARD_HI}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 16px; margin: -6px 0; border-radius: 8px; }}
QSlider::sub-page:horizontal {{ background: #8a6a2a; border-radius: 3px; }}
QProgressBar {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; text-align: center; min-height: 18px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: {CARD}; border: 1px solid {BORDER}; border-bottom: none; padding: 7px 14px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 3px; color: {MUTED}; }}
QTabBar::tab:selected {{ background: {CARD_HI}; color: {TEXT}; border-color: {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QPlainTextEdit, QListWidget {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
QMenuBar {{ background: {PANEL}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {CARD_HI}; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {ACCENT}; padding: 4px; }}
"""

# stat interne -> (fichier icône, libellé court)
STAT_ICON: dict[str, tuple[str, str]] = {
    "hp": ("health_points", "PV"), "ap": ("action_points", "PA"), "mp": ("movement_points", "PM"),
    "wp": ("wakfu_points", "PW"), "range": ("range", "Portée"), "crit_rate": ("critical_hit", "% Critique"),
    "block": ("block", "% Parade"), "crit_mastery": ("critical_mastery", "Maîtrise critique"),
    "melee_mastery": ("melee_mastery", "Maîtrise mêlée"), "distance_mastery": ("distance_mastery", "Maîtrise distance"),
    "rear_mastery": ("rear_mastery", "Maîtrise dos"), "berserk_mastery": ("berserk_mastery", "Maîtrise berserk"),
    "heal_mastery": ("healing_mastery", "Maîtrise soin"), "dmg_pct": ("damage_inflicted", "% Dommages infligés"),
    "lock": ("lock", "Tacle"), "dodge": ("dodge", "Esquive"), "initiative": ("initiative", "Initiative"),
    "willpower": ("force_of_will", "Volonté"), "control": ("control", "Contrôle"),
    "crit_res": ("critical_resistance", "Résistance critique"), "rear_res": ("rear_resistance", "Résistance dos"),
    "elem_mastery": ("elemental_damage", "Maîtrise élémentaire"), "elem_res": ("elemental_resistance", "Résistance élémentaire"),
    "wisdom": ("wisdom", "Sagesse"), "prospecting": ("prospecting", "Prospection"),
    "armor_given_pct": ("armor_given", "% Armure donnée"), "armor_received_pct": ("armor_received", "% Armure reçue"),
    "hp_pct": ("health_points", "% PV"),
}
ELEMENT_ICON = {"fire": "fire_coin", "water": "water_coin", "earth": "earth_coin", "air": "air_coin"}


@lru_cache(maxsize=None)
def pixmap(folder: str, name: str, size: int = 20) -> QPixmap:
    path = ASSETS / folder / f"{name}.png"
    pm = QPixmap(str(path)) if path.is_file() else QPixmap()
    if pm.isNull():
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        return pm
    return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def stat_pixmap(stat: str, size: int = 20) -> QPixmap:
    for e, icon in ELEMENT_ICON.items():
        if stat == e:
            return pixmap("stats", icon, size)
        if stat in (f"{e}_mastery", f"{e}_res"):
            return pixmap("stats", stat, size)
    return pixmap("stats", STAT_ICON.get(stat, ("empty_coin", ""))[0], size)


SHARD_FILE = {Color.RED: "Red", Color.GREEN: "Green", Color.BLUE: "Blue", Color.WHITE: "White"}


def shard_pixmap(color: Color, full: bool = True, size: int = 22) -> QPixmap:
    return pixmap("shards", f"shard{SHARD_FILE[color]}{'Full' if full else 'Empty'}", size)


def class_pixmap(key: str, size: int = 48) -> QPixmap:
    return pixmap("classes", key, size)
