"""The start-up screen: the logo, the version and the institutions behind eemkit.

It is shown while the main window loads the scientific libraries (a few
seconds), and for at least :data:`MIN_SECONDS` so that it does not flash.
Set ``EEMKIT_NO_SPLASH=1`` to start without it.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen, QWidget

from eemkit import __version__
from eemkit.gui import ICON_DIR

POWERED_BY = ("Università degli Studi di Siena",
              "Università degli Studi di Palermo",
              "National Biodiversity Future Center (Italy)")
TAGLINE = "EEM processing and PARAFAC modelling\nof dissolved organic matter fluorescence"
WIDTH, HEIGHT = 560, 330
MIN_SECONDS = 1.5
COLOURS = {"bg": "#ffffff", "border": "#d6dbe1", "title": "#14243d", "text": "#1d232b",
           "muted": "#5b6573", "accent": "#1f5fa8"}


def _font(base: QFont, pixels: int, bold: bool = False) -> QFont:
    f = QFont(base)
    f.setPixelSize(pixels)
    f.setBold(bold)
    return f


def splash_pixmap(ratio: float = 1.0) -> QPixmap:
    """The start-up image, ``WIDTH`` x ``HEIGHT`` logical pixels at device pixel ratio ``ratio``."""
    pm = QPixmap(round(WIDTH * ratio), round(HEIGHT * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(QColor(COLOURS["bg"]))
    base = QApplication.font()
    p = QPainter(pm)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform
                     | QPainter.TextAntialiasing)
    p.setPen(QPen(QColor(COLOURS["border"]), 1))
    p.drawRect(QRectF(0.5, 0.5, WIDTH - 1, HEIGHT - 1))

    logo = QPixmap(str(ICON_DIR / "eemkit-256.png"))
    p.drawPixmap(QRectF(40, 44, 132, 132), logo, QRectF(logo.rect()))

    left = 200
    p.setPen(QColor(COLOURS["title"]))
    p.setFont(_font(base, 44, bold=True))
    p.drawText(QRectF(left, 46, WIDTH - left - 30, 56), Qt.AlignLeft | Qt.AlignVCenter, "eemkit")
    p.setPen(QColor(COLOURS["accent"]))
    p.setFont(_font(base, 14))
    p.drawText(QRectF(left + 2, 102, WIDTH - left - 30, 20), Qt.AlignLeft, f"Version {__version__}")
    p.setPen(QColor(COLOURS["text"]))
    p.setFont(_font(base, 14))
    p.drawText(QRectF(left + 2, 130, WIDTH - left - 30, 44), Qt.AlignLeft | Qt.TextWordWrap,
               TAGLINE)

    p.setPen(QPen(QColor(COLOURS["border"]), 1))
    p.drawLine(40, 204, WIDTH - 40, 204)
    p.setPen(QColor(COLOURS["muted"]))
    p.setFont(_font(base, 12))
    p.drawText(QRectF(40, 216, WIDTH - 80, 18), Qt.AlignLeft, "Powered by")
    p.setPen(QColor(COLOURS["text"]))
    p.setFont(_font(base, 15, bold=True))
    for i, name in enumerate(POWERED_BY):
        p.drawText(QRectF(40, 238 + 24 * i, WIDTH - 80, 22), Qt.AlignLeft | Qt.AlignVCenter, name)
    p.end()
    return pm


def show_splash() -> QSplashScreen:
    """Show the start-up screen now (before the slow imports) and return it."""
    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen is not None else 1.0
    # On top of the main window, which may appear before MIN_SECONDS have passed.
    splash = QSplashScreen(splash_pixmap(ratio), Qt.WindowStaysOnTopHint)
    splash.shown_at = time.monotonic()
    splash.show()
    splash.showMessage("Starting…", Qt.AlignRight | Qt.AlignBottom, QColor(COLOURS["muted"]))
    QApplication.processEvents()
    return splash


def close_splash(splash: QSplashScreen, window: QWidget) -> None:
    """Close the start-up screen once ``window`` is shown, after at least ``MIN_SECONDS``."""
    left = MIN_SECONDS - (time.monotonic() - splash.shown_at)
    QTimer.singleShot(max(0, round(left * 1000)), lambda: splash.finish(window))
