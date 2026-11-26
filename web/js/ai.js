/**
 * Web worker that owns all searching, so the board never blocks.
 * Message kinds: move, analysis, hint, review.
 */

import { Chess } from './vendor/chess.js';
import { analyse, chooseMove, fromUci } from './engine.js';
import { reviewMove } from './coach.js';

function analyseAfter(fen, uci, depth, budget) {
  const board = new Chess(fen);
  const move = fromUci(uci);
  if (move) {
    try {
      board.move(move);
    } catch (error) {
      /* illegal or stale move — analyse the position as it stands */
    }
  }
  return analyse(board.fen(), depth, budget);
}

self.addEventListener('message', (event) => {
  const message = event.data || {};
  const { id, kind } = message;
  try {
    if (kind === 'move') {
      const uci = chooseMove(message.fen, message.level);
      self.postMessage({ id, kind, uci, engine: 'Web engine' });
      return;
    }

    if (kind === 'analysis') {
      const result = analyse(message.fen, message.depth ?? 3, message.budget ?? 1300);
      self.postMessage({ id, kind, ...result });
      return;
    }

    if (kind === 'hint') {
      const result = analyse(message.fen, 3, 1500);
      self.postMessage({ id, kind, uci: result.bestUci, engine: result.engine });
      return;
    }

    if (kind === 'review') {
      const before = analyse(message.fen, 3, 900);
      const afterUser = analyseAfter(message.fen, message.uci, 2, 500);
      const afterBest = message.bestUci
        ? analyseAfter(message.fen, before.bestUci, 2, 500)
        : afterUser;

      const verdict = reviewMove({
        fenBefore: message.fen,
        uci: message.uci,
        bestUci: before.bestUci,
        whiteCpBefore: before.whiteCp,
        whiteCpAfterUser: afterUser.whiteCp,
        whiteCpAfterBest: afterBest.whiteCp,
        engine: before.engine,
      });
      self.postMessage({ id, kind, verdict });
      return;
    }

    self.postMessage({ id, kind, error: `Unknown request: ${kind}` });
  } catch (error) {
    self.postMessage({ id, kind, error: String((error && error.message) || error) });
  }
});
