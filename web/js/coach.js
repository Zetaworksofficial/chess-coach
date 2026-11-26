/**
 * Browser port of engine/coach.py: move classification and plain-English
 * explanations for the live coach, plus the hint sentence builder.
 */

import { Chess } from './vendor/chess.js';
import { PIECE_VALUES, MATE, fromUci } from './engine.js';

const PIECE_NAMES = {
  p: 'pawn',
  n: 'knight',
  b: 'bishop',
  r: 'rook',
  q: 'queen',
  k: 'king',
};

export const LABEL_COLORS = {
  Best: '#81B64C',
  Good: '#7FA650',
  Inaccuracy: '#E9B93C',
  Mistake: '#E08B36',
  Blunder: '#CB4B42',
  Forced: '#8A8783',
  Book: '#A08C6A',
};

const other = (color) => (color === 'w' ? 'b' : 'w');

export function formatScore(whiteCp, mate = null) {
  if (mate !== null && mate !== undefined) {
    return mate >= 0 ? `M${Math.abs(mate)}` : `-M${Math.abs(mate)}`;
  }
  if (Math.abs(whiteCp) >= MATE - 1000) return whiteCp > 0 ? '+M' : '-M';
  const pawns = whiteCp / 100;
  if (Math.abs(pawns) < 0.05) return '0.0';
  return `${pawns > 0 ? '+' : ''}${pawns.toFixed(1)}`;
}

export function sanOf(board, move) {
  if (!move) return '';
  if (typeof move === 'string') return move;
  if (move.san) return move.san;
  try {
    return board.move({ from: move.from, to: move.to, promotion: move.promotion }).san;
  } catch (error) {
    return `${move.from}${move.to}`;
  }
}

function cheapestAttacker(board, square, color) {
  const squares = board.attackers(square, color);
  const pieces = squares.map((sq) => board.get(sq)).filter(Boolean);
  if (!pieces.length) return null;
  return pieces.sort((a, b) => PIECE_VALUES[a.type] - PIECE_VALUES[b.type])[0];
}

/** Most valuable piece of `color` that can be won by the side to move. */
export function hangingPiece(board, color) {
  if (board.turn() === color) return null;
  let best = null;
  for (const row of board.board()) {
    for (const cell of row) {
      if (!cell || cell.color !== color || cell.type === 'k') continue;
      const attacker = cheapestAttacker(board, cell.square, other(color));
      if (!attacker) continue;
      const defenders = board.attackers(cell.square, color);
      const value = PIECE_VALUES[cell.type];
      const attackerValue = PIECE_VALUES[attacker.type];
      if (defenders.length && attackerValue >= value) continue;
      const gain = value - (defenders.length ? attackerValue : 0);
      if (gain >= 90 && (!best || gain > best.gain)) {
        best = { gain, square: cell.square, type: cell.type, attacker: attacker.type };
      }
    }
  }
  return best;
}

function mateThreat(board, color) {
  if (board.turn() !== color) return null;
  for (const move of board.moves({ verbose: true })) {
    board.move({ from: move.from, to: move.to, promotion: move.promotion });
    const mate = board.isCheckmate();
    board.undo();
    if (mate) return move;
  }
  return null;
}

function bestMoveReason(board, move) {
  if (!move) return '';
  const piece = board.get(move.from);
  const target = board.get(move.to);
  if (move.flags && (move.flags.includes('k') || move.flags.includes('q'))) {
    return 'it tucks your king away and connects the rooks';
  }
  if (move.promotion) return 'it promotes your pawn into a new queen';
  if (target) return `it wins the ${PIECE_NAMES[target.type]} on ${move.to}`;
  if (move.flags && move.flags.includes('e')) {
    return 'it captures en passant and removes a dangerous pawn';
  }

  board.move({ from: move.from, to: move.to, promotion: move.promotion });
  const mate = board.isCheckmate();
  const check = board.isCheck();
  board.undo();
  if (mate) return 'it is checkmate';
  if (check) return 'it gives check and forces the king to react';

  const rank = Number(move.from[1]);
  if (piece && (piece.type === 'n' || piece.type === 'b') && (rank === 1 || rank === 8)) {
    return 'it develops a piece towards the centre';
  }
  if (piece && piece.type === 'p' && ['d', 'e'].includes(move.to[0])) {
    return 'it stakes a claim in the centre';
  }
  if (piece && piece.type === 'k') return 'it keeps your king safe';
  return 'it keeps your pieces active and coordinated';
}

/** Short hint sentence for the hint button. */
export function describeMove(board, move) {
  return `${sanOf(board, move)} — ${bestMoveReason(board, move)}.`;
}

export function classifyLoss(cpLoss, isBest) {
  if (isBest || cpLoss <= 15) return 'Best';
  if (cpLoss <= 60) return 'Good';
  if (cpLoss <= 130) return 'Inaccuracy';
  if (cpLoss <= 260) return 'Mistake';
  return 'Blunder';
}

function explainNegative(before, after, userMove, bestMove, label) {
  const mover = before.turn();
  const bestSan = sanOf(before, bestMove);
  const movedPiece = after.get(userMove.to);
  const hanging = hangingPiece(after, mover);

  if (hanging) {
    if (movedPiece && hanging.square === userMove.to) {
      return `Your ${PIECE_NAMES[hanging.type]} on ${hanging.square} is undefended and the ${PIECE_NAMES[hanging.attacker]} can take it. ${bestSan} avoided this.`;
    }
    if (hanging.gain >= 300) {
      return `This leaves your ${PIECE_NAMES[hanging.type]} on ${hanging.square} hanging to the ${PIECE_NAMES[hanging.attacker]}. ${bestSan} was safer.`;
    }
  }

  const mate = mateThreat(after, other(mover));
  if (mate) {
    return `Careful — this allows ${sanOf(after, mate)}, which is checkmate. ${bestSan} would have prevented it.`;
  }

  if (bestMove && before.get(bestMove.to)) {
    const captured = before.get(bestMove.to);
    if (PIECE_VALUES[captured.type] >= 300) {
      return `You missed ${bestSan}, winning the ${PIECE_NAMES[captured.type]} on ${bestMove.to}.`;
    }
  }

  if (bestMove && bestMove.promotion) {
    return `${bestSan} promotes your pawn — that was the big chance here.`;
  }

  if (movedPiece && (label === 'Mistake' || label === 'Blunder')) {
    return `${sanOf(before, userMove)} lets your ${PIECE_NAMES[movedPiece.type]} lose its job. Better was ${bestSan}, ${bestMoveReason(before, bestMove)}.`;
  }

  return `Better was ${bestSan} — ${bestMoveReason(before, bestMove)}. Your move leaves the position a little looser.`;
}

/**
 * Classify a played move and write a short explanation.
 * Mirrors engine/coach.py:review_move.
 */
export function reviewMove({
  fenBefore,
  uci,
  bestUci,
  whiteCpBefore,
  whiteCpAfterUser,
  whiteCpAfterBest,
  engine = '',
}) {
  const before = new Chess(fenBefore);
  const mover = before.turn();
  const sign = mover === 'w' ? 1 : -1;
  const userMove = fromUci(uci);
  if (!userMove) {
    return { label: 'Good', color: LABEL_COLORS.Good, explanation: 'That move could not be read.', bestSan: '', cpLoss: 0, engine };
  }

  const after = new Chess(fenBefore);
  if (before.moves({ verbose: true }).some((m) => `${m.from}${m.to}${m.promotion || ''}` === uci)) {
    after.move(userMove);
  }

  let bestMove = null;
  if (bestUci) {
    const candidate = before.moves({ verbose: true }).find((m) => `${m.from}${m.to}${m.promotion || ''}` === bestUci);
    if (candidate) bestMove = candidate;
  }

  if (before.moves().length <= 1) {
    return {
      label: 'Forced',
      color: LABEL_COLORS.Forced,
      explanation: 'This was your only legal move, so there was nothing to decide.',
      bestSan: sanOf(before, bestMove),
      cpLoss: 0,
      engine,
    };
  }

  const beforeView = sign * whiteCpBefore;
  const afterView = sign * whiteCpAfterUser;
  const bestView = sign * whiteCpAfterBest;

  const cpLoss = Math.trunc(Math.max(0, bestView - afterView));
  const isBest = Boolean(bestMove && `${bestMove.from}${bestMove.to}${bestMove.promotion || ''}` === uci);
  const label = classifyLoss(cpLoss, isBest);

  let explanation;
  if (label === 'Best') {
    const reason = bestMoveReason(before, { ...userMove, flags: userMove.flags || '' });
    explanation = reason
      ? `Top engine move — ${reason}.`
      : "That is the engine's first choice.";
    explanation = explanation.charAt(0).toUpperCase() + explanation.slice(1);
  } else if (label === 'Good') {
    const reason = bestMove ? bestMoveReason(before, bestMove) : '';
    explanation = `Solid move. ${sanOf(before, bestMove)} was marginally stronger${reason ? ` — ${reason}` : ''}, but your choice keeps the balance.`;
  } else {
    explanation = explainNegative(before, after, userMove, bestMove, label);
  }

  if (Math.abs(afterView) >= MATE - 1000 && afterView < 0) {
    explanation = `That walks into a forced mate. ${explanation}`;
  }

  return {
    label,
    color: LABEL_COLORS[label] || LABEL_COLORS.Best,
    explanation,
    bestSan: sanOf(before, bestMove),
    bestUci: bestMove ? `${bestMove.from}${bestMove.to}${bestMove.promotion || ''}` : '',
    cpLoss,
    engine,
  };
}
