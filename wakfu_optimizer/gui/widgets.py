"""Widgets : pastilles de châsses, cartes de stats, puces d'items, mise en page fluide."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QLayoutItem, QWidget, QWidgetItem

from ..data.models import Color
from .theme import BORDER, MUTED, shard_pixmap, stat_pixmap


class FlowLayout(QLayout):
    """Disposition qui passe à la ligne quand la largeur manque."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def addWidget(self, w: QWidget) -> None:  # noqa: N802
        self.addChildWidget(w)
        self.addItem(QWidgetItem(w))

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int) -> QLayoutItem | None:  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int) -> QLayoutItem | None:  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, r: QRect) -> None:  # noqa: N802
        super().setGeometry(r)
        self._do(r, False)
        pw = self.parentWidget()
        if pw is not None:
            pw.setMinimumHeight(self._do(QRect(0, 0, r.width(), 0), True))

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do(self, r: QRect, test: bool) -> int:
        x, y, line = r.x(), r.y(), 0
        for it in self._items:
            w = it.widget()
            hint = it.sizeHint()
            if w is not None and w.hasHeightForWidth():
                hint = QSize(hint.width(), w.heightForWidth(hint.width()))
            nx = x + hint.width() + self._sp
            if nx - self._sp > r.right() and line > 0:
                x, y = r.x(), y + line + self._sp
                nx, line = x + hint.width() + self._sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x, line = nx, max(line, hint.height())
        return y + line - r.y()


class ShardButton(QWidget):
    """Châsse cliquable : vide → rouge → verte → bleue → jaune (joker) → vide."""

    changed = Signal()
    ORDER: list[Color | None] = [None, Color.RED, Color.GREEN, Color.BLUE, Color.WHITE]

    def __init__(self, color: Color | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color = color
        self.setFixedSize(QSize(26, 26))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Clic : rouge → verte → bleue → jaune (joker) → aucune. Clic droit : aucune.")

    def mousePressEvent(self, ev) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if ev.button() == Qt.MouseButton.RightButton:
            self.color = None
        else:
            self.color = self.ORDER[(self.ORDER.index(self.color) + 1) % len(self.ORDER)]
        self.update()
        self.changed.emit()

    def paintEvent(self, ev) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.color is None:
            p.setPen(QPen(QColor(MUTED), 1.2, Qt.PenStyle.DashLine))
            p.drawEllipse(self.rect().adjusted(4, 4, -4, -4))
        else:
            p.drawPixmap(1, 1, shard_pixmap(self.color, True, 24))
        p.end()


class ShardRow(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.buttons = [ShardButton(Color.RED) for _ in range(4)]
        for b in self.buttons:
            b.changed.connect(self.changed)
            lay.addWidget(b)
        lay.addStretch(1)

    def colors(self) -> list[int]:
        return [int(b.color) for b in self.buttons if b.color is not None]

    def set_colors(self, codes: list[int]) -> None:
        for k, b in enumerate(self.buttons):
            b.color = Color(codes[k]) if k < len(codes) else None
            b.update()


def shard_label(color: Color, filled: bool, tooltip: str, size: int = 24) -> QLabel:
    lab = QLabel()
    lab.setPixmap(shard_pixmap(color, filled, size))
    lab.setToolTip(tooltip)
    lab.setFixedSize(size + 2, size + 2)
    return lab


class StatChip(QFrame):
    """Petite puce « icône + valeur » (stats d'un item)."""

    def __init__(self, stat: str, text: str, color: str | None = None, tooltip: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background: #2b2840; border-radius: 6px; }} QLabel {{ background: transparent; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(5, 2, 7, 2)
        lay.setSpacing(4)
        ic = QLabel()
        ic.setPixmap(stat_pixmap(stat, 16))
        lay.addWidget(ic)
        t = QLabel(text)
        if color:
            t.setStyleSheet(f"color: {color};")
        lay.addWidget(t)
        if tooltip:
            self.setToolTip(tooltip)


class StatCard(QFrame):
    """Carte « icône, libellé, valeur » du récapitulatif (style builder)."""

    def __init__(self, stat: str, label: str, value: str, color: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(stat_pixmap(stat, 22))
        lay.addWidget(ic)
        lab = QLabel(label)
        lab.setStyleSheet("background: transparent;")
        lay.addWidget(lab, 1)
        v = QLabel(value)
        v.setStyleSheet(f"background: transparent; font-weight: 700; color: {color or '#e8e6f0'};")
        v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(v)


class Separator(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {BORDER};")
