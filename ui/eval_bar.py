"""Vertical evaluation bar with a smooth animated fill and numeric score."""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from engine.coach import format_score
from .theme import BORDER, PANEL_ALT, TEXT, mono_font


class EvalBar(QWidget):
    """Chess.com style evaluation bar (white share grows from white's side)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._value = 0.5
        self._score_text = "0.0"
        self._flipped = False
        self._mate = None
        self._white_cp = 0
        self.setFixedWidth(32)
        self.setMinimumHeight(240)
        self.setToolTip("Evaluation — white's advantage grows upward")
        self.setAccessibleName("Evaluation bar")

        self._animation = QPropertyAnimation(self, b"value", self)
        self._animation.setDuration(420)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    # -- animated property -------------------------------------------------
    def get_value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, float(value)))
        self.update()

    value = Property(float, get_value, set_value)

    # -- API ---------------------------------------------------------------
    def set_flipped(self, flipped: bool) -> None:
        self._flipped = bool(flipped)
        self.update()

    def reset(self) -> None:
        self._white_cp = 0
        self._mate = None
        self._score_text = "0.0"
        self._animate(0.5)
        self.update()

    def set_eval(self, white_cp: int, mate: Optional[int] = None) -> None:
        self._white_cp = int(white_cp)
        self._mate = mate
        self._score_text = format_score(self._white_cp, self._mate)
        if mate is not None:
            share = 1.0 if mate > 0 else 0.0
            if mate == 0:
                share = 0.5
        else:
            cp = max(-2000, min(2000, self._white_cp))
            share = 1.0 / (1.0 + math.exp(-cp / 320.0))
        share = max(0.03, min(0.97, share))
        self._animate(share)
        self.setToolTip(f"Evaluation: {self._score_text}")

    def _animate(self, target: float) -> None:
        try:
            self._animation.stop()
            self._animation.setStartValue(self._value)
            self._animation.setEndValue(target)
            self._animation.start()
        except Exception:
            self.set_value(target)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#302E2B"))

        label_height = 22.0
        bar = QRectF(3.0, 2.0, self.width() - 6.0, max(10.0, self.height() - label_height - 4.0))
        path = QPainterPath()
        path.addRoundedRect(bar, 4.0, 4.0)
        painter.fillPath(path, QColor("#1A1918"))

        share = self._value
        if self._flipped:
            white_rect = QRectF(bar.x(), bar.y(), bar.width(), bar.height() * share)
        else:
            white_rect = QRectF(
                bar.x(), bar.y() + bar.height() * (1.0 - share), bar.width(), bar.height() * share
            )
        if white_rect.height() > 0.5:
            painter.save()
            painter.setClipPath(path)
            painter.fillRect(white_rect, QColor("#F4F3EF"))
            painter.restore()

        painter.setPen(QPen(QColor(BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Numeric score under the bar.
        text_rect = QRectF(0.0, self.height() - label_height, self.width(), label_height - 2.0)
        painter.setFont(mono_font(8.5, 700))
        painter.setPen(QColor(TEXT))
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignCenter), self._score_text)
        painter.end()

    def sizeHint(self):  # noqa: N802 - Qt API
        from PySide6.QtCore import QSize

        return QSize(32, 640)
