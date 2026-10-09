"""Shared building blocks so every page looks the same.

- ``PageHeader``: icon + title + subtitle on the left, actions on the right
- ``style_table`` / ``PillDelegate``: data tables with row dividers and
  coloured badges (severity, triage status) instead of coloured rows
- ``Switch``: an on/off switch that is a drop-in ``QCheckBox``
- ``SettingsCard``: titled card with a one-line description
- ``icon_button``: compact toolbar button with an icon
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QTableWidget, QVBoxLayout, QWidget,
)

from .icons import icon_label, set_icon
from .theme import ThemeManager, set_role, severity_color


def _palette():
    return ThemeManager.instance().palette


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

class PageHeader(QWidget):
    """Consistent page header: icon, title, subtitle, right-aligned actions."""

    def __init__(self, title: str, icon: str, subtitle: str = ""):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.icon = icon_label(icon, "accent", 22)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        self.title_label = QLabel(title)
        set_role(self.title_label, "pageTitle")
        self.subtitle_label = QLabel(subtitle)
        set_role(self.subtitle_label, "pageSubtitle")
        self.subtitle_label.setVisible(bool(subtitle))
        text.addWidget(self.title_label)
        text.addWidget(self.subtitle_label)
        layout.addLayout(text)
        layout.addStretch()

        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        layout.addLayout(self._actions)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))

    def add_action(self, widget: QWidget) -> QWidget:
        self._actions.addWidget(widget)
        return widget


def icon_button(icon: str, tooltip: str, token: str = "text") -> QPushButton:
    """Square icon-only button (e.g. Refresh)."""
    btn = QPushButton()
    btn.setProperty("variant", "icon")
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    set_icon(btn, icon, token, 16)
    btn.setFixedSize(QSize(32, 32))
    return btn


def text_button(text: str, icon: str | None = None, variant: str | None = None,
                token: str = "text") -> QPushButton:
    """Button with optional leading icon and theme variant."""
    # A leading space separates the icon from the label
    btn = QPushButton(f" {text}" if icon else text)
    if variant:
        btn.setProperty("variant", variant)
    if icon:
        set_icon(btn, icon, token, 16)
    return btn


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def style_table(table: QTableWidget, row_height: int = 36) -> None:
    """Data-table look: no grid or row numbers, divider lines, left headers."""
    table.setProperty("role", "data")
    table.setShowGrid(False)
    table.setAlternatingRowColors(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    header = table.horizontalHeader()
    header.setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    header.setHighlightSections(False)
    header.setMinimumSectionSize(60)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    table.setWordWrap(False)


STATUS_TOKENS = {
    "New": "info",
    "In progress": "warning",
    "Resolved": "success",
    "False positive": "text_muted",
    "Alert": "sev_critical",
    "Benign": "text_muted",
}


def status_color(status: str) -> str:
    return getattr(_palette(), STATUS_TOKENS.get(status, "text_muted"))


class PillDelegate(QStyledItemDelegate):
    """Paints the cell text as a small rounded badge.

    The item text is unchanged (tests, export and sorting still see
    "P0-Critical", "In progress", ...); only the painting differs.
    ``color_for(text) -> colour`` picks the badge colour.
    """

    def __init__(self, color_for, parent=None):
        super().__init__(parent)
        self._color_for = color_for

    def paint(self, painter: QPainter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        if not text:
            return

        color = QColor(self._color_for(text))
        font = QFont(opt.font)
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.DemiBold)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(font)
        fm = painter.fontMetrics()
        w = fm.horizontalAdvance(text) + 16
        h = fm.height() + 6
        r = opt.rect
        x = r.x() + 10
        y = r.y() + (r.height() - h) / 2
        pill = QRectF(x, y, min(w, r.width() - 14), h)
        fill = QColor(color)
        fill.setAlpha(40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(pill, h / 2, h / 2)
        painter.setPen(QPen(color))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width() + 24, size.height())


def tint(color: str, alpha: float = 0.16) -> str:
    """CSS rgba() of a palette colour at ``alpha`` (for tinted fills)."""
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def pill_label(text: str, color: str) -> QLabel:
    """Standalone badge matching the table badges (tinted fill + text)."""
    label = QLabel(text)
    style_pill(label, color)
    return label


def style_pill(label: QLabel, color: str) -> None:
    label.setStyleSheet(
        f"background-color: {tint(color)}; color: {color}; "
        "border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600;"
    )


def severity_delegate(parent=None) -> PillDelegate:
    return PillDelegate(severity_color, parent)


def status_delegate(parent=None) -> PillDelegate:
    return PillDelegate(status_color, parent)


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

class Switch(QCheckBox):
    """On/off switch drawn as a track + knob; behaves exactly like QCheckBox."""

    TRACK_W = 34
    TRACK_H = 18

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        ThemeManager.instance().theme_changed.connect(self.update)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) + 10 if self.text() else 0
        return QSize(self.TRACK_W + text_w + 4, max(self.TRACK_H, fm.height()) + 6)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        p = _palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        top = (self.height() - self.TRACK_H) / 2
        track = QRectF(1, top, self.TRACK_W, self.TRACK_H)
        on = self.isChecked()
        painter.setPen(QPen(QColor(p.accent if on else p.border), 1))
        painter.setBrush(QColor(p.accent if on else p.surface_alt))
        painter.drawRoundedRect(track, self.TRACK_H / 2, self.TRACK_H / 2)
        d = self.TRACK_H - 6
        knob_x = track.right() - d - 3 if on else track.left() + 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.text_inverse if on else p.text_muted))
        painter.drawEllipse(QRectF(knob_x, top + 3, d, d))
        if self.hasFocus():
            painter.setPen(QPen(QColor(p.accent), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track.adjusted(-2, -2, 2, 2),
                                    self.TRACK_H / 2 + 2, self.TRACK_H / 2 + 2)
        if self.text():
            painter.setPen(QColor(p.text))
            text_rect = self.rect().adjusted(self.TRACK_W + 10, 0, 0, 0)
            painter.drawText(text_rect,
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             self.text())
        painter.end()


# ---------------------------------------------------------------------------
# Settings card
# ---------------------------------------------------------------------------

class SettingsCard(QFrame):
    """Card with a title, short description and a content area."""

    def __init__(self, title: str, description: str = "", icon: str | None = None):
        super().__init__()
        self.setObjectName("settingsCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        if icon:
            head.addWidget(icon_label(icon, "text_muted", 18))
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = QLabel(title)
        set_role(self.title_label, "sectionTitle")
        titles.addWidget(self.title_label)
        if description:
            self.description_label = QLabel(description)
            set_role(self.description_label, "pageSubtitle")
            self.description_label.setWordWrap(True)
            titles.addWidget(self.description_label)
        head.addLayout(titles, 1)
        layout.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        layout.addLayout(self.body)
        self._apply_theme()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self, *_):
        p = _palette()
        self.setStyleSheet(f"""
            QFrame#settingsCard {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-radius: 8px;
            }}
        """)

    def add(self, widget_or_layout) -> None:
        if isinstance(widget_or_layout, QWidget):
            self.body.addWidget(widget_or_layout)
        else:
            self.body.addLayout(widget_or_layout)


def setting_row(label: str, description: str, control: QWidget) -> QHBoxLayout:
    """Label + muted description on the left, control on the right."""
    row = QHBoxLayout()
    row.setSpacing(16)
    texts = QVBoxLayout()
    texts.setSpacing(1)
    name = QLabel(label)
    set_role(name, "body")
    texts.addWidget(name)
    if description:
        desc = QLabel(description)
        set_role(desc, "pageSubtitle")
        desc.setWordWrap(True)
        texts.addWidget(desc)
    row.addLayout(texts, 1)
    row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return row
