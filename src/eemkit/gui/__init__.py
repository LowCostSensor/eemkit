"""Desktop application for eemkit (requires ``pip install eemkit[gui]``).

Start it with ``eemkit-gui [project.toml]`` or ``python -m eemkit.gui``.
The application is a front end to :mod:`eemkit.pipeline`: all processing
is done by the library, and the project file it saves is the same settings
TOML that scripts can run.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: PNG renderings of the logo (made by packaging/icons/make_icons.py).
ICON_DIR = Path(__file__).resolve().parent / "icons"


def app_icon():
    """The eemkit logo as a QIcon, with one image per size so that small icons stay sharp."""
    from PySide6.QtGui import QIcon

    icon = QIcon()
    for png in sorted(ICON_DIR.glob("eemkit-*.png")):
        icon.addFile(str(png))
    return icon


def _windows_taskbar_id() -> None:
    """Give the process its own taskbar identity on Windows.

    Started with ``python -m eemkit.gui``, the window would otherwise be grouped
    under python.exe and show the Python icon in the taskbar.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("eemkit.gui")
        except (AttributeError, OSError):  # pragma: no cover
            pass


def main(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover
        print(f"The eemkit desktop application needs PySide6 (pip install eemkit[gui]): {exc}",
              file=sys.stderr)
        return 1
    from eemkit.gui import theme
    from eemkit.gui.main_window import MainWindow

    argv = sys.argv if argv is None else argv
    _windows_taskbar_id()
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("eemkit")
    app.setDesktopFileName("eemkit")  # Linux (Wayland): matches eemkit.desktop
    icon = app_icon()
    app.setWindowIcon(icon)
    theme.apply_theme(app, theme.saved_theme())
    window = MainWindow(argv[1] if len(argv) > 1 else None)
    window.setWindowIcon(icon)
    window.show()
    return app.exec()
