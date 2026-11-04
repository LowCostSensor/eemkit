"""Desktop application for eemkit (requires ``pip install eemkit[gui]``).

Start it with ``eemkit-gui [project.toml]`` or ``python -m eemkit.gui``.
The application is a front end to :mod:`eemkit.pipeline`: all processing
is done by the library, and the project file it saves is the same settings
TOML that scripts can run.
"""

from __future__ import annotations

import sys


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
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("eemkit")
    theme.apply_theme(app, theme.saved_theme())
    window = MainWindow(argv[1] if len(argv) > 1 else None)
    window.show()
    return app.exec()
