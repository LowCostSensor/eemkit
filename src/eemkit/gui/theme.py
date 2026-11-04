"""Light and dark themes of the application (Qt Fusion style, palette and style sheet).

The theme is a preference of the user, not of the project: it is kept in
``QSettings`` and never written to the project file. Widgets opt into
special looks through dynamic properties: ``primary`` for the main action of
a step, ``invalid`` for a field that needs a value, ``role="note"`` for help
text and ``role="warning"`` for warnings.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory, QWidget

THEMES = ("system", "light", "dark")

COLOURS = {
    "light": {"bg": "#f4f6f8", "surface": "#ffffff", "border": "#d6dbe1", "text": "#1d232b",
              "muted": "#5b6573", "accent": "#1f5fa8", "accent_hover": "#184c86",
              "accent_soft": "#dce8f7", "nav": "#e9edf2", "warn": "#8a5a00",
              "warn_bg": "#fff4d6", "bad_bg": "#fbe3e3", "on_accent": "#ffffff"},
    "dark": {"bg": "#16191d", "surface": "#1f2328", "border": "#353c45", "text": "#e6e9ed",
             "muted": "#9aa4b0", "accent": "#4c8fdb", "accent_hover": "#6aa3e3",
             "accent_soft": "#22364d", "nav": "#1b1e23", "warn": "#f0b54a",
             "warn_bg": "#3a2f17", "bad_bg": "#4a2326", "on_accent": "#0b1220"},
}

STYLE = """
QWidget {{ color: {text}; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {bg}; }}
QMenuBar {{ background: {bg}; }}
QGroupBox {{ background: {surface}; border: 1px solid {border}; border-radius: 8px;
            margin-top: 14px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
                   color: {muted}; font-weight: 600; }}
QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 6px;
              padding: 6px 14px; }}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:pressed {{ background: {accent_soft}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton[primary="true"] {{ background: {accent}; color: {on_accent}; border: none;
                              font-weight: 600; padding: 8px 18px; }}
QPushButton[primary="true"]:hover {{ background: {accent_hover}; }}
QPushButton[primary="true"]:disabled {{ background: {border}; color: {muted}; }}
QPushButton[role="warning"] {{ color: {warn}; border: none; background: transparent; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 4px 6px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {accent}; }}
QLineEdit[invalid="true"] {{ background: {bad_bg}; }}
QLabel[role="note"] {{ color: {muted}; }}
QLabel[role="warning"] {{ color: {warn}; background: {warn_bg}; border-radius: 6px;
                         padding: 8px; }}
QTableView, QListWidget {{ background: {surface}; border: 1px solid {border};
                          border-radius: 6px; gridline-color: {border};
                          selection-background-color: {accent_soft}; selection-color: {text}; }}
QHeaderView::section {{ background: {bg}; color: {muted}; border: none;
                       border-bottom: 1px solid {border}; padding: 4px 6px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 6px; background: {surface}; }}
QTabBar::tab {{ background: transparent; padding: 6px 12px; color: {muted};
               border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {text}; border-bottom: 2px solid {accent}; }}
QProgressBar {{ border: 1px solid {border}; border-radius: 6px; background: {surface};
               text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
QSplitter::handle {{ background: {bg}; }}
QListWidget#nav {{ background: {nav}; border: none; border-radius: 0; padding: 10px 6px;
                  font-size: 10.5pt; outline: 0; }}
QListWidget#nav::item {{ padding: 10px 10px; border-radius: 6px; margin: 1px 0; }}
QListWidget#nav::item:selected {{ background: {accent_soft}; color: {text};
                                 border-left: 3px solid {accent}; }}
QListWidget#nav::item:hover:!selected {{ background: {bg}; }}
QLabel#brand {{ font-size: 15pt; font-weight: 700; padding: 14px 14px 2px 14px; }}
QLabel#tagline {{ color: {muted}; padding: 0 14px 8px 14px; }}
QLabel#summary {{ color: {muted}; padding: 10px 14px; }}
QWidget#sidebar {{ background: {nav}; border-right: 1px solid {border}; }}
"""


def saved_theme() -> str:
    t = QSettings("eemkit", "eemkit").value("theme", "system")
    return t if t in THEMES else "system"


def save_theme(name: str) -> None:
    QSettings("eemkit", "eemkit").setValue("theme", name)


def resolved(name: str) -> str:
    """'light' or 'dark' ('system' follows the operating system where Qt can tell)."""
    if name != "system":
        return name
    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", lambda: None)()
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


def apply_theme(app: QApplication, name: str = "system") -> str:
    """Apply a theme to the whole application; returns 'light' or 'dark'."""
    mode = resolved(name)
    c = COLOURS[mode]
    app.setStyle(QStyleFactory.create("Fusion"))
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Base, "surface"),
                      (QPalette.AlternateBase, "bg"), (QPalette.Button, "surface"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"),
                      (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "surface"),
                      (QPalette.ToolTipText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.HighlightedText, "on_accent"), (QPalette.PlaceholderText, "muted"),
                      (QPalette.Link, "accent")):
        pal.setColor(role, QColor(c[key]))
    app.setPalette(pal)
    app.setStyleSheet(STYLE.format(**c))
    app.setProperty("eemkit_theme", mode)
    return mode


def mark(widget: QWidget, **props) -> QWidget:
    """Set dynamic properties (e.g. ``primary=True``) and refresh the widget's style."""
    for k, v in props.items():
        widget.setProperty(k, v)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget
