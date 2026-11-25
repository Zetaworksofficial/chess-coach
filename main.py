"""Application entry point for the Chess Coach desktop app."""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import shiboken6  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import pieces as piece_assets  # noqa: E402
from ui import theme as theme_module  # noqa: E402
from ui.theme import apply_theme, icon  # noqa: E402


def main() -> int:
    """Create the Qt application and show the main window."""
    QApplication.setApplicationName("Chess Coach")
    QApplication.setOrganizationName("ChessCoach")
    QApplication.setApplicationDisplayName("Chess Coach")

    app = QApplication(sys.argv)
    apply_theme(app)

    # Import after the application exists so widget construction is safe.
    from ui.main_window import MainWindow

    window = MainWindow()
    window.setWindowIcon(icon("knight", "#E9E7E4", 64))
    window.show()

    state = {"done": False}

    def cleanup() -> None:
        """Stop the engine thread and release Qt resources before Qt shuts down."""
        if state["done"]:
            return
        state["done"] = True
        try:
            window.ai.shutdown()
        except Exception:
            pass
        piece_assets.piece_pixmap.cache_clear()
        piece_assets.piece_pixmap_hidpi.cache_clear()
        theme_module.icon_pixmap.cache_clear()
        try:
            shiboken6.delete(window)
        except Exception:
            pass

    app.aboutToQuit.connect(cleanup)
    try:
        return app.exec()
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
