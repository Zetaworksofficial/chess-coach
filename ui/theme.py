"""Centralised visual theme: palette, board themes, fonts, icons, Qt stylesheet.

Everything is defined in code so the app has no external theme files to lose.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# ---------------------------------------------------------------------------
# Palette (Chess.com inspired, flat and calm)
# ---------------------------------------------------------------------------
BG = "#302E2B"
PANEL = "#262421"
PANEL_ALT = "#3C3A38"
PANEL_RAISED = "#45433F"
BORDER = "#454340"
ACCENT = "#81B64C"
ACCENT_HOVER = "#95CC5E"
ACCENT_DARK = "#5D8636"
TEXT = "#E9E7E4"
TEXT_MUTED = "#9A9793"
TEXT_DIM = "#787571"
DANGER = "#C9453C"
WARNING = "#E5A03B"
INFO = "#4A9BD1"
WHITE_SIDE = "#F0EFEC"
BLACK_SIDE = "#2A2825"

SANS_STACK = ["Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu", "Noto Sans", "DejaVu Sans"]
MONO_STACK = ["JetBrains Mono", "Cascadia Mono", "Consolas", "SF Mono", "DejaVu Sans Mono", "Courier New"]


@dataclass(frozen=True)
class BoardTheme:
    """Colours for one board skin."""

    name: str
    light: str
    dark: str
    border: str
    coord_on_light: str
    coord_on_dark: str


BOARD_THEMES: dict[str, BoardTheme] = {
    "Classic Green": BoardTheme("Classic Green", "#EEEED2", "#769656", "#4E6B3C", "#6C8A4E", "#F0F0D8"),
    "Walnut": BoardTheme("Walnut", "#F0D9B5", "#B58863", "#7C5B40", "#A57750", "#F3E1C6"),
    "Slate Blue": BoardTheme("Slate Blue", "#DEE3E6", "#788A9E", "#556577", "#6C7F92", "#E8EDF0"),
}

# Highlight colours
LAST_MOVE_TINT = QColor(246, 246, 105, 140)
SELECT_TINT = QColor(252, 250, 160, 130)
CHECK_TINT = QColor(214, 62, 52, 130)
WRONG_TINT = QColor(204, 58, 48, 165)
LEGAL_DOT = QColor(28, 26, 24, 66)
LEGAL_RING = QColor(28, 26, 24, 80)
COACH_ARROW = QColor(129, 182, 76, 235)
USER_ARROW = QColor(64, 130, 214, 220)


def sans_family() -> str:
    """First available clean sans-serif family."""
    families = set(QFontDatabase.families())
    for name in SANS_STACK:
        if name in families:
            return name
    return "Sans Serif"


def mono_family() -> str:
    """First available monospace family (tabular numerals for clocks/moves)."""
    families = set(QFontDatabase.families())
    for name in MONO_STACK:
        if name in families:
            return name
    return "Monospace"


def ui_font(size: int = 10, weight: int = 400) -> QFont:
    font = QFont(sans_family())
    font.setPointSizeF(size)
    font.setWeight(QFont.Weight(weight))
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def mono_font(size: int = 10, weight: int = 500) -> QFont:
    font = QFont(mono_family())
    font.setPointSizeF(size)
    font.setWeight(QFont.Weight(weight))
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def dialog_qss() -> str:
    return build_stylesheet()


def build_stylesheet() -> str:
    """Global Qt stylesheet for the whole app."""
    return f"""
    QWidget {{
        color: {TEXT};
        font-size: 13px;
    }}
    QMainWindow, #Root {{
        background-color: {BG};
    }}
    QLabel {{
        background: transparent;
    }}
    QToolTip {{
        background-color: {PANEL_ALT};
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 4px 7px;
        border-radius: 4px;
    }}
    #Panel {{
        background-color: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}
    #Card {{
        background-color: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}
    #Rail {{
        background-color: {PANEL};
        border-right: 1px solid {BORDER};
    }}
    #SectionTitle {{
        color: {TEXT_MUTED};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    #Muted {{
        color: {TEXT_MUTED};
    }}
    #Dim {{
        color: {TEXT_DIM};
    }}
    #Value {{
        color: {TEXT};
        font-weight: 600;
    }}
    #Badge {{
        background-color: {PANEL_ALT};
        border: 1px solid {BORDER};
        border-radius: 9px;
        color: {TEXT};
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
    }}
    #Dot {{
        color: {TEXT_DIM};
    }}
    QPushButton {{
        background-color: {PANEL_ALT};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 8px 12px;
        color: {TEXT};
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: #484541;
        border-color: #57544F;
    }}
    QPushButton:pressed {{
        background-color: #33312E;
    }}
    QPushButton:disabled {{
        color: {TEXT_DIM};
        background-color: #322F2C;
        border-color: #3B3835;
    }}
    QPushButton#primary {{
        background-color: {ACCENT};
        border: 1px solid {ACCENT};
        color: #17240C;
        font-weight: 700;
        padding: 10px 14px;
        border-radius: 8px;
    }}
    QPushButton#primary:hover {{
        background-color: {ACCENT_HOVER};
        border-color: {ACCENT_HOVER};
    }}
    QPushButton#primary:pressed {{
        background-color: {ACCENT_DARK};
        border-color: {ACCENT_DARK};
    }}
    QPushButton#primary:disabled {{
        background-color: #4B5B3D;
        border-color: #4B5B3D;
        color: #93A186;
    }}
    QPushButton#segment {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 6px 4px;
        color: {TEXT_MUTED};
        font-weight: 600;
        font-size: 12px;
    }}
    QPushButton#segment:hover {{
        color: {TEXT};
        background-color: #44413D;
    }}
    QPushButton#segment:checked {{
        background-color: {ACCENT};
        border-color: {ACCENT};
        color: #17240C;
    }}
    QPushButton#nav {{
        background-color: transparent;
        border: none;
        border-left: 3px solid transparent;
        border-radius: 0px;
        padding: 10px 0px 12px 0px;
        color: {TEXT_MUTED};
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton#nav:hover {{
        background-color: #302E2B;
        color: {TEXT};
    }}
    QPushButton#nav:checked {{
        background-color: #302E2B;
        border-left: 3px solid {ACCENT};
        color: {TEXT};
    }}
    QToolButton#nav {{
        background-color: transparent;
        border: none;
        border-left: 3px solid transparent;
        border-radius: 0px;
        padding: 8px 0px 10px 0px;
        color: {TEXT_MUTED};
        font-size: 11px;
        font-weight: 600;
    }}
    QToolButton#nav:hover {{
        background-color: {BG};
        color: {TEXT};
    }}
    QToolButton#nav:checked {{
        background-color: {BG};
        border-left: 3px solid {ACCENT};
        color: {TEXT};
    }}
    QPushButton#link {{
        background: transparent;
        border: none;
        color: {ACCENT};
        padding: 2px 4px;
        font-size: 12px;
    }}
    QPushButton#link:hover {{
        color: {ACCENT_HOVER};
    }}
    QPushButton#move {{
        background: transparent;
        border: none;
        border-radius: 5px;
        padding: 4px 6px;
        text-align: left;
        color: {TEXT};
        font-size: 13px;
    }}
    QPushButton#move:hover {{
        background-color: #3B3936;
    }}
    QPushButton#move[current="true"] {{
        background-color: #4B5B3D;
        color: #F3F7EE;
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: #4B4845;
        border-radius: 3px;
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT};
        border-radius: 3px;
    }}
    QSlider::add-page:horizontal {{
        background: #4B4845;
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: #F6F5F2;
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
        border: 2px solid {ACCENT};
    }}
    QSlider::handle:horizontal:hover {{
        background: #FFFFFF;
        border-color: {ACCENT_HOVER};
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: #4E4B47;
        border-radius: 5px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #5E5B56;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: #4E4B47;
        border-radius: 5px;
        min-width: 28px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QLineEdit {{
        background-color: #1F1E1C;
        border: 1px solid {BORDER};
        border-radius: 7px;
        padding: 7px 9px;
        color: {TEXT};
        selection-background-color: {ACCENT};
        selection-color: #17240C;
    }}
    QLineEdit:focus {{
        border-color: {ACCENT};
    }}
    QComboBox {{
        background-color: {PANEL_ALT};
        border: 1px solid {BORDER};
        border-radius: 7px;
        padding: 6px 9px;
        color: {TEXT};
    }}
    QComboBox:hover {{
        border-color: #57544F;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {PANEL_ALT};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT};
        selection-color: #17240C;
        outline: none;
    }}
    QMessageBox {{
        background-color: {PANEL};
    }}
    QDialog {{
        background-color: {PANEL};
    }}
    QPushButton:checked {{
        color: {TEXT};
    }}
    QFrame#hline {{
        background-color: {BORDER};
        max-height: 1px;
        border: none;
    }}
    """


def apply_theme(app) -> None:
    """Apply fonts and the global stylesheet to a QApplication."""
    app.setFont(ui_font(10))
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())


# ---------------------------------------------------------------------------
# Icons: hand-written 24x24 SVG paths, rendered crisply at any size
# ---------------------------------------------------------------------------
# name -> (svg body, filled?)
_ICONS: dict[str, tuple[str, bool]] = {
    "play": ('<path d="M8 5.2v13.6L19 12z"/>', True),
    "learn": (
        '<path d="M4 5.6C4 4.2 5.2 3 6.6 3H11v15.6H6.6C5.2 18.6 4 19.8 4 21.2z"/>'
        '<path d="M20 5.6C20 4.2 18.8 3 17.4 3H13v15.6h4.4c1.4 0 2.6 1.2 2.6 2.6z"/>',
        True,
    ),
    "settings": (
        '<path d="M4 7.5h6M14 7.5h6M4 16.5h10M18 16.5h2"/>'
        '<circle cx="12" cy="7.5" r="2.4"/><circle cx="16" cy="16.5" r="2.4"/>',
        False,
    ),
    "flip": ('<path d="M4 8.5h13l-3.4-3.4M20 15.5H7l3.4 3.4"/>', False),
    "undo": ('<path d="M8.5 6.5H4V2M4 6.5l3.6-3.2"/><path d="M4.4 6.6a8.6 8.6 0 1 1-1.6 7.1"/>', False),
    "hint": (
        '<path d="M9.4 17.6h5.2M10.4 20.6h3.2"/>'
        '<path d="M12 3.4a6.2 6.2 0 0 1 3.6 11.2c-.6.4-.9 1-.9 1.7v1.3H9.3V16c0-.7-.3-1.3-.9-1.7A6.2 6.2 0 0 1 12 3.4z"/>',
        False,
    ),
    "flag": ('<path d="M6.5 21V3.5"/><path d="M6.5 4.2h9.8l-2.4 3.4 2.4 3.4H6.5z"/>', False),
    "plus": ('<path d="M12 5v14M5 12h14"/>', False),
    "clock": ('<circle cx="12" cy="12" r="8.4"/><path d="M12 7.4V12l3.2 2"/>', False),
    "spark": ('<path d="M12 3.2l2.1 5.5 5.5 2.1-5.5 2.1L12 18.4l-2.1-5.5L4.4 10.8l5.5-2.1z"/>', False),
    "chevron-right": ('<path d="M9.4 5.6L15.8 12l-6.4 6.4"/>', False),
    "chevron-left": ('<path d="M14.6 5.6L8.2 12l6.4 6.4"/>', False),
    "check": ('<path d="M4.8 12.4l4.4 4.6L19.2 6.6"/>', False),
    "close": ('<path d="M6 6l12 12M18 6L6 18"/>', False),
    "target": ('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.4"/>', False),
    "user": (
        '<circle cx="12" cy="8" r="3.6"/>'
        '<path d="M4.8 20.4c0-4 3.2-6.4 7.2-6.4s7.2 2.4 7.2 6.4"/>',
        False,
    ),
    "board": (
        '<rect x="3.6" y="3.6" width="16.8" height="16.8" rx="2.2"/>'
        '<path d="M3.6 9.6h16.8M3.6 14.4h16.8M9.6 3.6v16.8M14.4 3.6v16.8"/>',
        False,
    ),
    "knight": (
        '<path d="M8.4 20.4c0-2.3.7-4 2.5-5.3 1.7-1.2 2.9-2.6 3.3-4.3" fill="none" stroke-width="2"/>'
        '<path d="M20 20.4H6.6c.2-2 .9-3.5 2.3-4.6 2.4-1.9 3.9-3.7 4.5-5.5.4-1.3 0-2.4-.9-3.3l.5-3.2 2.3 1.8c.9-.9 2-1.3 3.2-1 2 .5 3.3 2.3 3.5 4.9.2 2.3.1 4.9-.1 7.9z" fill="currentColor" stroke="none"/>',
        False,
    ),
}


def icon(name: str, color: str = TEXT, size: int = 20) -> QIcon:
    """Build a QIcon from the embedded SVG paths."""
    pixmap = icon_pixmap(name, color, size)
    return QIcon(pixmap)


@lru_cache(maxsize=256)
def icon_pixmap(name: str, color: str = TEXT, size: int = 20) -> QPixmap:
    body, filled = _ICONS.get(name, _ICONS["spark"])
    body = body.replace("currentColor", color)
    if filled:
        group = f'<g fill="{color}" stroke="none">{body}</g>'
    else:
        group = (
            f'<g fill="none" stroke="{color}" stroke-width="1.9" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</g>'
        )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="{size}" height="{size}">{group}</svg>'
    )
    return render_svg(svg, QSize(size, size))


def render_svg(svg: str, size: QSize, dpr: float = 2.0) -> QPixmap:
    """Render an SVG string into a high-DPI QPixmap."""
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(int(size.width() * dpr), int(size.height() * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap
