"""Stockfish bridge, level mapping and the non-blocking analysis worker.

The manager owns a QThread worker that performs every blocking engine call, so
the Qt event loop never stalls.  Every task degrades gracefully to the bundled
pure-python engine when Stockfish is missing or misbehaves.
"""

from __future__ import annotations

import os
import queue
import random
import shutil
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

import chess
import chess.engine
from PySide6.QtCore import QObject, QThread, Signal, Slot

from . import fallback_engine

MATE_CP = 100_000

LEVEL_TIERS: tuple[tuple[int, str], ...] = (
    (15, "Beginner"),
    (35, "Casual"),
    (60, "Intermediate"),
    (85, "Advanced"),
    (100, "Master"),
)

_STOCKFISH_NAMES = (
    "stockfish",
    "stockfish-16",
    "stockfish_16",
    "stockfish-15",
    "stockfish-ubuntu-x86-64-avx2",
    "stockfish-ubuntu-x86-64",
    "stockfish-macos-m1-apple-silicon",
    "stockfish.exe",
    "stockfish-windows-x86-64-avx2.exe",
)

_COMMON_DIRS = (
    "/usr/games",
    "/usr/local/bin",
    "/usr/bin",
    "/opt/homebrew/bin",
    "/opt/local/bin",
    str(Path.home() / "bin"),
    str(Path.home() / "Downloads"),
    str(Path.home() / ".local" / "bin"),
    "C:/Program Files/Stockfish",
    "C:/Program Files (x86)/Stockfish",
    "C:/Stockfish",
)


def tier_for(level: int) -> str:
    """Human tier label for a level."""
    level = max(1, min(100, int(level)))
    for limit, label in LEVEL_TIERS:
        if level <= limit:
            return label
    return "Master"


def elo_for(level: int) -> int:
    """Smooth 400 -> 3000 Elo estimate across levels 1-100."""
    level = max(1, min(100, int(level)))
    return int(round(400.0 * (3000.0 / 400.0) ** ((level - 1) / 99.0)))


def level_summary(level: int) -> tuple[int, str, int]:
    level = max(1, min(100, int(level)))
    return level, tier_for(level), elo_for(level)


def mistake_probability(level: int) -> float:
    """Chance of deliberately choosing a weaker Stockfish candidate."""
    if level <= 10:
        return 0.55
    if level <= 20:
        return 0.42
    if level <= 30:
        return 0.30
    if level <= 45:
        return 0.16
    if level <= 60:
        return 0.06
    return 0.0


def _iter_stockfish_candidates(user_path: str = ""):
    if user_path:
        expanded = str(Path(user_path).expanduser())
        yield expanded
        found = shutil.which(user_path)
        if found:
            yield found
    for name in _STOCKFISH_NAMES:
        found = shutil.which(name)
        if found:
            yield found
    for directory in _COMMON_DIRS:
        base = Path(directory)
        if not base.is_dir():
            continue
        for name in _STOCKFISH_NAMES:
            candidate = base / name
            if candidate.is_file():
                yield str(candidate)


def find_stockfish(user_path: str = "") -> str:
    """Return a usable Stockfish binary path, or an empty string."""
    seen: set[str] = set()
    for candidate in _iter_stockfish_candidates(user_path):
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        try:
            if path.is_file():
                if os.name != "nt" and not os.access(str(path), os.X_OK):
                    continue
                return str(path)
        except OSError:
            continue
    return ""


def _clamp_cp(value: float) -> int:
    return int(max(-MATE_CP, min(MATE_CP, value)))


def _score_fields(score: Optional["chess.engine.PovScore"]) -> dict:
    """Normalise an engine score into white-centric centipawns + mate."""
    if score is None:
        return {"white_cp": 0, "mate": None}
    white = score.pov(chess.WHITE)
    if white.is_mate():
        mate = white.mate()
        mate = 0 if mate is None else int(mate)
        cp = MATE_CP - abs(mate) * 100
        return {"white_cp": cp if mate >= 0 else -cp, "mate": mate}
    value = white.score(mate_score=MATE_CP)
    return {"white_cp": _clamp_cp(value or 0), "mate": None}


class _EngineThread(QThread):
    """Worker thread performing every blocking engine call."""

    result = Signal(int, dict)
    status = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._queue: "queue.Queue[Optional[tuple[int, dict]]]" = queue.Queue()
        self._running = True
        self._lock = threading.Lock()
        self._rng = random.Random()
        self._sf: Optional[chess.engine.SimpleEngine] = None
        self._sf_path = ""
        self._reported = ""

    # -- lifecycle ---------------------------------------------------------
    def submit(self, task_id: int, payload: dict) -> None:
        self._queue.put((task_id, payload))

    def stop(self) -> None:
        self._running = False
        self._queue.put(None)

    def run(self) -> None:  # noqa: D401 - QThread entry point
        while self._running:
            try:
                item = self._queue.get(timeout=0.15)
            except queue.Empty:
                continue
            if item is None:
                break
            task_id, payload = item
            try:
                data = self._handle(payload)
            except Exception as exc:  # never let the worker die
                data = {
                    "kind": payload.get("kind", ""),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            if not self._running:
                break
            self.result.emit(task_id, data)
        self._close_engine()

    def _close_engine(self) -> None:
        with self._lock:
            if self._sf is not None:
                try:
                    self._sf.quit()
                except Exception:
                    pass
                self._sf = None
            self._sf_path = ""

    # -- stockfish plumbing ------------------------------------------------
    def _engine(self, path: str) -> Optional[chess.engine.SimpleEngine]:
        if not path:
            return None
        with self._lock:
            if self._sf is not None and self._sf_path == path:
                return self._sf
            if self._sf is not None:
                try:
                    self._sf.quit()
                except Exception:
                    pass
                self._sf = None
                self._sf_path = ""
            try:
                engine = chess.engine.SimpleEngine.popen_uci(path, timeout=8.0)
                try:
                    engine.configure({"Threads": 1, "Hash": 64})
                except Exception:
                    pass
                self._sf = engine
                self._sf_path = path
                name = ""
                try:
                    name = engine.id.get("name", "") if engine.id else ""
                except Exception:
                    name = ""
                label = f"Stockfish ({name})" if name else "Stockfish"
                if label != self._reported:
                    self._reported = label
                    self.status.emit(label)
                return engine
            except Exception:
                self._sf = None
                self._sf_path = ""
                if self._reported != "Built-in engine":
                    self._reported = "Built-in engine"
                    self.status.emit("Built-in engine")
                return None

    def _configure_strength(self, level: int, engine: chess.engine.SimpleEngine) -> None:
        elo = max(1320, min(3190, elo_for(level)))
        skill = int(round((level - 1) / 99.0 * 20))
        try:
            engine.configure(
                {"UCI_LimitStrength": True, "UCI_Elo": elo, "Skill Level": skill}
            )
            return
        except Exception:
            pass
        try:
            engine.configure({"Skill Level": skill})
        except Exception:
            pass

    def _configure_full_strength(self, engine: chess.engine.SimpleEngine) -> None:
        try:
            engine.configure({"UCI_LimitStrength": False, "Skill Level": 20})
        except Exception:
            pass

    @staticmethod
    def _limit(level: int, purpose: str) -> "chess.engine.Limit":
        if purpose == "coach":
            return chess.engine.Limit(depth=12, time=1.0)
        if purpose == "hint":
            return chess.engine.Limit(depth=14, time=1.2)
        depth = 3 + int(round(level * 0.13))
        seconds = 0.05 + level * 0.0045
        return chess.engine.Limit(depth=depth, time=seconds)

    # -- task router -------------------------------------------------------
    def _handle(self, payload: dict) -> dict:
        kind = payload.get("kind", "")
        path = payload.get("stockfish_path", "")
        if kind == "probe":
            engine = self._engine(path)
            if engine is None:
                return {"kind": "probe", "engine": "Built-in engine", "stockfish": False}
            name = ""
            try:
                name = engine.id.get("name", "") if engine.id else ""
            except Exception:
                name = ""
            return {
                "kind": "probe",
                "engine": f"Stockfish ({name})" if name else "Stockfish",
                "stockfish": True,
            }

        if kind == "move":
            return self._move_task(chess.Board(payload["fen"]), payload, path)
        if kind == "hint":
            return self._hint_task(chess.Board(payload["fen"]), path)
        if kind == "analysis":
            return self._analysis_task(chess.Board(payload["fen"]), path, payload)
        if kind == "coach":
            return self._coach_task(payload, path)
        return {"kind": kind, "error": "Unknown task"}

    # -- building blocks ---------------------------------------------------
    def _white_eval(self, board: chess.Board, path: str, depth: int = 10) -> int:
        engine = self._engine(path)
        if engine is not None:
            try:
                self._configure_full_strength(engine)
                info = engine.analyse(board, chess.engine.Limit(depth=depth, time=0.9))
                return _score_fields(info.get("score"))["white_cp"]
            except Exception:
                self._close_engine()
        data = fallback_engine.analyse_position(board, 2)
        return int(data["white_cp"])

    def _best_move(
        self, board: chess.Board, path: str, depth: int = 10
    ) -> tuple[Optional[chess.Move], int, str]:
        engine = self._engine(path)
        if engine is not None:
            try:
                self._configure_full_strength(engine)
                info = engine.analyse(board, chess.engine.Limit(depth=depth, time=1.0))
                pv = info.get("pv") or []
                move = pv[0] if pv else None
                if move is not None and move in board.legal_moves:
                    return move, _score_fields(info.get("score"))["white_cp"], "Stockfish"
            except Exception:
                self._close_engine()
        if board.is_game_over(claim_draw=True):
            return None, fallback_engine.evaluate_white(board), "Built-in engine"
        move, score = fallback_engine.search(board, 3)
        white = score if board.turn == chess.WHITE else -score
        return move, white, "Built-in engine"

    # -- tasks -------------------------------------------------------------
    def _move_task(self, board: chess.Board, payload: dict, path: str) -> dict:
        level = int(payload.get("level", 40))
        if board.is_game_over(claim_draw=True):
            return {"kind": "move", "uci": None, "engine": "none"}

        engine = self._engine(path)
        if engine is not None:
            try:
                self._configure_strength(level, engine)
                multipv = 4 if level <= 60 else 1
                infos = engine.analyse(
                    board, self._limit(level, "move"), multipv=multipv
                )
                if isinstance(infos, dict):
                    infos = [infos]
                infos = [info for info in infos if info.get("pv")]
                if not infos:
                    raise RuntimeError("engine returned no principal variation")
                best = infos[0]["pv"][0]
                choice = best
                if len(infos) > 1 and self._rng.random() < mistake_probability(level):
                    candidates = [
                        info["pv"][0]
                        for info in infos[1:]
                        if info["pv"] and info["pv"][0] in board.legal_moves
                    ]
                    if candidates:
                        choice = self._rng.choice(candidates)
                fields = _score_fields(infos[0].get("score"))
                return {
                    "kind": "move",
                    "uci": choice.uci(),
                    "best_uci": best.uci(),
                    "white_cp": fields["white_cp"],
                    "mate": fields["mate"],
                    "engine": "Stockfish",
                    "depth": int(infos[0].get("depth", 0) or 0),
                }
            except Exception:
                self._close_engine()

        # Built-in engine path.
        move = fallback_engine.choose_move(board, level, self._rng)
        if move is None:
            legal = list(board.legal_moves)
            move = self._rng.choice(legal) if legal else None
        if move is None:
            return {"kind": "move", "uci": None, "engine": "Built-in engine"}
        white_cp = fallback_engine.evaluate_white(board)
        mate = fallback_engine._mate_in(white_cp if board.turn == chess.WHITE else -white_cp)
        return {
            "kind": "move",
            "uci": move.uci(),
            "best_uci": move.uci(),
            "white_cp": _clamp_cp(white_cp),
            "mate": mate,
            "engine": "Built-in engine",
            "depth": fallback_engine.profile(level).depth,
        }

    def _hint_task(self, board: chess.Board, path: str) -> dict:
        if board.is_game_over(claim_draw=True):
            return {"kind": "hint", "uci": None}
        move, white_cp, source = self._best_move(board, path, depth=14)
        if move is None:
            return {"kind": "hint", "uci": None, "engine": source}
        return {
            "kind": "hint",
            "uci": move.uci(),
            "white_cp": white_cp,
            "engine": source,
        }

    def _analysis_task(self, board: chess.Board, path: str, payload: dict) -> dict:
        depth = int(payload.get("depth", 10))
        engine = self._engine(path)
        if engine is not None:
            try:
                self._configure_full_strength(engine)
                info = engine.analyse(
                    board, chess.engine.Limit(depth=depth, time=0.6)
                )
                fields = _score_fields(info.get("score"))
                return {
                    "kind": "analysis",
                    "white_cp": fields["white_cp"],
                    "mate": fields["mate"],
                    "engine": "Stockfish",
                }
            except Exception:
                self._close_engine()
        data = fallback_engine.analyse_position(board, 3)
        return {
            "kind": "analysis",
            "white_cp": int(data["white_cp"]),
            "mate": data["mate"],
            "engine": "Built-in engine",
        }

    def _coach_task(self, payload: dict, path: str) -> dict:
        before = chess.Board(payload["fen_before"])
        user_uci = payload.get("user_uci", "")
        try:
            user_move = chess.Move.from_uci(user_uci)
        except Exception:
            user_move = None

        after_user = before.copy()
        if user_move is not None and user_move in before.legal_moves:
            after_user.push(user_move)

        best_move, before_white, source = self._best_move(before, path, depth=12)

        after_best = before.copy()
        if best_move is not None and best_move in before.legal_moves:
            after_best.push(best_move)
        after_best_white = self._white_eval(after_best, path)
        after_user_white = self._white_eval(after_user, path)

        return {
            "kind": "coach",
            "best_uci": best_move.uci() if best_move else None,
            "white_cp_before": before_white,
            "white_cp_after_user": after_user_white,
            "white_cp_after_best": after_best_white,
            "engine": source,
        }


class AIManager(QObject):
    """Main-thread facade around the worker thread."""

    engine_status = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.stockfish_path = ""
        self._callbacks: dict[int, Callable[[dict], None]] = {}
        self._next_id = 1
        self._thread = _EngineThread(self)
        self._thread.result.connect(self._on_result)
        self._thread.status.connect(self.engine_status)
        self._thread.start()

    # -- public API --------------------------------------------------------
    def set_stockfish_path(self, path: str) -> None:
        self.stockfish_path = path or ""

    def probe(self, callback: Callable[[dict], None]) -> None:
        self._submit({"kind": "probe"}, callback)

    def request_move(self, fen: str, level: int, callback: Callable[[dict], None]) -> None:
        self._submit({"kind": "move", "fen": fen, "level": int(level)}, callback)

    def request_hint(self, fen: str, callback: Callable[[dict], None]) -> None:
        self._submit({"kind": "hint", "fen": fen}, callback)

    def request_analysis(self, fen: str, callback: Callable[[dict], None]) -> None:
        self._submit({"kind": "analysis", "fen": fen, "depth": 10}, callback)

    def request_coach(
        self,
        fen_before: str,
        user_uci: str,
        callback: Callable[[dict], None],
    ) -> None:
        self._submit(
            {"kind": "coach", "fen_before": fen_before, "user_uci": user_uci},
            callback,
        )

    def shutdown(self) -> None:
        self._callbacks.clear()
        try:
            self._thread.stop()
            self._thread.wait(4000)
        except Exception:
            pass

    # -- internals ---------------------------------------------------------
    def _submit(self, payload: dict, callback: Callable[[dict], None]) -> None:
        task_id = self._next_id
        self._next_id += 1
        self._callbacks[task_id] = callback
        payload["stockfish_path"] = self.stockfish_path
        self._thread.submit(task_id, payload)

    @Slot(int, dict)
    def _on_result(self, task_id: int, data: dict) -> None:
        callback = self._callbacks.pop(task_id, None)
        if callback is None:
            return
        try:
            callback(data)
        except RuntimeError:
            # Widget deleted while the task was running: ignore.
            pass
