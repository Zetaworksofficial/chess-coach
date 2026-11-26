/**
 * Browser copy of lessons/curriculum.py.
 *
 * Every lesson starts from a real FEN and expects concrete UCI moves. A step may
 * script an opponent reply so a whole idea can be walked through.
 */

export const FUNDAMENTALS = 'Fundamentals';
export const TACTICS = 'Tactics';
export const ENDGAMES = 'Checkmates & Endgames';

export const CATEGORIES = [FUNDAMENTALS, TACTICS, ENDGAMES];

/** @type {Array<{id:string,category:string,title:string,summary:string,fen:string,goal:string,steps:Array<{moves:string[],hint:string,reply?:string,success?:string}>,finish:string,tip:string,minutes:number,tags:string[]}>} */
export const LESSONS = [
  {
    id: 'rook-slide',
    category: FUNDAMENTALS,
    title: 'Meet the Rook',
    summary: 'Straight lines, long range: how a rook moves and checks.',
    fen: '4k3/8/8/8/8/8/8/R3K3 w - - 0 1',
    goal: 'Rooks move any number of squares along a rank or file. Send your rook to a8 to give check.',
    steps: [
      {
        moves: ['a1a8'],
        hint: 'Slide the rook all the way up the a-file to the eighth rank.',
        success: 'Ra8+ — the rook sweeps the whole back rank and checks the king.',
      },
    ],
    finish:
      'A rook on the seventh or eighth rank is a monster: it cuts the enemy king off and attacks from behind.',
    tip: 'Rooks belong on open files, not behind their own pawns.',
    minutes: 3,
    tags: ['pieces', 'checks'],
  },
  {
    id: 'bishop-diagonal',
    category: FUNDAMENTALS,
    title: "The Bishop's Diagonal",
    summary: 'Bishops only ever travel on diagonals of their own colour.',
    fen: '4k3/8/7n/8/8/8/8/2B1K3 w - - 0 1',
    goal: 'Bishops never leave their colour. Capture the knight on h6 with your bishop.',
    steps: [
      {
        moves: ['c1h6'],
        hint: 'c1, d2, e3, f4, g5, h6 — one clean diagonal.',
        success: 'Bxh6 — four squares crossed in one move. That is bishop power.',
      },
    ],
    finish:
      'A bishop on c1 can reach h6 instantly. Keep your bishops on long open diagonals and they dominate.',
    tip: 'Bishops are strongest in pairs on an open board.',
    minutes: 3,
    tags: ['pieces', 'captures'],
  },
  {
    id: 'castling',
    category: FUNDAMENTALS,
    title: 'Castling to Safety',
    summary: 'Two pieces in one move: king safety and a fighting rook.',
    fen: 'r3k2r/pppq1ppp/2npbn2/4p3/4P3/2NPBN2/PPPQ1PPP/R3K2R w KQkq - 0 1',
    goal: 'Your king is still in the centre. Castle kingside by moving the king two squares towards the rook.',
    steps: [
      {
        moves: ['e1g1', 'e1c1'],
        hint: 'Drag the king from e1 onto g1 — that is castling kingside.',
        success: 'O-O! The king reaches safety and the rook joins the game at the same time.',
      },
    ],
    finish:
      'Castling is legal only when neither piece has moved, the squares between them are empty, and the king does not castle out of, through, or into check.',
    tip: 'Castle early — most games are decided by who gets their king safe first.',
    minutes: 3,
    tags: ['king safety', 'special moves'],
  },
  {
    id: 'en-passant',
    category: FUNDAMENTALS,
    title: 'En Passant',
    summary: 'The capture that only exists for one move.',
    fen: '4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1',
    goal: 'Black just pushed d7-d5 to slip past your pawn. Capture it en passant.',
    steps: [
      {
        moves: ['e5d6'],
        hint: 'Pawns capture diagonally forward — take on d6, the square the black pawn skipped.',
        success: 'exd6 en passant — the pawn vanishes from d5 even though you never landed there.',
      },
    ],
    finish:
      'En passant is available only on the very next move after a double pawn step. Miss it and the right is gone forever.',
    tip: 'Watch out for en passant when a pawn storms past yours in the centre.',
    minutes: 3,
    tags: ['pawns', 'special moves'],
  },
  {
    id: 'promotion',
    category: FUNDAMENTALS,
    title: 'Promotion',
    summary: 'A pawn that reaches the far rank becomes a new piece.',
    fen: '8/4P3/8/8/8/8/8/K6k w - - 0 1',
    goal: 'Push your pawn to e8 and promote it — choose the queen, the strongest piece.',
    steps: [
      {
        moves: ['e7e8q'],
        hint: 'Move the pawn to e8, then pick the queen.',
        success: 'A brand new queen appears on e8. Pawns can also promote to a rook, bishop or knight.',
      },
    ],
    finish:
      'Promotion wins games: a single extra queen usually decides the result. Underpromotion to a knight can be the only winning move when it delivers a fork.',
    tip: 'Push passed pawns — every step brings a new queen closer.',
    minutes: 3,
    tags: ['pawns', 'endgame'],
  },
  {
    id: 'knight-fork',
    category: TACTICS,
    title: 'Knight Forks',
    summary: 'One leap, two targets: the classic knight double attack.',
    fen: '6k1/3r1p1p/8/3N4/8/8/5PPP/6K1 w - - 0 1',
    goal: 'The knight can attack the king and a rook at once. Find the fork.',
    steps: [
      {
        moves: ['d5f6'],
        hint: 'Look for a square that touches both g8 and d7.',
        reply: 'g8f8',
        success: 'Nf6+ forks the king and the rook on d7. The king must move, and the rook stays lost.',
      },
      {
        moves: ['f6d7'],
        hint: 'The king stepped to f8 — collect the rook on d7.',
        success: 'A clean rook for nothing. That is what a fork is for.',
      },
    ],
    finish:
      "Knights are the best forking pieces because their attack pattern is hard to see. Before every move, scan for undefended pieces a knight's jump apart.",
    tip: 'Undefended heavy pieces on the same colour complex are fork fodder.',
    minutes: 4,
    tags: ['tactics', 'knights'],
  },
  {
    id: 'pin',
    category: TACTICS,
    title: 'Pins',
    summary: 'Freeze a piece by putting something valuable behind it.',
    fen: 'r1bqk2r/ppp2ppp/2n5/8/2B5/8/PPP2PPP/R1BQK1NR w kq - 0 1',
    goal: 'The black king stands on e8. Slide your bishop to b5 and pin the knight on c6.',
    steps: [
      {
        moves: ['c4b5'],
        hint: 'b5, c6, d7, e8 — put your bishop on that diagonal.',
        success: 'Bb5! The knight cannot move: it would expose its own king. A pinned piece is half a piece.',
      },
    ],
    finish:
      'Pins work along lines to the king (absolute pins) or to any valuable piece (relative pins). Attack a pinned piece with a pawn whenever you can — it cannot run away.',
    tip: 'Ask what is behind the piece you want to attack.',
    minutes: 4,
    tags: ['tactics', 'bishop'],
  },
  {
    id: 'skewer',
    category: TACTICS,
    title: 'Skewers',
    summary: 'Check the king first, win the piece hiding behind it.',
    fen: 'q1k5/8/8/8/8/6K1/8/7R w - - 0 1',
    goal: 'The black queen is trapped behind her king on the eighth rank. Skewer them.',
    steps: [
      {
        moves: ['h1h8'],
        hint: 'The rook lives on h1. Check along the eighth rank.',
        reply: 'c8b7',
        success: 'Rh8+! The king must step aside and the queen is suddenly defenceless.',
      },
      {
        moves: ['h8a8'],
        hint: 'The king moved — take the queen on a8.',
        success: 'The skewer collects the queen. Beautiful geometry.',
      },
    ],
    finish:
      'A skewer is a pin in reverse: the valuable piece is in front, the target is behind. Rooks, bishops and queens all love long open lines.',
    tip: 'Look for kings lined up with queens on the same rank, file or diagonal.',
    minutes: 4,
    tags: ['tactics', 'rook'],
  },
  {
    id: 'discovered-attack',
    category: TACTICS,
    title: 'Discovered Attack',
    summary: 'Move one piece, unleash another.',
    fen: '4k2q/8/8/4N3/8/8/1B6/6K1 w - - 0 1',
    goal: 'Your knight shields your bishop. Move the knight with a threat so the bishop hits the queen on h8.',
    steps: [
      {
        moves: ['e5g6', 'e5f7'],
        hint: "Jump the knight to g6, attacking the queen while the bishop's diagonal opens.",
        success: "The bishop's long diagonal snaps open and the queen is attacked twice. She must run.",
      },
    ],
    finish:
      'Discovered attacks are double threats: the moving piece attacks something, and the piece behind it attacks something else. Two problems at once is usually one too many.',
    tip: 'Before moving a piece, ask what the piece behind it will see.',
    minutes: 4,
    tags: ['tactics', 'bishop', 'knight'],
  },
  {
    id: 'back-rank-mate',
    category: ENDGAMES,
    title: 'Back-Rank Mate',
    summary: 'A castled king can become its own prison.',
    fen: '6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1',
    goal: 'The black king is walled in by its own pawns. Deliver checkmate on the eighth rank.',
    steps: [
      {
        moves: ['a1a8'],
        hint: 'Ra8 — the pawns on f7, g7 and h7 block every escape square.',
        success: 'Ra8# — the back-rank mate. The king had no square to run to.',
      },
    ],
    finish:
      "A king behind unmoved pawns is a permanent mating target. Give it an escape square (a 'luft' move like h6) before it is too late.",
    tip: 'Count the escape squares before you castle.',
    minutes: 4,
    tags: ['checkmate', 'rook'],
  },
  {
    id: 'ladder-mate',
    category: ENDGAMES,
    title: 'Ladder Mate',
    summary: 'Two rooks climb the board and squeeze the king to the edge.',
    fen: '8/1K6/8/7k/8/8/R7/1R6 w - - 0 1',
    goal: 'Use both rooks to push the lone king to the first rank, then mate. Each rook guards the rank the other one leaves.',
    steps: [
      {
        moves: ['b1b5'],
        hint: 'Check the king on the fifth rank with the b1 rook.',
        reply: 'h5h4',
        success: 'Rb5+ — the fifth rank is cut off, the king is pushed down.',
      },
      {
        moves: ['a2a4'],
        hint: 'Now check along the fourth rank with the other rook.',
        reply: 'h4h3',
        success: 'Ra4+ — the ladder works because the rooks protect each other.',
      },
      {
        moves: ['b5b3'],
        hint: 'Check along the third rank.',
        reply: 'h3h2',
        success: 'Rb3+ — the king is being walked down the board.',
      },
      {
        moves: ['a4a2'],
        hint: 'Check along the second rank.',
        reply: 'h2h1',
        success: 'Ra2+ — one more rank to go.',
      },
      {
        moves: ['b3b1'],
        hint: 'Close the ladder on the first rank.',
        success: 'Rb1# — the king is squeezed against the edge. Ladder mate complete.',
      },
    ],
    finish:
      'Two rooks beat a lone king in a few moves: never let the king escape past a rook, and always keep the rooks a knight\'s move apart.',
    tip: 'The fifth rank is the natural first rung of the ladder.',
    minutes: 6,
    tags: ['checkmate', 'rooks', 'technique'],
  },
  {
    id: 'queen-mate',
    category: ENDGAMES,
    title: 'King + Queen vs King',
    summary: 'The king does the work, the queen delivers the blow.',
    fen: '7k/5K2/8/8/8/8/8/1Q6 w - - 0 1',
    goal: 'Your king already covers g7 and g8. Bring the queen to the h-file and mate the trapped king.',
    steps: [
      {
        moves: ['b1h1'],
        hint: 'The queen belongs on h1: the king is boxed in and the h-file is open.',
        success: 'Qh1# — the queen cuts the last escape square. King and queen finish the job together.',
      },
    ],
    finish:
      'With king and queen against a bare king, use the queen to shrink the box and your king to cover the escape squares. Never stalemate: always leave the enemy king one square until the mate is ready.',
    tip: 'Checkmate needs the enemy king to have no legal move — not just a check.',
    minutes: 4,
    tags: ['checkmate', 'queen', 'technique'],
  },
];

export function lessonsIn(category) {
  return LESSONS.filter((lesson) => lesson.category === category);
}

export function lessonById(id) {
  return LESSONS.find((lesson) => lesson.id === id) || null;
}
