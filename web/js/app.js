/**
 * Chess Coach — browser build.
 *
 * Shares the desktop app's palette, board themes, lesson curriculum, coach
 * grading and 1-100 level mapping. Rules come from the vendored chess.js.
 */

import { Chess } from './vendor/chess.js';
import { LESSONS, CATEGORIES, lessonById, lessonsIn } from './curriculum.js';
import { formatScore, describeMove } from './coach.js';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const THEMES = {
  'Classic Green': { light: '#EEEED2', dark: '#769656', border: '#4E6B3C' },
  Walnut: { light: '#F0D9B5', dark: '#B58863', border: '#7C5B40' },
  'Slate Blue': { light: '#DEE3E6', dark: '#788A9E', border: '#556577' },
};

const PIECE_VALUE = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 0 };
const DISPLAY_VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9 };
const START_COUNTS = { p: 8, n: 2, b: 2, r: 2, q: 1 };

const isLight = (file, rank) => (file + rank) % 2 === 1;
const toUci = (move) => `${move.from}${move.to}${move.promotion || ''}`;
const other = (color) => (color === 'w' ? 'b' : 'w');
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const $ = (id) => document.getElementById(id);

const settings = {
  get(key, fallback) {
    try {
      const raw = window.localStorage.getItem(`chesscoach.${key}`);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (error) {
      return fallback;
    }
  },
  set(key, value) {
    try {
      window.localStorage.setItem(`chesscoach.${key}`, JSON.stringify(value));
    } catch (error) {
      /* storage can be unavailable in private mode — the app still works */
    }
  },
};

/* ------------------------------------------------------------------ engine */

class Engine {
  constructor() {
    this.pending = new Map();
    this.seq = 0;
    this.ready = false;
    try {
      this.worker = new Worker(new URL('./ai.js', import.meta.url), { type: 'module' });
      this.worker.addEventListener('message', (event) => {
        const data = event.data || {};
        const entry = this.pending.get(data.id);
        if (!entry) return;
        this.pending.delete(data.id);
        window.clearTimeout(entry.timer);
        entry.resolve(data);
      });
      this.worker.addEventListener('error', () => this.failAll('The engine worker could not start.'));
      this.ready = true;
    } catch (error) {
      this.worker = null;
    }
  }

  failAll(reason) {
    for (const [, entry] of this.pending) {
      window.clearTimeout(entry.timer);
      entry.resolve({ error: reason });
    }
    this.pending.clear();
  }

  request(kind, payload = {}) {
    if (!this.worker) return Promise.resolve({ error: 'No engine available.' });
    const id = ++this.seq;
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(id);
        resolve({ error: 'The engine took too long.' });
      }, 25000);
      this.pending.set(id, { resolve, timer });
      this.worker.postMessage({ ...payload, kind, id });
    });
  }
}

const engine = new Engine();

/* -------------------------------------------------------------- board view */

class BoardView {
  constructor(root, options = {}) {
    this.root = root;
    this.onMove = options.onMove || (() => {});
    this.orientation = 'w';
    this.game = new Chess();
    this.interactive = true;
    this.lastMove = null;
    this.selected = null;
    this.targets = new Map();
    this.wrong = [];
    this.arrow = null;
    this.showCoords = true;
    this._drag = null;
    this._ghost = null;
    this._svg = null;
    this._bindPointer();
  }

  setPosition(fen, { lastMove = null, interactive = null, orientation = null } = {}) {
    try {
      this.game = new Chess(fen);
    } catch (error) {
      this.game = new Chess();
    }
    this.lastMove = lastMove;
    if (interactive !== null) this.interactive = interactive;
    if (orientation) this.orientation = orientation;
    this.selected = null;
    this.targets.clear();
    this.render();
  }

  setArrow(move) {
    this.arrow = move ? { from: move.from, to: move.to } : null;
    this.render();
  }

  flashWrong(squares) {
    this.wrong = squares.slice();
    this.render();
    window.setTimeout(() => {
      this.wrong = [];
      this.render();
    }, 750);
  }

  flip() {
    this.orientation = this.orientation === 'w' ? 'b' : 'w';
    this.render();
  }

  /* -- geometry --------------------------------------------------------- */
  cell(square) {
    const file = square.charCodeAt(0) - 97;
    const rank = Number(square[1]) - 1;
    return this.orientation === 'w'
      ? { x: file + 0.5, y: 7 - rank + 0.5 }
      : { x: 7 - file + 0.5, y: rank + 0.5 };
  }

  squareAtPoint(clientX, clientY) {
    const rect = this.root.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const size = rect.width / 8;
    const col = Math.floor((clientX - rect.left) / size);
    const row = Math.floor((clientY - rect.top) / size);
    if (col < 0 || col > 7 || row < 0 || row > 7) return null;
    const file = this.orientation === 'w' ? col : 7 - col;
    const rank = this.orientation === 'w' ? 7 - row : row;
    return 'abcdefgh'[file] + (rank + 1);
  }

  /* -- rendering -------------------------------------------------------- */
  render() {
    const fragment = document.createDocumentFragment();
    const checkSquare = this.game.isCheck() ? this._kingSquare(this.game.turn()) : null;
    const canInteract = this.interactive;

    for (let row = 0; row < 8; row += 1) {
      for (let col = 0; col < 8; col += 1) {
        const file = this.orientation === 'w' ? col : 7 - col;
        const rank = this.orientation === 'w' ? 7 - row : row;
        const name = 'abcdefgh'[file] + (rank + 1);
        const square = document.createElement('div');
        const classes = ['sq', isLight(file, rank) ? 'light' : 'dark'];
        if (this.lastMove && (this.lastMove.from === name || this.lastMove.to === name)) classes.push('last-move');
        if (this.selected === name) classes.push('selected');
        if (this.wrong.includes(name)) classes.push('wrong');
        if (checkSquare === name) classes.push('check');
        if (this.targets.has(name)) {
          classes.push('target');
          if (this.game.get(name)) classes.push('occupied');
        }
        if (canInteract) classes.push('can-move');
        square.className = classes.join(' ');
        square.dataset.square = name;

        const piece = this.game.get(name);
        if (piece) {
          const img = document.createElement('img');
          img.className = 'piece';
          img.src = `assets/pieces/${piece.color}${piece.type.toUpperCase()}.svg`;
          img.alt = `${piece.color === 'w' ? 'White' : 'Black'} ${piece.type}`;
          img.draggable = false;
          square.appendChild(img);
        }

        if (this.showCoords) {
          const showFile = this.orientation === 'w' ? rank === 0 : rank === 7;
          const showRank = this.orientation === 'w' ? file === 0 : file === 7;
          if (showFile) {
            const label = document.createElement('span');
            label.className = 'coord file';
            label.textContent = 'abcdefgh'[file];
            square.appendChild(label);
          }
          if (showRank) {
            const label = document.createElement('span');
            label.className = 'coord rank';
            label.textContent = String(rank + 1);
            square.appendChild(label);
          }
        }
        fragment.appendChild(square);
      }
    }

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'arrows');
    svg.setAttribute('viewBox', '0 0 8 8');
    svg.setAttribute('preserveAspectRatio', 'none');
    fragment.appendChild(svg);

    this.root.replaceChildren(fragment);
    this._svg = svg;
    this._drawArrow();
  }

  _kingSquare(color) {
    for (const row of this.game.board()) {
      for (const cell of row) {
        if (cell && cell.type === 'k' && cell.color === color) return cell.square;
      }
    }
    return null;
  }

  _drawArrow() {
    if (!this._svg || !this.arrow) return;
    const a = this.cell(this.arrow.from);
    const b = this.cell(this.arrow.to);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const length = Math.hypot(dx, dy);
    if (length < 0.4) return;
    const ux = dx / length;
    const uy = dy / length;
    const start = { x: a.x + ux * 0.24, y: a.y + uy * 0.24 };
    const tip = { x: b.x - ux * 0.2, y: b.y - uy * 0.2 };
    const shaft = { x: tip.x - ux * 0.36, y: tip.y - uy * 0.36 };
    const perp = { x: -uy, y: ux };
    const half = 0.21;

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', start.x);
    line.setAttribute('y1', start.y);
    line.setAttribute('x2', shaft.x);
    line.setAttribute('y2', shaft.y);
    line.setAttribute('stroke', 'rgba(129, 182, 76, 0.92)');
    line.setAttribute('stroke-width', '0.17');
    line.setAttribute('stroke-linecap', 'round');

    const head = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    head.setAttribute(
      'points',
      [
        `${tip.x},${tip.y}`,
        `${shaft.x + perp.x * half},${shaft.y + perp.y * half}`,
        `${shaft.x - perp.x * half},${shaft.y - perp.y * half}`,
      ].join(' '),
    );
    head.setAttribute('fill', 'rgba(129, 182, 76, 0.92)');

    this._svg.replaceChildren(line, head);
  }

  /* -- pointer ---------------------------------------------------------- */
  _bindPointer() {
    this.root.addEventListener('contextmenu', (event) => event.preventDefault());
    this.root.addEventListener('pointerdown', (event) => this._onDown(event));
    this.root.addEventListener('pointermove', (event) => this._onMove(event));
    this.root.addEventListener('pointerup', (event) => this._onUp(event));
    this.root.addEventListener('pointercancel', () => this._endDrag());
  }

  _ownPiece(square) {
    const piece = this.game.get(square);
    return piece && piece.color === this.game.turn();
  }

  _onDown(event) {
    if (event.button !== 0 || !this.interactive) return;
    const square = this.squareAtPoint(event.clientX, event.clientY);
    if (!square) return;

    if (this.selected && this.targets.has(square)) {
      const from = this.selected;
      this.selected = null;
      this.targets.clear();
      this.render();
      this.onMove(from, square);
      return;
    }

    if (this._ownPiece(square)) {
      this.selected = square;
      this.targets = new Map(
        this.game
          .moves({ square, verbose: true })
          .map((move) => [move.to, move]),
      );
      this._drag = { from: square, x: event.clientX, y: event.clientY, active: false };
      try {
        this.root.setPointerCapture(event.pointerId);
      } catch (error) {
        /* capture is best effort */
      }
      this.render();
      return;
    }

    if (this.selected) {
      this.selected = null;
      this.targets.clear();
      this.render();
    }
  }

  _onMove(event) {
    if (!this._drag) return;
    const distance = Math.hypot(event.clientX - this._drag.x, event.clientY - this._drag.y);
    if (!this._drag.active && distance > 4) {
      this._drag.active = true;
      const img = this.root.querySelector(`[data-square="${this._drag.from}"] .piece`);
      if (img) {
        img.classList.add('is-dragging');
        const rect = this.root.getBoundingClientRect();
        const ghost = img.cloneNode();
        ghost.classList.remove('is-dragging');
        ghost.classList.add('drag-ghost');
        ghost.style.width = `${rect.width / 8}px`;
        ghost.style.height = `${rect.width / 8}px`;
        document.body.appendChild(ghost);
        this._ghost = ghost;
      }
    }
    if (this._drag.active && this._ghost) {
      this._ghost.style.left = `${event.clientX}px`;
      this._ghost.style.top = `${event.clientY}px`;
    }
  }

  _onUp(event) {
    const drag = this._drag;
    this._drag = null;
    this._endDrag();
    if (!drag) return;
    if (!drag.active) return;

    const square = this.squareAtPoint(event.clientX, event.clientY);
    this.selected = null;
    this.targets.clear();
    this.render();
    if (square && square !== drag.from) this.onMove(drag.from, square);
  }

  _endDrag() {
    if (this._ghost && this._ghost.parentNode) this._ghost.parentNode.removeChild(this._ghost);
    this._ghost = null;
  }
}

/* --------------------------------------------------------------- utilities */

function formatClock(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value >= 20) {
    const minutes = Math.floor(value / 60);
    const rest = Math.floor(value % 60);
    return `${minutes}:${String(rest).padStart(2, '0')}`;
  }
  return value.toFixed(1);
}

function tierFor(level) {
  if (level <= 20) return 'Beginner';
  if (level <= 40) return 'Casual';
  if (level <= 60) return 'Intermediate';
  if (level <= 80) return 'Advanced';
  return 'Master';
}

function eloFor(level) {
  const value = 400 * Math.pow(3000 / 400, (level - 1) / 99);
  return Math.round(value / 25) * 25;
}

/* ------------------------------------------------------------------ state */

const prefs = {
  level: clamp(Number(settings.get('level', 40)) || 40, 1, 100),
  side: settings.get('side', 'White'),
  time: settings.get('time', 'Untimed'),
  theme: THEMES[settings.get('theme', 'Classic Green')] ? settings.get('theme', 'Classic Green') : 'Classic Green',
  evalOn: settings.get('eval', true) !== false,
  coachOn: settings.get('coach', true) !== false,
};

const game = {
  chess: new Chess(),
  human: 'w',
  level: prefs.level,
  time: prefs.time,
  clocks: null,
  increment: 0,
  active: false,
  thinking: false,
  coachEnabled: prefs.coachOn,
  history: [],
  viewPly: null,
  generation: 0,
  lastTick: 0,
};

const ui = {
  board: $('board'),
  barTop: $('bar-top'),
  barBottom: $('bar-bottom'),
  evalBar: $('eval-bar'),
  evalFill: $('eval-fill'),
  promotion: $('promotion'),
  promotionOptions: $('promotion-options'),
  promotionCancel: $('promotion-cancel'),
  level: $('level'),
  levelValue: $('level-value'),
  levelTier: $('level-tier'),
  levelElo: $('level-elo'),
  sideSeg: $('side-seg'),
  timeSeg: $('time-seg'),
  newGame: $('new-game'),
  engineBadge: $('engine-badge'),
  coachToggle: $('coach-toggle'),
  coachCard: $('coach-card'),
  coachLabel: $('coach-label'),
  coachText: $('coach-text'),
  hint: $('hint'),
  takeback: $('takeback'),
  moves: $('moves'),
  live: $('live'),
  flip: $('flip'),
  resign: $('resign'),
  toast: $('toast'),
  railDot: $('rail-dot'),
  themes: $('themes'),
  evalToggle: $('eval-toggle'),
  coachDefault: $('coach-default'),
  engineName: $('engine-name'),
  lessonBrowser: $('lesson-browser'),
  lessonGrid: $('lesson-grid'),
  lessonTabs: $('lesson-tabs'),
  lessonProgress: $('lesson-progress'),
  lessonRunner: $('lesson-runner'),
  lessonBoard: $('lesson-board'),
  lessonTitle: $('lesson-title'),
  lessonSummary: $('lesson-summary'),
  lessonGoal: $('lesson-goal'),
  lessonStep: $('lesson-step'),
  lessonMinutes: $('lesson-minutes'),
  lessonNote: $('lesson-note'),
  lessonNoteLabel: $('lesson-note-label'),
  lessonNoteText: $('lesson-note-text'),
  lessonHint: $('lesson-hint'),
  lessonRestart: $('lesson-restart'),
  lessonNext: $('lesson-next'),
  lessonBack: $('lesson-back'),
  lessonTip: $('lesson-tip'),
};

const board = new BoardView(ui.board, { onMove: onBoardMove });

let toastTimer = 0;
function toast(text) {
  ui.toast.textContent = text;
  ui.toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    ui.toast.hidden = true;
  }, 2600);
}

function setEngineBusy(busy) {
  ui.railDot.classList.toggle('is-busy', Boolean(busy));
  ui.railDot.classList.toggle('is-ready', !busy);
}

function applyTheme(name) {
  const theme = THEMES[name] || THEMES['Classic Green'];
  prefs.theme = THEMES[name] ? name : 'Classic Green';
  document.documentElement.style.setProperty('--theme-light', theme.light);
  document.documentElement.style.setProperty('--theme-dark', theme.dark);
  for (const button of ui.themes.querySelectorAll('.theme-btn')) {
    button.classList.toggle('is-active', button.dataset.theme === prefs.theme);
  }
  settings.set('theme', prefs.theme);
}

/* ------------------------------------------------------------------- eval */

function setEval(whiteCp, mate = null) {
  const ratio = mate !== null && mate !== undefined
    ? (mate > 0 ? 0.985 : 0.015)
    : 1 / (1 + Math.pow(10, -whiteCp / 400));
  ui.evalFill.style.height = `${(ratio * 100).toFixed(1)}%`;
  ui.evalBar.title = `Evaluation ${formatScore(whiteCp, mate)}`;
  ui.evalBar.classList.toggle('is-flipped', board.orientation === 'b');
}

async function requestEval() {
  if (!game.active) return;
  const generation = game.generation;
  const fen = game.chess.fen();
  setEngineBusy(true);
  const data = await engine.request('analysis', { fen, depth: 3, budget: 1200 });
  setEngineBusy(false);
  if (generation !== game.generation || data.error) return;
  setEval(data.whiteCp, data.mate);
}

/* ---------------------------------------------------------------- cloning */

function capturedBy(color) {
  const enemy = other(color);
  const counts = { p: 0, n: 0, b: 0, r: 0, q: 0 };
  for (const row of game.chess.board()) {
    for (const cell of row) {
      if (cell && cell.color === enemy && cell.type !== 'k') counts[cell.type] += 1;
    }
  }
  const pieces = [];
  for (const type of ['p', 'n', 'b', 'r', 'q']) {
    const missing = Math.max(0, START_COUNTS[type] - counts[type]);
    for (let index = 0; index < missing; index += 1) pieces.push(`${enemy}${type.toUpperCase()}`);
  }
  return pieces;
}

function materialAdvantage(color) {
  const mine = capturedBy(color).reduce((total, symbol) => total + DISPLAY_VALUE[symbol[1].toLowerCase()], 0);
  const theirs = capturedBy(other(color)).reduce((total, symbol) => total + DISPLAY_VALUE[symbol[1].toLowerCase()], 0);
  return mine - theirs;
}

/* --------------------------------------------------------------- rendering */

function renderBar(element, color) {
  const isHuman = color === game.human;
  const avatar = `${color}${isHuman ? 'K' : 'N'}`;
  const captured = capturedBy(color);
  const advantage = materialAdvantage(color);
  const clock = game.clocks ? game.clocks[color] : null;

  const capturedHtml = captured
    .map((symbol) => `<img src="assets/pieces/${symbol}.svg" alt="">`)
    .join('');

  element.className = 'player-bar';
  if (game.active && game.chess.turn() === color) element.classList.add('is-turn');
  element.innerHTML = `
    <div class="player-avatar"><img src="assets/pieces/${avatar}.svg" alt=""></div>
    <div class="player-main">
      <span class="player-name">${isHuman ? 'You' : `Computer · Lv ${game.level}`}</span>
      <div class="player-meta">
        <span class="captured">${capturedHtml}</span>
        ${advantage > 0 ? `<span class="material-diff">+${advantage}</span>` : ''}
      </div>
    </div>
    ${clock === null ? '' : `<span class="clock${clock < 20 ? ' is-low' : ''}">${formatClock(clock)}</span>`}
  `;
}

function renderPlayers() {
  renderBar(ui.barBottom, game.human);
  renderBar(ui.barTop, other(game.human));
}

function moveButton(entry, ply) {
  const current = game.viewPly === ply ? ' is-current' : '';
  return `<button type="button" class="move-btn${current}" data-ply="${ply}">${entry.san}</button>`;
}

function renderMoves() {
  if (!game.history.length) {
    ui.moves.innerHTML = '<p class="muted small">No moves yet.</p>';
    ui.live.hidden = true;
    return;
  }
  const rows = [];
  for (let index = 0; index < game.history.length; index += 2) {
    const white = game.history[index];
    const black = game.history[index + 1];
    rows.push(`<span class="number">${index / 2 + 1}.</span>`);
    rows.push(moveButton(white, index + 1));
    rows.push(black ? moveButton(black, index + 2) : '<span></span>');
  }
  ui.moves.innerHTML = rows.join('');
  ui.live.hidden = game.viewPly === null;
}

function renderBoard() {
  const viewing = game.viewPly !== null;
  let fen = game.chess.fen();
  let last = game.history[game.history.length - 1] || null;
  if (viewing) {
    fen = game.viewPly === 0 ? START_FEN : game.history[game.viewPly - 1].fenAfter;
    last = game.viewPly > 0 ? game.history[game.viewPly - 1] : null;
  }
  const humanTurn = game.active && !game.thinking && !viewing && game.chess.turn() === game.human;
  board.setPosition(fen, {
    lastMove: last ? { from: last.from, to: last.to } : null,
    interactive: humanTurn,
  });
  ui.evalBar.classList.toggle('is-flipped', board.orientation === 'b');
}

function renderControls() {
  const canAct = game.active && !game.thinking && game.viewPly === null && game.chess.turn() === game.human;
  ui.hint.disabled = !canAct;
  ui.takeback.disabled = !game.active || game.thinking || !game.history.length;
  ui.resign.disabled = !game.active;
}

function renderAll() {
  renderBoard();
  renderPlayers();
  renderMoves();
  renderControls();
}

function setCoach(label, text, tone = 'idle') {
  ui.coachLabel.textContent = label;
  ui.coachText.textContent = text;
  ui.coachCard.className = `verdict${tone === 'idle' ? '' : ` is-${tone}`}`;
}

function verdictTone(label) {
  if (label === 'Best' || label === 'Good') return 'good';
  if (label === 'Inaccuracy') return 'warn';
  if (label === 'Mistake' || label === 'Blunder') return 'bad';
  return 'idle';
}

/* ------------------------------------------------------------- game engine */

function checkGameOver() {
  const chess = game.chess;
  let text = '';
  let tone = 'idle';
  let label = 'Game over';

  if (chess.isCheckmate()) {
    const winnerIsWhite = chess.turn() === 'b';
    const humanWon = winnerIsWhite === (game.human === 'w');
    text = `Checkmate — ${winnerIsWhite ? 'White' : 'Black'} wins.`;
    tone = humanWon ? 'good' : 'bad';
    label = humanWon ? 'You won' : 'Checkmate';
  } else if (chess.isStalemate()) {
    text = 'Stalemate — the game is drawn.';
    label = 'Draw';
  } else if (chess.isInsufficientMaterial()) {
    text = 'Draw — neither side has enough material to mate.';
    label = 'Draw';
  } else if (chess.isThreefoldRepetition()) {
    text = 'Draw — the same position appeared three times.';
    label = 'Draw';
  } else if (chess.isDraw()) {
    text = 'Draw — the fifty-move rule applies.';
    label = 'Draw';
  }

  if (!text) return false;
  game.active = false;
  game.thinking = false;
  game.generation += 1;
  setCoach(label, text, tone);
  renderAll();
  return true;
}

function playMove(move, byHuman) {
  const chess = game.chess;
  const color = chess.turn();
  const fenBefore = chess.fen();
  const applied = chess.move({ from: move.from, to: move.to, promotion: move.promotion });
  if (!applied) return;

  game.history.push({
    san: applied.san,
    uci: toUci(applied),
    color,
    fenBefore,
    fenAfter: chess.fen(),
    from: applied.from,
    to: applied.to,
  });
  game.viewPly = null;
  if (game.clocks) game.clocks[color] += game.increment;
  board.setArrow(null);
  game.thinking = false;
  renderAll();

  if (checkGameOver()) return;

  const generation = game.generation;
  if (byHuman) {
    if (game.coachEnabled) reviewAndContinue(fenBefore, toUci(applied), generation);
    else {
      requestEval();
      maybeAiMove(generation);
    }
  } else {
    requestEval();
  }
}

function reviewAndContinue(fenBefore, uci, generation) {
  setCoach('Thinking', 'Reviewing your move…', 'idle');
  let finished = false;
  const safety = window.setTimeout(() => {
    if (finished || generation !== game.generation) return;
    finished = true;
    maybeAiMove(generation);
  }, 12000);

  setEngineBusy(true);
  engine.request('review', { fen: fenBefore, uci }).then((data) => {
    if (finished || generation !== game.generation) return;
    finished = true;
    window.clearTimeout(safety);
    setEngineBusy(false);
    if (data.verdict) showVerdict(data.verdict);
    else setCoach('Coach', 'The engine could not review that move.', 'idle');
    maybeAiMove(generation);
  });
}

function showVerdict(verdict) {
  setCoach(verdict.label, verdict.explanation, verdictTone(verdict.label));
  if (verdict.label === 'Inaccuracy' || verdict.label === 'Mistake' || verdict.label === 'Blunder') {
    if (verdict.bestUci && game.viewPly === null) {
      board.setArrow({
        from: verdict.bestUci.slice(0, 2),
        to: verdict.bestUci.slice(2, 4),
      });
    }
  } else {
    board.setArrow(null);
  }
}

function maybeAiMove(generation) {
  if (generation !== game.generation) return;
  if (!game.active || game.chess.turn() === game.human) {
    renderAll();
    return;
  }
  if (game.thinking) return;
  game.thinking = true;
  renderAll();
  window.setTimeout(() => requestAiMove(generation), 260);
}

async function requestAiMove(generation) {
  if (generation !== game.generation) return;
  if (!game.active || game.chess.turn() === game.human) {
    game.thinking = false;
    renderAll();
    return;
  }
  const snapshot = game.chess.fen();
  setEngineBusy(true);
  const data = await engine.request('move', { fen: snapshot, level: game.level });
  setEngineBusy(false);
  if (generation !== game.generation) return;
  game.thinking = false;
  if (!game.active || game.chess.fen() !== snapshot) {
    renderAll();
    return;
  }
  const legal = game.chess.moves({ verbose: true });
  const chosen = legal.find((move) => toUci(move) === data.uci) || legal[Math.floor(Math.random() * legal.length)];
  if (chosen) playMove(chosen, false);
  else renderAll();
}

function onBoardMove(from, to) {
  if (game.viewPly !== null) {
    toast('You are reviewing an earlier position — go back to live.');
    return;
  }
  if (!game.active || game.thinking || game.chess.turn() !== game.human) return;

  const options = game.chess.moves({ square: from, verbose: true }).filter((move) => move.to === to);
  if (!options.length) return;

  if (options.some((move) => move.promotion)) {
    askPromotion(options.map((move) => move.promotion)).then((choice) => {
      if (!choice) {
        renderAll();
        return;
      }
      const pick = options.find((move) => move.promotion === choice) || options[0];
      playMove(pick, true);
    });
    return;
  }
  playMove(options[0], true);
}

function askPromotion(types) {
  return new Promise((resolve) => {
    ui.promotion.hidden = false;
    ui.promotionOptions.replaceChildren();
    for (const type of types) {
      const button = document.createElement('button');
      button.type = 'button';
      const img = document.createElement('img');
      img.src = `assets/pieces/${game.human}${type.toUpperCase()}.svg`;
      img.alt = type;
      button.appendChild(img);
      button.addEventListener('click', () => close(type));
      ui.promotionOptions.appendChild(button);
    }
    const cancel = () => close(null);
    ui.promotionCancel.addEventListener('click', cancel);
    function close(choice) {
      ui.promotion.hidden = true;
      ui.promotionOptions.replaceChildren();
      ui.promotionCancel.removeEventListener('click', cancel);
      resolve(choice);
    }
  });
}

/* ------------------------------------------------------------ game actions */

function startNewGame() {
  game.generation += 1;
  const side = ui.sideSeg.querySelector('.is-active').dataset.value;
  game.human = side === 'Random' ? (Math.random() < 0.5 ? 'w' : 'b') : side === 'Black' ? 'b' : 'w';
  game.level = clamp(Number(ui.level.value) || 40, 1, 100);
  game.time = ui.timeSeg.querySelector('.is-active').dataset.value;
  game.chess = new Chess();
  game.history = [];
  game.viewPly = null;
  game.active = true;
  game.thinking = false;
  game.clocks = game.time === '3+2'
    ? { w: 180, b: 180 }
    : game.time === '10+0'
      ? { w: 600, b: 600 }
      : null;
  game.increment = game.time === '3+2' ? 2 : 0;
  game.lastTick = performance.now();

  prefs.level = game.level;
  prefs.side = side;
  prefs.time = game.time;
  settings.set('level', game.level);
  settings.set('side', side);
  settings.set('time', game.time);

  board.orientation = game.human;
  board.setArrow(null);
  ui.evalBar.classList.toggle('is-flipped', game.human === 'b');
  setEval(0, null);
  board.setPosition(game.chess.fen(), { interactive: game.human === 'w' });
  setCoach('Ready', game.human === 'w' ? 'Make a move and I’ll tell you what I think of it.' : 'You are playing Black — the engine opens.', 'idle');
  renderAll();

  const generation = game.generation;
  if (game.chess.turn() === game.human) requestEval();
  else maybeAiMove(generation);
}

function takeback() {
  if (game.thinking || !game.history.length) return;
  game.generation += 1;
  game.active = true;
  game.thinking = false;
  game.viewPly = null;
  board.setArrow(null);

  let popped = 0;
  while (game.history.length && popped < 2) {
    try {
      game.chess.undo();
    } catch (error) {
      break;
    }
    game.history.pop();
    popped += 1;
    if (game.chess.turn() === game.human) break;
  }

  setCoach('Ready', 'Move taken back. Try something else.', 'idle');
  renderAll();
  const generation = game.generation;
  if (game.chess.turn() === game.human) requestEval();
  else maybeAiMove(generation);
}

async function askHint() {
  if (!game.active || game.thinking || game.chess.turn() !== game.human || game.viewPly !== null) return;
  const generation = game.generation;
  const fen = game.chess.fen();
  setCoach('Thinking', 'Looking for the best idea…', 'idle');
  setEngineBusy(true);
  const data = await engine.request('hint', { fen });
  setEngineBusy(false);
  if (generation !== game.generation) return;
  if (!data.uci) {
    setCoach('Coach', 'No hint available in this position.', 'idle');
    return;
  }
  const snapshot = new Chess(fen);
  const move = snapshot.moves({ verbose: true }).find((candidate) => toUci(candidate) === data.uci);
  if (!move) {
    setCoach('Coach', 'No hint available in this position.', 'idle');
    return;
  }
  setCoach('Hint', describeMove(snapshot, move), 'good');
  board.setArrow({ from: move.from, to: move.to });
}

function resign() {
  if (!game.active) return;
  if (!window.confirm('Resign this game? The result will stand.')) return;
  game.generation += 1;
  game.active = false;
  game.thinking = false;
  setCoach('Resigned', 'You resigned — the engine wins this one.', 'bad');
  renderAll();
}

/* ------------------------------------------------------------------ clocks */

window.setInterval(() => {
  const now = performance.now();
  const delta = (now - game.lastTick) / 1000;
  game.lastTick = now;
  if (!game.clocks || !game.active || game.viewPly !== null) return;

  const turn = game.chess.turn();
  game.clocks[turn] = Math.max(0, game.clocks[turn] - Math.max(0, delta));
  if (game.clocks[turn] <= 0) {
    game.active = false;
    game.thinking = false;
    game.generation += 1;
    const humanLost = turn === game.human;
    setCoach('Flag', humanLost ? 'You ran out of time.' : 'The engine ran out of time — you win.', humanLost ? 'bad' : 'good');
    renderAll();
    return;
  }
  renderPlayers();
}, 200);

/* ------------------------------------------------------------------- learn */

const lessons = {
  current: null,
  step: 0,
  token: 0,
  filter: 'All',
  completed: new Set(Array.isArray(settings.get('lessons', [])) ? settings.get('lessons', []) : []),
};

const lessonBoard = new BoardView(ui.lessonBoard, { onMove: onLessonMove });

function renderLessonTabs() {
  const tabs = ['All', ...CATEGORIES];
  ui.lessonTabs.innerHTML = tabs
    .map(
      (name) =>
        `<button type="button" class="${name === lessons.filter ? 'is-active' : ''}" data-tab="${name}">${name}</button>`,
    )
    .join('');
}

function renderLessonGrid() {
  const items = lessons.filter === 'All' ? LESSONS : lessonsIn(lessons.filter);
  ui.lessonGrid.innerHTML = items
    .map((lesson) => {
      const done = lessons.completed.has(lesson.id);
      return `
        <button type="button" class="lesson-card${done ? ' is-done' : ''}" data-lesson="${lesson.id}">
          <span class="lesson-top">
            <h3>${lesson.title}</h3>
            ${done ? '<span class="done-dot">✓</span>' : ''}
          </span>
          <p>${lesson.summary}</p>
          <span class="lesson-foot">
            <span>${lesson.category}</span>
            <span>${lesson.minutes} min · ${lesson.steps.length} step${lesson.steps.length > 1 ? 's' : ''}</span>
          </span>
        </button>`;
    })
    .join('');
}

function renderLessonProgress() {
  ui.lessonProgress.textContent = `${lessons.completed.size} / ${LESSONS.length} complete`;
}

function lessonMessage(label, text, tone = 'idle') {
  ui.lessonNoteLabel.textContent = label;
  ui.lessonNoteText.textContent = text;
  ui.lessonNote.className = `verdict${tone === 'idle' ? '' : ` is-${tone}`}`;
}

function openLesson(id) {
  const lesson = lessonById(id);
  if (!lesson) return;
  lessons.current = lesson;
  lessons.step = 0;
  lessons.token += 1;
  lessons.filter = lessons.filter === 'All' ? 'All' : lessons.filter;

  ui.lessonBrowser.hidden = true;
  ui.lessonRunner.hidden = false;
  ui.lessonTitle.textContent = lesson.title;
  ui.lessonSummary.textContent = lesson.summary;
  ui.lessonGoal.textContent = lesson.goal;
  ui.lessonTip.textContent = lesson.tip;
  ui.lessonMinutes.textContent = `${lesson.minutes} min · ${lesson.category}`;
  ui.lessonNext.hidden = true;
  lessonBoard.setArrow(null);
  lessonBoard.setPosition(lesson.fen, { interactive: true, orientation: 'w' });
  showLessonStep();
}

function showLessonStep() {
  const lesson = lessons.current;
  if (!lesson) return;
  const total = lesson.steps.length;
  if (lessons.step >= total) return;
  ui.lessonStep.textContent = `Step ${lessons.step + 1} of ${total}`;
  lessonMessage('Your move', 'Find the move the lesson is asking for.');
  ui.lessonNext.hidden = true;
  lessonBoard.setPosition(lessonBoard.game.fen(), { interactive: true });
}

function expectedMove(step) {
  const uci = step.moves[0];
  return { from: uci.slice(0, 2), to: uci.slice(2, 4) };
}

function onLessonMove(from, to) {
  const lesson = lessons.current;
  if (!lesson) return;
  const step = lesson.steps[lessons.step];
  if (!step) return;

  const chess = lessonBoard.game;
  const options = chess.moves({ square: from, verbose: true }).filter((move) => move.to === to);
  if (!options.length) return;

  const chosen = options.find((move) => step.moves.includes(toUci(move)));
  if (!chosen) {
    lessonBoard.flashWrong([from, to]);
    lessonMessage('Not quite', 'That move is legal but not the point of this lesson. Try the hint.', 'warn');
    return;
  }

  chess.move({ from: chosen.from, to: chosen.to, promotion: chosen.promotion });
  lessonBoard.setArrow(null);
  lessonBoard.setPosition(chess.fen(), {
    lastMove: { from: chosen.from, to: chosen.to },
    interactive: false,
  });
  lessonMessage('Correct', step.success || 'That is the move.', 'good');

  const token = ++lessons.token;
  window.setTimeout(() => {
    if (token !== lessons.token || lessons.current !== lesson) return;

    if (step.reply) {
      const reply = chess.moves({ verbose: true }).find((move) => toUci(move) === step.reply);
      if (reply) {
        chess.move({ from: reply.from, to: reply.to, promotion: reply.promotion });
        lessonBoard.setPosition(chess.fen(), {
          lastMove: { from: reply.from, to: reply.to },
          interactive: false,
        });
      }
    }

    lessons.step += 1;
    if (lessons.step >= lesson.steps.length) finishLesson();
    else showLessonStep();
  }, step.reply ? 750 : 950);
}

function finishLesson() {
  const lesson = lessons.current;
  if (!lesson) return;
  ui.lessonStep.textContent = 'Complete';
  lessonMessage('Lesson complete', lesson.finish, 'good');
  lessons.completed.add(lesson.id);
  settings.set('lessons', [...lessons.completed]);
  renderLessonGrid();
  renderLessonProgress();

  const index = LESSONS.findIndex((item) => item.id === lesson.id);
  const next = LESSONS[index + 1];
  ui.lessonNext.hidden = false;
  ui.lessonNext.textContent = next ? 'Next lesson' : 'Back to lessons';
  ui.lessonNext.dataset.next = next ? next.id : '';
}

function closeLesson() {
  lessons.token += 1;
  lessons.current = null;
  ui.lessonRunner.hidden = true;
  ui.lessonBrowser.hidden = false;
}

function nextLesson() {
  const id = ui.lessonNext.dataset.next;
  if (id) openLesson(id);
  else closeLesson();
}

function lessonHint() {
  const lesson = lessons.current;
  if (!lesson) return;
  const step = lesson.steps[lessons.step];
  if (!step) return;
  const target = expectedMove(step);
  lessonMessage('Hint', step.hint, 'good');
  lessonBoard.setArrow(target);
}

function restartLesson() {
  const lesson = lessons.current;
  if (!lesson) return;
  openLesson(lesson.id);
}

/* ---------------------------------------------------------------- settings */

function renderThemeButtons() {
  ui.themes.innerHTML = Object.entries(THEMES)
    .map(([name, theme]) => {
      const cells = Array.from({ length: 8 }, (_, index) => {
        const light = (Math.floor(index / 4) + (index % 4)) % 2 === 0;
        return `<span style="background:${light ? theme.light : theme.dark}"></span>`;
      }).join('');
      return `<button type="button" class="theme-btn${name === prefs.theme ? ' is-active' : ''}" data-theme="${name}">
        <span class="swatch">${cells}</span>${name}
      </button>`;
    })
    .join('');
}

/* -------------------------------------------------------------------- wire */

function showPage(name) {
  for (const page of document.querySelectorAll('.page')) {
    page.classList.toggle('is-active', page.id === `page-${name}`);
  }
  for (const button of document.querySelectorAll('.nav-btn')) {
    button.classList.toggle('is-active', button.dataset.page === name);
  }
}

function wire() {
  for (const button of document.querySelectorAll('.nav-btn')) {
    button.addEventListener('click', () => showPage(button.dataset.page));
  }

  ui.newGame.addEventListener('click', startNewGame);
  ui.hint.addEventListener('click', askHint);
  ui.takeback.addEventListener('click', takeback);
  ui.resign.addEventListener('click', resign);
  ui.flip.addEventListener('click', () => {
    board.flip();
    setEval(0, null);
    renderBoard();
  });
  ui.live.addEventListener('click', () => {
    game.viewPly = null;
    renderAll();
  });

  ui.moves.addEventListener('click', (event) => {
    const button = event.target.closest('.move-btn');
    if (!button) return;
    const ply = Number(button.dataset.ply);
    game.viewPly = game.viewPly === ply ? null : ply;
    renderAll();
  });

  ui.level.addEventListener('input', () => {
    const level = clamp(Number(ui.level.value) || 1, 1, 100);
    ui.levelValue.textContent = String(level);
    ui.levelTier.textContent = tierFor(level);
    ui.levelElo.textContent = `~${eloFor(level)} Elo`;
    ui.level.style.setProperty('--fill', `${level}%`);
    game.level = level;
    prefs.level = level;
    settings.set('level', level);
    renderPlayers();
    ui.engineBadge.textContent = `Lv ${level}`;
  });

  for (const segment of [ui.sideSeg, ui.timeSeg]) {
    segment.addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      for (const sibling of segment.querySelectorAll('button')) {
        sibling.classList.toggle('is-active', sibling === button);
      }
    });
  }

  ui.coachToggle.addEventListener('change', () => {
    game.coachEnabled = ui.coachToggle.checked;
    if (!game.coachEnabled) {
      board.setArrow(null);
      setCoach('Coach off', 'Turn the coach back on to get move reviews.', 'idle');
    } else {
      setCoach('Ready', 'Make a move and I’ll tell you what I think of it.', 'idle');
    }
  });

  ui.themes.addEventListener('click', (event) => {
    const button = event.target.closest('.theme-btn');
    if (button) applyTheme(button.dataset.theme);
  });

  ui.evalToggle.addEventListener('change', () => {
    prefs.evalOn = ui.evalToggle.checked;
    ui.evalBar.classList.toggle('is-hidden', !prefs.evalOn);
    settings.set('eval', prefs.evalOn);
  });

  ui.coachDefault.addEventListener('change', () => {
    prefs.coachOn = ui.coachDefault.checked;
    settings.set('coach', prefs.coachOn);
    game.coachEnabled = prefs.coachOn;
    ui.coachToggle.checked = prefs.coachOn;
  });

  ui.lessonTabs.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-tab]');
    if (!button) return;
    lessons.filter = button.dataset.tab;
    renderLessonTabs();
    renderLessonGrid();
  });

  ui.lessonGrid.addEventListener('click', (event) => {
    const card = event.target.closest('.lesson-card');
    if (card) openLesson(card.dataset.lesson);
  });

  ui.lessonBack.addEventListener('click', closeLesson);
  ui.lessonHint.addEventListener('click', lessonHint);
  ui.lessonRestart.addEventListener('click', restartLesson);
  ui.lessonNext.addEventListener('click', nextLesson);
}

function boot() {
  ui.level.value = String(prefs.level);
  ui.levelValue.textContent = String(prefs.level);
  ui.levelTier.textContent = tierFor(prefs.level);
  ui.levelElo.textContent = `~${eloFor(prefs.level)} Elo`;
  ui.level.style.setProperty('--fill', `${prefs.level}%`);
  ui.engineBadge.textContent = `Lv ${prefs.level}`;
  game.level = prefs.level;
  game.coachEnabled = prefs.coachOn;

  for (const segment of [ui.sideSeg, ui.timeSeg]) {
    for (const button of segment.querySelectorAll('button')) {
      button.classList.toggle('is-active', button.dataset.value === (segment === ui.sideSeg ? prefs.side : prefs.time));
    }
  }

  ui.coachToggle.checked = game.coachEnabled;
  ui.evalToggle.checked = prefs.evalOn;
  ui.coachDefault.checked = prefs.coachOn;
  ui.evalBar.classList.toggle('is-hidden', !prefs.evalOn);

  renderThemeButtons();
  applyTheme(prefs.theme);
  renderLessonTabs();
  renderLessonGrid();
  renderLessonProgress();

  ui.engineName.textContent = engine.ready ? 'Web engine · ready' : 'Web engine · unavailable';
  ui.railDot.classList.toggle('is-ready', engine.ready);
  ui.engineBadge.textContent = engine.ready ? `Lv ${prefs.level}` : 'Offline';

  wire();
  startNewGame();
}

boot();
