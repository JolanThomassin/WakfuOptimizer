"""Affichage d'un build, façon builder : récapitulatif à gauche, équipement en cartes à droite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..data.models import ELEMENT_FR, ELEMENTS, RARITY_COLOR, RARITY_FR, SLOT_FR, GameData, Item
from ..engine.characteristics import BRANCH_FR, LINE_FR
from ..engine.options import Build, OptimizeOptions, SlotChoice
from ..engine.report import SLOT_ORDER, build_json, build_text
from ..engine.scoring import damage_multiplier
from ..engine.stats import Totals
from .theme import BAD, ELEMENT_COLOR, GOOD, MUTED, STAT_ICON, class_pixmap, stat_pixmap
from .widgets import FlowLayout, Separator, StatCard, StatChip, shard_label

APP_DIR = Path(__file__).resolve().parents[2]

# Stats affichées sur les cartes d'items, dans cet ordre
ITEM_STATS = ["ap", "mp", "wp", "range", "hp", "crit_rate", "block", "elem_mastery", "fire_mastery", "water_mastery",
              "earth_mastery", "air_mastery", "melee_mastery", "distance_mastery", "crit_mastery", "rear_mastery",
              "berserk_mastery", "heal_mastery", "dmg_pct", "elem_res", "fire_res", "water_res", "earth_res", "air_res",
              "lock", "dodge", "initiative", "willpower", "control", "crit_res", "rear_res"]


def _label(stat: str) -> str:
    for e in ELEMENTS:
        if stat == f"{e}_mastery":
            return f"Maîtrise {ELEMENT_FR[e]}"
        if stat == f"{e}_res":
            return f"Résistance {ELEMENT_FR[e]}"
    return STAT_ICON.get(stat, ("", stat))[1]


def _signed(v: int) -> str:
    return f"{v:+d}"


def _section(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("section")
    return lab


class ItemCard(QFrame):
    exclude_item = Signal(int)
    force_item = Signal(int)

    def __init__(self, data: GameData, opts: OptimizeOptions, ch: SlotChoice, it: Item, icons: Any,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("itemCard")
        self.it, self.icons = it, icons
        runes = {r.id: r for r in data.runes}
        subs = {s.id: s for s in data.sublimations}
        lang = opts.lang
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        # --- en-tête : icône, nom, emplacement / niveau / rareté
        head = QHBoxLayout()
        self.icon = QLabel()
        self.icon.setFixedSize(44, 44)
        self.icon.setStyleSheet("background: #1a1826; border-radius: 8px;")
        self._set_icon()
        icons.ready.connect(self._icon_ready)
        head.addWidget(self.icon)
        names = QVBoxLayout()
        names.setSpacing(0)
        n = QLabel(it.name(lang))
        n.setStyleSheet(f"color: {RARITY_COLOR[it.rarity]}; font-weight: 700; font-size: 11pt; background: transparent;")
        n.setWordWrap(True)
        names.addWidget(n)
        sub = QLabel(f"{SLOT_FR[ch.slot]} · niv. {it.level} · {RARITY_FR[it.rarity]}")
        sub.setObjectName("muted")
        sub.setStyleSheet("background: transparent;")
        names.addWidget(sub)
        head.addLayout(names, 1)
        lay.addLayout(head)
        # --- puces de stats
        chips = QWidget()
        chips.setStyleSheet("background: transparent;")
        flow = FlowLayout(chips, 4)
        st = it.stats_at(opts.level)
        for k in ITEM_STATS:
            v = int(st.get(k, 0))
            if v:
                flow.addWidget(StatChip(k, _signed(v), BAD if v < 0 else None, _label(k)))
        for (v, n_el), els in zip(it.random_mastery, ch.mastery_elements or [()] * len(it.random_mastery)):
            for e in els:
                flow.addWidget(StatChip(e, f"+{v}", ELEMENT_COLOR[e], f"Maîtrise {ELEMENT_FR[e]} (élément au choix)"))
            if not els:
                flow.addWidget(StatChip("elem_mastery", f"+{v} ×{n_el}", None, "Maîtrise sur éléments au choix"))
        for (v, n_el), els in zip(it.random_resistance, ch.resistance_elements or [()] * len(it.random_resistance)):
            for e in els:
                flow.addWidget(StatChip(e, f"+{v} rés.", ELEMENT_COLOR[e], f"Résistance {ELEMENT_FR[e]} (élément au choix)"))
        if it.has_special_effect:
            flow.addWidget(StatChip("elem_mastery", "effet spécial", MUTED, "Effet spécial non pris en compte dans le score"))
        lay.addWidget(chips)
        # --- châsses
        if ch.shards or ch.special_sublimation_id:
            row = QHBoxLayout()
            row.setSpacing(4)
            for s in ch.shards:
                if s.rune_id in runes:
                    r = runes[s.rune_id]
                    tip = f"{r.name(lang)} niv. {s.rune_level} : +{r.value(s.rune_level, ch.slot)} {_label(r.stat)}"
                    if ch.slot in r.doubled_on:
                        tip += " (doublé sur cet emplacement)"
                    row.addWidget(shard_label(s.color, True, tip))
                else:
                    row.addWidget(shard_label(s.color, False, "Châsse vide"))
            txt = []
            for s in ch.shards:
                if s.rune_id in runes:
                    txt.append(f"+{runes[s.rune_id].value(s.rune_level, ch.slot)} {runes[s.rune_id].name(lang)}")
            rl = QLabel(" · ".join(txt))
            rl.setObjectName("muted")
            rl.setWordWrap(True)
            rl.setStyleSheet("background: transparent; font-size: 9pt;")
            row.addWidget(rl, 1)
            lay.addLayout(row)
        for sid, star in ((ch.sublimation_id, ""), (ch.special_sublimation_id, "★ ")):
            if sid in subs:
                sb = subs[sid]
                st_ = data.states.get(sb.state_id)
                sl = QLabel(f"{star}{sb.name(lang)}")
                sl.setStyleSheet("background: transparent; color: #e0a83a; font-weight: 600;")
                if st_:
                    sl.setToolTip(st_.description)
                lay.addWidget(sl)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.setToolTip("Clic droit : exclure ou forcer cet item")

    def _set_icon(self) -> None:
        self.icon.setPixmap(self.icons.get(self.it.gfx_id).pixmap(QSize(40, 40)))

    def _icon_ready(self, gfx: int) -> None:
        if gfx == self.it.gfx_id:
            self._set_icon()

    def _menu(self, pos: Any) -> None:
        menu = QMenu(self)
        a1 = menu.addAction("Exclure cet item (je ne l'ai pas)")
        a2 = menu.addAction("Forcer cet item (je l'ai déjà)")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == a1:
            self.exclude_item.emit(self.it.id)
        elif chosen == a2:
            self.force_item.emit(self.it.id)


class BuildView(QWidget):
    exclude_item = Signal(int)
    force_item = Signal(int)

    def __init__(self, data: GameData, opts: OptimizeOptions, build: Build, totals: Totals, score: float,
                 icons: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.data, self.opts, self.build, self.totals, self.score = data, opts, build, totals, score
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(12)
        root.addWidget(self._summary(), 0)
        root.addWidget(self._equipment(icons), 1)

    # ------------------------------------------------------------ récapitulatif
    def _summary(self) -> QWidget:
        t, s, data, opts = self.totals, self.totals.stats, self.data, self.opts
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(640)
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        # en-tête
        head = QHBoxLayout()
        cp = data.classes.get(opts.class_key)
        ic = QLabel()
        ic.setPixmap(class_pixmap(opts.class_key, 56))
        head.addWidget(ic)
        hv = QVBoxLayout()
        title = QLabel(cp.name if cp else opts.class_key)
        title.setObjectName("title")
        hv.addWidget(title)
        sub = QLabel(f"Niveau {opts.level} · {', '.join(ELEMENT_FR[e] for e in opts.elements)}")
        sub.setObjectName("muted")
        hv.addWidget(sub)
        head.addLayout(hv, 1)
        sc = QVBoxLayout()
        for txt, val in (("Score", f"{self.score:.1f}"), ("Dégâts", f"×{damage_multiplier(t.d2):.2f}"),
                         ("PV effectifs", f"{t.defense / 1e4:,.0f}".replace(",", " "))):
            r = QLabel(f"<span style='color:{MUTED}'>{txt}</span> <b>{val}</b>")
            r.setAlignment(Qt.AlignmentFlag.AlignRight)
            sc.addWidget(r)
        head.addLayout(sc)
        lay.addLayout(head)
        # PV PA PM PW
        g = QGridLayout()
        g.setSpacing(6)
        for k, (stat, lab, val, col) in enumerate((("hp", "PV", t.hp, "#ff6b7a"), ("ap", "PA", s.get("ap", 0), "#4cc3ff"),
                                                    ("mp", "PM", s.get("mp", 0), "#a5d94b"), ("wp", "PW", s.get("wp", 0), "#3fd9c8"))):
            g.addWidget(StatCard(stat, lab, str(val), col), 0, k)
        lay.addLayout(g)
        # maîtrises et résistances
        lay.addWidget(_section("Maîtrises et Résistances"))
        mr = QGridLayout()
        mr.setSpacing(6)
        for k, e in enumerate(ELEMENTS):
            mr.addWidget(StatCard(e, "", str(t.mastery[e]), ELEMENT_COLOR[e]), 0, k)
            mr.addWidget(StatCard(e, "", f"{t.res_pct[e]} % ({t.res_flat[e]})", ELEMENT_COLOR[e]), 1, k)
        lay.addLayout(mr)
        # combat
        lay.addWidget(_section("Combat"))
        lay.addLayout(self._grid([("dmg_pct", s.get("dmg_pct", 0), "%"), ("crit_rate", s.get("crit_rate", 0), "%"),
                                  ("block", s.get("block", 0), "%"), ("range", s.get("range", 0), ""),
                                  ("initiative", s.get("initiative", 0), ""), ("willpower", s.get("willpower", 0), ""),
                                  ("dodge", s.get("dodge", 0), ""), ("lock", s.get("lock", 0), ""),
                                  ("control", s.get("control", 0), "")]))
        lay.addWidget(_section("Secondaire"))
        lay.addLayout(self._grid([("crit_mastery", s.get("crit_mastery", 0), ""), ("crit_res", s.get("crit_res", 0), ""),
                                  ("rear_mastery", s.get("rear_mastery", 0), ""), ("rear_res", s.get("rear_res", 0), ""),
                                  ("melee_mastery", s.get("melee_mastery", 0), ""), ("distance_mastery", s.get("distance_mastery", 0), ""),
                                  ("heal_mastery", s.get("heal_mastery", 0), ""), ("berserk_mastery", s.get("berserk_mastery", 0), "")]))
        # caractéristiques, sublimations
        if self.build.characteristics:
            lay.addWidget(_section("Caractéristiques"))
            by_branch: dict[str, list[str]] = {}
            for key, n in sorted(self.build.characteristics.items()):
                b, ln = key.split(".", 1)
                by_branch.setdefault(b, []).append(f"{LINE_FR.get(ln, ln)} <b>{n}</b>")
            for b, lines in by_branch.items():
                lab = QLabel(f"<span style='color:#e0a83a'>{BRANCH_FR.get(b, b)}</span> — " + ", ".join(lines))
                lab.setWordWrap(True)
                lay.addWidget(lab)
        if t.active_states:
            lay.addWidget(_section("Sublimations actives"))
            parts = []
            for sid, lvl in t.active_states.items():
                stt = data.states.get(sid)
                if stt:
                    parts.append(f"{stt.name} <b>{lvl}</b>")
            lab = QLabel(", ".join(parts))
            lab.setWordWrap(True)
            lay.addWidget(lab)
        lay.addWidget(Separator())
        row = QHBoxLayout()
        b1 = QPushButton("Copier le build (texte)")
        b1.clicked.connect(lambda: QApplication.clipboard().setText(build_text(data, opts, self.build, t, self.score)))
        b2 = QPushButton("Exporter en JSON…")
        b2.clicked.connect(self.export_json)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)
        lay.addStretch(1)
        scroll.setWidget(card)
        return scroll

    def _grid(self, rows: list[tuple[str, int, str]]) -> QGridLayout:
        g = QGridLayout()
        g.setSpacing(6)
        for k, (stat, v, unit) in enumerate(rows):
            col = GOOD if v > 0 else BAD if v < 0 else None
            g.addWidget(StatCard(stat, _label(stat), f"{v}{(' ' + unit) if unit else ''}", col), k // 2, k % 2)
        return g

    # ------------------------------------------------------------ équipement
    def _equipment(self, icons: Any) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        grid = FlowLayout(inner, 10)
        items = self.data.item_by_id()
        k = 0
        for slot in SLOT_ORDER:
            ch = self.build.slots.get(slot)
            if ch is None:
                continue
            card = ItemCard(self.data, self.opts, ch, items[ch.item_id], icons)
            card.exclude_item.connect(self.exclude_item)
            card.force_item.connect(self.force_item)
            card.setFixedWidth(360)
            grid.addWidget(card)
            k += 1
        scroll.setWidget(inner)
        return scroll

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le build", str(APP_DIR / "build.json"), "JSON (*.json)")
        if path:
            Path(path).write_text(build_json(self.data, self.opts, self.build, self.totals, self.score), encoding="utf-8")


def text_view(text: str) -> QPlainTextEdit:
    w = QPlainTextEdit(text)
    w.setReadOnly(True)
    return w


_ = stat_pixmap
