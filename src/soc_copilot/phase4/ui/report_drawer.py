"""Investigation report drawer (UX-4).

Right-side slide-in panel that replaces the QMessageBox threat report.
Shows loading / report / error states, keeps a short session history,
and supports copy/export of the Markdown rendering.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .report_format import report_mode, report_to_markdown
from .theme import FONT_MD, ThemeManager, severity_color
from .motion import show_toast, slide_open_width


def _palette():
    return ThemeManager.instance().palette


_MODE_COLOR = {"AI report": "accent", "Partial": "warning", "Local-only": "info"}
_MAX_HISTORY = 10


class ReportDrawer(QFrame):
    """Right-side investigation report panel."""

    retry_requested = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("reportDrawer")
        self.setMinimumWidth(320)
        self.setMaximumWidth(560)
        self._current_report = None
        self._current_target = ""
        self._history: list = []  # [(label, report)]
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._init_ui()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self.hide()

    # ------------------------------------------------------------------ UI

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setObjectName("drawerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 10, 10)
        title = QLabel("🔍 Investigation Report")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._title_label = title
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.close_btn = QPushButton("✕")
        self.close_btn.setProperty("variant", "ghost")
        self.close_btn.setFixedWidth(32)
        self.close_btn.setToolTip("Close (Esc)")
        self.close_btn.clicked.connect(self.close_drawer)
        header_layout.addWidget(self.close_btn)
        layout.addWidget(header)

        # History selector (hidden until first report arrives)
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(240)
        self.history_combo.setToolTip("Recent reports")
        self.history_combo.currentIndexChanged.connect(self._on_history_select)
        hist_wrap = QWidget()
        hist_layout = QHBoxLayout(hist_wrap)
        hist_layout.setContentsMargins(14, 0, 14, 6)
        hist_label = QLabel("Recent:")
        set_muted(hist_label)
        hist_layout.addWidget(hist_label)
        hist_layout.addWidget(self.history_combo, 1)
        self._history_row = hist_wrap
        hist_wrap.setVisible(False)
        layout.addWidget(hist_wrap)

        # Stacked content pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # --- loading page ---
        loading = QWidget()
        loading_layout = QVBoxLayout(loading)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label = QLabel()
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setWordWrap(True)
        loading_layout.addWidget(self._loading_label)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)  # indeterminate
        self._loading_bar.setFixedWidth(200)
        loading_layout.addWidget(
            self._loading_bar, alignment=Qt.AlignmentFlag.AlignCenter
        )
        self.stack.addWidget(loading)  # index 0

        # --- report page ---
        self._report_scroll = QScrollArea()
        self._report_scroll.setWidgetResizable(True)
        self._report_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._report_body = QWidget()
        self._report_body.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self._report_layout = QVBoxLayout(self._report_body)
        self._report_layout.setContentsMargins(14, 10, 14, 10)
        self._report_layout.setSpacing(10)
        # Content keeps its natural height — scroll, never squeeze.
        self._report_layout.setSizeConstraint(
            self._report_layout.SizeConstraint.SetMinAndMaxSize
        )
        self._report_layout.addStretch()
        self._report_scroll.setWidget(self._report_body)
        self.stack.addWidget(self._report_scroll)  # index 1

        # --- error page ---
        error_page = QWidget()
        error_layout = QVBoxLayout(error_page)
        error_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_card = QFrame()
        self._error_card.setObjectName("drawerErrorCard")
        card_layout = QVBoxLayout(self._error_card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)
        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        card_layout.addWidget(self._error_label)
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setProperty("variant", "danger")
        self.retry_btn.clicked.connect(
            lambda: self.retry_requested.emit(self._current_target)
        )
        card_layout.addWidget(
            self.retry_btn, alignment=Qt.AlignmentFlag.AlignCenter
        )
        error_layout.addWidget(self._error_card)
        self.stack.addWidget(error_page)  # index 2

        # Footer
        footer = QWidget()
        footer.setObjectName("drawerFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 8, 14, 10)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setProperty("variant", "secondary")
        self.copy_btn.clicked.connect(self._copy_markdown)
        footer_layout.addWidget(self.copy_btn)
        self.export_btn = QPushButton("Export…")
        self.export_btn.setProperty("variant", "secondary")
        self.export_btn.clicked.connect(self._export_markdown)
        footer_layout.addWidget(self.export_btn)
        footer_layout.addStretch()
        close2 = QPushButton("Close")
        close2.clicked.connect(self.close_drawer)
        footer_layout.addWidget(close2)
        self._footer = footer
        self.copy_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        layout.addWidget(footer)

        self._apply_theme()

    def _apply_theme(self):
        p = _palette()
        self.setStyleSheet(f"""
            QFrame#reportDrawer {{
                background-color: {p.input_bg};
                border-left: 1px solid {p.border};
            }}
            QWidget#drawerHeader, QWidget#drawerFooter {{
                background-color: {p.surface};
            }}
            QFrame#drawerErrorCard {{
                background-color: {p.danger_bg};
                border: 1px solid {p.danger};
                border-radius: 8px;
            }}
        """)
        self._title_label.setStyleSheet(f"color: {p.accent};")
        if self.stack.currentIndex() == 1 and self._current_report is not None:
            self._render_report(self._current_report)
        elif self.stack.currentIndex() == 2:
            self._error_label.setStyleSheet(f"color: {p.danger};")

    # ------------------------------------------------------------- states

    def show_loading(self, target: str):
        self._current_target = target
        p = _palette()
        self._loading_label.setText(f"Investigating {target}…")
        self._loading_label.setStyleSheet(f"color: {p.text_muted};")
        self.stack.setCurrentIndex(0)
        self._footer.setVisible(False)
        self._reveal()

    def show_report(self, report):
        self._current_report = report
        self._current_target = getattr(report, "target", "") or ""
        self._render_report(report)
        self._push_history(report)
        self.stack.setCurrentIndex(1)
        self._footer.setVisible(True)
        self._reveal()

    def show_error(self, target: str, message: str):
        self._current_target = target
        self._current_report = None
        self._error_label.setText(f"Investigation failed for {target}:\n{message}")
        self._error_label.setStyleSheet(f"color: {_palette().danger};")
        self.stack.setCurrentIndex(2)
        self._footer.setVisible(True)
        self.copy_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self._reveal()

    def _reveal(self):
        """Show the drawer, sliding it in if it was closed."""
        was_hidden = not self.isVisible()
        self.show()
        self.raise_()
        if was_hidden:
            slide_open_width(self, 440)

    def close_drawer(self):
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_drawer()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------- report

    def _severity_key(self, report) -> str:
        from .theme import severity_key
        sev = getattr(report, "severity", None)
        return severity_key(getattr(sev, "value", sev) or "")

    def _badge(self, text, color) -> QLabel:
        badge = QLabel(text)
        badge.setStyleSheet(
            f"background-color: {color}; color: {_palette().text_inverse};"
            " font-weight: bold; border-radius: 4px; padding: 4px 10px;"
        )
        badge.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        return badge

    def _section_header(self, text) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {_palette().accent}; font-size: 13px; font-weight: bold;"
            " padding-top: 8px;"
        )
        return lbl

    def _body_label(self, text) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lbl.setStyleSheet(f"color: {_palette().text}; font-size: {FONT_MD};")
        lbl.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        return lbl

    def _render_report(self, report):
        self.copy_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

        # Clear previous content — detach immediately so pending
        # deleteLater()s can't repaint during a re-render (theme switch).
        while self._report_layout.count():
            self._discard_layout_item(self._report_layout.takeAt(0))

        p = _palette()

        # Target
        target = getattr(report, "target", "Unknown")
        target_lbl = self._body_label(target)
        target_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        target_lbl.setStyleSheet(f"color: {p.text};")
        self._report_layout.addWidget(target_lbl)

        # Badges
        badge_row = QHBoxLayout()
        sev_key = self._severity_key(report)
        sev_text = getattr(getattr(report, "severity", None), "value", None) \
            or getattr(report, "severity", "UNKNOWN") or "UNKNOWN"
        sev_badge = self._badge(f" {sev_text} ", severity_color(sev_key))
        sev_badge.setObjectName("sevBadge")
        badge_row.addWidget(sev_badge)
        mode = report_mode(report)
        mode_badge = self._badge(f" {mode} ", getattr(p, _MODE_COLOR[mode]))
        mode_badge.setObjectName("modeBadge")
        badge_row.addWidget(mode_badge)
        badge_row.addStretch()
        self._report_layout.addLayout(badge_row)

        generated = getattr(report, "generated_at", None)
        gen_text = generated.strftime("%Y-%m-%d %H:%M:%S") \
            if isinstance(generated, datetime) else str(generated or "Unknown")
        model = getattr(report, "llm_model", None)
        meta = f"Generated: {gen_text}" + (f"  •  Model: {model}" if model else "")
        meta_lbl = QLabel(meta)
        meta_lbl.setObjectName("reportMeta")
        meta_lbl.setStyleSheet(f"color: {p.text_muted}; font-size: 10px;")
        self._report_layout.addWidget(meta_lbl)

        # Summary
        self._report_layout.addWidget(self._section_header("Summary"))
        self._report_layout.addWidget(
            self._body_label(getattr(report, "summary", "") or "No summary provided.")
        )

        # Recommendations
        recs = getattr(report, "recommendations", None) or []
        if recs:
            self._report_layout.addWidget(self._section_header("Recommendations"))
            self._report_layout.addWidget(
                self._body_label("\n".join(f"• {r}" for r in recs))
            )

        # Recon / Reputation / Exposure — field rows (label muted, value text)
        for title, fields in self._data_sections(report):
            self._report_layout.addWidget(self._section_header(title))
            self._report_layout.addWidget(self._field_label(fields))

        self._report_layout.addStretch()

    @staticmethod
    def _discard_layout_item(item):
        """Detach a widget (or nested layout) from the report body."""
        if item is None:
            return
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
            return
        layout = item.layout()
        if layout is not None:
            while layout.count():
                ReportDrawer._discard_layout_item(layout.takeAt(0))

    def _field_label(self, fields) -> QLabel:
        """One rich-text label: 'Label: value' rows, label muted."""
        from html import escape
        muted = _palette().text_muted
        text = _palette().text
        rows = "".join(
            f"<span style='color:{muted}'>{escape(label)}:</span>"
            f"&nbsp;<span style='color:{text}'>{escape(value)}</span><br>"
            for label, value in fields
        )
        lbl = QLabel(rows)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lbl.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        return lbl

    def _data_sections(self, report):
        """Yield (title, [(label, value)]) for present data sections."""
        from .report_format import (
            _recon_fields, _reputation_fields, _shodan_fields,
        )
        sections = []
        recon = getattr(report, "recon", None)
        if recon is not None:
            fields = _recon_fields(recon)
            if fields:
                sections.append(("Recon", fields))
        rep = getattr(report, "reputation", None)
        if rep is not None:
            fields = _reputation_fields(rep)
            if fields:
                sections.append(("Reputation", fields))
        shodan = getattr(report, "shodan", None)
        if shodan is not None:
            fields = _shodan_fields(shodan)
            if fields:
                sections.append(("Exposure (Shodan)", fields))
        return sections

    # ------------------------------------------------------------- history

    def _push_history(self, report):
        target = getattr(report, "target", "") or "?"
        generated = getattr(report, "generated_at", None)
        stamp = generated.strftime("%H:%M") if isinstance(generated, datetime) else ""
        label = f"{target} — {stamp}" if stamp else target
        self._history.insert(0, (label, report))
        del self._history[_MAX_HISTORY:]
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        self.history_combo.addItems([label for label, _ in self._history])
        self.history_combo.blockSignals(False)
        self._history_row.setVisible(True)

    def _on_history_select(self, index: int):
        if 0 <= index < len(self._history):
            report = self._history[index][1]
            self._current_report = report
            self._current_target = getattr(report, "target", "") or ""
            self._render_report(report)
            self.stack.setCurrentIndex(1)
            self._footer.setVisible(True)

    # ------------------------------------------------------------- actions

    def _copy_markdown(self):
        if self._current_report is None:
            return
        QApplication.clipboard().setText(report_to_markdown(self._current_report))
        self.copy_btn.setText("Copied")
        show_toast(self, "Report copied as Markdown", "success")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("Copy"))

    def _export_markdown(self):
        if self._current_report is None:
            return
        target = self._current_target or "report"
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export report",
            f"threat_report_{target}_{stamp}.md",
            "Markdown (*.md)",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report_to_markdown(self._current_report))


def set_muted(widget):
    from .theme import set_role
    set_role(widget, "muted")
