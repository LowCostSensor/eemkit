"""Tab 3: fluorescence indices, Coble peaks and CDOM (absorbance) metrics."""

from __future__ import annotations

import warnings

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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
from eemkit.gui.common import DataFrameModel, PlotPanel, TaskBar, note, pair, primary, spin
from eemkit.gui.state import Project
from eemkit.pipeline import compute_absorbance, compute_indices

INDEX_COLUMNS = ("FI", "HIX", "BIX", "peak_B", "peak_T", "peak_A", "peak_M", "peak_C")
CDOM_COLUMNS = ("a254", "a350", "S275_295", "S350_400", "SR", "E2_E3", "SUVA254")


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

        self.cdom = QCheckBox("Compute CDOM metrics from the absorbance spectra")
        self.cdom.setChecked(True)
        self.use_base = QCheckBox("Subtract the mean absorbance over")
        self.base_lo = spin(680, 200, 1100, 1, 0, " nm")
        self.base_hi = spin(700, 200, 1100, 1, 0, " nm")
        self.min_r2 = spin(0.95, 0.0, 1.0, 0.01, 2)
        self.doc = QComboBox()
        cdom = QGroupBox("Absorbance (CDOM)")
        f = QFormLayout(cdom)
        f.addRow(self.cdom)
        f.addRow("Baseline", pair(self.use_base, self.base_lo, QLabel("–"), self.base_hi))
        f.addRow("Minimum R² of slope fits", self.min_r2)
        f.addRow("DOC column (mg/L)", self.doc)
        f.addRow(note("a254, a350: Napierian absorption coefficients (m⁻¹). S275–295, "
                      "S350–400, SR: log-linear fits (Helms et al. 2008). E2:E3 = A250/A365. "
                      "SUVA254 (L mg⁻¹ m⁻¹, Weishaar et al. 2003) needs a DOC column. Values "
                      "that need a non-positive absorbance or a poor fit are left empty, with "
                      "the reason in cdom_notes. The R² threshold is an eemkit quality "
                      "setting, not a literature value: report it."))
        self.b_compute = primary(QPushButton("Compute indices"))
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
        ll.addWidget(cdom)
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
        a = self.project.settings["absorbance"]
        self.use_base.setChecked(bool(a.get("baseline")))
        if a.get("baseline"):
            self.base_lo.setValue(float(a["baseline"][0]))
            self.base_hi.setValue(float(a["baseline"][1]))
        self.min_r2.setValue(float(a["min_r2"]))
        self._fill_doc()

    def _fill_doc(self) -> None:
        ds = self.project.after_raman if self.project.after_raman is not None \
            else self.project.raw
        cols = [] if ds is None else [c for c in ds.coords if ds[c].dims == ("sample",)
                                      and c != "sample"]
        want = self.project.settings["absorbance"].get("doc_column", "")
        self.doc.blockSignals(True)
        self.doc.clear()
        self.doc.addItems(["(none)"] + sorted(set(cols) | ({want} if want else set())))
        self.doc.setCurrentText(want or "(none)")
        self.doc.blockSignals(False)

    def _on_changed(self, what: str) -> None:
        if what == "settings":
            self.load_settings()
        if what in ("raw", "corrected"):
            self._fill_doc()
        if what in ("indices", "corrected") and self.project.indices is None:
            self.model.set_frame(pd.DataFrame())
            self.plot.clear("Compute the indices to plot them.")

    def compute(self) -> None:
        if self.project.after_raman is None:
            QMessageBox.information(self, "eemkit", "Apply the corrections first.")
            return
        self.project.set_settings("indices", {"ex_method": self.ex_method.currentText(),
                                              "bix_em_den": self.bix_den.value()}, "indices")
        doc = self.doc.currentText()
        self.project.set_settings("absorbance", {
            "baseline": [self.base_lo.value(), self.base_hi.value()]
            if self.use_base.isChecked() else [],
            "min_r2": self.min_r2.value(),
            "doc_column": "" if doc == "(none)" else doc}, "indices")
        ds, settings = self.project.after_raman, self.project.settings
        with_cdom = self.cdom.isChecked() and "absorbance" in ds

        def work(progress, cancelled):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", EEMKitWarning)
                df = compute_indices(ds, settings)
                if with_cdom:
                    df = df.join(compute_absorbance(ds, settings))
            return df, [str(w.message) for w in caught]

        def done(result):
            df, warns = result
            self.project.indices = df
            self.project.changed.emit("indices")
            self.model.set_frame(df)
            self.view.resizeColumnsToContents()
            values = [c for c in INDEX_COLUMNS + CDOM_COLUMNS if c in df]
            meta = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])
                    and c != "cdom_notes"]
            # default axes: the campaign columns if chosen, else a column with few values
            c = self.project.settings["campaigns"]
            few = [m for m in meta if df[m].nunique() <= len(plot.CATEGORICAL)]
            timeish = [m for m in meta if any(k in m.lower() for k in
                                              ("campaign", "date", "month", "time"))]
            x0 = c.get("time") if c.get("time") in meta else next(
                (m for m in timeish + meta if 1 < df[m].nunique() <= 40),
                meta[0] if meta else "")
            by0 = c.get("group") if c.get("group") in meta else next(
                (m for m in few if m != x0 and df[m].nunique() > 1), "(none)")
            for box, items, cur in ((self.what, values, None), (self.x, meta, x0),
                                    (self.by, ["(none)"] + meta, by0)):
                box.blockSignals(True)
                box.clear()
                box.addItems(items)
                if cur:
                    box.setCurrentText(cur)
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
