# Chess Coach

A desktop chess trainer with a Chess.com-inspired interface, a **1–100 difficulty scale** that works with or without Stockfish, and a coach that reviews every move you play — plus **12 playable lessons**.

Built with **Python 3.10+**, **PySide6 (Qt 6)** and **python-chess**. Native window, no web view, no bundled engine binary required.

```
pip install -r requirements.txt
python main.py
```

## Highlights

- **Accurate chess rules** — legal move generation, castling, en passant, promotion dialogs, check/checkmate/stalemate, threefold repetition, the fifty-move rule and insufficient material all come from `python-chess`.
- **Adjustable AI, levels 1–100** — smooth Elo estimate from ~400 to ~3000 with tier labels, live level readout and a slider you can move mid-game.
- **Two engines, zero setup** — Stockfish is auto-detected from `PATH` (or pick a binary in Settings). If it is missing, a bundled pure-Python engine (negamax + alpha-beta + quiescence + piece-square tables) takes over instantly.
- **Never blocks the UI** — every search and analysis runs on a `QThread` worker.
- **Live coach** — each move is graded Best / Good / Inaccuracy / Mistake / Blunder with a colour-coded badge, a plain-English explanation and a green arrow showing the better move.
- **12 interactive lessons** — real FEN positions, scripted opponent replies, red flash and rollback for wrong moves, hints, and progress tracking.

## The interface

Three zones, like a modern chess site:

| Zone | Contents |
| --- | --- |
| Left nav rail | Play, Learn, Settings with active indicator |
| Board area | Toggleable evaluation bar, AI player bar (level badge, estimated Elo, captures, clock), responsive board with coordinates, your player bar |
| Right sidebar | AI level slider, side and time-control selectors, coach toggle, New Game, two-column move list with ply inspection, coach card, Hint / Takeback / Flip / Resign |

Board interaction supports **click-to-move and drag-and-drop**, **board flipping**, **right-click arrows**, legal-move dots, capture rings, last-move and check highlights.

### Board themes

| Theme | Light | Dark |
| --- | --- | --- |
| Classic Green | `#EEEED2` | `#769656` |
| Walnut | `#F0D9B5` | `#B58863` |
| Slate Blue | `#DEE3E6` | `#788A9E` |

## AI levels

| Level | Tier | Approx. Elo | Behaviour |
| --- | --- | --- | --- |
| 1–15 | Beginner | ~400–470 | Deliberate weak candidates, 1-ply search |
| 16–35 | Casual | ~470–640 | Shallow search, frequent mistakes |
| 36–60 | Intermediate | ~640–1050 | 2-ply search, occasional slips |
| 61–85 | Advanced | ~1050–1900 | 3-ply search, small noise window |
| 86–100 | Master | ~1900–3000 | 4-ply search, best move only |

With Stockfish installed the level maps to `Skill Level`, `UCI_LimitStrength` + `UCI_Elo`, a depth/movetime budget, and a mistake probability for levels 1–30. Everything degrades gracefully: if the binary disappears or misbehaves, the built-in engine answers.

## Lessons

| Category | Lessons |
| --- | --- |
| Fundamentals | Meet the Rook, The Bishop's Diagonal, Castling to Safety, En Passant, Promotion |
| Tactics | Knight Forks, Pins, Skewers, Discovered Attack |
| Checkmates & Endgames | Back-Rank Mate, Ladder Mate, King + Queen vs King |

Each lesson loads a real position, states a one-sentence goal, lets you make the move on the board, and walks you through multi-step ideas with scripted replies.

## Coach

| Grade | Centipawn loss |
| --- | --- |
| Best | 0–15 |
| Good | 16–60 |
| Inaccuracy | 61–130 |
| Mistake | 131–260 |
| Blunder | 261+ |

The explanation is generated from the position: hanging pieces, missed captures, allowed mates, promotion chances and the reason the suggested move is stronger.

## Project layout

```
main.py                  entry point
ui/
  main_window.py         navigation, play/learn/settings pages, game flow, clocks
  board_widget.py        board rendering, drag & drop, arrows, promotion dialog
  eval_bar.py            animated evaluation bar
  sidebar.py             setup controls, move list, coach card, actions
  lessons_view.py        curriculum browser and lesson runner
  player_bar.py          player strips with captures and clocks
  pieces.py              Staunton SVG artwork (generated to assets/pieces)
  theme.py               palette, board themes, fonts, icons, stylesheet
engine/
  ai_manager.py          Stockfish detection, level mapping, QThread worker
  fallback_engine.py     negamax + alpha-beta + quiescence + PST engine
  coach.py               move classification and explanations
lessons/
  curriculum.py          12 structured lessons
assets/pieces/           12 generated SVG pieces (never Unicode glyphs)
requirements.txt
```

## Settings

- Board theme (Classic Green, Walnut, Slate Blue)
- Stockfish binary path with auto-detect and validation
- Show/hide the evaluation bar
- Coach mode on by default

Settings, AI level and lesson progress are remembered between launches via `QSettings`.

## Notes

- Python 3.10 or newer is required.
- Stockfish is optional. Without it the app is fully playable, just a little weaker at the top end.
- Piece art is vector SVG generated by the app into `assets/pieces/` on first run, so the board stays crisp at any window size.
- Sound is intentionally not included: nothing external is required and nothing can fail to load.
