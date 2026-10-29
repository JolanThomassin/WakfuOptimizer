"""Fenêtre principale (PySide6). Toute la logique métier est dans data/ et engine/."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QSize, Qt, QThread, QUrl, Signal, Slot as QtSlot
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..data.fetch import DEFAULT_CACHE_ROOT, DataUnavailableError, GameDataFetcher
from ..data.models import (
    COLOR_FR,
    ELEMENT_FR,
    ELEMENTS,
    RARITY_COLOR,
    RARITY_FR,
    SHARD_SLOTS,
    SLOT_FR,
    GameData,
    Rarity,
    Slot,
)
from ..data.parse import load_game_data
from ..engine.characteristics import BRANCH_FR, LINE_FR
from ..engine.options import Build, OptimizeOptions, default_min_ap, default_min_mp
from ..engine.report import SLOT_ORDER, build_json, build_text, describe_item_stats
from ..engine.scoring import damage_multiplier
from ..engine.stats import Totals
from .build_view import BuildView
from .theme import class_pixmap
from .widgets import ShardRow

log = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parents[2]
PRESETS_DIR = APP_DIR / "presets"
ICON_DIR = DEFAULT_CACHE_ROOT / "icons"
LAST_SETTINGS = APP_DIR / "presets" / "_dernier.json"
LANGS = {"fr": "Français", "en": "English", "es": "Español", "pt": "Português"}


# =====================================================================  threads
class DataWorker(QObject):
    done = Signal(object, str)      # GameData | None, message
    status = Signal(str)

    def __init__(self, force: bool) -> None:
        super().__init__()
        self.force = force

    @QtSlot()
    def run(self) -> None:
        try:
            self.status.emit("Vérification de la version des données Ankama…")
            bundle = GameDataFetcher().ensure(force=self.force)
            self.status.emit(f"Lecture des données {bundle.version}…")
            data = load_game_data(bundle)
            msg = f"Données {data.version}" + (" (hors ligne, cache local)" if bundle.offline else "")
            self.done.emit(data, msg)
        except DataUnavailableError as exc:
            self.done.emit(None, str(exc))
        except Exception as exc:  # noqa: BLE001 - affiché à l'utilisateur
            log.exception("Chargement des données")
            self.done.emit(None, f"Erreur au chargement des données : {exc}")


class SolveWorker(QObject):
    progress = Signal(str, float)
    done = Signal(object)

    def __init__(self, data: GameData, opts: OptimizeOptions) -> None:
        super().__init__()
        self.data, self.opts = data, opts
        self.cancel = threading.Event()
        self.optimizer: Any = None

    @QtSlot()
    def run(self) -> None:
        try:
            from ..engine.solver import Optimizer
            self.optimizer = Optimizer(self.data, self.opts, progress=lambda m, f: self.progress.emit(m, f), cancel=self.cancel)
            self.done.emit(self.optimizer.run())
        except Exception as exc:  # noqa: BLE001
            log.exception("Optimisation")
            self.done.emit(exc)

    def stop(self) -> None:
        self.cancel.set()
        if self.optimizer is not None:
            self.optimizer.stop()


# =====================================================================  icônes
class IconCache(QObject):
    """Télécharge les icônes d'items (CDN Ankama), cache disque, repli sur un carré gris."""

    ready = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.net = QNetworkAccessManager(self)
        self.mem: dict[int, QIcon] = {}
        self.pending: set[int] = set()
        ph = QPixmap(32, 32)
        ph.fill(QColor("#555"))
        self.placeholder = QIcon(ph)
        ICON_DIR.mkdir(parents=True, exist_ok=True)

    def get(self, gfx: int) -> QIcon:
        if gfx in self.mem:
            return self.mem[gfx]
        path = ICON_DIR / f"{gfx}.png"
        if path.is_file():
            pm = QPixmap(str(path))
            if not pm.isNull():
                self.mem[gfx] = QIcon(pm)
                return self.mem[gfx]
        if gfx and gfx not in self.pending:
            self.pending.add(gfx)
            reply = self.net.get(QNetworkRequest(QUrl(f"https://static.ankama.com/wakfu/portal/game/item/64/{gfx}.png")))
            reply.finished.connect(lambda r=reply, g=gfx: self._done(r, g))
        return self.placeholder

    def _done(self, reply: QNetworkReply, gfx: int) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError:
            raw = bytes(reply.readAll().data())
            pm = QPixmap()
            if pm.loadFromData(raw):
                (ICON_DIR / f"{gfx}.png").write_bytes(raw)
                self.mem[gfx] = QIcon(pm)
                self.ready.emit(gfx)
        reply.deleteLater()


# =====================================================================  dialogue items
class ItemPicker(QDialog):
    """Recherche d'items à exclure (« je ne l'ai pas ») ou forcer (« je l'ai déjà »)."""

    def __init__(self, data: GameData, opts: OptimizeOptions, excluded: set[int], forced: set[int],
                 icons: IconCache, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Items exclus et forcés")
        self.resize(760, 560)
        self.data, self.lang, self.level, self.icons = data, opts.lang, opts.level, icons
        self.excluded, self.forced = set(excluded), set(forced)
        self.by_id = data.item_by_id()
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(placeholderText="Rechercher un item (nom)…")
        self.search.textChanged.connect(self.refresh)
        self.only_level = QCheckBox("Niveau ≤ personnage")
        self.only_level.setChecked(True)
        self.only_level.toggled.connect(self.refresh)
        top.addWidget(self.search, 1)
        top.addWidget(self.only_level)
        lay.addLayout(top)
        self.results = QListWidget()
        self.results.setIconSize(QSize(28, 28))
        lay.addWidget(self.results, 1)
        btns = QHBoxLayout()
        for text, fn in (("Exclure", self.do_exclude), ("Forcer", self.do_force), ("Retirer des listes", self.do_clear)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        lay.addLayout(btns)
        lists = QHBoxLayout()
        self.ex_list, self.fo_list = QListWidget(), QListWidget()
        for title, w in (("Exclus", self.ex_list), ("Forcés", self.fo_list)):
            box = QGroupBox(title)
            QVBoxLayout(box).addWidget(w)
            lists.addWidget(box)
        lay.addLayout(lists, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.refresh()

    def _label(self, iid: int) -> str:
        it = self.by_id.get(iid)
        if it is None:
            return f"#{iid}"
        return f"{it.name(self.lang)}  —  niv. {it.level}, {RARITY_FR[it.rarity]}, {it.type_name}"

    def refresh(self) -> None:
        q = self.search.text().strip().lower()
        self.results.clear()
        if len(q) >= 2:
            n = 0
            for it in self.data.items:
                if self.only_level.isChecked() and it.level > self.level:
                    continue
                if q in it.name(self.lang).lower():
                    li = QListWidgetItem(self.icons.get(it.gfx_id), self._label(it.id))
                    li.setData(Qt.ItemDataRole.UserRole, it.id)
                    li.setForeground(QColor(RARITY_COLOR[it.rarity]))
                    self.results.addItem(li)
                    n += 1
                    if n >= 300:
                        break
        for w, ids in ((self.ex_list, self.excluded), (self.fo_list, self.forced)):
            w.clear()
            for iid in sorted(ids):
                li = QListWidgetItem(self._label(iid))
                li.setData(Qt.ItemDataRole.UserRole, iid)
                w.addItem(li)

    def _selected(self) -> list[int]:
        out = [int(i.data(Qt.ItemDataRole.UserRole)) for i in self.results.selectedItems()]
        for w in (self.ex_list, self.fo_list):
            out += [int(i.data(Qt.ItemDataRole.UserRole)) for i in w.selectedItems()]
        return out

    def do_exclude(self) -> None:
        for iid in self._selected():
            self.forced.discard(iid)
            self.excluded.add(iid)
        self.refresh()

    def do_force(self) -> None:
        for iid in self._selected():
            self.excluded.discard(iid)
            self.forced.add(iid)
        self.refresh()

    def do_clear(self) -> None:
        for iid in self._selected():
            self.excluded.discard(iid)
            self.forced.discard(iid)
        self.refresh()


# =====================================================================  fenêtre
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wakfu Optimizer")
        self.resize(1400, 900)
        self.data: GameData | None = None
        self.excluded: set[int] = set()
        self.forced: set[int] = set()
        self.icons = IconCache()
        self._threads: list[QThread] = []
        self.solve_worker: SolveWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        # ----- panneau gauche (paramètres) dans une zone défilante
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("sidebarScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel = QWidget()
        panel.setObjectName("sidebar")
        self.form = QVBoxLayout(panel)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(420)
        scroll.setMaximumWidth(480)
        root.addWidget(scroll)
        self._build_character()
        self._build_priorities()
        self._build_constraints()
        self._build_shards()
        self.form.addStretch(1)
        # ----- droite : bouton, progression, résultats
        right = QVBoxLayout()
        bar = QHBoxLayout()
        self.go = QPushButton("Optimiser")
        self.go.setObjectName("primary")
        self.go.setMinimumHeight(42)
        self.go.clicked.connect(self.start)
        self.stop_btn = QPushButton("Annuler")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.cancel)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(True)
        self.progress.setFormat("")
        bar.addWidget(self.go, 2)
        bar.addWidget(self.stop_btn)
        bar.addWidget(self.progress, 3)
        right.addLayout(bar)
        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        right.addWidget(self.msg)
        self.tabs = QTabWidget()
        right.addWidget(self.tabs, 1)
        rw = QWidget()
        rw.setLayout(right)
        root.addWidget(rw, 1)
        self._build_menu()
        self.statusBar().showMessage("Chargement des données…")
        self._set_busy(True, solving=False)
        self.load_settings()
        self.load_data(force=False)

    # --------------------------------------------------------------- panneaux
    def _group(self, title: str) -> QFormLayout:
        box = QGroupBox(title)
        fl = QFormLayout(box)
        fl.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.addWidget(box)
        return fl

    def _build_character(self) -> None:
        fl = self._group("Personnage")
        self.cls = QComboBox()
        self.cls.currentIndexChanged.connect(self._class_changed)
        fl.addRow("Classe", self.cls)
        self.level = QComboBox()
        self._fill_levels([(lo, hi) for lo, hi in ((1, 20), (21, 35), (36, 50), (51, 65), (66, 80), (81, 95), (96, 110),
                                                  (111, 125), (126, 140), (141, 155), (156, 170), (171, 185), (186, 200),
                                                  (201, 215), (216, 230), (231, 245))])
        self.level.currentIndexChanged.connect(lambda _i: self._level_changed(self.level_value()))
        fl.addRow("Niveau", self.level)
        er = QHBoxLayout()
        self.el = {}
        for e in ELEMENTS:
            cb = QCheckBox(ELEMENT_FR[e])
            self.el[e] = cb
            er.addWidget(cb)
        fl.addRow("Éléments joués", er)
        self.lang = QComboBox()
        for k, v in LANGS.items():
            self.lang.addItem(v, k)
        fl.addRow("Langue des items", self.lang)

    def _build_priorities(self) -> None:
        fl = self._group("Priorités")
        r1 = QHBoxLayout()
        self.melee, self.distance = QRadioButton("Mêlée"), QRadioButton("Distance")
        g1 = QButtonGroup(self)
        g1.addButton(self.melee)
        g1.addButton(self.distance)
        self.melee.setChecked(True)
        r1.addWidget(self.melee)
        r1.addWidget(self.distance)
        r1.addStretch(1)
        fl.addRow("Portée", r1)
        r2 = QHBoxLayout()
        self.single, self.area = QRadioButton("Monocible"), QRadioButton("Zone")
        g2 = QButtonGroup(self)
        g2.addButton(self.single)
        g2.addButton(self.area)
        self.single.setChecked(True)
        for w in (self.single, self.area):
            w.setToolTip("Ces maîtrises n'existent plus sur l'équipement : sans effet sur le calcul.")
            r2.addWidget(w)
        r2.addStretch(1)
        fl.addRow("Cible", r2)
        r3 = QHBoxLayout()
        self.crit, self.rear, self.berserk, self.heal = (QCheckBox("Critique"), QCheckBox("Dos"),
                                                         QCheckBox("Berserk"), QCheckBox("Soin"))
        self.crit.setChecked(True)
        for w in (self.crit, self.rear, self.berserk, self.heal):
            r3.addWidget(w)
        fl.addRow("Maîtrises", r3)
        self.rear_share = QSpinBox()
        self.rear_share.setRange(0, 100)
        self.rear_share.setValue(50)
        self.rear_share.setSuffix(" % des coups de dos")
        fl.addRow("", self.rear_share)
        sl = QHBoxLayout()
        self.weight = QSlider(Qt.Orientation.Horizontal)
        self.weight.setRange(0, 100)
        self.weight.setValue(70)
        self.weight_lab = QLabel()
        self.weight.valueChanged.connect(lambda v: self.weight_lab.setText(f"Off. {v} / Déf. {100 - v}"))
        self.weight.valueChanged.emit(self.weight.value())
        sl.addWidget(QLabel("Défense"))
        sl.addWidget(self.weight, 1)
        sl.addWidget(QLabel("Offense"))
        fl.addRow(sl)
        fl.addRow("", self.weight_lab)
        self.balance = QCheckBox("Équilibrer les résistances (maximiser la plus faible)")
        self.balance.setChecked(True)
        fl.addRow(self.balance)
        self.cond = QCheckBox("Compter les sublimations conditionnelles (PV > 90 %, sans armure)")
        fl.addRow(self.cond)
        uv = QGridLayout()
        self.ap_val, self.mp_val = self._spin(0, 50, 6), self._spin(0, 50, 4)
        self.po_val, self.wp_val = self._spin(0, 50, 1), self._spin(0, 50, 1)
        for k, (lab, w) in enumerate((("1 PA vaut", self.ap_val), ("1 PM vaut", self.mp_val),
                                      ("1 PO vaut", self.po_val), ("1 PW vaut", self.wp_val))):
            w.setSuffix(" pts")
            w.setToolTip("Bonus de score par point au-delà des minimums (PA jusqu'à 14, PM 6, PO 6, PW 12).\n"
                         "Repère : le score de dégâts va de 0 à « poids offense ».")
            uv.addWidget(QLabel(lab), k // 2, (k % 2) * 2)
            uv.addWidget(w, k // 2, (k % 2) * 2 + 1)
        fl.addRow(uv)

    def _spin(self, lo: int, hi: int, val: int, suffix: str = "") -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        if suffix:
            s.setSuffix(suffix)
        return s

    def _build_constraints(self) -> None:
        fl = self._group("Contraintes")
        g = QGridLayout()
        self.min_ap, self.min_mp = self._spin(0, 20, 11), self._spin(0, 10, 5)
        self.min_range, self.min_wp = self._spin(0, 10, 0), self._spin(0, 20, 0)
        self.min_crit, self.min_ctrl = self._spin(0, 100, 0, " %"), self._spin(0, 20, 0)
        self.min_res = self._spin(0, 90, 0, " %")
        for k, (lab, w) in enumerate((("PA min", self.min_ap), ("PM min", self.min_mp), ("PO min", self.min_range),
                                      ("PW min", self.min_wp), ("Crit min", self.min_crit), ("Contrôle min", self.min_ctrl),
                                      ("Rés. min", self.min_res))):
            g.addWidget(QLabel(lab), k // 2, (k % 2) * 2)
            g.addWidget(w, k // 2, (k % 2) * 2 + 1)
        self.min_res.setToolTip("Résistance minimale sur chacun des 4 éléments (en %).")
        self.min_ctrl.setToolTip("Aucun équipement ne donne de contrôle : seul le Majeur « Contrôle » en donne (+2).")
        fl.addRow(g)
        rar = QGridLayout()
        self.rar = {}
        for k, r in enumerate(Rarity):
            cb = QCheckBox(RARITY_FR[r])
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {RARITY_COLOR[r]};" if r not in (Rarity.COMMON, Rarity.UNUSUAL) else "")
            self.rar[int(r)] = cb
            rar.addWidget(cb, k // 4, k % 4)
        fl.addRow("Raretés", rar)
        self.lower = QCheckBox("Autoriser les items des tranches inférieures")
        self.no_relic, self.no_epic = QCheckBox("Exclure Relique"), QCheckBox("Exclure Épique")
        self.no_shop = QCheckBox("Exclure les items boutique")
        self.no_shop.setChecked(True)
        self.pets = QCheckBox("Inclure familier et monture")
        self.pets.setChecked(True)
        self.chars = QCheckBox("Optimiser les points de caractéristiques")
        self.chars.setChecked(True)
        for w in (self.lower, self.no_relic, self.no_epic, self.no_shop, self.pets, self.chars):
            fl.addRow(w)
        row = QHBoxLayout()
        self.items_btn = QPushButton("Items exclus / forcés…")
        self.items_btn.clicked.connect(self.pick_items)
        self.items_lab = QLabel()
        row.addWidget(self.items_btn)
        row.addWidget(self.items_lab, 1)
        fl.addRow(row)
        tl = QHBoxLayout()
        self.time_limit = self._spin(5, 600, 30, " s")
        self.alts = self._spin(0, 5, 3)
        tl.addWidget(QLabel("Temps max"))
        tl.addWidget(self.time_limit)
        tl.addWidget(QLabel("Alternatives"))
        tl.addWidget(self.alts)
        fl.addRow(tl)
        self._update_items_label()

    def _build_shards(self) -> None:
        fl = self._group("Châsses et sublimations")
        self.mode_ideal = QRadioButton("Idéal (le solveur choisit les couleurs)")
        self.mode_mine = QRadioButton("Mes items (je saisis les couleurs)")
        self.mode_none = QRadioButton("Ignorer les châsses")
        g = QButtonGroup(self)
        for w in (self.mode_ideal, self.mode_mine, self.mode_none):
            g.addButton(w)
            fl.addRow(w)
        self.mode_ideal.setChecked(True)
        self.shard_count = self._spin(1, 4, 4)
        fl.addRow("Châsses par item (idéal)", self.shard_count)
        self.jokers = self._spin(0, 4, 1)
        self.jokers.setToolTip("Châsses jaunes (joker : acceptent toutes les runes et comptent comme n'importe quelle couleur)")
        fl.addRow("Châsses jaunes max par item", self.jokers)
        self.grid_box = QWidget()
        gl = QGridLayout(self.grid_box)
        gl.setContentsMargins(0, 0, 0, 0)
        self.rows: dict[Slot, ShardRow] = {}
        for k, s in enumerate(SHARD_SLOTS):
            gl.addWidget(QLabel(SLOT_FR[s]), k, 0)
            row = ShardRow()
            self.rows[s] = row
            gl.addWidget(row, k, 1)
        fl.addRow(self.grid_box)
        hint = QLabel("Clic : rouge → verte → bleue → jaune (joker) → aucune. Clic droit : aucune.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        fl.addRow(hint)
        for w in (self.mode_ideal, self.mode_mine, self.mode_none):
            w.toggled.connect(self._mode_changed)
        self._mode_changed()

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("Fichier")
        for text, fn in (("Mettre à jour les données", lambda: self.load_data(force=True)),
                         ("Enregistrer un préréglage…", self.save_preset),
                         ("Charger un préréglage…", self.load_preset)):
            a = QAction(text, self)
            a.triggered.connect(fn)
            m.addAction(a)
        m.addSeparator()
        q = QAction("Quitter", self)
        q.triggered.connect(self.close)
        m.addAction(q)
        h = self.menuBar().addMenu("Aide")
        a = QAction("À propos", self)
        a.triggered.connect(self.about)
        h.addAction(a)

    # --------------------------------------------------------------- réactions
    def _mode_changed(self) -> None:
        self.grid_box.setVisible(self.mode_mine.isChecked())
        self.shard_count.setEnabled(self.mode_ideal.isChecked())
        self.jokers.setEnabled(self.mode_ideal.isChecked())

    def _class_changed(self) -> None:
        if self.data is None or getattr(self, "_loading_settings", False):
            return
        cp = self.data.classes.get(self.cls.currentData())
        if cp is None:
            return
        for e, cb in self.el.items():
            cb.setChecked(e in cp.elements)
        (self.melee if cp.range == "melee" else self.distance).setChecked(True)
        self.rear.setChecked(cp.rear)
        self.berserk.setChecked(cp.berserk)
        self.heal.setChecked(cp.role == "heal")
        self.weight.setValue(40 if cp.role == "tank" else 70)

    def _fill_levels(self, brackets: list[tuple[int, int]]) -> None:
        cur = self.level.currentData()
        self.level.blockSignals(True)
        self.level.clear()
        for _lo, hi in sorted(brackets, key=lambda b: -b[1]):
            self.level.addItem(f"Niveau {hi}", hi)
        self.level.blockSignals(False)
        self.set_level(int(cur) if cur else 245)

    def level_value(self) -> int:
        return int(self.level.currentData() or 245)

    def set_level(self, lvl: int) -> None:
        best = 0
        for i in range(self.level.count()):
            if int(self.level.itemData(i)) >= lvl:
                best = i
        self.level.setCurrentIndex(best)

    def _level_changed(self, lvl: int) -> None:
        if not hasattr(self, "min_ap"):
            return
        if not getattr(self, "_loading_settings", False):
            self.min_ap.setValue(default_min_ap(lvl))
            self.min_mp.setValue(default_min_mp(lvl))

    def _update_items_label(self) -> None:
        self.items_lab.setText(f"{len(self.excluded)} exclus, {len(self.forced)} forcés")

    # --------------------------------------------------------------- données
    def load_data(self, force: bool) -> None:
        self._set_busy(True, solving=False)
        self.progress.setRange(0, 0)
        w = DataWorker(force)
        w.status.connect(self.statusBar().showMessage)
        w.done.connect(self._data_loaded)
        self._run(w)

    def _data_loaded(self, data: GameData | None, msg: str) -> None:
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        if data is None:
            self.statusBar().showMessage(msg)
            QMessageBox.critical(self, "Données indisponibles", msg)
            self._set_busy(False, solving=False)
            self.go.setEnabled(False)
            return
        prev_cls = self.cls.currentData()
        self.data = data
        self._loading_settings = True
        self.cls.clear()
        for k, cp in sorted(data.classes.items(), key=lambda kv: kv[1].name):
            self.cls.addItem(QIcon(class_pixmap(k, 32)), cp.name, k)
        self._fill_levels(data.brackets)
        self._loading_settings = False
        if getattr(self, "_pending", None):
            self.apply_options(OptimizeOptions.from_dict(self._pending))
            self._pending = {}
        else:
            idx = self.cls.findData(prev_cls or "iop")
            self.cls.setCurrentIndex(max(0, idx))
            self._class_changed()
            self._level_changed(self.level_value())
        self.statusBar().showMessage(f"{msg} — {len(data.items)} items, {len(data.runes)} runes, {len(data.sublimations)} sublimations")
        self._set_busy(False, solving=False)

    def _run(self, worker: QObject) -> None:
        th = QThread(self)
        worker.moveToThread(th)
        th.started.connect(worker.run)  # type: ignore[attr-defined]
        worker.done.connect(th.quit)  # type: ignore[attr-defined]
        th.finished.connect(lambda: self._threads.remove(th) if th in self._threads else None)
        self._threads.append(th)
        th._worker = worker  # type: ignore[attr-defined]  # garde une référence
        th.start()

    def _set_busy(self, busy: bool, solving: bool) -> None:
        self.go.setEnabled(not busy and self.data is not None)
        self.stop_btn.setEnabled(busy and solving)
        self.items_btn.setEnabled(self.data is not None and not busy)

    # --------------------------------------------------------------- options
    def options(self) -> OptimizeOptions:
        els = tuple(e for e, cb in self.el.items() if cb.isChecked())
        return OptimizeOptions(
            class_key=str(self.cls.currentData() or "iop"), level=self.level_value(), elements=els or tuple(ELEMENTS),
            lang=str(self.lang.currentData()), range="melee" if self.melee.isChecked() else "distance",
            target="single" if self.single.isChecked() else "area", crit=self.crit.isChecked(), rear=self.rear.isChecked(),
            rear_share=self.rear_share.value(), berserk=self.berserk.isChecked(), heal=self.heal.isChecked(),
            offense_weight=self.weight.value(), ap_value=self.ap_val.value(), mp_value=self.mp_val.value(),
            range_value=self.po_val.value(), wp_value=self.wp_val.value(), max_jokers=self.jokers.value(), balance_res=self.balance.isChecked(), count_conditional=self.cond.isChecked(),
            min_ap=self.min_ap.value(), min_mp=self.min_mp.value(), min_range=self.min_range.value(),
            min_wp=self.min_wp.value(), min_crit=self.min_crit.value(), min_control=self.min_ctrl.value(),
            min_res_pct=self.min_res.value(),
            allowed_rarities=tuple(k for k, cb in self.rar.items() if cb.isChecked()),
            lower_brackets=self.lower.isChecked(), exclude_relic=self.no_relic.isChecked(),
            exclude_epic=self.no_epic.isChecked(), exclude_shop=self.no_shop.isChecked(),
            include_pet_mount=self.pets.isChecked(), optimize_characteristics=self.chars.isChecked(),
            excluded_ids=tuple(sorted(self.excluded)), forced_ids=tuple(sorted(self.forced)),
            shard_mode="ideal" if self.mode_ideal.isChecked() else "mine" if self.mode_mine.isChecked() else "none",
            shard_count=self.shard_count.value(), my_colors={s.value: r.colors() for s, r in self.rows.items()},
            alternatives=self.alts.value(), time_limit=float(self.time_limit.value()),
        )

    def apply_options(self, o: OptimizeOptions) -> None:
        self._loading_settings = True
        try:
            i = self.cls.findData(o.class_key)
            if i >= 0:
                self.cls.setCurrentIndex(i)
            self.set_level(o.level)
            for e, cb in self.el.items():
                cb.setChecked(e in o.elements)
            i = self.lang.findData(o.lang)
            if i >= 0:
                self.lang.setCurrentIndex(i)
            (self.melee if o.range == "melee" else self.distance).setChecked(True)
            (self.single if o.target == "single" else self.area).setChecked(True)
            self.crit.setChecked(o.crit)
            self.rear.setChecked(o.rear)
            self.rear_share.setValue(o.rear_share)
            self.berserk.setChecked(o.berserk)
            self.heal.setChecked(o.heal)
            self.weight.setValue(o.offense_weight)
            self.ap_val.setValue(o.ap_value)
            self.mp_val.setValue(o.mp_value)
            self.po_val.setValue(o.range_value)
            self.wp_val.setValue(o.wp_value)
            self.jokers.setValue(o.max_jokers)
            self.balance.setChecked(o.balance_res)
            self.cond.setChecked(o.count_conditional)
            self.min_ap.setValue(o.min_ap)
            self.min_mp.setValue(o.min_mp)
            self.min_range.setValue(o.min_range)
            self.min_wp.setValue(o.min_wp)
            self.min_crit.setValue(o.min_crit)
            self.min_ctrl.setValue(o.min_control)
            self.min_res.setValue(o.min_res_pct)
            for k, cb in self.rar.items():
                cb.setChecked(k in o.allowed_rarities)
            self.lower.setChecked(o.lower_brackets)
            self.no_relic.setChecked(o.exclude_relic)
            self.no_epic.setChecked(o.exclude_epic)
            self.no_shop.setChecked(o.exclude_shop)
            self.pets.setChecked(o.include_pet_mount)
            self.chars.setChecked(o.optimize_characteristics)
            self.excluded, self.forced = set(o.excluded_ids), set(o.forced_ids)
            {"ideal": self.mode_ideal, "mine": self.mode_mine}.get(o.shard_mode, self.mode_none).setChecked(True)
            self.shard_count.setValue(o.shard_count)
            for s, row in self.rows.items():
                if s.value in o.my_colors:
                    row.set_colors(o.my_colors[s.value])
            self.alts.setValue(o.alternatives)
            self.time_limit.setValue(int(o.time_limit))
        finally:
            self._loading_settings = False
        self._update_items_label()

    def load_settings(self) -> None:
        self._pending: dict[str, Any] = {}
        try:
            if LAST_SETTINGS.is_file():
                self._pending = json.loads(LAST_SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._pending = {}

    def save_settings(self) -> None:
        try:
            PRESETS_DIR.mkdir(parents=True, exist_ok=True)
            LAST_SETTINGS.write_text(self.options().to_json(), encoding="utf-8")
        except OSError:
            log.warning("Impossible d'enregistrer les réglages")

    def save_preset(self) -> None:
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le préréglage", str(PRESETS_DIR / "preset.json"), "JSON (*.json)")
        if path:
            Path(path).write_text(self.options().to_json(), encoding="utf-8")

    def load_preset(self) -> None:
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Charger un préréglage", str(PRESETS_DIR), "JSON (*.json)")
        if path:
            try:
                self.apply_options(OptimizeOptions.from_dict(json.loads(Path(path).read_text(encoding="utf-8"))))
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Préréglage", f"Fichier illisible : {exc}")

    def pick_items(self) -> None:
        if self.data is None:
            return
        dlg = ItemPicker(self.data, self.options(), self.excluded, self.forced, self.icons, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.excluded, self.forced = dlg.excluded, dlg.forced
            self._update_items_label()

    def _exclude(self, iid: int) -> None:
        self.forced.discard(iid)
        self.excluded.add(iid)
        self._update_items_label()
        self.msg.setText("Item exclu. Relancez « Optimiser » pour recalculer.")

    def _force(self, iid: int) -> None:
        self.excluded.discard(iid)
        self.forced.add(iid)
        self._update_items_label()
        self.msg.setText("Item forcé. Relancez « Optimiser » pour recalculer.")

    # --------------------------------------------------------------- calcul
    def start(self) -> None:
        if self.data is None:
            return
        o = self.options()
        if not o.elements:
            QMessageBox.warning(self, "Éléments", "Cochez au moins un élément.")
            return
        self.save_settings()
        self._set_busy(True, solving=True)
        self.progress.setValue(0)
        self.progress.setFormat("%p %")
        self.msg.setText("Calcul en cours…")
        self.last_opts = o
        w = SolveWorker(self.data, o)
        w.progress.connect(self._progress)
        w.done.connect(self._solved)
        self.solve_worker = w
        self._run(w)

    def cancel(self) -> None:
        if self.solve_worker is not None:
            self.solve_worker.stop()
            self.msg.setText("Annulation…")

    def _progress(self, text: str, frac: float) -> None:
        self.progress.setValue(int(frac * 1000))
        self.statusBar().showMessage(text)

    def _solved(self, res: Any) -> None:
        self._set_busy(False, solving=False)
        self.solve_worker = None
        self.progress.setValue(1000)
        if isinstance(res, Exception):
            self.msg.setText(f"<span style='color:#d33'>Erreur : {res}</span>")
            QMessageBox.critical(self, "Erreur", f"L'optimisation a échoué :\n{res}\n\nDétails dans logs/app.log")
            return
        warn = "".join(f"<br>⚠ {w}" for w in res.warnings)
        if not res.builds:
            diag = "".join(f"<br>• {d}" for d in res.diagnostics)
            self.msg.setText(f"<b style='color:#d33'>{res.status}</b>{diag}{warn}")
            self.statusBar().showMessage(res.message)
            return
        self.msg.setText(f"<b>Build trouvé</b> — {res.message}{warn}")
        self.statusBar().showMessage(res.message)
        self.tabs.clear()
        best = res.scores[0]
        for k, (b, t, sc) in enumerate(zip(res.builds, res.totals, res.scores)):
            view = BuildView(self.data, self.last_opts, b, t, sc, self.icons)  # type: ignore[arg-type]
            view.exclude_item.connect(self._exclude)
            view.force_item.connect(self._force)
            title = "Meilleur build" if k == 0 else f"Alternative {k} ({sc - best:+.1f})"
            self.tabs.addTab(view, title)

    def about(self) -> None:
        v = self.data.version if self.data else "?"
        QMessageBox.information(self, "À propos", (
            "Wakfu Optimizer — outil communautaire non officiel.\n\n"
            f"Données de jeu : CDN Ankama (version {v}). Les données restent la propriété d'Ankama.\n"
            "Solveur : Google OR-Tools CP-SAT. Formules : voir README.md."))

    def closeEvent(self, ev: Any) -> None:  # noqa: N802
        self.save_settings()
        if self.solve_worker is not None:
            self.solve_worker.stop()
        for th in list(self._threads):
            th.quit()
            th.wait(3000)
        super().closeEvent(ev)
