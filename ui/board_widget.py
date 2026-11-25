"""The interactive chess board widget.

Renders a responsive 8x8 board with Chess.com-style highlights, supports both
click-to-move and drag-and-drop, draws right-click arrows and coach arrows.
"""

from __future__ import annotations

import math
from typing import Optional

import chess
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import pieces
from .theme import (
    BG,
    BOARD_THEMES,
    CHECK_TINT,
    COACH_ARROW,
    LAST_MOVE_TINT,
    LEGAL_DOT,
    LEGAL_RING,
    PANEL,
    SELECT_TINT,
    USER_ARROW,
    WRONG_TINT,
    BoardTheme,
    mono_font,
    ui_font,
)

DRAG_THRESHOLD = 3.0

PROMOTION_PIECES = (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
PROMOTION_NAMES = {
    chess.QUEEN: "Queen",
    chess.ROOK: "Rook",
    chess.BISHOP: "Bishop",
    chess.KNIGHT: "Knight",
}


class BoardStage(QWidget):
    """Keeps the board square and aligns the bars and eval bar to it."""

    def __init__(
        self,
        board: "BoardWidget",
        eval_bar: QWidget,
        top_bar: Optional[QWidget] = None,
        bottom_bar: Optional[QWidget] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.board = board
        self.eval_bar = eval_bar
        self.top_bar = top_bar
        self.bottom_bar = bottom_bar
        self.eval_visible = True
        self.gap = 10
        self.vgap = 10
        board.setParent(self)
        eval_bar.setParent(self)
        if top_bar is not None:
            top_bar.setParent(self)
        if bottom_bar is not None:
            bottom_bar.setParent(self)
        self.setMinimumSize(400, 420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_eval_visible(self, visible: bool) -> None:
        self.eval_visible = bool(visible)
        self.eval_bar.setVisible(bool(visible))
        self.updateGeometry()
        self._layout_children()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._layout_children()
        super().resizeEvent(event)

    def _layout_children(self) -> None:
        bar_w = self.eval_bar.width() if self.eval_visible else 0
        gap = self.gap if bar_w else 0
        top_h = self.top_bar.height() if self.top_bar is not None else 0
        bottom_h = self.bottom_bar.height() if self.bottom_bar is not None else 0
        vgap = self.vgap if top_h else 0
        vgap_bottom = self.vgap if bottom_h else 0

        available_h = self.height() - top_h - bottom_h - vgap - vgap_bottom
        available_w = self.width() - bar_w - gap
        side = max(160, int(min(available_w, available_h)))
        block_w = side + bar_w + gap
        x0 = int((self.width() - block_w) / 2)
        total_h = side + top_h + bottom_h + vgap + vgap_bottom
        y0 = int((self.height() - total_h) / 2)

        if self.top_bar is not None:
            self.top_bar.setGeometry(x0, y0, block_w, top_h)
            board_y = y0 + top_h + vgap
        else:
            board_y = y0

        if bar_w:
            self.eval_bar.setGeometry(x0, board_y, bar_w, side)
        self.board.setGeometry(x0 + bar_w + gap, board_y, side, side)

        if self.bottom_bar is not None:
            self.bottom_bar.setGeometry(x0, board_y + side + vgap_bottom, block_w, bottom_h)


class PromotionDialog(QDialog):
    """Small modal picker shown when a pawn reaches the last rank."""

    def __init__(self, color: bool, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Promote pawn")
        self.setModal(True)
        self.choice: Optional[int] = None
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Choose a promotion piece")
        title.setFont(ui_font(12, 600))
        layout.addWidget(title)

        subtitle = QLabel("Queens are strongest — but a knight can be the only winning move.")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        row = QHBoxLayout()
        row.setSpacing(8)
        for piece_type in PROMOTION_PIECES:
            button = QPushButton()
            button.setObjectName("promotion")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(74, 84)
            symbol = ("w" if color == chess.WHITE else "b") + chess.piece_symbol(piece_type).upper()
            button.setIcon(pieces.piece_pixmap_hidpi(symbol, 56, 2.0))
            button.setIconSize(QSize(56, 56))
            button.setToolTip(PROMOTION_NAMES[piece_type])
            button.setStyleSheet(
                "QPushButton#promotion { background-color: #3C3A38; border: 1px solid #454340;"
                " border-radius: 8px; padding: 6px; }"
                "QPushButton#promotion:hover { background-color: #4A4744; border-color: #81B64C; }"
            )
            button.clicked.connect(lambda _checked=False, pt=piece_type: self._pick(pt))
            row.addWidget(button)
        layout.addLayout(row)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _pick(self, piece_type: int) -> None:
        self.choice = piece_type
        self.accept()

    @classmethod
    def ask(cls, color: bool, parent: Optional[QWidget] = None) -> Optional[int]:
        dialog = cls(color, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.choice
        return None


class BoardWidget(QWidget):
    """Responsive board renderer and mouse interaction surface."""

    move_requested = Signal(int, int)
    illegal_drop = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.board = chess.Board()
        self.orientation = chess.WHITE
        self.interactive = True
        self.theme: BoardTheme = BOARD_THEMES["Classic Green"]
        self.show_coordinates = True
        self.last_move: Optional[chess.Move] = None
        self.coach_arrow: Optional[chess.Move] = None
        self.selected: Optional[int] = None
        self.legal_targets: dict[int, chess.Move] = {}
        self.wrong_move: Optional[tuple[int, int]] = None

        self._drag_square: Optional[int] = None
        self._drag_pos: Optional[QPointF] = None
        self._drag_active = False
        self._press_pos: Optional[QPointF] = None
        self._hover_square: Optional[int] = None
        self._arrow_start: Optional[int] = None
        self._arrow_end: Optional[int] = None
        self._user_arrow: Optional[tuple[int, int]] = None

        self._square = 60.0
        self._origin = QPointF(0.0, 0.0)

        self._arrow_timer = QTimer(self)
        self._arrow_timer.setSingleShot(True)
        self._arrow_timer.timeout.connect(self._clear_user_arrow)

        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Chess board")
        self.setCursor(Qt.CursorShape.ArrowCursor)

    # ------------------------------------------------------------------
    # State API
    # ------------------------------------------------------------------
    def set_position(
        self,
        board: chess.Board,
        last_move: Optional[chess.Move] = None,
        interactive: Optional[bool] = None,
    ) -> None:
        self.board = board.copy()
        self.last_move = last_move
        if interactive is not None:
            self.interactive = interactive
        self.selected = None
        self.legal_targets.clear()
        self._drag_square = None
        self._drag_pos = None
        self._drag_active = False
        self.update()

    def set_theme(self, name: str) -> None:
        self.theme = BOARD_THEMES.get(name, BOARD_THEMES["Classic Green"])
        self.update()

    def set_coach_arrow(self, move: Optional[chess.Move]) -> None:
        self.coach_arrow = move
        self.update()

    def set_wrong_move(self, squares: Optional[tuple[int, int]]) -> None:
        self.wrong_move = squares
        self.update()

    def clear_selection(self) -> None:
        self.selected = None
        self.legal_targets.clear()
        self.update()

    def flip(self) -> None:
        self.orientation = not self.orientation
        self.update()

    def set_orientation(self, color: bool) -> None:
        self.orientation = color
        self.update()

    def clear_user_arrow(self) -> None:
        self._user_arrow = None
        self.update()

    def _clear_user_arrow(self) -> None:
        self._user_arrow = None
        self.update()

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def _metrics(self) -> None:
        side = float(min(self.width(), self.height()))
        self._square = side / 8.0
        self._origin = QPointF(
            (self.width() - side) / 2.0, (self.height() - side) / 2.0
        )

    def square_rect(self, square: int) -> QRectF:
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        if self.orientation == chess.WHITE:
            col, row = file, 7 - rank
        else:
            col, row = 7 - file, rank
        return QRectF(
            self._origin.x() + col * self._square,
            self._origin.y() + row * self._square,
            self._square,
            self._square,
        )

    def square_center(self, square: int) -> QPointF:
        rect = self.square_rect(square)
        return QPointF(rect.center())

    def square_at(self, point: QPointF) -> Optional[int]:
        if self._square <= 0:
            return None
        dx = point.x() - self._origin.x()
        dy = point.y() - self._origin.y()
        if dx < 0 or dy < 0:
            return None
        col = int(dx // self._square)
        row = int(dy // self._square)
        if col < 0 or col > 7 or row < 0 or row > 7:
            return None
        if self.orientation == chess.WHITE:
            file, rank = col, 7 - row
        else:
            file, rank = 7 - col, row
        return chess.square(file, rank)

    def board_rect(self) -> QRectF:
        return QRectF(self._origin.x(), self._origin.y(), self._square * 8, self._square * 8)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._metrics()
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.fillRect(self.rect(), QColor(BG))

        if self._square < 8:
            painter.end()
            return

        board_rect = self.board_rect()

        # Squares
        for square in chess.SQUARES:
            rect = self.square_rect(square)
            light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            painter.fillRect(rect, QColor(self.theme.light if light else self.theme.dark))

        # Wrong move flash (lesson feedback)
        if self.wrong_move is not None:
            for square in self.wrong_move:
                painter.fillRect(self.square_rect(square), WRONG_TINT)

        # Last move
        if self.last_move is not None:
            for square in (self.last_move.from_square, self.last_move.to_square):
                painter.fillRect(self.square_rect(square), LAST_MOVE_TINT)

        # Selection
        if self.selected is not None:
            painter.fillRect(self.square_rect(self.selected), SELECT_TINT)

        # Check highlight
        if self.board.is_check():
            king_square = self.board.king(self.board.turn)
            if king_square is not None:
                rect = self.square_rect(king_square)
                gradient = QRadialGradient(rect.center(), self._square * 0.62)
                gradient.setColorAt(0.0, QColor(255, 70, 55, 200))
                gradient.setColorAt(0.55, QColor(214, 62, 52, 140))
                gradient.setColorAt(1.0, QColor(214, 62, 52, 0))
                painter.fillRect(rect, QBrush(gradient))

        # Legal move hints
        for target, _move in self.legal_targets.items():
            rect = self.square_rect(target)
            occupied = self.board.piece_at(target) is not None
            if occupied:
                pen = QPen(LEGAL_RING, max(2.0, self._square * 0.085))
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect.adjusted(2, 2, -2, -2))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(LEGAL_DOT)
                radius = self._square * 0.155
                painter.drawEllipse(rect.center(), radius, radius)

        # Pieces
        for square, piece in self.board.piece_map().items():
            if self._drag_active and square == self._drag_square:
                continue
            self._draw_piece(painter, pieces.piece_symbol(piece), self.square_rect(square))

        # Arrows
        if self.coach_arrow is not None:
            self._draw_arrow(
                painter,
                self.coach_arrow.from_square,
                self.coach_arrow.to_square,
                COACH_ARROW,
            )
        if self._user_arrow is not None:
            self._draw_arrow(painter, self._user_arrow[0], self._user_arrow[1], USER_ARROW)
        if self._arrow_start is not None and self._arrow_end is not None:
            if self._arrow_start != self._arrow_end:
                self._draw_arrow(painter, self._arrow_start, self._arrow_end, USER_ARROW)

        # Coordinates inside the edge squares
        if self.show_coordinates:
            self._draw_coordinates(painter)

        # Dragged piece on top
        if self._drag_active and self._drag_square is not None and self._drag_pos is not None:
            piece = self.board.piece_at(self._drag_square)
            if piece is not None:
                size = self._square * 1.02
                target = QRectF(
                    self._drag_pos.x() - size / 2,
                    self._drag_pos.y() - size / 2,
                    size,
                    size,
                )
                self._draw_piece(painter, pieces.piece_symbol(piece), target)

        # Frame
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(self.theme.border), 1))
        painter.drawRect(board_rect.adjusted(0.5, 0.5, -0.5, -0.5))
        painter.end()

    def _draw_piece(self, painter: QPainter, symbol: str, rect: QRectF) -> None:
        size = int(round(rect.width()))
        if size < 8:
            return
        dpr = max(1.0, float(self.devicePixelRatioF()))
        pixmap: QPixmap = pieces.piece_pixmap(symbol, int(round(size * dpr)))
        painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))

    def _draw_arrow(
        self,
        painter: QPainter,
        from_square: int,
        to_square: int,
        color: QColor,
        scale: float = 1.0,
    ) -> None:
        start = self.square_center(from_square)
        end = self.square_center(to_square)
        vec = QPointF(end.x() - start.x(), end.y() - start.y())
        length = math.hypot(vec.x(), vec.y())
        if length < 1.0:
            return
        unit = QPointF(vec.x() / length, vec.y() / length)
        begin = QPointF(
            start.x() + unit.x() * self._square * 0.18,
            start.y() + unit.y() * self._square * 0.18,
        )
        tip = QPointF(
            end.x() - unit.x() * self._square * 0.18,
            end.y() - unit.y() * self._square * 0.18,
        )
        shaft_end = QPointF(
            tip.x() - unit.x() * self._square * 0.34,
            tip.y() - unit.y() * self._square * 0.34,
        )
        width = max(3.0, self._square * 0.155 * scale)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(begin, shaft_end)

        half = width * 1.25
        perp = QPointF(-unit.y(), unit.x())
        polygon = QPolygonF(
            [
                tip,
                QPointF(shaft_end.x() + perp.x() * half, shaft_end.y() + perp.y() * half),
                QPointF(shaft_end.x() - perp.x() * half, shaft_end.y() - perp.y() * half),
            ]
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(polygon)

    def _draw_coordinates(self, painter: QPainter) -> None:
        font = mono_font(max(7.0, self._square * 0.125), 600)
        painter.setFont(font)
        for square in chess.SQUARES:
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            rect = self.square_rect(square)
            light = (file + rank) % 2 == 1
            color = QColor(self.theme.coord_on_light if light else self.theme.coord_on_dark)
            color.setAlpha(235)
            painter.setPen(color)

            show_file = (rank == 0) if self.orientation == chess.WHITE else (rank == 7)
            show_rank = (file == 0) if self.orientation == chess.WHITE else (file == 7)

            if show_file:
                painter.drawText(
                    rect.adjusted(4, 0, -4, -2),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom),
                    chess.square_name(square)[0],
                )
            if show_rank:
                painter.drawText(
                    rect.adjusted(4, 2, -4, 0),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                    str(rank + 1),
                )

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------
    def _is_own_piece(self, square: int) -> bool:
        piece = self.board.piece_at(square)
        return piece is not None and piece.color == self.board.turn

    def _targets_for(self, square: int) -> dict[int, chess.Move]:
        targets: dict[int, chess.Move] = {}
        for move in self.board.legal_moves:
            if move.from_square == square:
                targets.setdefault(move.to_square, move)
        return targets

    def _try_emit_move(self, from_square: int, to_square: int) -> bool:
        candidates = [
            move
            for move in self.board.legal_moves
            if move.from_square == from_square and move.to_square == to_square
        ]
        if not candidates:
            return False
        self.move_requested.emit(from_square, to_square)
        self.selected = None
        self.legal_targets.clear()
        self.update()
        return True

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        position = event.position()
        square = self.square_at(position)

        if event.button() == Qt.MouseButton.RightButton:
            self.clear_user_arrow()
            if square is not None:
                self._arrow_start = square
                self._arrow_end = square
            self.update()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        self._arrow_timer.stop()
        self._user_arrow = None
        self._press_pos = QPointF(position)

        if square is None or not self.interactive:
            self.selected = None
            self.legal_targets.clear()
            self.update()
            return

        if self.selected is not None and square in self.legal_targets:
            if self._try_emit_move(self.selected, square):
                return

        if self._is_own_piece(square):
            self.selected = square
            self.legal_targets = self._targets_for(square)
            self._drag_square = square
            self._drag_pos = QPointF(position)
            self._drag_active = False
            self.update()
        else:
            self.selected = None
            self.legal_targets.clear()
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        position = event.position()
        hover = self.square_at(position)
        if hover != self._hover_square:
            self._hover_square = hover
            if self.interactive and hover is not None and self._is_own_piece(hover):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

        if self._arrow_start is not None:
            if hover is not None:
                self._arrow_end = hover
                self.update()
            return

        if self._drag_square is not None:
            if not self._drag_active and self._press_pos is not None:
                if (
                    math.hypot(
                        position.x() - self._press_pos.x(),
                        position.y() - self._press_pos.y(),
                    )
                    >= DRAG_THRESHOLD
                ):
                    self._drag_active = True
            if self._drag_active:
                self._drag_pos = QPointF(position)
                self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        position = event.position()
        square = self.square_at(position)

        if event.button() == Qt.MouseButton.RightButton:
            if self._arrow_start is not None and self._arrow_end is not None:
                if self._arrow_start != self._arrow_end:
                    self._user_arrow = (self._arrow_start, self._arrow_end)
                    self._arrow_timer.start(1500)
            self._arrow_start = None
            self._arrow_end = None
            self.update()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._drag_square is not None and self._drag_active:
            origin = self._drag_square
            self._drag_active = False
            self._drag_pos = None
            self._drag_square = None
            self._press_pos = None
            if square is not None and square != origin:
                if self._try_emit_move(origin, square):
                    return
                piece = self.board.piece_at(origin)
                if piece is not None and piece.color == self.board.turn:
                    self.illegal_drop.emit(
                        f"{chess.square_name(origin)} to {chess.square_name(square)} is not legal."
                    )
            self.update()
            return

        self._drag_square = None
        self._press_pos = None
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape:
            self.selected = None
            self.legal_targets.clear()
            self._user_arrow = None
            self.update()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover_square = None
        super().leaveEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(640, 640)

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API
        return width
