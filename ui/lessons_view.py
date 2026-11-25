"""Interactive lessons page: curriculum list, lesson board and instructions."""

from __future__ import annotations

from typing import Optional

import chess
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lessons.curriculum import CATEGORIES, LESSONS, Lesson, category_counts, lesson_by_id
from .board_widget import BoardWidget, PromotionDialog
from .theme import (
    ACCENT,
    BORDER,
    DANGER,
    PANEL,
    PANEL_ALT,
    TEXT,
    TEXT_DIM,
    TEXT_MUTED,
    icon,
    mono_font,
    ui_font,
)


class LessonItem(QWidget):
    """One clickable row in the curriculum list."""

    clicked = Signal(str)

    def __init__(self, index: int, lesson: Lesson, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.lesson = lesson
        self.completed = False
        self.selected = False
        self.setObjectName("LessonItem")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self.number = QLabel(str(index))
        self.number.setFixedSize(24, 24)
        self.number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.number.setFont(mono_font(8.5, 700))
        layout.addWidget(self.number, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        self.title = QLabel(lesson.title)
        self.title.setFont(ui_font(9.5, 600))
        text_layout.addWidget(self.title)
        self.subtitle = QLabel(lesson.summary)
        self.subtitle.setWordWrap(True)
        self.subtitle.setFont(ui_font(8.0, 450))
        self.subtitle.setStyleSheet(f"color: {TEXT_MUTED};")
        text_layout.addWidget(self.subtitle)
        layout.addLayout(text_layout, 1)

        self.check = QLabel("")
        self.check.setFixedSize(16, 16)
        layout.addWidget(self.check, 0, Qt.AlignmentFlag.AlignTop)

        self._apply_style()

    def set_completed(self, completed: bool) -> None:
        self.completed = completed
        self.number.setText("")
        if completed:
            self.number.setPixmap(icon("check", ACCENT, 14).pixmap(14, 14))
        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._apply_style()

    def _apply_style(self) -> None:
        if self.selected:
            background = "#3E4A33"
            border = f"1px solid {ACCENT}"
        else:
            background = PANEL_ALT if self.completed else "#33312E"
            border = "1px solid transparent"
        color = TEXT if not self.completed else "#BFCBB2"
        self.title.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.setStyleSheet(
            f"#LessonItem {{ background-color: {background}; border: {border};"
            " border-radius: 8px; }"
            "#LessonItem:hover { background-color: #46433F; }"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.lesson.id)
        super().mousePressEvent(event)


class LessonsView(QWidget):
    """Full 'Learn' page."""

    lesson_completed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.lesson: Optional[Lesson] = None
        self.board = chess.Board()
        self.step_index = 0
        self.locked = False
        self.finished = False
        self.completed_ids: set[str] = set()
        self.wrong_squares: Optional[tuple[int, int]] = None
        self._items: dict[str, LessonItem] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(14)

        # -- curriculum list ------------------------------------------------
        list_card = QFrame()
        list_card.setObjectName("Card")
        list_card.setFixedWidth(292)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Lessons")
        title.setFont(ui_font(13, 700))
        header.addWidget(title)
        header.addStretch(1)
        self.progress_label = QLabel("0 / 12")
        self.progress_label.setObjectName("Badge")
        self.progress_label.setFont(mono_font(8.0, 700))
        header.addWidget(self.progress_label)
        list_layout.addLayout(header)

        subtitle = QLabel("Short, playable positions. Make the move on the board.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("Muted")
        subtitle.setFont(ui_font(8.5, 450))
        list_layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 4, 4, 4)
        host_layout.setSpacing(6)

        counts = category_counts()
        for category in CATEGORIES:
            group = QLabel(f"{category.upper()}  ·  {counts.get(category, 0)}")
            group.setObjectName("SectionTitle")
            group.setFont(ui_font(7.8, 700))
            group.setContentsMargins(2, 8, 0, 0)
            host_layout.addWidget(group)
            index = 1
            for lesson in LESSONS:
                if lesson.category != category:
                    continue
                item = LessonItem(index, lesson)
                item.clicked.connect(self.select_lesson)
                host_layout.addWidget(item)
                self._items[lesson.id] = item
                index += 1
        host_layout.addStretch(1)
        scroll.setWidget(host)
        list_layout.addWidget(scroll, 1)
        root.addWidget(list_card)

        # -- board column ---------------------------------------------------
        board_column = QWidget()
        board_layout = QVBoxLayout(board_column)
        board_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.setSpacing(10)

        board_header = QHBoxLayout()
        self.breadcrumb = QLabel("FUNDAMENTALS")
        self.breadcrumb.setObjectName("SectionTitle")
        self.breadcrumb.setFont(ui_font(8.0, 700))
        board_header.addWidget(self.breadcrumb)
        board_header.addStretch(1)
        self.lesson_counter = QLabel("")
        self.lesson_counter.setObjectName("Muted")
        self.lesson_counter.setFont(mono_font(8.5, 500))
        board_header.addWidget(self.lesson_counter)
        board_layout.addLayout(board_header)

        self.board_widget = BoardWidget()
        self.board_widget.setMinimumSize(380, 380)
        self.board_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.board_widget.move_requested.connect(self._on_move)
        board_layout.addWidget(self.board_widget, 1)

        goal_row = QFrame()
        goal_row.setStyleSheet(
            f"background-color: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;"
        )
        goal_layout = QHBoxLayout(goal_row)
        goal_layout.setContentsMargins(12, 9, 12, 9)
        goal_layout.setSpacing(10)
        goal_icon = QLabel()
        goal_icon.setPixmap(icon("target", ACCENT, 18).pixmap(18, 18))
        goal_layout.addWidget(goal_icon, 0, Qt.AlignmentFlag.AlignTop)
        self.goal_label = QLabel("Pick a lesson to begin.")
        self.goal_label.setWordWrap(True)
        self.goal_label.setFont(ui_font(9.2, 500))
        goal_layout.addWidget(self.goal_label, 1)
        board_layout.addWidget(goal_row)

        root.addWidget(board_column, 1)

        # -- instruction column ---------------------------------------------
        side = QWidget()
        side.setFixedWidth(312)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(10)

        title_card = QFrame()
        title_card.setObjectName("Card")
        title_layout = QVBoxLayout(title_card)
        title_layout.setContentsMargins(14, 12, 14, 12)
        title_layout.setSpacing(4)
        self.lesson_title = QLabel("Choose a lesson")
        self.lesson_title.setFont(ui_font(12, 700))
        self.lesson_title.setWordWrap(True)
        title_layout.addWidget(self.lesson_title)
        self.lesson_meta = QLabel("")
        self.lesson_meta.setObjectName("Muted")
        self.lesson_meta.setFont(ui_font(8.5, 450))
        title_layout.addWidget(self.lesson_meta)
        side_layout.addWidget(title_card)

        self.message = QLabel("Select a lesson from the list to start.")
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(58)
        self.message.setFont(ui_font(9.2, 450))
        self.message.setStyleSheet(self._message_style(PANEL, TEXT))
        side_layout.addWidget(self.message)

        steps_card = QFrame()
        steps_card.setObjectName("Card")
        steps_layout = QVBoxLayout(steps_card)
        steps_layout.setContentsMargins(14, 12, 14, 12)
        steps_layout.setSpacing(6)
        steps_header = QLabel("STEPS")
        steps_header.setObjectName("SectionTitle")
        steps_header.setFont(ui_font(8.0, 700))
        steps_layout.addWidget(steps_header)
        self.steps_host = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_host)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(6)
        steps_layout.addWidget(self.steps_host)
        steps_layout.addStretch(1)
        side_layout.addWidget(steps_card, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.hint_button = QPushButton(" Hint")
        self.hint_button.setIcon(icon("hint", TEXT, 16))
        self.hint_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hint_button.clicked.connect(self._show_hint)
        self.reset_button = QPushButton(" Reset")
        self.reset_button.setIcon(icon("undo", TEXT, 16))
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self._reset_lesson)
        buttons.addWidget(self.hint_button, 1)
        buttons.addWidget(self.reset_button, 1)
        side_layout.addLayout(buttons)

        self.next_button = QPushButton("Next Lesson")
        self.next_button.setObjectName("primary")
        self.next_button.setIcon(icon("chevron-right", "#17240C", 16))
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.clicked.connect(self._next_lesson)
        side_layout.addWidget(self.next_button)

        root.addWidget(side)

        if LESSONS:
            self.select_lesson(LESSONS[0].id)

    # ------------------------------------------------------------------
    def set_completed_ids(self, ids: set[str]) -> None:
        self.completed_ids = set(ids)
        for lesson_id, item in self._items.items():
            item.set_completed(lesson_id in self.completed_ids)
        self._refresh_progress()

    def _refresh_progress(self) -> None:
        self.progress_label.setText(f"{len(self.completed_ids)} / {len(LESSONS)}")

    def _message_style(self, background: str, color: str) -> str:
        return (
            f"background-color: {background}; border: 1px solid {BORDER};"
            f" border-radius: 9px; padding: 10px; color: {color};"
        )

    def _set_message(self, text: str, tone: str = "neutral") -> None:
        palette = {
            "neutral": (PANEL, TEXT),
            "ok": ("#2F3B25", "#D8E8C6"),
            "bad": ("#3E2422", "#F0D3CF"),
            "info": ("#22303B", "#CFE2F1"),
        }
        background, color = palette.get(tone, palette["neutral"])
        self.message.setText(text)
        self.message.setStyleSheet(self._message_style(background, color))

    # ------------------------------------------------------------------
    def select_lesson(self, lesson_id: str) -> None:
        lesson = lesson_by_id(lesson_id)
        if lesson is None:
            return
        self.lesson = lesson
        self.board = lesson.start_board
        self.step_index = 0
        self.locked = False
        self.finished = False
        self.board_widget.set_wrong_move(None)
        self.board_widget.set_coach_arrow(None)
        self.wrong_squares = None

        for key, item in self._items.items():
            item.set_selected(key == lesson_id)

        self.breadcrumb.setText(lesson.category.upper())
        index = LESSONS.index(lesson) + 1
        self.lesson_counter.setText(f"Lesson {index} of {len(LESSONS)}")
        self.lesson_title.setText(lesson.title)
        tags = " · ".join(lesson.tags)
        self.lesson_meta.setText(f"{lesson.minutes} min · {lesson.move_count} step(s) · {tags}")
        self.goal_label.setText(lesson.goal)
        self.next_button.setEnabled(True)
        self._set_message("Your move. Play it directly on the board.", "info")
        self._build_steps()
        self._refresh_board()

    def _build_steps(self) -> None:
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if self.lesson is None:
            return
        for index, step in enumerate(self.lesson.steps):
            if index < self.step_index:
                marker = "✓"
                color = ACCENT
                text_color = TEXT_MUTED
            elif index == self.step_index:
                marker = "›"
                color = TEXT
                text_color = TEXT
            else:
                marker = "·"
                color = TEXT_DIM
                text_color = TEXT_DIM
            label = QLabel(f"{marker}  {step.hint}")
            label.setWordWrap(True)
            label.setFont(ui_font(8.8, 600 if index == self.step_index else 450))
            label.setStyleSheet(f"color: {text_color if index != self.step_index else color};")
            self.steps_layout.addWidget(label)

    def _refresh_board(self, last_move: Optional[chess.Move] = None) -> None:
        interactive = (
            self.lesson is not None
            and not self.finished
            and not self.locked
            and not self.board.is_game_over()
        )
        self.board_widget.set_position(self.board, last_move=last_move, interactive=interactive)
        self.board_widget.set_orientation(chess.WHITE)

    # ------------------------------------------------------------------
    def _on_move(self, from_square: int, to_square: int) -> None:
        if self.lesson is None or self.locked or self.finished:
            self._refresh_board()
            return
        candidates = [
            move
            for move in self.board.legal_moves
            if move.from_square == from_square and move.to_square == to_square
        ]
        if not candidates:
            self._refresh_board()
            return

        move = candidates[0]
        if len({candidate.promotion for candidate in candidates}) > 1:
            choice = PromotionDialog.ask(self.board.turn, self.window())
            if choice is None:
                self._refresh_board()
                return
            move = next(
                (candidate for candidate in candidates if candidate.promotion == choice),
                candidates[0],
            )

        step = self.lesson.steps[self.step_index]
        accepted = [candidate for candidate in candidates if candidate.uci() in step.moves]

        if accepted:
            self.board.push(accepted[0])
            self.step_index += 1
            self.board_widget.set_coach_arrow(None)
            self._set_message(step.success or "Correct!", "ok")
            self._build_steps()
            self._refresh_board(last_move=accepted[0])
            if step.reply:
                self.locked = True
                self._refresh_board(last_move=accepted[0])
                QTimer.singleShot(520, lambda reply=step.reply: self._play_reply(reply))
            else:
                self._check_complete()
            return

        # Legal but not the expected move: flash it, explain, then roll back.
        self.board.push(move)
        self.wrong_squares = (from_square, to_square)
        self.board_widget.set_coach_arrow(None)
        self.board_widget.set_wrong_move(self.wrong_squares)
        self._refresh_board(last_move=move)
        self._set_message(f"Not quite. {step.hint}", "bad")
        self.locked = True
        QTimer.singleShot(1250, self._undo_wrong)

    def _play_reply(self, uci: str) -> None:
        if self.lesson is None:
            return
        try:
            reply = chess.Move.from_uci(uci)
        except ValueError:
            reply = None
        if reply is not None and reply in self.board.legal_moves:
            self.board.push(reply)
        self.locked = False
        self._refresh_board(last_move=reply)
        self._check_complete()

    def _undo_wrong(self) -> None:
        if not self.locked:
            return
        if self.board.move_stack:
            try:
                self.board.pop()
            except IndexError:
                pass
        self.board_widget.set_wrong_move(None)
        self.wrong_squares = None
        self.locked = False
        if self.lesson is not None and not self.finished:
            step = self.lesson.steps[self.step_index]
            self._set_message(f"Try again. {step.hint}", "info")
        self._refresh_board(last_move=self.board.peek() if self.board.move_stack else None)

    def _check_complete(self) -> None:
        if self.lesson is None:
            return
        if self.step_index < len(self.lesson.steps):
            self._refresh_board()
            return
        self.finished = True
        self.locked = False
        if self.lesson.id not in self.completed_ids:
            self.completed_ids.add(self.lesson.id)
            self.lesson_completed.emit(self.lesson.id)
        item = self._items.get(self.lesson.id)
        if item is not None:
            item.set_completed(True)
        self._refresh_progress()
        self.board_widget.set_wrong_move(None)
        board = self.board
        suffix = ""
        if board.is_checkmate():
            suffix = " Checkmate — exactly right."
        elif board.is_game_over():
            suffix = f" The position is finished ({board.result()})."
        self._set_message(f"Lesson complete! {self.lesson.finish}{suffix}", "ok")
        self._refresh_board(last_move=board.peek() if board.move_stack else None)
        self.board_widget.set_coach_arrow(None)

    def _show_hint(self) -> None:
        if self.lesson is None or self.finished:
            return
        step = self.lesson.steps[self.step_index]
        self._set_message(f"Hint: {step.hint}", "info")
        try:
            move = chess.Move.from_uci(step.moves[0])
        except ValueError:
            move = None
        if move is not None and move in self.board.legal_moves:
            self.board_widget.set_coach_arrow(move)

    def _reset_lesson(self) -> None:
        if self.lesson is None:
            return
        self.select_lesson(self.lesson.id)

    def _next_lesson(self) -> None:
        if self.lesson is None:
            return
        index = LESSONS.index(self.lesson)
        if index + 1 < len(LESSONS):
            self.select_lesson(LESSONS[index + 1].id)
        else:
            self.select_lesson(LESSONS[0].id)
