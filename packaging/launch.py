"""Entry point for the PyInstaller build (see eemkit-gui.spec).

The build has no console, so an error at start-up is written to
``eemkit-crash.log`` in the temporary folder instead of vanishing.
"""

import sys
import tempfile
import traceback
from pathlib import Path

if __name__ == "__main__":
    try:
        import PySide6.QtWidgets  # noqa: F401 - fail here, with a traceback, if Qt is broken

        from eemkit.gui import main

        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        log = Path(tempfile.gettempdir()) / "eemkit-crash.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        raise
