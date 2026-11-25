"""Staunton-style piece artwork drawn as SVG and exported to ``assets/pieces``.

The artwork is generated from vectors committed here (no Unicode chess glyphs,
no external downloads).  Files are (re)written on demand so the app always has
crisp scalable art available, and pixmaps are rendered from those files.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import chess
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "pieces"

WHITE_FILL = "#F7F6F2"
WHITE_STROKE = "#3B3936"
BLACK_FILL = "#33302B"
BLACK_STROKE = "#141312"

_BASE = '<rect x="19" y="79" width="62" height="10" rx="5"/>'
_COLLAR = '<rect x="27" y="69" width="46" height="7.5" rx="3.5"/>'
_BAND = '<rect x="28.5" y="42" width="43" height="9" rx="3"/>'
_BODY_ROBE = '<path d="M34 74c0-13 4-22 10-30h12c6 8 10 17 10 30z"/>'

# Filled silhouettes per piece, drawn back to front.
_SHAPES: dict[str, list[str]] = {
    "P": [
        '<path d="M37 72c0-9 6.5-13 9-20h8c2.5 7 9 11 9 20z"/>',
        '<circle cx="50" cy="36.5" r="13.5"/>',
        _COLLAR,
        _BASE,
    ],
    "R": [
        '<path d="M33 74l2.5-38h29L67 74z"/>',
        '<path d="M27 36V17h9v9h4v-9h9v9h4v-9h9v19z"/>',
        _COLLAR,
        _BASE,
    ],
    "N": [
        '<path d="M33 79C30 66 28 58 30 52C32 44 27 42 22 40'
        'L20 36C20 33 24 31 30 30C36 29 41 27 44 24'
        'L46 12L53 21C58 24 63 30 66 38C72 50 73 64 71 79Z"/>',
        _COLLAR,
        _BASE,
    ],
    "B": [
        '<path d="M50 17c11 11 18 20 18 29a18 18 0 0 1-36 0c0-9 7-18 18-29z"/>',
        '<circle cx="50" cy="13" r="5.2"/>',
        _COLLAR,
        _BASE,
    ],
    "Q": [
        _BODY_ROBE,
        '<path d="M30 44L34 20L42 36L50 16L58 36L66 20L70 44Z"/>',
        _BAND,
        '<circle cx="34" cy="17.5" r="3.2"/>',
        '<circle cx="50" cy="12.5" r="3.6"/>',
        '<circle cx="66" cy="17.5" r="3.2"/>',
        _BASE,
    ],
    "K": [
        _BODY_ROBE,
        '<path d="M33 43c0-8 7-13 17-13s17 5 17 13z"/>',
        _BAND,
        '<rect x="46.4" y="9" width="7.2" height="21" rx="2.4"/>',
        '<rect x="39" y="15" width="22" height="7.2" rx="2.4"/>',
        _BASE,
    ],
}

# Extra line-work drawn in the stroke colour on top of the silhouette.
_DETAILS: dict[str, list[str]] = {
    "R": [
        '<path d="M36.5 52h27" stroke-width="2.6" opacity="0.45"/>',
        '<path d="M35 64h30" stroke-width="2.6" opacity="0.45"/>',
    ],
    "N": [
        '<circle cx="41" cy="31.5" r="2.7" fill="{stroke}" stroke="none"/>',
        '<circle cx="26.5" cy="35" r="1.9" fill="{stroke}" stroke="none"/>',
        '<path d="M24 42C28 44 32 45 36 45" stroke-width="2.4" opacity="0.45"/>',
        '<path d="M54 26C59 33 62 42 63 52" stroke-width="2.6" opacity="0.4"/>',
        '<path d="M58 46C62 50 64 56 65 63" stroke-width="2.4" opacity="0.35"/>',
        '<path d="M45 22C48 18 50 16 51 13" stroke-width="2.2" opacity="0.35"/>',
    ],
    "B": [
        '<path d="M50 29v16" stroke-width="3" opacity="0.5"/>',
    ],
    "Q": [
        '<path d="M44 50h12" stroke-width="2.4" opacity="0.35"/>',
    ],
    "K": [
        '<path d="M44 49h12" stroke-width="2.4" opacity="0.35"/>',
    ],
    "P": [
        '<path d="M43 49h14" stroke-width="2.4" opacity="0.3"/>',
    ],
}


def build_svg(letter: str, white: bool) -> str:
    """Return the full SVG document for one piece."""
    fill = WHITE_FILL if white else BLACK_FILL
    stroke = WHITE_STROKE if white else BLACK_STROKE
    sw = 2.6 if white else 2.4
    shapes = "".join(_SHAPES[letter])
    details = "".join(_DETAILS.get(letter, [])).replace("{stroke}", stroke)
    detail_group = (
        f'<g fill="none" stroke="{stroke}" stroke-linecap="round">{details}</g>'
        if details
        else ""
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'width="100" height="100">'
        f'<g fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
        f'stroke-linejoin="round" stroke-linecap="round">{shapes}</g>'
        f"{detail_group}"
        "</svg>"
    )


PIECE_LETTERS = ("P", "N", "B", "R", "Q", "K")


def piece_symbol(piece: chess.Piece) -> str:
    """``chess.Piece`` -> file symbol such as ``wQ``."""
    return ("w" if piece.color == chess.WHITE else "b") + piece.symbol().upper()


def svg_symbol(symbol: str) -> str:
    return build_svg(symbol[1].upper(), symbol[0] == "w")


@lru_cache(maxsize=1)
def ensure_piece_files() -> dict[str, str]:
    """Write every SVG into ``assets/pieces`` if missing; return the paths."""
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for color in ("w", "b"):
        for letter in PIECE_LETTERS:
            symbol = color + letter
            path = ASSET_DIR / f"{symbol}.svg"
            svg = build_svg(letter, color == "w")
            try:
                if not path.exists() or path.read_text(encoding="utf-8") != svg:
                    path.write_text(svg, encoding="utf-8")
            except OSError:
                # Read-only install: rendering still works from the SVG string.
                pass
            paths[symbol] = str(path)
    return paths


@lru_cache(maxsize=512)
def piece_pixmap(symbol: str, size: int) -> QPixmap:
    """Render a piece symbol to a transparent pixmap of ``size`` pixels."""
    size = max(8, int(size))
    paths = ensure_piece_files()
    renderer = QSvgRenderer(paths.get(symbol, ""))
    if not renderer.isValid():
        renderer = QSvgRenderer(svg_symbol(symbol).encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


@lru_cache(maxsize=256)
def piece_pixmap_hidpi(symbol: str, size: int, dpr: float = 2.0) -> QPixmap:
    """High-DPI variant: rendered at ``size * dpr`` with the ratio attached."""
    big = piece_pixmap(symbol, max(8, int(round(size * dpr))))
    scaled = QPixmap(big)
    scaled.setDevicePixelRatio(dpr)
    return scaled
