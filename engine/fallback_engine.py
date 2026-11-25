"""Pure-python chess engine used when Stockfish is unavailable.

Negamax + alpha-beta pruning + quiescence search + piece-square tables, scaled
across levels 1-100 by search depth, move-selection noise and blunder rate.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Optional

import chess

INF = 10**8
MATE = 100_000

PIECE_VALUES: dict[int, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def _flip(table: list[int]) -> list[int]:
    """Convert an a8-first table into python-chess square order (a1 = 0)."""
    out = [0] * 64
    for row in range(8):
        for col in range(8):
            out[row * 8 + col] = table[(7 - row) * 8 + col]
    return out


_PST_SRC: dict[int, list[int]] = {
    chess.PAWN: [
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 25, 25, 10, 5, 5,
        0, 0, 0, 20, 20, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -20, -20, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ],
    chess.KNIGHT: [
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ],
    chess.BISHOP: [
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ],
    chess.ROOK: [
        0, 0, 0, 5, 5, 0, 0, 0,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        5, 10, 10, 10, 10, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ],
    chess.QUEEN: [
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -10, 5, 5, 5, 5, 5, 0, -10,
        0, 0, 5, 5, 5, 5, 0, -5,
        -5, 0, 5, 5, 5, 5, 0, -5,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ],
    chess.KING: [
        20, 30, 10, 0, 0, 10, 30, 20,
        20, 20, 0, 0, 0, 0, 20, 20,
        -10, -20, -20, -20, -20, -20, -20, -10,
        -20, -30, -30, -40, -40, -30, -30, -20,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
    ],
}

PST: dict[int, list[int]] = {piece: _flip(table) for piece, table in _PST_SRC.items()}
PST_BLACK: dict[int, list[int]] = {
    piece: [table[sq ^ 56] for sq in range(64)] for piece, table in PST.items()
}


def material(board: chess.Board) -> int:
    """White-minus-black material in centipawns (pieces only)."""
    total = 0
    for piece in board.piece_map().values():
        value = PIECE_VALUES[piece.piece_type]
        total += value if piece.color == chess.WHITE else -value
    return total


def evaluate_white(board: chess.Board) -> int:
    """Static evaluation in centipawns from White's point of view."""
    if board.is_checkmate():
        return -MATE if board.turn == chess.WHITE else MATE
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    bishops = {chess.WHITE: 0, chess.BLACK: 0}
    for square, piece in board.piece_map().items():
        value = PIECE_VALUES[piece.piece_type]
        if piece.color == chess.WHITE:
            score += value + PST[piece.piece_type][square]
            if piece.piece_type == chess.BISHOP:
                bishops[chess.WHITE] += 1
        else:
            score -= value + PST_BLACK[piece.piece_type][square]
            if piece.piece_type == chess.BISHOP:
                bishops[chess.BLACK] += 1

    if bishops[chess.WHITE] >= 2:
        score += 32
    if bishops[chess.BLACK] >= 2:
        score -= 32
    return score


def _relative(board: chess.Board) -> int:
    """Static evaluation from the side-to-move point of view."""
    value = evaluate_white(board)
    return value if board.turn == chess.WHITE else -value


class _Timeout(Exception):
    """Raised internally when the search deadline is reached."""


def _order_moves(board: chess.Board, moves: list[chess.Move]) -> list[chess.Move]:
    def score(move: chess.Move) -> int:
        value = 0
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            attacker = board.piece_at(move.from_square)
            victim_value = PIECE_VALUES[victim.piece_type] if victim else PIECE_VALUES[chess.PAWN]
            attacker_value = PIECE_VALUES[attacker.piece_type] if attacker else 0
            value += 12 * victim_value - attacker_value
        if move.promotion:
            value += PIECE_VALUES.get(move.promotion, 900) * 2
        return -value

    return sorted(moves, key=score)


def _qsearch(board, alpha, beta, deadline, nodes, ply, qdepth=5):
    nodes[0] += 1
    if nodes[0] % 256 == 0 and deadline is not None and time.monotonic() > deadline:
        raise _Timeout

    stand = _relative(board)
    if stand >= beta:
        return beta
    if stand > alpha:
        alpha = stand
    if qdepth <= 0:
        return alpha

    tactical = [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
    for move in _order_moves(board, tactical):
        board.push(move)
        score = -_qsearch(board, -beta, -alpha, deadline, nodes, ply + 1, qdepth - 1)
        board.pop()
        if score >= beta:
            return beta
        if score > alpha:
            alpha = score
    return alpha


def _negamax(board, depth, alpha, beta, deadline, nodes, ply):
    nodes[0] += 1
    if nodes[0] % 256 == 0 and deadline is not None and time.monotonic() > deadline:
        raise _Timeout

    if board.is_checkmate():
        return -MATE + ply
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    if depth <= 0:
        return _qsearch(board, alpha, beta, deadline, nodes, ply)

    moves = _order_moves(board, list(board.legal_moves))
    if not moves:
        return 0 if not board.is_check() else -MATE + ply

    best = -INF
    for move in moves:
        board.push(move)
        score = -_negamax(board, depth - 1, -beta, -alpha, deadline, nodes, ply + 1)
        board.pop()
        if score > best:
            best = score
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def search(
    board: chess.Board,
    depth: int = 2,
    deadline: Optional[float] = None,
) -> tuple[Optional[chess.Move], int]:
    """Iterative-deepening negamax. Returns (best_move, score) for the mover."""
    if board.is_game_over(claim_draw=True):
        return None, _relative(board)

    moves = _order_moves(board, list(board.legal_moves))
    if not moves:
        return None, 0

    best_move = moves[0]
    best_score = _relative(board)
    nodes = [0]

    for current_depth in range(1, max(1, depth) + 1):
        alpha, beta = -INF, INF
        current_best: Optional[chess.Move] = None
        current_score = -INF
        try:
            for move in moves:
                board.push(move)
                score = -_negamax(
                    board, current_depth - 1, -beta, -alpha, deadline, nodes, 1
                )
                board.pop()
                if score > current_score:
                    current_score, current_best = score, move
                if score > alpha:
                    alpha = score
        except _Timeout:
            if current_best is not None and current_score > -INF:
                best_move, best_score = current_best, current_score
            break
        if current_best is not None:
            best_move, best_score = current_best, current_score
            moves = [current_best] + [m for m in moves if m != current_best]
    return best_move, best_score


def rank_moves(board: chess.Board, depth: int = 1) -> list[tuple[chess.Move, int]]:
    """Score every legal move from the mover's point of view, best first."""
    scored: list[tuple[chess.Move, int]] = []
    for move in list(board.legal_moves):
        board.push(move)
        if board.is_checkmate():
            value = MATE
        elif board.is_stalemate() or board.is_insufficient_material():
            value = 0
        elif depth <= 1:
            value = -_relative(board)
        else:
            _, value = search(board, depth - 1, time.monotonic() + 0.35)
            value = -value
        board.pop()
        scored.append((move, value))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


@dataclass(frozen=True)
class Profile:
    depth: int
    noise: int
    blunder: float
    time_limit: float


def profile(level: int) -> Profile:
    """Map a 1-100 level onto fallback search settings."""
    level = max(1, min(100, int(level)))
    if level <= 12:
        return Profile(1, 420, 0.42, 0.35)
    if level <= 25:
        return Profile(1, 280, 0.30, 0.5)
    if level <= 40:
        return Profile(2, 190, 0.18, 0.9)
    if level <= 60:
        return Profile(2, 110, 0.09, 1.2)
    if level <= 78:
        return Profile(3, 55, 0.04, 1.9)
    if level <= 90:
        return Profile(3, 20, 0.015, 2.4)
    return Profile(4, 0, 0.0, 3.0)


def choose_move(
    board: chess.Board,
    level: int = 40,
    rng: Optional[random.Random] = None,
) -> Optional[chess.Move]:
    """Pick a move for ``level``: strong at 100, plausibly weak at 1."""
    rng = rng or random.Random()
    if board.is_game_over(claim_draw=True):
        return None

    settings = profile(level)
    legal = list(board.legal_moves)
    if not legal:
        return None

    deadline = time.monotonic() + settings.time_limit
    best, _score = search(board, settings.depth, deadline)
    if best is None or best not in legal:
        best = legal[0]

    if settings.noise <= 0 and settings.blunder <= 0:
        return best

    ranked = rank_moves(board, 2 if settings.depth >= 3 else 1)
    if not ranked:
        return best
    ranked = [item for item in ranked if item[0] in legal] or [(best, 0)]

    if settings.blunder > 0 and rng.random() < settings.blunder:
        index = int(len(ranked) * rng.uniform(0.4, 0.95))
        return ranked[min(index, len(ranked) - 1)][0]

    top_score = ranked[0][1]
    pool = [move for move, value in ranked if value >= top_score - settings.noise]
    if not pool:
        pool = [ranked[0][0]]
    # Do not always pick the very best move inside the noise window.
    if len(pool) > 1 and rng.random() < 0.65:
        pool = pool[: max(1, min(len(pool), 4))]
    return rng.choice(pool)


def pick_suboptimal(
    board: chess.Board,
    exclude: Optional[chess.Move],
    level: int,
    rng: Optional[random.Random] = None,
) -> Optional[chess.Move]:
    """Choose a deliberately weaker (but plausible) move for low levels."""
    rng = rng or random.Random()
    ranked = rank_moves(board, 1)
    ranked = [item for item in ranked if item[0] != exclude]
    if not ranked:
        return None
    level = max(1, min(100, int(level)))
    spread = min(0.9, max(0.15, 1.0 - level / 45.0))
    index = int(len(ranked) * rng.uniform(0.2 * spread, spread))
    return ranked[min(index, len(ranked) - 1)][0]


def analyse_position(board: chess.Board, depth: int = 3) -> dict:
    """Return a quick analysis dict for the evaluation bar and coach."""
    deadline = time.monotonic() + 2.0
    move, score = search(board, depth, deadline)
    white = score if board.turn == chess.WHITE else -score
    return {
        "best_move": move,
        "score": score,
        "white_cp": max(-MATE, min(MATE, white)),
        "mate": _mate_in(score),
        "engine": "Python",
    }


def _mate_in(score: int) -> Optional[int]:
    if abs(score) < MATE - 1000:
        return None
    plies = MATE - abs(score)
    moves = max(1, (plies + 1) // 2)
    return moves if score > 0 else -moves
