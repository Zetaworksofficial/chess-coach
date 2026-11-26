/**
 * Browser port of engine/fallback_engine.py.
 *
 * Negamax + alpha-beta pruning + quiescence search + piece-square tables,
 * scaled across levels 1-100 by search depth, move-selection noise and
 * blunder rate. Everything runs inside a worker so the board stays smooth.
 */

import { Chess } from './vendor/chess.js';

const MATE = 100000;
const INF = 1e8;

export const PIECE_VALUES = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 0 };

/** Tables are written a8-first, exactly like the Python source. */
const SRC = {
  p: [
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 25, 25, 10, 5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, -5, -10, 0, 0, -10, -5, 5,
    5, 10, 10, -20, -20, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
  ],
  n: [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
  ],
  b: [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
  ],
  r: [
    0, 0, 0, 5, 5, 0, 0, 0,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    5, 10, 10, 10, 10, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
  ],
  q: [
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -10, 5, 5, 5, 5, 5, 0, -10,
    0, 0, 5, 5, 5, 5, 0, -5,
    -5, 0, 5, 5, 5, 5, 0, -5,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
  ],
  k: [
    20, 30, 10, 0, 0, 10, 30, 20,
    20, 20, 0, 0, 0, 0, 20, 20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
  ],
};

function flip(table) {
  const out = new Array(64);
  for (let row = 0; row < 8; row += 1) {
    for (let col = 0; col < 8; col += 1) {
      out[row * 8 + col] = table[(7 - row) * 8 + col];
    }
  }
  return out;
}

const PST = {};
const PST_BLACK = {};
for (const [type, table] of Object.entries(SRC)) {
  PST[type] = flip(table);
  PST_BLACK[type] = PST[type].map((_, index) => PST[type][index ^ 56]);
}

const TIMEOUT = Symbol('timeout');

export function toUci(move) {
  return `${move.from}${move.to}${move.promotion || ''}`;
}

function fromUci(uci) {
  if (!uci || uci.length < 4) return null;
  return { from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.slice(4) || undefined };
}

function squareIndex(square) {
  return square.charCodeAt(0) - 97 + (Number(square[1]) - 1) * 8;
}

/** Static evaluation in centipawns from White's point of view. */
export function evaluateWhite(board) {
  let score = 0;
  let whiteBishops = 0;
  let blackBishops = 0;
  for (const row of board.board()) {
    for (const cell of row) {
      if (!cell) continue;
      const value = PIECE_VALUES[cell.type];
      const index = squareIndex(cell.square);
      if (cell.color === 'w') {
        score += value + PST[cell.type][index];
        if (cell.type === 'b') whiteBishops += 1;
      } else {
        score -= value + PST_BLACK[cell.type][index];
        if (cell.type === 'b') blackBishops += 1;
      }
    }
  }
  if (whiteBishops >= 2) score += 32;
  if (blackBishops >= 2) score -= 32;
  return score;
}

function relative(board) {
  const value = evaluateWhite(board);
  return board.turn() === 'w' ? value : -value;
}

function orderMoves(moves) {
  const scored = moves.map((move) => {
    let value = 0;
    if (move.captured) {
      value += 12 * PIECE_VALUES[move.captured] - (PIECE_VALUES[move.piece] || 0);
    }
    if (move.promotion) value += (PIECE_VALUES[move.promotion] || 900) * 2;
    return { move, value };
  });
  scored.sort((a, b) => b.value - a.value);
  return scored.map((entry) => entry.move);
}

function checkDeadline(ctx) {
  ctx.nodes += 1;
  if ((ctx.nodes & 255) === 0 && ctx.deadline && performance.now() > ctx.deadline) {
    throw TIMEOUT;
  }
}

function qsearch(board, alpha, beta, ctx, qdepth = 5) {
  checkDeadline(ctx);

  const stand = relative(board);
  if (stand >= beta) return beta;
  if (stand > alpha) alpha = stand;
  if (qdepth <= 0) return alpha;

  const tactical = board.moves({ verbose: true }).filter((move) => move.captured || move.promotion);
  for (const move of orderMoves(tactical)) {
    board.move({ from: move.from, to: move.to, promotion: move.promotion });
    const score = -qsearch(board, -beta, -alpha, ctx, qdepth - 1);
    board.undo();
    if (score >= beta) return beta;
    if (score > alpha) alpha = score;
  }
  return alpha;
}

function negamax(board, depth, alpha, beta, ctx, ply) {
  checkDeadline(ctx);

  if (depth <= 0) return qsearch(board, alpha, beta, ctx);

  const moves = orderMoves(board.moves({ verbose: true }));
  if (!moves.length) return board.isCheck() ? -MATE + ply : 0;

  let best = -INF;
  for (const move of moves) {
    board.move({ from: move.from, to: move.to, promotion: move.promotion });
    const score = -negamax(board, depth - 1, -beta, -alpha, ctx, ply + 1);
    board.undo();
    if (score > best) best = score;
    if (best > alpha) alpha = best;
    if (alpha >= beta) break;
  }
  return best;
}

/** Iterative-deepening search. Returns the best move for the side to move. */
export function search(board, depth = 2, deadline = null) {
  const legal = orderMoves(board.moves({ verbose: true }));
  if (!legal.length) return { move: null, score: relative(board) };

  let bestMove = legal[0];
  let bestScore = relative(board);
  let moves = legal;
  const ctx = { nodes: 0, deadline };

  for (let current = 1; current <= Math.max(1, depth); current += 1) {
    let alpha = -INF;
    const beta = INF;
    let currentBest = null;
    let currentScore = -INF;
    try {
      for (const move of moves) {
        board.move({ from: move.from, to: move.to, promotion: move.promotion });
        const score = -negamax(board, current - 1, -beta, -alpha, ctx, 1);
        board.undo();
        if (score > currentScore) {
          currentScore = score;
          currentBest = move;
        }
        if (score > alpha) alpha = score;
      }
    } catch (error) {
      if (error !== TIMEOUT) throw error;
      if (currentBest && currentScore > -INF) {
        bestMove = currentBest;
        bestScore = currentScore;
      }
      break;
    }
    if (currentBest) {
      bestMove = currentBest;
      bestScore = currentScore;
      moves = [currentBest, ...moves.filter((move) => move !== currentBest)];
    }
  }
  return { move: bestMove, score: bestScore };
}

/** Score every legal move from the mover's point of view, best first. */
export function rankMoves(board, depth = 1) {
  const scored = [];
  for (const move of board.moves({ verbose: true })) {
    board.move({ from: move.from, to: move.to, promotion: move.promotion });
    let value;
    if (board.isCheckmate()) value = MATE;
    else if (board.isStalemate() || board.isInsufficientMaterial()) value = 0;
    else if (depth <= 1) value = -relative(board);
    else value = -search(board, depth - 1, performance.now() + 350).score;
    board.undo();
    scored.push({ move, value });
  }
  scored.sort((a, b) => b.value - a.value);
  return scored;
}

/**
 * Map a 1-100 level onto search settings. Same table as the desktop engine.
 */
export function profile(level) {
  const value = Math.max(1, Math.min(100, Math.round(Number(level) || 40)));
  if (value <= 12) return { depth: 1, noise: 420, blunder: 0.42, timeLimit: 0.35 };
  if (value <= 25) return { depth: 1, noise: 280, blunder: 0.3, timeLimit: 0.5 };
  if (value <= 40) return { depth: 2, noise: 190, blunder: 0.18, timeLimit: 0.9 };
  if (value <= 60) return { depth: 2, noise: 110, blunder: 0.09, timeLimit: 1.2 };
  if (value <= 78) return { depth: 3, noise: 55, blunder: 0.04, timeLimit: 1.9 };
  if (value <= 90) return { depth: 3, noise: 20, blunder: 0.015, timeLimit: 2.4 };
  return { depth: 4, noise: 0, blunder: 0, timeLimit: 3 };
}

/** Pick a move for `level`: strong at 100, plausibly weak at 1. */
export function chooseMove(fen, level = 40, rng = Math.random) {
  const board = new Chess(fen);
  if (board.isGameOver()) return null;

  const legal = board.moves({ verbose: true });
  if (!legal.length) return null;

  const settings = profile(level);
  const deadline = performance.now() + settings.timeLimit * 1000;
  let best = search(board, settings.depth, deadline).move;
  if (!best) best = legal[0];

  if (settings.noise <= 0 && settings.blunder <= 0) return toUci(best);

  let ranked = rankMoves(board, settings.depth >= 3 ? 2 : 1);
  if (!ranked.length) return toUci(best);

  if (settings.blunder > 0 && rng() < settings.blunder) {
    const index = Math.floor(ranked.length * (0.4 + rng() * 0.55));
    return toUci(ranked[Math.min(index, ranked.length - 1)].move);
  }

  const topScore = ranked[0].value;
  let pool = ranked
    .filter((entry) => entry.value >= topScore - settings.noise)
    .map((entry) => entry.move);
  if (!pool.length) pool = [ranked[0].move];
  if (pool.length > 1 && rng() < 0.65) pool = pool.slice(0, Math.min(pool.length, 4));
  return toUci(pool[Math.floor(rng() * pool.length)]);
}

function mateIn(score) {
  if (Math.abs(score) < MATE - 1000) return null;
  const plies = MATE - Math.abs(score);
  const moves = Math.max(1, Math.ceil(plies / 2));
  return score > 0 ? moves : -moves;
}

/** Quick analysis for the evaluation bar, coach and hints. */
export function analyse(fen, depth = 3, budget = 1500) {
  const board = new Chess(fen);
  const result = search(board, depth, performance.now() + budget);
  const white = board.turn() === 'w' ? result.score : -result.score;
  return {
    bestUci: result.move ? toUci(result.move) : null,
    score: result.score,
    whiteCp: Math.max(-MATE, Math.min(MATE, white)),
    mate: mateIn(result.score),
    engine: 'Web engine',
  };
}

export { MATE, fromUci };
