"""Tab 3: fluorescence indices and Coble peaks."""

from __future__ import annotations

import warnings

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from eemkit import plot
from eemkit.errors import EEMKitWarning
from eemkit.gui.common import DataFrameModel, PlotPanel, TaskBar, note, spin
from eemkit.gui.state import Project
from eemkit.pipeline import compute_indices

INDEX_COLUMNS = ("FI", "HIX", "BIX", "peak_B", "peak_T", "peak_A", "peak_M", "peak_C")


class IndicesTab(QWidget):
    def __init__(self, project: Project, tasks: TaskBar, parent=None):
        super().__init__(parent)
        self.project, self.tasks = project, tasks

        self.ex_method = QComboBox()
        self.ex_method.addItems(["linear", "nearest", "exact"])
        self.bix_den = spin(430, 300, 600, 1, 0, " nm")
        settings = QGroupBox("Settings")
        f = QFormLayout(settings)
        f.addRow("Excitations off the grid", self.ex_method)
        f.addRow("BIX denominator emission", self.bix_den)
        f.addRow(note("FI: Cory & McKnight 2005 (ex 370, em 470/520). HIX: Ohno 2002. BIX: "
                      "Huguet et al. 2009. Peaks: Coble 1996. Computed after Raman units, "
                      "before scatter removal."))
        self.b_compute = QPushButton("Compute indices")
        self.b_compute.clicked.connect(self.compute)
        self.b_export = QPushButton("Save table…")
        self.b_export.clicked.connect(self.export)

        self.model = DataFrameModel()
        view = QTableView()
        view.setModel(self.model)
        view.setSortingEnabled(False)
        self.view = view

        self.what = QComboBox()
        self.x = QComboBox()
        self.by = QComboBox()
        for c in (self.what, self.x, self.by):
            c.currentIndexChanged.connect(self.draw)
        self.plot = PlotPanel()
        controls = QHBoxLayout()
        for lab, w in (("Show", self.what), ("along", self.x), ("grouped by", self.by)):
            controls.addWidget(QLabel(lab))
            controls.addWidget(w, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(settings)
        buttons = QHBoxLayout()
        buttons.addWidget(self.b_compute)
        buttons.addWidget(self.b_export)
        ll.addLayout(buttons)
        ll.addWidget(view, 1)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addLayout(controls)
        rl.addWidget(self.plot, 1)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        QVBoxLayout(self).addWidget(split)
        project.changed.connect(self._on_changed)
        tasks.busy_changed.connect(lambda b: self.b_compute.setEnabled(not b))
        self.load_settings()

    def load_settings(self) -> None:
        s = self.project.settings["indices"]
        self.ex_method.setCurrentText(s["ex_method"])
        self.bix_den.setValue(float(s["bix_em_den"]))

    def _on_changed(self, what: str) -> None:
        if what == "settings":
            self.load_settings()
        if what in ("indices", "corrected") and self.project.indices is None:
            self.model.set_frame(pd.DataFrame())
            self.plot.clear("Compute the indices to plot them.")

    def compute(self) -> None:
        if self.project.after_raman is None:
            QMessageBox.information(self, "eemkit", "Apply the corrections first.")
            return
        self.project.set_settings("indices", {"ex_method": self.ex_method.currentText(),
                                              "bix_em_den": self.bix_den.value()}, "indices")
        ds, settings = self.project.after_raman, self.project.settings

        def work(progress, cancelled):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", EEMKitWarning)
                df = compute_indices(ds, settings)
            return df, [str(w.message) for w in caught]

        def done(result):
            df, warns = result
            self.project.indices = df
            self.project.changed.emit("indices")
            self.model.set_frame(df)
            self.view.resizeColumnsToContents()
            meta = [c for c in df.columns if c not in INDEX_COLUMNS]
            for box, items in ((self.what, [c for c in INDEX_COLUMNS if c in df]),
                               (self.x, meta), (self.by, ["(none)"] + meta)):
                box.blockSignals(True)
                box.clear()
                box.addItems(items)
                box.blockSignals(False)
            self.draw()
            if warns:
                QMessageBox.information(self, "eemkit", "\n".join(warns))

        self.tasks.run(work, done, "Computing indices…")

    def draw(self) -> None:
        df = self.project.indices
        if df is None or not self.what.currentText() or not self.x.currentText():
            return
        by = self.by.currentText()
        data = df.reset_index()
        if by == "(none)":
            data["all samples"] = "all"
            by = "all samples"
        if data[by].nunique() > len(plot.CATEGORICAL):
            self.plot.clear(f"'{by}' has more than {len(plot.CATEGORICAL)} groups; choose "
                            "another grouping.")
            return
        fig = plot.scores_over(data, [self.what.currentText()], x=self.x.currentText(), by=by,
                               width=6.5)
        self.plot.show_figure(fig)

    def export(self) -> None:
        if self.project.indices is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save indices", "indices.csv", "CSV (*.csv)")
        if path and self.project.in_data_root(path):
            QMessageBox.warning(self, "eemkit", "The data folder is read only; choose another "
                                "folder.")
        elif path:
            self.project.indices.to_csv(path, float_format="%.6g")
