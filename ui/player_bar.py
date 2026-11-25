"""Player info bars: avatar, name, level badge, captures and clock."""

from __future__ import annotations

from typing import Optional

import chess
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import pieces
from .theme import (
    ACCENT,
    BORDER,
    DANGER,
    PANEL,
    PANEL_ALT,
    TEXT,
    TEXT_MUTED,
    icon,
    mono_font,
    ui_font,
)

MINI_PIECE = 18


class CapturedRow(QWidget):
    """Paints the small captured-piece icons plus the material advantage."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.symbols: list[str] = []
        self.advantage = 0
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_captured(self, symbols: list[str], advantage: int) -> None:
        self.symbols = list(symbols)
        self.advantage = int(advantage)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x = 0.0
        for symbol in self.symbols:
            pixmap = pieces.piece_pixmap(symbol, MINI_PIECE * 2)
            painter.drawPixmap(
                int(x),
                2,
                MINI_PIECE,
                MINI_PIECE,
                pixmap,
            )
            x += MINI_PIECE - 2
        if self.advantage > 0:
            painter.setFont(mono_font(9, 700))
            painter.setPen(QColor(TEXT_MUTED))
            painter.drawText(int(x + 4), 15, f"+{self.advantage}")
        painter.end()


class PlayerBar(QFrame):
    """One player strip (used for both the engine and the human)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("PlayerBar")
        self.setFixedHeight(62)
        self._active = False
        self._low_time = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 12, 8)
        layout.setSpacing(10)

        self.avatar = QLabel()
        self.avatar.setFixedSize(38, 38)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setStyleSheet(
            f"background-color: {PANEL_ALT}; border: 1px solid {BORDER}; border-radius: 19px;"
        )
        layout.addWidget(self.avatar)

        info = QVBoxLayout()
        info.setSpacing(1)
        info.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setSpacing(7)
        self.name_label = QLabel("Player")
        self.name_label.setFont(ui_font(10.5, 700))
        top.addWidget(self.name_label)

        self.badge = QLabel("")
        self.badge.setObjectName("Badge")
        self.badge.hide()
        top.addWidget(self.badge)

        self.sub_label = QLabel("")
        self.sub_label.setObjectName("Muted")
        self.sub_label.setFont(ui_font(8.5, 500))
        top.addWidget(self.sub_label)
        top.addStretch(1)
        info.addLayout(top)

        self.captured = CapturedRow()
        self.captured.setStyleSheet(f"color: {TEXT_MUTED};")
        info.addWidget(self.captured)

        layout.addLayout(info, 1)

        self.clock = QLabel("")
        self.clock.setFont(mono_font(15, 700))
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock.setMinimumWidth(64)
        self.clock.setStyleSheet(
            f"background-color: #1F1E1C; border: 1px solid {BORDER}; border-radius: 6px;"
            f" padding: 3px 8px; color: {TEXT};"
        )
        self.clock.hide()
        layout.addWidget(self.clock)

        self.setStyleSheet(self._style())

    # -- API ---------------------------------------------------------------
    def set_player(
        self,
        name: str,
        badge: str = "",
        subtitle: str = "",
        avatar_icon: str = "",
        accent: str = ACCENT,
    ) -> None:
        self.name_label.setText(name)
        if badge:
            self.badge.setText(badge)
            self.badge.show()
        else:
            self.badge.hide()
        self.sub_label.setText(subtitle)
        if avatar_icon:
            self.avatar.setPixmap(icon(avatar_icon, accent, 22).pixmap(22, 22))
        self.avatar.setStyleSheet(
            f"background-color: {PANEL_ALT}; border: 1px solid {BORDER}; border-radius: 19px;"
        )

    def set_captured(self, symbols: list[str], advantage: int) -> None:
        self.captured.set_captured(symbols, advantage)

    def set_clock(self, text: Optional[str], low: bool = False) -> None:
        if text is None:
            self.clock.hide()
            return
        self.clock.show()
        self.clock.setText(text)
        color = DANGER if low else TEXT
        background = "#3A201E" if low else "#1F1E1C"
        self.clock.setStyleSheet(
            f"background-color: {background}; border: 1px solid {BORDER};"
            f" border-radius: 6px; padding: 3px 8px; color: {color};"
        )

    def set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        self.setStyleSheet(self._style())

    def _style(self) -> str:
        left = f"3px solid {ACCENT}" if self._active else f"1px solid {BORDER}"
        return (
            f"QFrame#PlayerBar {{ background-color: {PANEL}; border: 1px solid {BORDER};"
            f" border-left: {left}; border-radius: 10px; }}"
        )

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(600, 62)
