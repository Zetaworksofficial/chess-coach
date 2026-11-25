"""Main window: navigation rail, Play page, Learn page and Settings."""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

import chess
from PySide6.QtCore import QSize, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from engine import coach as coach_engine
from engine.ai_manager import AIManager, find_stockfish, level_summary
from engine.fallback_engine import PIECE_VALUES
from lessons.curriculum import LESSONS
from .board_widget import BoardStage, BoardWidget
from .eval_bar import EvalBar
from .lessons_view import LessonsView
from .player_bar import PlayerBar
from .sidebar import SegmentedControl, Sidebar, ToggleSwitch
from .theme import (
    ACCENT,
    BG,
    BOARD_THEMES,
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

SIDE_CHOICES = ("White", "Black", "Random")
TIME_CHOICES = ("Untimed", "3+2 Blitz", "10+0 Rapid")


def format_clock(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds >= 20.0:
        minutes = int(seconds // 60)
        rest = int(seconds % 60)
        return f"{minutes}:{rest:02d}"
    return f"{seconds:.1f}"


def _symbol_value(symbol: str) -> int:
    piece_type = chess.PIECE_SYMBOLS.index(symbol[1].lower())
    return PIECE_VALUES.get(piece_type, 0)


def captured_material(board: chess.Board) -> tuple[list[str], list[str], int, int]:
    """Return (black pieces taken by white, white pieces taken by black, adv_w, adv_b)."""
    initial = {
        chess.PAWN: 8,
        chess.KNIGHT: 2,
        chess.BISHOP: 2,
        chess.ROOK: 2,
        chess.QUEEN: 1,
    }
    order = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    white_taken: list[str] = []
    black_taken: list[str] = []
    for piece_type in order:
        letter = chess.piece_symbol(piece_type).upper()
        white_count = len(board.pieces(piece_type, chess.WHITE))
        black_count = len(board.pieces(piece_type, chess.BLACK))
        white_taken.extend(["b" + letter] * max(0, initial[piece_type] - black_count))
        black_taken.extend(["w" + letter] * max(0, initial[piece_type] - white_count))

    white_value = sum(_symbol_value(symbol) for symbol in white_taken)
    black_value = sum(_symbol_value(symbol) for symbol in black_taken)
    diff = int(round((white_value - black_value) / 100.0))
    return white_taken, black_taken, max(0, diff), max(0, -diff)


def theme_swatch(name: str, width: int = 44, height: int = 26) -> QIcon:
    theme = BOARD_THEMES.get(name, BOARD_THEMES["Classic Green"])
    pixmap = QPixmap(width * 2, height * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    size = width * 2 / 4
    for row in range(4):
        for col in range(4):
            color = QColor(theme.light if (row + col) % 2 == 0 else theme.dark)
            painter.fillRect(
                int(col * size), int(row * size), int(size) + 1, int(size) + 1, color
            )
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    """The single application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess Coach")
        self.setMinimumSize(1180, 820)
        self.resize(1380, 920)
        self.setObjectName("Root")

        self.store = QSettings("ChessCoach", "ChessCoach")
        board_theme = str(self.store.value("board_theme", "Classic Green"))
        if board_theme not in BOARD_THEMES:
            board_theme = "Classic Green"
        self.board_theme_name = board_theme
        self.stockfish_path = str(self.store.value("stockfish_path", "") or "")
        self.coach_default = str(self.store.value("coach", "true")).lower() == "true"
        self.eval_visible = str(self.store.value("eval", "true")).lower() == "true"
        self.ai_level = int(self.store.value("level", 40) or 40)
        completed = self.store.value("completed_lessons", [])
        if isinstance(completed, str):
            completed = [completed] if completed else []
        self.completed_lessons: set[str] = set(completed or [])

        # Game state
        self.board = chess.Board()
        self.human_color = chess.WHITE
        self.ai_color = chess.BLACK
        self.time_control = "Untimed"
        self.coach_enabled = self.coach_default
        self.game_active = False
        self.thinking = False
        self.view_ply: Optional[int] = None
        self.history: list[dict] = []
        self.result_text = ""
        self.result_tone = "normal"
        self._generation = 0
        self._initial_fen = chess.STARTING_FEN
        self.clocks: Optional[dict[bool, float]] = None
        self.increment = 0
        self._clock_last = time.monotonic()
        self.engine_name = "Built-in engine"
        self._coach_arrow: Optional[chess.Move] = None
        self._ai_level_live = self.ai_level
        self._ai_triggered = True
        self._coach_pending = False

        self.ai = AIManager(self)
        self.ai.engine_status.connect(self._on_engine_status)

        self._build_ui()
        self._connect()
        self._restore_settings()
        self._update_engine_status("Detecting Stockfish…")
        self.ai.set_stockfish_path(find_stockfish(self.stockfish_path))
        self._start_new_game({"level": self.ai_level, "side": "White", "time": "Untimed"})
        QTimer.singleShot(120, lambda: self.ai.probe(self._on_probe))

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(200)
        self._clock_timer.timeout.connect(self._tick_clocks)
        self._clock_timer.start()

    # ==================================================================
    # UI construction
    # ==================================================================
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_rail())

        self.pages = QStackedWidget()
        self.play_page = self._build_play_page()
        self.lessons_view = LessonsView()
        self.settings_page = self._build_settings_page()
        self.pages.addWidget(self.play_page)
        self.pages.addWidget(self.lessons_view)
        self.pages.addWidget(self.settings_page)
        layout.addWidget(self.pages, 1)

    def _build_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(92)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(0, 14, 0, 14)
        layout.setSpacing(4)

        logo = QLabel()
        logo.setPixmap(icon("knight", ACCENT, 30).pixmap(30, 30))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setToolTip("Chess Coach")
        layout.addWidget(logo)
        layout.addSpacing(8)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QToolButton] = []
        entries = (
            ("Play", "play"),
            ("Learn", "learn"),
            ("Settings", "settings"),
        )
        for index, (label, icon_name) in enumerate(entries):
            button = QToolButton()
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIcon(icon(icon_name, TEXT_MUTED, 22))
            button.setIconSize(QSize(22, 22))
            button.setFixedSize(92, 66)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("iconName", icon_name)
            button.setToolTip(f"{label}  ·  Ctrl+{index + 1}")
            if index == 0:
                button.setChecked(True)
                button.setIcon(icon(icon_name, ACCENT, 22))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)

        self.rail_engine_dot = QLabel("●")
        self.rail_engine_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rail_engine_dot.setToolTip("Engine status")
        self.rail_engine_dot.setStyleSheet(f"color: {TEXT_DIM};")
        layout.addWidget(self.rail_engine_dot)

        version = QLabel("v1.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setFont(mono_font(7.5, 500))
        version.setStyleSheet(f"color: {TEXT_DIM};")
        layout.addWidget(version)
        return rail

    def _build_play_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(20, 16, 0, 16)
        layout.setSpacing(16)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        self.top_bar = PlayerBar()
        self.bottom_bar = PlayerBar()
        self.eval_bar = EvalBar()
        self.board_widget = BoardWidget()
        self.board_widget.set_theme(self.board_theme_name)
        self.stage = BoardStage(
            self.board_widget, self.eval_bar, self.top_bar, self.bottom_bar
        )
        center_layout.addWidget(self.stage, 1)

        layout.addWidget(center, 1)

        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar, 0)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(32, 22, 32, 22)
        outer.setSpacing(14)

        title = QLabel("Settings")
        title.setFont(ui_font(18, 700))
        outer.addWidget(title)
        subtitle = QLabel("Board look, engine and coaching defaults.")
        subtitle.setObjectName("Muted")
        subtitle.setFont(ui_font(9.5, 450))
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 4, 12, 12)
        host_layout.setSpacing(14)

        # -- board theme ----------------------------------------------------
        theme_card, theme_layout = self._settings_card("Board theme", "Pick the colours you like to look at.")
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(8)
        self.theme_buttons: dict[str, QPushButton] = {}
        for name in BOARD_THEMES:
            button = QPushButton(f" {name}")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(theme_swatch(name))
            button.setIconSize(QSize(44, 26))
            button.setMinimumHeight(44)
            button.setStyleSheet(
                "QPushButton { text-align: left; padding: 6px 10px; border-radius: 8px;"
                f" border: 1px solid {BORDER}; background-color: {PANEL_ALT}; }}"
                f"QPushButton:checked {{ border: 1px solid {ACCENT}; background-color: #3E4A33; }}"
            )
            button.clicked.connect(lambda _checked=False, value=name: self._set_board_theme(value))
            swatch_row.addWidget(button, 1)
            self.theme_buttons[name] = button
        theme_layout.addLayout(swatch_row)
        host_layout.addWidget(theme_card)

        # -- engine ---------------------------------------------------------
        engine_card, engine_layout = self._settings_card(
            "Engine",
            "Stockfish is detected automatically from PATH. Point to a binary here if yours lives elsewhere.",
        )
        self.engine_status_label = QLabel("Detecting…")
        self.engine_status_label.setFont(ui_font(9.5, 600))
        self.engine_status_label.setStyleSheet(f"color: {TEXT};")
        engine_layout.addWidget(self.engine_status_label)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.engine_path_edit = QLineEdit()
        self.engine_path_edit.setPlaceholderText("Auto-detected — or browse to a Stockfish binary")
        path_row.addWidget(self.engine_path_edit, 1)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_stockfish)
        path_row.addWidget(browse_button)
        detect_button = QPushButton("Auto-detect")
        detect_button.clicked.connect(self._autodetect_stockfish)
        path_row.addWidget(detect_button)
        engine_layout.addLayout(path_row)

        hint = QLabel(
            "No Stockfish? No problem — the bundled engine runs pure Python and needs no install."
        )
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        hint.setFont(ui_font(8.5, 450))
        engine_layout.addWidget(hint)
        host_layout.addWidget(engine_card)

        # -- gameplay -------------------------------------------------------
        play_card, play_layout = self._settings_card("Gameplay", "Defaults applied to new games.")
        eval_row = self._toggle_row(
            "Show evaluation bar",
            "Animated +/− score next to the board.",
        )
        self.eval_toggle = eval_row[0]
        play_layout.addLayout(eval_row[1])

        coach_row = self._toggle_row(
            "Coach mode by default",
            "Reviews your moves and draws the better idea.",
        )
        self.coach_default_toggle = coach_row[0]
        play_layout.addLayout(coach_row[1])
        host_layout.addWidget(play_card)

        # -- about ----------------------------------------------------------
        about_card, about_layout = self._settings_card("About", "Chess Coach 1.0")
        about = QLabel(
            "A desktop chess trainer built with PySide6 and python-chess. "
            f"{len(LESSONS)} interactive lessons cover the fundamentals, tactics and basic mates. "
            "All rules — castling, en passant, promotion, repetition and the fifty-move rule — "
            "come from python-chess."
        )
        about.setWordWrap(True)
        about.setObjectName("Muted")
        about.setFont(ui_font(9.0, 450))
        about_layout.addWidget(about)
        host_layout.addWidget(about_card)
        host_layout.addStretch(1)

        scroll.setWidget(host)
        outer.addWidget(scroll, 1)
        return page

    def _settings_card(self, title: str, description: str):
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setFont(ui_font(11.5, 700))
        layout.addWidget(heading)
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setObjectName("Muted")
        description_label.setFont(ui_font(8.8, 450))
        layout.addWidget(description_label)
        card.setMaximumWidth(820)
        return card, layout

    def _toggle_row(self, title: str, subtitle: str):
        row = QHBoxLayout()
        row.setSpacing(10)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        label = QLabel(title)
        label.setFont(ui_font(9.5, 600))
        text_col.addWidget(label)
        sub = QLabel(subtitle)
        sub.setObjectName("Muted")
        sub.setFont(ui_font(8.5, 450))
        text_col.addWidget(sub)
        row.addLayout(text_col, 1)
        switch = ToggleSwitch(True)
        row.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
        return switch, row

    # ==================================================================
    # Signals
    # ==================================================================
    def _connect(self) -> None:
        self.nav_group.idClicked.connect(self._on_nav)
        self.board_widget.move_requested.connect(self._on_board_move)
        self.board_widget.illegal_drop.connect(lambda _msg: None)

        self.sidebar.new_game_requested.connect(self._start_new_game)
        self.sidebar.level_changed.connect(self._on_level_changed)
        self.sidebar.coach_toggled.connect(self._on_coach_toggled)
        self.sidebar.hint_requested.connect(self._on_hint)
        self.sidebar.takeback_requested.connect(self._on_takeback)
        self.sidebar.flip_requested.connect(self._on_flip)
        self.sidebar.resign_requested.connect(self._on_resign)
        self.sidebar.move_selected.connect(self._on_move_selected)
        self.sidebar.live_requested.connect(self._on_live)

        self.lessons_view.lesson_completed.connect(self._on_lesson_completed)
        self.lessons_view.set_completed_ids(self.completed_lessons)

        self.engine_path_edit.editingFinished.connect(
            lambda: self._apply_engine_path(self.engine_path_edit.text().strip())
        )

    def _restore_settings(self) -> None:
        self.sidebar.set_coach_enabled(self.coach_default)
        self.sidebar.set_level(self.ai_level)
        for name, button in self.theme_buttons.items():
            button.setChecked(name == self.board_theme_name)
        self.eval_toggle.set_checked(self.eval_visible)
        self.coach_default_toggle.set_checked(self.coach_default)
        self.engine_path_edit.setText(self.stockfish_path)
        self.stage.set_eval_visible(self.eval_visible)
        self.eval_toggle.toggled.connect(self._on_eval_toggled)
        self.coach_default_toggle.toggled.connect(self._on_coach_default_toggled)

    # ==================================================================
    # Navigation & settings
    # ==================================================================
    def _on_nav(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for position, button in enumerate(self.nav_buttons):
            icon_name = str(button.property("iconName"))
            color = ACCENT if position == index else TEXT_MUTED
            button.setIcon(icon(icon_name, color, 22))

    def _set_board_theme(self, name: str) -> None:
        self.board_theme_name = name
        self.store.setValue("board_theme", name)
        for key, button in self.theme_buttons.items():
            button.setChecked(key == name)
        self.board_widget.set_theme(name)

    def _on_eval_toggled(self, enabled: bool) -> None:
        self.eval_visible = bool(enabled)
        self.store.setValue("eval", "true" if enabled else "false")
        self.stage.set_eval_visible(self.eval_visible)

    def _on_coach_default_toggled(self, enabled: bool) -> None:
        self.coach_default = bool(enabled)
        self.store.setValue("coach", "true" if enabled else "false")

    def _browse_stockfish(self) -> None:
        start = str(Path.home())
        path, _selected = QFileDialog.getOpenFileName(
            self, "Select the Stockfish binary", start, "All files (*)"
        )
        if path:
            self.engine_path_edit.setText(path)
            self._apply_engine_path(path)

    def _autodetect_stockfish(self) -> None:
        found = find_stockfish(self.stockfish_path)
        if not found:
            found = find_stockfish()
        if found:
            self.engine_path_edit.setText(found)
            self._apply_engine_path(found)
        else:
            self.engine_path_edit.setText("")
            self._apply_engine_path("")
            self._update_engine_status(
                "Stockfish not found — the bundled Python engine is playing instead."
            )

    def _apply_engine_path(self, path: str) -> None:
        resolved = find_stockfish(path) if path else find_stockfish()
        if path and not resolved:
            resolved = path
        self.stockfish_path = resolved or ""
        self.store.setValue("stockfish_path", self.stockfish_path)
        self.ai.set_stockfish_path(self.stockfish_path)
        self.engine_path_edit.setText(self.stockfish_path)
        self._update_engine_status("Testing engine…")
        self.ai.probe(self._on_probe)

    def _on_probe(self, data: dict) -> None:
        name = data.get("engine") or "Built-in engine"
        self.engine_name = name
        self.sidebar.set_engine_label(name)
        if data.get("stockfish"):
            self._update_engine_status(f"Using {name}.")
            self.rail_engine_dot.setStyleSheet(f"color: {ACCENT};")
            self.rail_engine_dot.setToolTip(f"{name} is ready")
        else:
            self._update_engine_status(
                "Using the built-in engine. Install Stockfish for stronger opponents."
            )
            self.rail_engine_dot.setStyleSheet(f"color: #C9A227;")
            self.rail_engine_dot.setToolTip("Built-in engine active")

    def _on_engine_status(self, text: str) -> None:
        self.engine_name = text
        self.sidebar.set_engine_label(text)
        self._update_engine_status(text)

    def _update_engine_status(self, text: str) -> None:
        if hasattr(self, "engine_status_label"):
            self.engine_status_label.setText(text)

    # ==================================================================
    # Game lifecycle
    # ==================================================================
    def _start_new_game(self, config: dict) -> None:
        level = int(config.get("level", self.ai_level))
        side = config.get("side", "White")
        time_control = config.get("time", "Untimed")

        self.ai_level = max(1, min(100, level))
        self._ai_level_live = self.ai_level
        self.store.setValue("level", self.ai_level)
        self.sidebar.set_level(self.ai_level)

        if side == "Random":
            human = random.choice([chess.WHITE, chess.BLACK])
        elif side == "Black":
            human = chess.BLACK
        else:
            human = chess.WHITE
        self.human_color = human
        self.ai_color = not human

        self.board = chess.Board()
        self._initial_fen = chess.STARTING_FEN
        self.history = []
        self.view_ply = None
        self.result_text = ""
        self.result_tone = "normal"
        self.thinking = False
        self.game_active = True
        self.time_control = time_control
        self._coach_arrow = None
        self._ai_triggered = True
        self._coach_pending = False
        self._generation += 1
        self._configure_clocks(time_control)
        self._clock_last = time.monotonic()

        self.board_widget.set_orientation(self.human_color)
        self.board_widget.set_coach_arrow(None)
        self.sidebar.clear_coach()
        self.sidebar.set_moves([], None)
        self.eval_bar.reset()
        self.sidebar.coach_idle()
        self._refresh_all()

        self._request_eval()
        if self.board.turn == self.ai_color:
            self._schedule_ai_move(450)

    def _configure_clocks(self, time_control: str) -> None:
        if time_control == "3+2 Blitz":
            self.clocks = {chess.WHITE: 180.0, chess.BLACK: 180.0}
            self.increment = 2
        elif time_control == "10+0 Rapid":
            self.clocks = {chess.WHITE: 600.0, chess.BLACK: 600.0}
            self.increment = 0
        else:
            self.clocks = None
            self.increment = 0

    # -- moves ----------------------------------------------------------
    def _on_board_move(self, from_square: int, to_square: int) -> None:
        if not self.game_active or self.thinking:
            return
        if self.board.turn != self.human_color:
            return
        if self.view_ply is not None:
            self.view_ply = None

        candidates = [
            move
            for move in self.board.legal_moves
            if move.from_square == from_square and move.to_square == to_square
        ]
        if not candidates:
            self._refresh_all()
            return

        move = candidates[0]
        if len({candidate.promotion for candidate in candidates}) > 1:
            from .board_widget import PromotionDialog

            choice = PromotionDialog.ask(self.human_color, self)
            if choice is None:
                self._refresh_all()
                return
            move = next(
                (candidate for candidate in candidates if candidate.promotion == choice),
                candidates[0],
            )

        self._make_human_move(move)

    def _make_human_move(self, move: chess.Move) -> None:
        if move not in self.board.legal_moves:
            return
        fen_before = self.board.fen()
        self._push_move(move, by_human=True)
        self._ai_triggered = False

        if not self.game_active:
            return

        generation = self._generation
        if self.coach_enabled:
            self._coach_pending = True
            self.sidebar.coach_thinking()
            self.ai.request_coach(
                fen_before,
                move.uci(),
                lambda data, gen=generation, fen=fen_before, mv=move: self._on_coach(
                    data, gen, fen, mv
                ),
            )
            # Safety net: never leave the game hanging if a review is lost.
            QTimer.singleShot(9000, lambda gen=generation: self._trigger_ai_move(gen))
        else:
            self._trigger_ai_move(generation)
        self._refresh_all()

    def _trigger_ai_move(self, generation: int) -> None:
        if generation != self._generation or self._ai_triggered:
            return
        self._ai_triggered = True
        self._coach_pending = False
        if self.game_active and self.board.turn == self.ai_color:
            self._schedule_ai_move(240)
        else:
            self._refresh_all()

    def _push_move(self, move: chess.Move, by_human: bool) -> None:
        color = self.board.turn
        try:
            san = self.board.san(move)
        except Exception:
            san = move.uci()
        fen_before = self.board.fen()
        try:
            self.board.push(move)
        except Exception:
            return
        entry = {
            "san": san,
            "uci": move.uci(),
            "move": move,
            "color": color,
            "fen_before": fen_before,
            "fen_after": self.board.fen(),
            "by_human": by_human,
        }
        self.history.append(entry)
        self.view_ply = None
        if self.clocks is not None:
            self.clocks[color] = self.clocks.get(color, 0.0) + self.increment
        self._coach_arrow = None
        self.thinking = False
        self._check_game_over()
        self._refresh_all()

    def _schedule_ai_move(self, delay_ms: int) -> None:
        if not self.game_active or self.board.turn != self.ai_color:
            return
        self.thinking = True
        self._refresh_all()
        generation = self._generation
        QTimer.singleShot(delay_ms, lambda: self._request_ai_move(generation))

    def _request_ai_move(self, generation: int) -> None:
        if generation != self._generation:
            return
        if not self.game_active or self.board.turn != self.ai_color:
            self.thinking = False
            self._refresh_all()
            return
        fen = self.board.fen()
        self.ai.request_move(
            fen,
            self._ai_level_live,
            lambda data, gen=generation: self._on_ai_move(data, gen),
        )

    def _on_ai_move(self, data: dict, generation: int) -> None:
        if generation != self._generation:
            return
        self.thinking = False
        if not self.game_active:
            self._refresh_all()
            return

        move: Optional[chess.Move] = None
        uci = data.get("uci")
        if uci:
            try:
                candidate = chess.Move.from_uci(uci)
                if candidate in self.board.legal_moves:
                    move = candidate
            except ValueError:
                move = None
        if move is None:
            legal = list(self.board.legal_moves)
            move = random.choice(legal) if legal else None

        if move is not None:
            self._push_move(move, by_human=False)
            if data.get("engine"):
                self.engine_name = str(data["engine"])
            if self.game_active:
                self._request_eval()

    def _on_coach(
        self,
        data: dict,
        generation: int,
        fen_before: str,
        move: chess.Move,
    ) -> None:
        if generation != self._generation:
            return
        try:
            self._show_coach_verdict(data, generation, fen_before, move)
        finally:
            self._coach_pending = False
            self._trigger_ai_move(generation)

    def _show_coach_verdict(
        self,
        data: dict,
        generation: int,
        fen_before: str,
        move: chess.Move,
    ) -> None:
        if data.get("error") or not data.get("best_uci"):
            self.sidebar.coach_error("The engine could not review that move.")
            return
        verdict = coach_engine.review_move(
            fen_before,
            move,
            str(data.get("best_uci")),
            int(data.get("white_cp_before", 0)),
            int(data.get("white_cp_after_user", 0)),
            int(data.get("white_cp_after_best", 0)),
            str(data.get("engine", "")),
        )
        note = f"Reviewed by {verdict.engine}" if verdict.engine else ""
        self.sidebar.show_verdict(verdict.label, verdict.color, verdict.explanation, note)

        if verdict.label in ("Inaccuracy", "Mistake", "Blunder") and verdict.best_move:
            board_after = chess.Board(fen_before)
            if move in board_after.legal_moves:
                board_after.push(move)
            if board_after.fen() == self.board.fen():
                self._coach_arrow = verdict.best_move
                self.board_widget.set_coach_arrow(verdict.best_move)

    # -- actions --------------------------------------------------------
    def _on_hint(self) -> None:
        if not self.game_active or self.thinking:
            return
        if self.board.turn != self.human_color:
            return
        self.sidebar.coach_hint_pending()
        generation = self._generation
        fen = self.board.fen()
        self.ai.request_hint(
            fen, lambda data, gen=generation: self._on_hint_result(data, gen)
        )

    def _on_hint_result(self, data: dict, generation: int) -> None:
        if generation != self._generation:
            return
        uci = data.get("uci")
        move: Optional[chess.Move] = None
        if uci:
            try:
                candidate = chess.Move.from_uci(uci)
                if candidate in self.board.legal_moves:
                    move = candidate
            except ValueError:
                move = None
        if move is None:
            self.sidebar.coach_error("No hint available in this position.")
            return
        text = coach_engine.describe_move(self.board, move)
        self.sidebar.show_hint(text)
        self._coach_arrow = move
        self.board_widget.set_coach_arrow(move)

    def _on_takeback(self) -> None:
        if self.thinking or not self.history:
            return
        self._generation += 1
        self.thinking = False
        self._ai_triggered = True
        self._coach_pending = False
        self.view_ply = None
        popped = 0
        while self.history and popped < 2:
            try:
                self.board.pop()
            except IndexError:
                break
            self.history.pop()
            popped += 1
            if self.board.turn == self.human_color:
                break
        self.game_active = True
        self.result_text = ""
        self.result_tone = "normal"
        self._coach_arrow = None
        self.board_widget.set_coach_arrow(None)
        self.sidebar.clear_coach()
        self.sidebar.set_moves([], None)
        self._refresh_all()
        self._request_eval()
        if self.board.turn == self.ai_color:
            self._schedule_ai_move(350)

    def _on_flip(self) -> None:
        self.board_widget.flip()
        self.eval_bar.set_flipped(self.board_widget.orientation == chess.BLACK)

    def _on_resign(self) -> None:
        if not self.game_active:
            return
        answer = QMessageBox.question(
            self,
            "Resign game",
            "Resign this game? The result will stand.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._generation += 1
        self.thinking = False
        self._ai_triggered = True
        self._coach_pending = False
        self.game_active = False
        self.result_text = "You resigned — engine wins."
        self.result_tone = "bad"
        self.sidebar.set_status(self.result_text, "bad")
        self._refresh_all()

    def _on_move_selected(self, ply: int) -> None:
        total = len(self.history)
        if ply <= 0:
            self.view_ply = 0 if total else None
        elif ply >= total:
            self.view_ply = None
        else:
            self.view_ply = ply
        self._refresh_all()

    def _on_live(self) -> None:
        self.view_ply = None
        self._refresh_all()

    def _on_level_changed(self, level: int) -> None:
        self._ai_level_live = int(level)
        self.ai_level = int(level)
        self.store.setValue("level", self.ai_level)
        self.sidebar.set_level(self.ai_level)
        self._refresh_players()

    def _on_coach_toggled(self, enabled: bool) -> None:
        self.coach_enabled = bool(enabled)
        if not enabled:
            self.sidebar.coach_idle("Coach mode is off. Turn it on to get move reviews.")
            self._coach_arrow = None
            self.board_widget.set_coach_arrow(None)
        else:
            self.sidebar.coach_idle("Coach mode on — make a move and I will review it.")

    def _on_lesson_completed(self, lesson_id: str) -> None:
        self.completed_lessons.add(lesson_id)
        self.store.setValue("completed_lessons", sorted(self.completed_lessons))
        self.sidebar.set_status("Lesson complete — nice work.", "good")

    # ==================================================================
    # Engine evaluation & clocks
    # ==================================================================
    def _request_eval(self) -> None:
        if not self.game_active:
            return
        generation = self._generation
        self.ai.request_analysis(
            self.board.fen(),
            lambda data, gen=generation: self._on_eval(data, gen),
        )

    def _on_eval(self, data: dict, generation: int) -> None:
        if generation != self._generation:
            return
        if data.get("error"):
            return
        mate = data.get("mate")
        self.eval_bar.set_eval(int(data.get("white_cp", 0)), mate if mate is not None else None)

    def _tick_clocks(self) -> None:
        now = time.monotonic()
        delta = now - self._clock_last
        self._clock_last = now
        if self.clocks is None or not self.game_active:
            return
        if self.board.is_game_over(claim_draw=True):
            return
        side = self.board.turn
        self.clocks[side] = max(0.0, self.clocks[side] - delta)
        if self.clocks[side] <= 0.0:
            self.game_active = False
            winner_is_human = side != self.human_color
            self.result_text = (
                "Time out — you win on time!"
                if winner_is_human
                else "Time out — the engine wins on time."
            )
            self.result_tone = "good" if winner_is_human else "bad"
            self._refresh_all()
            return
        self._refresh_clocks()

    # ==================================================================
    # Rendering
    # ==================================================================
    def _fen_at(self, ply: int) -> str:
        if ply <= 0:
            return self._initial_fen
        index = min(ply, len(self.history)) - 1
        return self.history[index]["fen_after"]

    def _refresh_all(self) -> None:
        self._refresh_board()
        self._refresh_players()
        self._refresh_clocks()
        self._refresh_moves()
        self._update_actions()
        self._update_status()

    def _refresh_board(self) -> None:
        if self.view_ply is None:
            display_board = self.board
            last_move = self.history[-1]["move"] if self.history else None
            interactive = (
                self.game_active
                and not self.thinking
                and self.board.turn == self.human_color
            )
        else:
            try:
                display_board = chess.Board(self._fen_at(self.view_ply))
            except ValueError:
                display_board = chess.Board()
            last_move = (
                self.history[self.view_ply - 1]["move"] if self.view_ply >= 1 else None
            )
            interactive = False
        self.board_widget.set_position(display_board, last_move=last_move, interactive=interactive)
        self.board_widget.set_coach_arrow(self._coach_arrow if self.view_ply is None else None)
        self.eval_bar.set_flipped(self.board_widget.orientation == chess.BLACK)

    def _refresh_players(self) -> None:
        white_taken, black_taken, white_adv, black_adv = captured_material(self.board)
        ai_level, tier, elo = level_summary(self._ai_level_live)
        ai_is_white = self.ai_color == chess.WHITE

        self.top_bar.set_player(
            "Coach Engine",
            badge=f"Lv. {ai_level}",
            subtitle=f"{tier} · ~{elo:,} Elo",
            avatar_icon="knight",
            accent=ACCENT,
        )
        self.top_bar.set_captured(
            black_taken if ai_is_white else white_taken,
            black_adv if ai_is_white else white_adv,
        )

        human_side = "White" if self.human_color == chess.WHITE else "Black"
        self.bottom_bar.set_player(
            "You",
            badge=human_side,
            subtitle="Human player",
            avatar_icon="user",
            accent="#C9C6C1",
        )
        self.bottom_bar.set_captured(
            white_taken if ai_is_white else black_taken,
            white_adv if ai_is_white else black_adv,
        )

        self.top_bar.set_active(self.game_active and self.board.turn == self.ai_color)
        self.bottom_bar.set_active(self.game_active and self.board.turn == self.human_color)

    def _refresh_clocks(self) -> None:
        if self.clocks is None:
            self.top_bar.set_clock(None)
            self.bottom_bar.set_clock(None)
            return
        ai_time = self.clocks.get(self.ai_color, 0.0)
        human_time = self.clocks.get(self.human_color, 0.0)
        self.top_bar.set_clock(format_clock(ai_time), low=ai_time < 20.0 and ai_time > 0)
        self.bottom_bar.set_clock(
            format_clock(human_time), low=human_time < 20.0 and human_time > 0
        )

    def _refresh_moves(self) -> None:
        self.sidebar.set_moves([entry["san"] for entry in self.history], self.view_ply)

    def _update_actions(self) -> None:
        human_turn = (
            self.game_active
            and not self.thinking
            and self.board.turn == self.human_color
            and self.view_ply is None
        )
        self.sidebar.set_actions_enabled(
            hint=human_turn,
            takeback=self.game_active and bool(self.history) and not self.thinking,
            resign=self.game_active,
            flip=True,
        )

    def _update_status(self) -> None:
        if self.result_text:
            self.sidebar.set_status(self.result_text, self.result_tone)
            return
        if self.view_ply is not None:
            self.sidebar.set_status(
                f"Inspecting move {self.view_ply} of {len(self.history)} — click Live to resume.",
                "warn",
            )
            return
        if not self.game_active:
            self.sidebar.set_status("Game over. Start a new game to play again.", "normal")
            return
        if self._coach_pending:
            self.sidebar.set_status("Reviewing your move…", "warn")
            return
        if self.thinking:
            self.sidebar.set_status(f"{self.engine_name} is thinking…", "warn")
            return
        if self.board.turn == self.human_color:
            check = " You are in check." if self.board.is_check() else ""
            self.sidebar.set_status(f"Your move.{check}", "good")
        else:
            self.sidebar.set_status("Waiting for the engine…", "normal")

    def _check_game_over(self) -> None:
        if not self.board.is_game_over(claim_draw=True):
            return
        outcome = self.board.outcome(claim_draw=True)
        self.game_active = False
        self.thinking = False
        if outcome is None or outcome.winner is None:
            termination = outcome.termination if outcome else None
            messages = {
                chess.Termination.STALEMATE: "Draw by stalemate.",
                chess.Termination.INSUFFICIENT_MATERIAL: "Draw — not enough material to mate.",
                chess.Termination.SEVENTYFIVE_MOVES: "Draw by the seventy-five move rule.",
                chess.Termination.FIFTY_MOVES: "Draw by the fifty-move rule.",
                chess.Termination.THREEFOLD_REPETITION: "Draw by threefold repetition.",
                chess.Termination.FIVEFOLD_REPETITION: "Draw by fivefold repetition.",
            }
            self.result_text = messages.get(termination, "Draw.")
            self.result_tone = "normal"
        elif outcome.winner == self.human_color:
            self.result_text = "Checkmate — you win!"
            self.result_tone = "good"
        else:
            self.result_text = "Checkmate — the engine wins."
            self.result_tone = "bad"

    # ==================================================================
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        try:
            self._clock_timer.stop()
        except Exception:
            pass
        self.ai.shutdown()
        super().closeEvent(event)
