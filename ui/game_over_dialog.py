"""Custom checkmate popup.

A frameless, theme-matched card that appears when either side is checkmated:
the winner's king, a one-line result, and Rematch / View board actions.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import pieces
from .theme import ACCENT, BORDER, PANEL, TEXT, TEXT_MUTED, ui_font

LOSING_RED = "#E8837B"


class GameOverDialog(QDialog):
    """Result card for a finished game."""

    rematch_requested = Signal()

    def __init__(
        self,
        human_won: bool,
        winner_white: bool,
        moves: int,
        level: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.human_won = bool(human_won)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setAccessibleName("Checkmate")
        self.setFixedWidth(372)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)

        card = QFrame()
        card.setObjectName("ResultCard")
        card.setStyleSheet(
            f"QFrame#ResultCard {{ background-color: {PANEL}; border: 1px solid {BORDER};"
            " border-radius: 14px; }"
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(54)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 165))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(3)

        art = QLabel()
        art.setPixmap(pieces.piece_pixmap_hidpi(("w" if winner_white else "b") + "K", 64, 2.0))
        art.setFixedSize(64, 64)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        layout.addWidget(art, 0, Qt.AlignmentFlag.AlignHCenter)

        kicker = QLabel(f"{'White' if winner_white else 'Black'} wins")
        kicker.setFont(ui_font(8.5, 800))
        kicker.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        kicker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(kicker)

        title = QLabel("Checkmate")
        title.setFont(ui_font(19, 800))
        title.setStyleSheet(f"color: {TEXT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("You won" if human_won else "You lost")
        subtitle.setFont(ui_font(11.5, 700))
        subtitle.setStyleSheet(f"color: {ACCENT if human_won else LOSING_RED};")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        if human_won:
            detail_text = (
                f"You delivered mate after {moves} move{'s' if moves != 1 else ''} "
                f"against level {level}."
            )
        else:
            detail_text = (
                f"The engine mated you after {moves} move{'s' if moves != 1 else ''} "
                f"at level {level}."
            )

        detail = QLabel(detail_text)
        detail.setFont(ui_font(9, 400))
        detail.setStyleSheet(f"color: {TEXT_MUTED};")
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(detail)

        layout.addSpacing(12)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.rematch_button = QPushButton("Rematch")
        self.rematch_button.setObjectName("primary")
        self.rematch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rematch_button.setDefault(True)
        self.rematch_button.clicked.connect(self._on_rematch)

        view_button = QPushButton("View board")
        view_button.setCursor(Qt.CursorShape.PointingHandCursor)
        view_button.clicked.connect(self.reject)

        buttons.addWidget(self.rematch_button, 1)
        buttons.addWidget(view_button, 1)
        layout.addLayout(buttons)

        self.rematch_button.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    # ------------------------------------------------------------------
    def _on_rematch(self) -> None:
        self.accept()
        self.rematch_requested.emit()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            centre = parent.window().frameGeometry().center()
            self.move(centre - self.rect().center())
