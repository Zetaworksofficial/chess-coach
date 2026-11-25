"""Right-hand sidebar: game setup, live move list, coach card and actions."""

from __future__ import annotations

from typing import Optional

import chess
from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from engine.ai_manager import elo_for, level_summary, tier_for
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    DANGER,
    INFO,
    PANEL,
    PANEL_ALT,
    TEXT,
    TEXT_DIM,
    TEXT_MUTED,
    WARNING,
    icon,
    mono_font,
    ui_font,
)

TIER_COLORS = {
    "Beginner": "#7FB04F",
    "Casual": "#A9C46C",
    "Intermediate": "#E0B23C",
    "Advanced": "#DE8B3A",
    "Master": "#CB4B42",
}


def _section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    label.setFont(ui_font(8.0, 700))
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("hline")
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {BORDER}; border: none;")
    return line


class ToggleSwitch(QWidget):
    """Small animated on/off switch (no external images)."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._checked = bool(checked)
        self._offset = 1.0 if checked else 0.0
        self.setFixedSize(42, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Coach mode toggle")
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = max(0.0, min(1.0, float(value)))
        self.update()

    offset = Property(float, get_offset, set_offset)

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool, emit: bool = False) -> None:
        checked = bool(checked)
        if checked == self._checked:
            self.set_offset(1.0 if checked else 0.0)
            return
        self._checked = checked
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()
        if emit:
            self.toggled.emit(checked)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_checked(not self._checked, emit=True)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QColor(ACCENT) if self._checked else QColor("#4B4845")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(0, 2, self.width(), self.height() - 4, 10, 10)
        knob_x = 2.0 + self._offset * (self.width() - 22.0)
        painter.setBrush(QColor("#F7F6F3"))
        painter.drawEllipse(int(knob_x), 3, 18, 18)
        painter.end()


class SegmentedControl(QWidget):
    """Row of mutually exclusive pill buttons."""

    value_changed = Signal(str)

    def __init__(self, options: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Segment")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#Segment {{ background-color: #1F1E1C; border: 1px solid {BORDER};"
            " border-radius: 8px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        self._buttons: dict[str, QPushButton] = {}
        self._value = options[0] if options else ""
        for option in options:
            button = QPushButton(option)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(option == self._value)
            button.clicked.connect(lambda _checked=False, name=option: self.set_value(name, True))
            layout.addWidget(button, 1)
            self._buttons[option] = button

    def value(self) -> str:
        return self._value

    def set_value(self, value: str, emit: bool = False) -> None:
        if value not in self._buttons:
            return
        changed = value != self._value
        self._value = value
        for name, button in self._buttons.items():
            button.setChecked(name == value)
        if emit and changed:
            self.value_changed.emit(value)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(240, 34)


class LevelControl(QWidget):
    """AI level slider with live tier + Elo readout."""

    level_changed = Signal(int)

    def __init__(self, level: int = 40, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._level = max(1, min(100, int(level)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(_section_label("AI level"))
        header.addStretch(1)
        self.value_label = QLabel("Lv. 40")
        self.value_label.setFont(mono_font(10, 700))
        header.addWidget(self.value_label)
        layout.addLayout(header)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.setValue(self._level)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(5)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.valueChanged.connect(self._on_slider)
        layout.addWidget(self.slider)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.tier_label = QLabel("Intermediate")
        self.tier_label.setObjectName("Badge")
        self.tier_label.setFont(ui_font(8.5, 700))
        footer.addWidget(self.tier_label)
        self.elo_label = QLabel("~1,150 Elo")
        self.elo_label.setObjectName("Muted")
        self.elo_label.setFont(ui_font(9.0, 500))
        footer.addWidget(self.elo_label)
        footer.addStretch(1)
        self.scale_label = QLabel("1 – 100")
        self.scale_label.setObjectName("Dim")
        self.scale_label.setFont(mono_font(8.0, 500))
        footer.addWidget(self.scale_label)
        layout.addLayout(footer)

        self._refresh_labels()

    def level(self) -> int:
        return self._level

    def set_level(self, level: int, emit: bool = False) -> None:
        level = max(1, min(100, int(level)))
        if level == self._level:
            self._refresh_labels()
            return
        self._level = level
        self.slider.blockSignals(True)
        self.slider.setValue(level)
        self.slider.blockSignals(False)
        self._refresh_labels()
        if emit:
            self.level_changed.emit(level)

    def _on_slider(self, value: int) -> None:
        self._level = int(value)
        self._refresh_labels()
        self.level_changed.emit(self._level)

    def _refresh_labels(self) -> None:
        _level, tier, elo = level_summary(self._level)
        self.value_label.setText(f"Lv. {self._level}")
        self.tier_label.setText(tier)
        color = TIER_COLORS.get(tier, ACCENT)
        self.tier_label.setStyleSheet(
            f"background-color: {color}; border: none; border-radius: 9px;"
            " color: #17240C; padding: 2px 8px; font-weight: 700; font-size: 11px;"
        )
        self.elo_label.setText(f"~{elo:,} Elo")


class CoachCard(QFrame):
    """The coach's verdict card."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(_section_label("Coach"))
        header.addStretch(1)
        self.badge = QLabel("")
        self.badge.setFont(ui_font(8.5, 700))
        self.badge.hide()
        header.addWidget(self.badge)
        layout.addLayout(header)

        self.body = QLabel("Make a move and I will review it.")
        self.body.setWordWrap(True)
        self.body.setFont(ui_font(9.5, 450))
        self.body.setStyleSheet(f"color: {TEXT};")
        self.body.setMinimumHeight(38)
        layout.addWidget(self.body)

        self.footnote = QLabel("Coach mode reviews every move you play.")
        self.footnote.setObjectName("Dim")
        self.footnote.setFont(ui_font(8.0, 450))
        self.footnote.setWordWrap(True)
        layout.addWidget(self.footnote)

    def set_badge(self, text: str, color: str) -> None:
        if not text:
            self.badge.hide()
            return
        self.badge.setText(text)
        self.badge.setStyleSheet(
            f"background-color: {color}; border: none; border-radius: 9px;"
            " color: #16220C; padding: 2px 9px; font-weight: 700; font-size: 11px;"
        )
        self.badge.show()

    def set_text(self, text: str, muted: bool = False) -> None:
        self.body.setText(text)
        self.body.setStyleSheet(f"color: {TEXT_MUTED if muted else TEXT};")

    def set_footnote(self, text: str) -> None:
        self.footnote.setText(text)


class Sidebar(QWidget):
    """Container for all play-page controls."""

    new_game_requested = Signal(dict)
    level_changed = Signal(int)
    coach_toggled = Signal(bool)
    hint_requested = Signal()
    takeback_requested = Signal()
    flip_requested = Signal()
    resign_requested = Signal()
    move_selected = Signal(int)
    live_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(372)
        self._last_signature: tuple = ()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 8)
        header_layout.setSpacing(8)
        title = QLabel("Play")
        title.setFont(ui_font(15, 700))
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        self.engine_badge = QLabel("Detecting engine…")
        self.engine_badge.setObjectName("Badge")
        self.engine_badge.setFont(ui_font(8.0, 600))
        header_layout.addWidget(self.engine_badge)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        content = QVBoxLayout(container)
        content.setContentsMargins(18, 4, 18, 18)
        content.setSpacing(12)

        # -- setup card ----------------------------------------------------
        setup = QFrame()
        setup.setObjectName("Card")
        setup_layout = QVBoxLayout(setup)
        setup_layout.setContentsMargins(14, 14, 14, 14)
        setup_layout.setSpacing(10)

        self.level_control = LevelControl(40)
        setup_layout.addWidget(self.level_control)
        setup_layout.addWidget(_divider())

        setup_layout.addWidget(_section_label("Play as"))
        self.side_control = SegmentedControl(["White", "Black", "Random"])
        setup_layout.addWidget(self.side_control)

        setup_layout.addWidget(_section_label("Time control"))
        self.time_control = SegmentedControl(["Untimed", "3+2 Blitz", "10+0 Rapid"])
        setup_layout.addWidget(self.time_control)

        coach_row = QHBoxLayout()
        coach_row.setSpacing(10)
        coach_text = QVBoxLayout()
        coach_text.setSpacing(1)
        coach_title = QLabel("Coach mode")
        coach_title.setFont(ui_font(10, 600))
        coach_text.addWidget(coach_title)
        coach_sub = QLabel("Review every move you play")
        coach_sub.setObjectName("Muted")
        coach_sub.setFont(ui_font(8.5, 450))
        coach_text.addWidget(coach_sub)
        coach_row.addLayout(coach_text, 1)
        self.coach_switch = ToggleSwitch(True)
        coach_row.addWidget(self.coach_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        setup_layout.addLayout(coach_row)

        self.new_game_button = QPushButton("  New Game")
        self.new_game_button.setObjectName("primary")
        self.new_game_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_game_button.setIcon(icon("plus", "#17240C", 16))
        self.new_game_button.setIconSize(QSize(16, 16))
        self.new_game_button.setFont(ui_font(10.5, 700))
        setup_layout.addWidget(self.new_game_button)

        content.addWidget(setup)

        # -- moves card ----------------------------------------------------
        moves_card = QFrame()
        moves_card.setObjectName("Card")
        moves_layout = QVBoxLayout(moves_card)
        moves_layout.setContentsMargins(14, 12, 14, 12)
        moves_layout.setSpacing(8)

        moves_header = QHBoxLayout()
        moves_header.addWidget(_section_label("Moves"))
        moves_header.addStretch(1)
        self.live_button = QPushButton("Live")
        self.live_button.setObjectName("link")
        self.live_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_button.setToolTip("Jump back to the current position")
        moves_header.addWidget(self.live_button)
        moves_layout.addLayout(moves_header)

        self.move_scroll = QScrollArea()
        self.move_scroll.setWidgetResizable(True)
        self.move_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.move_scroll.setMinimumHeight(150)
        self.move_scroll.setMaximumHeight(196)
        self.move_host = QWidget()
        self.move_grid = QGridLayout(self.move_host)
        self.move_grid.setContentsMargins(0, 0, 0, 0)
        self.move_grid.setHorizontalSpacing(4)
        self.move_grid.setVerticalSpacing(1)
        self.move_grid.setColumnStretch(0, 0)
        self.move_grid.setColumnStretch(1, 1)
        self.move_grid.setColumnStretch(2, 1)
        self.move_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.move_scroll.setWidget(self.move_host)
        moves_layout.addWidget(self.move_scroll)

        self.move_placeholder = QLabel("No moves yet — start a game.")
        self.move_placeholder.setObjectName("Dim")
        self.move_placeholder.setFont(ui_font(9.0, 450))
        self.move_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        moves_layout.addWidget(self.move_placeholder)

        content.addWidget(moves_card)

        # -- coach card ----------------------------------------------------
        self.coach_card = CoachCard()
        content.addWidget(self.coach_card)

        # -- actions -------------------------------------------------------
        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(8)
        self.hint_button = self._action_button("Hint", "hint")
        self.takeback_button = self._action_button("Takeback", "undo")
        self.flip_button = self._action_button("Flip Board", "flip")
        self.resign_button = self._action_button("Resign", "flag")
        actions.addWidget(self.hint_button, 0, 0)
        actions.addWidget(self.takeback_button, 0, 1)
        actions.addWidget(self.flip_button, 1, 0)
        actions.addWidget(self.resign_button, 1, 1)
        content.addLayout(actions)

        self.status_label = QLabel("Ready when you are.")
        self.status_label.setWordWrap(True)
        self.status_label.setFont(ui_font(9.0, 500))
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED};")
        content.addWidget(self.status_label)
        content.addStretch(1)

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        # -- wiring --------------------------------------------------------
        self.new_game_button.clicked.connect(self._emit_new_game)
        self.level_control.level_changed.connect(self._on_level)
        self.coach_switch.toggled.connect(self.coach_toggled)
        self.hint_button.clicked.connect(self.hint_requested)
        self.takeback_button.clicked.connect(self.takeback_requested)
        self.flip_button.clicked.connect(self.flip_requested)
        self.resign_button.clicked.connect(self.resign_requested)
        self.live_button.clicked.connect(self.live_requested)

    # ------------------------------------------------------------------
    def _action_button(self, text: str, icon_name: str) -> QPushButton:
        button = QPushButton(f" {text}")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIcon(icon(icon_name, TEXT, 16))
        button.setIconSize(QSize(16, 16))
        button.setFont(ui_font(9.5, 600))
        button.setMinimumHeight(36)
        return button

    def _emit_new_game(self) -> None:
        self.new_game_requested.emit(self.config())

    def _on_level(self, level: int) -> None:
        self.level_changed.emit(level)

    # -- configuration --------------------------------------------------
    def config(self) -> dict:
        return {
            "level": self.level_control.level(),
            "side": self.side_control.value(),
            "time": self.time_control.value(),
        }

    def set_level(self, level: int) -> None:
        self.level_control.set_level(level)

    def set_coach_enabled(self, enabled: bool) -> None:
        self.coach_switch.set_checked(enabled)

    def coach_enabled(self) -> bool:
        return self.coach_switch.is_checked()

    def set_engine_label(self, text: str) -> None:
        self.engine_badge.setText(text)
        strong = "built-in" not in text.lower()
        self.engine_badge.setToolTip(
            "Stockfish is used for the strongest play and analysis."
            if strong
            else "Stockfish was not found — the bundled engine plays instead."
        )

    def set_game_context(self, level: int, human_color: bool, time_control: str) -> None:
        self.set_level(level)
        self.side_control.set_value("White" if human_color == chess.WHITE else "Black")

    # -- moves ----------------------------------------------------------
    def set_moves(self, sans: list[str], current_ply: Optional[int]) -> None:
        total = len(sans)
        live = current_ply is None or current_ply >= total
        signature = (tuple(sans), None if live else current_ply)
        if signature == self._last_signature:
            return
        self._last_signature = signature

        while self.move_grid.count():
            item = self.move_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.move_placeholder.setVisible(total == 0)
        self.move_scroll.setVisible(total > 0)
        self.live_button.setVisible(not live)

        for index in range(0, total, 2):
            number = QLabel(f"{index // 2 + 1}.")
            number.setFont(mono_font(8.5, 600))
            number.setStyleSheet(f"color: {TEXT_DIM};")
            number.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            number.setFixedWidth(26)
            self.move_grid.addWidget(number, index // 2, 0)

            white_button = self._move_button(sans[index], index + 1, current_ply)
            self.move_grid.addWidget(white_button, index // 2, 1)

            if index + 1 < total:
                black_button = self._move_button(sans[index + 1], index + 2, current_ply)
                self.move_grid.addWidget(black_button, index // 2, 2)
            else:
                spacer = QWidget()
                spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                self.move_grid.addWidget(spacer, index // 2, 2)

        self.move_host.adjustSize()

        if total:
            QTimer.singleShot(0, self._scroll_moves_to_bottom)

    def _move_button(self, san: str, ply: int, current_ply: Optional[int]) -> QPushButton:
        button = QPushButton(san)
        button.setObjectName("move")
        button.setFont(mono_font(9.5, 500))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("current", "true" if current_ply == ply else "false")
        button.clicked.connect(lambda _checked=False, value=ply: self.move_selected.emit(value))
        return button

    def _scroll_moves_to_bottom(self) -> None:
        bar = self.move_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # -- status / coach --------------------------------------------------
    def set_status(self, text: str, tone: str = "normal") -> None:
        colors = {"normal": TEXT_MUTED, "good": ACCENT, "bad": DANGER, "warn": WARNING}
        color = colors.get(tone, TEXT_MUTED)
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")

    def set_actions_enabled(
        self,
        hint: bool,
        takeback: bool,
        resign: bool,
        flip: bool = True,
    ) -> None:
        self.hint_button.setEnabled(hint)
        self.takeback_button.setEnabled(takeback)
        self.resign_button.setEnabled(resign)
        self.flip_button.setEnabled(flip)

    def coach_idle(self, text: str = "Make a move and I will review it.") -> None:
        self.coach_card.set_badge("", "")
        self.coach_card.set_text(text, muted=True)

    def coach_thinking(self, text: str = "Analysing your move…") -> None:
        self.coach_card.set_badge("Thinking", INFO)
        self.coach_card.set_text(text, muted=True)

    def coach_hint_pending(self) -> None:
        self.coach_card.set_badge("Hint", INFO)
        self.coach_card.set_text("Looking for the strongest continuation…", muted=True)

    def coach_error(self, text: str = "The engine could not review that move.") -> None:
        self.coach_card.set_badge("Coach", WARNING)
        self.coach_card.set_text(text, muted=True)

    def show_verdict(self, label: str, color: str, text: str, note: str = "") -> None:
        self.coach_card.set_badge(label, color)
        self.coach_card.set_text(text)
        if note:
            self.coach_card.set_footnote(note)

    def show_hint(self, text: str) -> None:
        self.coach_card.set_badge("Hint", INFO)
        self.coach_card.set_text(text)
        self.coach_card.set_footnote("Arrows on the board show the move.")

    def clear_coach(self) -> None:
        self.coach_card.set_badge("", "")
        self.coach_card.set_text("Make a move and I will review it.", muted=True)
        self.coach_card.set_footnote("Coach mode reviews every move you play.")
