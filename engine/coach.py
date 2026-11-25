"""Move classification and plain-English explanations for the live coach."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chess

from .fallback_engine import PIECE_VALUES, MATE

PIECE_NAMES: dict[int, str] = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

LABEL_COLORS: dict[str, str] = {
    "Best": "#81B64C",
    "Good": "#7FA650",
    "Inaccuracy": "#E9B93C",
    "Mistake": "#E08B36",
    "Blunder": "#CB4B42",
    "Forced": "#8A8783",
    "Book": "#A08C6A",
}


@dataclass
class CoachVerdict:
    """Result of reviewing one move."""

    label: str
    color: str
    explanation: str
    best_move: Optional[chess.Move] = None
    best_san: str = ""
    cp_loss: int = 0
    engine: str = ""


def format_score(white_cp: int, mate: Optional[int] = None) -> str:
    """``+1.4``, ``-0.3``, ``M3``, ``0.0`` for the evaluation bar."""
    if mate is not None:
        return f"M{abs(int(mate))}" if mate >= 0 else f"-M{abs(int(mate))}"
    if abs(white_cp) >= MATE - 1000:
        return "+M" if white_cp > 0 else "-M"
    pawns = white_cp / 100.0
    if abs(pawns) < 0.05:
        return "0.0"
    return f"{pawns:+.1f}"


def piece_word(piece: chess.Piece) -> str:
    return PIECE_NAMES.get(piece.piece_type, "piece")


def san_of(board: chess.Board, move: chess.Move) -> str:
    try:
        return board.san(move)
    except Exception:
        return move.uci()


def _cheapest_attacker(board: chess.Board, square: int, by_color: bool) -> Optional[chess.Piece]:
    attackers = [sq for sq in board.attackers(by_color, square)]
    pieces = [board.piece_at(sq) for sq in attackers]
    pieces = [p for p in pieces if p is not None]
    if not pieces:
        return None
    return min(pieces, key=lambda p: PIECE_VALUES[p.piece_type])


def hanging_piece(board: chess.Board, color: bool):
    """Most valuable piece of ``color`` that can be won by the side to move."""
    if board.turn == color:
        return None
    best = None
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        attacker = _cheapest_attacker(board, square, not color)
        if attacker is None:
            continue
        defenders = board.attackers(color, square)
        value = PIECE_VALUES[piece.piece_type]
        attacker_value = PIECE_VALUES[attacker.piece_type]
        if defenders and attacker_value >= value:
            continue
        gain = value - (attacker_value if defenders else 0)
        if gain >= 90 and (best is None or gain > best[0]):
            best = (gain, square, piece, attacker)
    return best


def _mate_threat(board: chess.Board, by_color: bool) -> Optional[chess.Move]:
    """A one-move mate available to ``by_color`` (whose turn it is)."""
    if board.turn != by_color:
        return None
    for move in board.legal_moves:
        try:
            if not board.gives_check(move):
                continue
        except Exception:
            continue
        board.push(move)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return move
    return None


def _best_move_reason(board: chess.Board, move: chess.Move) -> str:
    if move is None:
        return ""
    piece = board.piece_at(move.from_square)
    target = board.piece_at(move.to_square)
    if board.is_castling(move):
        return "it tucks your king away and connects the rooks"
    if move.promotion:
        return "it promotes your pawn into a new queen"
    if target is not None:
        return f"it wins the {piece_word(target)} on {chess.square_name(move.to_square)}"
    if board.is_en_passant(move):
        return "it captures en passant and removes a dangerous pawn"
    try:
        board.push(move)
        gives_check = board.is_check()
        mate = board.is_checkmate()
        board.pop()
    except Exception:
        gives_check, mate = False, False
    if mate:
        return "it is checkmate"
    if gives_check:
        return "it gives check and forces the king to react"
    if piece is not None and piece.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(move.from_square) in (0, 7):
        return "it develops a piece towards the centre"
    if piece is not None and piece.piece_type == chess.PAWN and chess.square_file(move.to_square) in (3, 4):
        return "it stakes a claim in the centre"
    if piece is not None and piece.piece_type == chess.KING:
        return "it keeps your king safe"
    return "it keeps your pieces active and coordinated"


def describe_move(board: chess.Board, move: chess.Move) -> str:
    """Short hint sentence for the board/hint button."""
    return f"{san_of(board, move)} — {_best_move_reason(board, move)}."


def classify_loss(cp_loss: int, is_best: bool) -> str:
    if is_best or cp_loss <= 15:
        return "Best"
    if cp_loss <= 60:
        return "Good"
    if cp_loss <= 130:
        return "Inaccuracy"
    if cp_loss <= 260:
        return "Mistake"
    return "Blunder"


def _explain_negative(
    before: chess.Board,
    after: chess.Board,
    user_move: chess.Move,
    best_move: Optional[chess.Move],
    label: str,
) -> str:
    mover = before.turn
    best_san = san_of(before, best_move) if best_move else ""
    moved_piece = after.piece_at(user_move.to_square)
    hanging = hanging_piece(after, mover)

    if hanging is not None:
        gain, square, piece, attacker = hanging
        if moved_piece is not None and square == user_move.to_square:
            return (
                f"Your {piece_word(piece)} on {chess.square_name(square)} is undefended "
                f"and the {piece_word(attacker)} can take it. {best_san} avoided this."
            ).strip()
        if gain >= 300:
            return (
                f"This leaves your {piece_word(piece)} on {chess.square_name(square)} "
                f"hanging to the {piece_word(attacker)}. {best_san} was safer."
            ).strip()

    mate = _mate_threat(after, not mover)
    if mate is not None:
        return (
            f"Careful — this allows {san_of(after, mate)}, which is checkmate. "
            f"{best_san} would have prevented it."
        ).strip()

    if best_move is not None and before.is_capture(best_move):
        captured = before.piece_at(best_move.to_square)
        if captured is not None and PIECE_VALUES[captured.piece_type] >= 300:
            return (
                f"You missed {best_san}, winning the {piece_word(captured)} on "
                f"{chess.square_name(best_move.to_square)}."
            )

    if best_move is not None and best_move.promotion:
        return f"{best_san} promotes your pawn — that was the big chance here."

    if moved_piece is not None and label in ("Mistake", "Blunder"):
        return (
            f"{san_of(before, user_move)} lets your {piece_word(moved_piece)} lose its job. "
            f"Better was {best_san}, {_best_move_reason(before, best_move)}."
        )

    return (
        f"Better was {best_san} — {_best_move_reason(before, best_move)}. "
        f"Your move leaves the position a little looser."
    )


def review_move(
    fen_before: str,
    user_move: chess.Move,
    best_uci: Optional[str],
    white_cp_before: int,
    white_cp_after_user: int,
    white_cp_after_best: int,
    engine: str = "",
) -> CoachVerdict:
    """Classify a played move and write a short explanation."""
    before = chess.Board(fen_before)
    mover = before.turn
    sign = 1 if mover == chess.WHITE else -1

    after = before.copy()
    if user_move in before.legal_moves:
        after.push(user_move)

    best_move: Optional[chess.Move] = None
    if best_uci:
        try:
            candidate = chess.Move.from_uci(best_uci)
            if candidate in before.legal_moves:
                best_move = candidate
        except Exception:
            best_move = None

    legal_count = before.legal_moves.count()
    if legal_count <= 1:
        return CoachVerdict(
            label="Forced",
            color=LABEL_COLORS["Forced"],
            explanation="This was your only legal move, so there was nothing to decide.",
            best_move=best_move,
            best_san=san_of(before, best_move) if best_move else "",
            cp_loss=0,
            engine=engine,
        )

    before_view = sign * white_cp_before
    after_view = sign * white_cp_after_user
    best_view = sign * white_cp_after_best

    cp_loss = int(max(0, best_view - after_view))
    is_best = best_move is not None and user_move == best_move
    label = classify_loss(cp_loss, is_best)

    if label == "Best":
        explanation = (
            f"Top engine move — {_best_move_reason(before, user_move)}."
            if _best_move_reason(before, user_move)
            else "That is the engine's first choice."
        )
        explanation = explanation[0].upper() + explanation[1:]
    elif label == "Good":
        reason = _best_move_reason(before, best_move) if best_move else ""
        explanation = (
            f"Solid move. {san_of(before, best_move)} was marginally stronger"
            f"{' — ' + reason if reason else ''}, but your choice keeps the balance."
        )
    else:
        explanation = _explain_negative(before, after, user_move, best_move, label)

    if abs(after_view) >= MATE - 1000 and after_view < 0:
        explanation = "That walks into a forced mate. " + explanation

    return CoachVerdict(
        label=label,
        color=LABEL_COLORS.get(label, "#81B64C"),
        explanation=explanation,
        best_move=best_move,
        best_san=san_of(before, best_move) if best_move else "",
        cp_loss=cp_loss,
        engine=engine,
    )
