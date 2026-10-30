"""Widgets and helpers shared by the tabs: table model, plot panel, background tasks."""

from __future__ import annotations

import threading
import traceback
import warnings
from collections.abc import Callable, Sequence

import matplotlib

matplotlib.use("Agg")  # eemkit.plot builds figures off-screen; panels embed them
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from eemkit.errors import Cancelled, EEMKitError, EEMKitWarning

SUGGESTED = QColor("#fff4d6")
EXCLUDED = QColor("#f0efec")


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #

class DataFrameModel(QAbstractTableModel):
    """A pandas DataFrame in a QTableView; optionally editable column by column."""

    edited = Signal()

    def __init__(self, df: pd.DataFrame | None = None, editable: Sequence[str] = (),
                 row_colour: Callable[[pd.Series], QColor | None] | None = None,
                 float_format: str = "{:.4g}", parent=None):
        super().__init__(parent)
        self._df = pd.DataFrame() if df is None else df
        self.editable = set(editable)
        self.row_colour = row_colour
        self.float_format = float_format

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    def set_frame(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | None = None):  # noqa: N802 (Qt API)
        return 0 if parent is not None and parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex | None = None):  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self._df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        v = self._df.iat[index.row(), index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole):
            if isinstance(v, float):
                return "" if pd.isna(v) else self.float_format.format(v)
            return "" if v is None else str(v)
        if role == Qt.BackgroundRole and self.row_colour is not None:
            return self.row_colour(self._df.iloc[index.row()])
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        return str(self._df.index[section]) if not isinstance(self._df.index, pd.RangeIndex) \
            else str(section + 1)

    def flags(self, index):
        f = super().flags(index)
        if self._df.columns[index.column()] in self.editable:
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.EditRole):  # noqa: N802
        if role != Qt.EditRole or not index.isValid():
            return False
        self._df.iat[index.row(), index.column()] = str(value).strip()
        self.dataChanged.emit(self.index(index.row(), 0),
                              self.index(index.row(), self.columnCount() - 1))
        self.edited.emit()
        return True


class ChoiceDelegate(QStyledItemDelegate):
    """Cell editor offering a fixed list of values (and the empty string)."""

    def __init__(self, choices: Callable[[], Sequence[str]], parent=None):
        super().__init__(parent)
        self.choices = choices

    def createEditor(self, parent, option, index):  # noqa: N802
        box = QComboBox(parent)
        box.addItems([""] + list(self.choices()))
        box.setEditable(False)
        return box

    def setEditorData(self, editor, index):  # noqa: N802
        editor.setCurrentText(index.data(Qt.EditRole) or "")

    def setModelData(self, editor, model, index):  # noqa: N802
        model.setData(index, editor.currentText())


# --------------------------------------------------------------------------- #
# Plots
# --------------------------------------------------------------------------- #

class PlotPanel(QWidget):
    """Shows one matplotlib figure at a time, with the navigation toolbar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._canvas = self._toolbar = None
        self.placeholder = QLabel("Nothing to show yet.")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self.placeholder)

    def show_figure(self, fig) -> None:
        self.clear()
        self.placeholder.hide()
        self._canvas = FigureCanvasQTAgg(fig)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)
        self._layout.addWidget(self._toolbar)
        self._layout.addWidget(self._canvas, 1)
        self._canvas.draw_idle()

    @property
    def figure(self):
        return self._canvas.figure if self._canvas is not None else None

    def clear(self, message: str | None = None) -> None:
        for w in (self._toolbar, self._canvas):
            if w is not None:
                self._layout.removeWidget(w)
                w.hide()  # deleteLater waits for the event loop; hide at once
                w.setParent(None)
                w.deleteLater()
        if self._canvas is not None:
            plt.close(self._canvas.figure)
        self._canvas = self._toolbar = None
        if message is not None:
            self.placeholder.setText(message)
            self.placeholder.show()


# --------------------------------------------------------------------------- #
# Background tasks
# --------------------------------------------------------------------------- #

class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str, str)  # short message, traceback
    progress = Signal(str, int, int)
    warned = Signal(list)


class _Task(QRunnable):
    def __init__(self, fn, signals: _Signals, cancel: threading.Event):
        super().__init__()
        self.fn, self.signals, self.cancel = fn, signals, cancel

    def run(self):
        # eemkit warnings (e.g. a model that did not converge) are collected and shown,
        # never turned into errors or lost; only one task runs at a time
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", EEMKitWarning)
            try:
                result = self.fn(lambda msg, i, n: self.signals.progress.emit(msg, i, n),
                                 self.cancel.is_set)
            except Cancelled:
                self.signals.failed.emit("Cancelled.", "")
                return
            except EEMKitError as exc:
                self.signals.failed.emit(str(exc), "")
                return
            except Exception as exc:  # noqa: BLE001 - report anything to the user
                self.signals.failed.emit(f"{type(exc).__name__}: {exc}", traceback.format_exc())
                return
        self.signals.warned.emit([str(w.message) for w in caught
                                  if issubclass(w.category, EEMKitWarning)])
        self.signals.done.emit(result)


class TaskBar(QWidget):
    """Progress bar and Cancel button; runs one background task at a time.

    ``run(fn, on_done)`` calls ``fn(progress, cancelled)`` in a worker thread;
    ``on_done(result)`` runs in the GUI thread. Errors are shown in a dialog.
    """

    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("")
        self.bar = QProgressBar()
        self.bar.setMaximumWidth(260)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)
        self.warnings_button = QPushButton("")
        self.warnings_button.setFlat(True)
        self.warnings_button.setStyleSheet("color: #8a5a00;")
        self.warnings_button.clicked.connect(self.show_warnings)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.warnings_button)
        lay.addWidget(self.bar)
        lay.addWidget(self.cancel_button)
        self._cancel = threading.Event()
        self._signals: _Signals | None = None
        self.busy = False
        self.warnings: list[str] = []
        self._idle()

    def _idle(self) -> None:
        self.bar.hide()
        self.cancel_button.hide()
        self.warnings_button.setVisible(bool(self.warnings))

    def _warned(self, messages: list[str]) -> None:
        self.warnings = list(dict.fromkeys(messages))
        n = len(self.warnings)
        self.warnings_button.setText(f"⚠ {n} warning{'s' if n > 1 else ''}")

    def show_warnings(self) -> None:
        box = QMessageBox(QMessageBox.Information, "eemkit",
                          "The last computation finished with warnings. Review them before "
                          "using the results.", parent=self)
        box.setDetailedText("\n".join(self.warnings))
        box.exec()

    def run(self, fn, on_done: Callable[[object], None], label: str = "Working…") -> bool:
        if self.busy:
            QMessageBox.information(self, "Busy", "Another computation is still running.")
            return False
        self.busy = True
        self.busy_changed.emit(True)
        self._cancel = threading.Event()
        self._signals = sig = _Signals()
        self.warnings = []
        self.warnings_button.hide()
        self.label.setText(label)
        self.bar.setRange(0, 0)
        self.bar.show()
        self.cancel_button.show()
        sig.progress.connect(self._progress)
        sig.warned.connect(self._warned)
        sig.done.connect(lambda r: self._finish(on_done, r))
        sig.failed.connect(self._failed)
        QThreadPool.globalInstance().start(_Task(fn, sig, self._cancel))
        return True

    def cancel(self) -> None:
        self._cancel.set()
        self.label.setText("Cancelling after the current step…")

    def _progress(self, msg: str, i: int, n: int) -> None:
        self.label.setText(msg)
        if n:
            self.bar.setRange(0, n)
            self.bar.setValue(i)

    def _end(self, text: str) -> None:
        self.busy = False
        self._idle()
        self.label.setText(text)
        self.busy_changed.emit(False)

    def _finish(self, on_done, result) -> None:
        self._end("Done.")
        on_done(result)

    def _failed(self, msg: str, tb: str) -> None:
        self._end(msg.splitlines()[0] if msg else "Failed.")
        if msg != "Cancelled.":
            box = QMessageBox(QMessageBox.Warning, "eemkit", msg, parent=self)
            if tb:
                box.setDetailedText(tb)
            box.exec()


# --------------------------------------------------------------------------- #
# Form fields
# --------------------------------------------------------------------------- #

class OptionalFloat(QLineEdit):
    """A number field that may be left empty (= not set)."""

    def __init__(self, value=None, placeholder: str = "not set", required: bool = False,
                 parent=None):
        super().__init__(parent)
        self.required = required
        self.setPlaceholderText(placeholder)
        self.set_value(value)
        self.textChanged.connect(self._validate)
        self._validate()

    def value(self) -> float | None:
        t = self.text().strip().replace(",", ".")
        if not t:
            return None
        try:
            return float(t)
        except ValueError:
            return None

    def set_value(self, v) -> None:
        self.setText("" if v is None else f"{float(v):g}")

    def is_valid(self) -> bool:
        t = self.text().strip()
        if not t:
            return not self.required
        return self.value() is not None

    def _validate(self) -> None:
        self.setStyleSheet("" if self.is_valid() else "background: #fbe3e3;")


def spin(value: float, lo: float, hi: float, step: float = 1.0, decimals: int = 1,
         suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(float(value))
    if suffix:
        s.setSuffix(suffix)
    return s


def pair(*widgets: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        lay.addWidget(x)
    return w


def note(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #52514e;")
    return lab
