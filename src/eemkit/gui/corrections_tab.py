"""Tab 2: correction settings, applying them, and a preview of any sample."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from eemkit import corrections as C
from eemkit import pipeline, plot
from eemkit.gui.common import OptionalFloat, PlotPanel, TaskBar, note, pair, spin
from eemkit.gui.state import Project

BANDS = {"rayleigh1": "Rayleigh 1st order", "raman1": "Raman 1st order",
         "rayleigh2": "Rayleigh 2nd order", "raman2": "Raman 2nd order"}
STAGES = {"Raw sample": ("raw", "intensity"), "Raw blank": ("raw", "blank_intensity"),
          "After inner filter, blank, Raman units": ("after_raman", "intensity"),
          "Corrected (scatter removed, cropped)": ("corrected", "intensity"),
          "Spectral correction factors": ("after_raman", "spectral_correction_ex")}
CONVENTIONS = {"multiply": "correction factors (multiply)",
               "divide": "instrument response (divide)"}


class CorrectionsTab(QWidget):
    def __init__(self, project: Project, tasks: TaskBar, parent=None):
        super().__init__(parent)
        self.project, self.tasks = project, tasks
        s = pipeline.DEFAULTS

        self.factor_files = {k: QLineEdit() for k in ("ex_factors", "em_factors")}
        self.factor_info = {k: QLabel("") for k in self.factor_files}
        self.convention = QComboBox()
        self.convention.addItems(list(CONVENTIONS.values()))
        g_sp = QGroupBox("Instrument spectral correction (optional)")
        f = QFormLayout(g_sp)
        for key, label in (("ex_factors", "Excitation file"), ("em_factors", "Emission file")):
            edit = self.factor_files[key]
            edit.setReadOnly(True)
            edit.setPlaceholderText("not applied")
            b_choose, b_clear = QPushButton("Choose…"), QPushButton("Clear")
            b_choose.clicked.connect(lambda _, k=key: self.choose_factors(k))
            b_clear.clicked.connect(lambda _, k=key: self.set_factor_file(k, ""))
            f.addRow(label, pair(edit, b_choose, b_clear))
            self.factor_info[key].setStyleSheet("color: gray")
            f.addRow("", self.factor_info[key])
        f.addRow("Files contain", self.convention)
        f.addRow(note("Applied first, to sample and blank EEMs. Two columns: wavelength (nm), "
                      "factor. Factors are specific to your instrument and must be measured "
                      "(e.g. with certified reference standards); eemkit provides none. Leave "
                      "empty if you have no factors: indices then depend on the instrument "
                      "(Cory et al. 2010)."))

        self.l_abs = OptionalFloat(required=True, placeholder="required, e.g. 1")
        self.l_fl = OptionalFloat(required=True, placeholder="required, e.g. 1")
        g_ife = QGroupBox("Inner filter (Kothawala et al. 2013)")
        f = QFormLayout(g_ife)
        f.addRow("Absorbance cuvette (cm)", self.l_abs)
        f.addRow("Fluorescence cuvette (cm)", self.l_fl)
        f.addRow(note("Path lengths depend on your cuvettes and have no default."))

        r = s["raman"]
        self.r_ex = spin(r["ex"], 200, 600, 1, 0, " nm")
        self.r_lo = spin(r["em_range"][0], 200, 800, 1, 0, " nm")
        self.r_hi = spin(r["em_range"][1], 200, 800, 1, 0, " nm")
        self.r_base = QCheckBox("Subtract a linear baseline under the peak")
        g_ram = QGroupBox("Raman units (Lawaetz && Stedmon 2009)")  # && shows one &
        f = QFormLayout(g_ram)
        f.addRow("Excitation", self.r_ex)
        f.addRow("Emission range", pair(self.r_lo, QLabel("–"), self.r_hi))
        f.addRow(self.r_base)

        sc = s["scatter"]
        self.shift = spin(sc["raman_shift_cm1"], 2500, 4500, 10, 0, " cm⁻¹")
        self.widths = {}
        g_sc = QGroupBox("Scatter removal")
        f = QFormLayout(g_sc)
        f.addRow("Water Raman shift", self.shift)
        for band, label in BANDS.items():
            lo = spin(sc[band][0], 0, 100, 1, 1, " nm")
            hi = spin(sc[band][1], 0, 100, 1, 1, " nm")
            self.widths[band] = (lo, hi)
            f.addRow(label, pair(QLabel("below"), lo, QLabel("above"), hi))
        self.zero_below = OptionalFloat(placeholder="off")
        f.addRow("Zeros below Rayleigh, offset (nm)", self.zero_below)
        self.interp = QComboBox()
        self.interp.addItems(["no (keep as missing)", "em", "ex", "both"])
        f.addRow("Interpolate removed bands", self.interp)
        f.addRow(note("Defaults are generic (10 nm bands); check them against the blanks in the "
                      "preview. Zeros below Rayleigh: Thygesen et al. 2004."))

        self.crop = {k: OptionalFloat(placeholder="no limit")
                     for k in ("ex_min", "ex_max", "em_min", "em_max")}
        g_crop = QGroupBox("Crop")
        f = QFormLayout(g_crop)
        f.addRow("Excitation (nm)", pair(self.crop["ex_min"], QLabel("–"), self.crop["ex_max"]))
        f.addRow("Emission (nm)", pair(self.crop["em_min"], QLabel("–"), self.crop["em_max"]))

        self.missing = QComboBox()
        self.missing.addItems(["error", "drop", "keep"])
        g_miss = QGroupBox("Samples without blank or absorbance")
        f = QFormLayout(g_miss)
        f.addRow("Policy", self.missing)

        self.b_apply = QPushButton("Apply corrections")
        self.b_apply.clicked.connect(self.apply)
        form = QWidget()
        fl = QVBoxLayout(form)
        for g in (g_sp, g_ife, g_ram, g_sc, g_crop, g_miss):
            fl.addWidget(g)
        fl.addWidget(self.b_apply)
        fl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(form)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(380)

        self.sample = QComboBox()
        self.stage = QComboBox()
        self.stage.addItems(list(STAGES))
        self.sample.currentIndexChanged.connect(self.preview)
        self.stage.currentIndexChanged.connect(self.preview)
        self.plot = PlotPanel()
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right = QWidget()
        rl = QVBoxLayout(right)
        top = QHBoxLayout()
        top.addWidget(QLabel("Sample"))
        top.addWidget(self.sample, 1)
        top.addWidget(QLabel("Step"))
        top.addWidget(self.stage, 1)
        rl.addLayout(top)
        rl.addWidget(self.plot, 1)
        rl.addWidget(self.summary)

        split = QSplitter()
        split.addWidget(scroll)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        QVBoxLayout(self).addWidget(split)
        project.changed.connect(self._on_changed)
        tasks.busy_changed.connect(lambda b: self.b_apply.setEnabled(not b))
        self.load_settings()

    # settings <-> form -------------------------------------------------- #

    def load_settings(self) -> None:
        s = self.project.settings
        for key in self.factor_files:
            p = self.project.resolve(key, "spectral")
            self.set_factor_file(key, str(p) if p is not None else "")
        self.convention.setCurrentText(CONVENTIONS[s["spectral"].get("convention", "multiply")])
        self.l_abs.set_value(s["inner_filter"].get("absorbance_path_length_cm"))
        self.l_fl.set_value(s["inner_filter"].get("fluorescence_path_length_cm"))
        r = s["raman"]
        self.r_ex.setValue(float(r["ex"]))
        self.r_lo.setValue(float(r["em_range"][0]))
        self.r_hi.setValue(float(r["em_range"][1]))
        self.r_base.setChecked(bool(r["baseline"]))
        sc = s["scatter"]
        self.shift.setValue(float(sc["raman_shift_cm1"]))
        for band, (lo, hi) in self.widths.items():
            lo.setValue(float(sc[band][0]))
            hi.setValue(float(sc[band][1]))
        self.zero_below.set_value(sc.get("zero_below_rayleigh"))
        self.interp.setCurrentIndex(["em", "ex", "both"].index(sc["interpolate"]) + 1
                                    if sc.get("interpolate") else 0)
        for k, w in self.crop.items():
            w.set_value(s["crop"].get(k))
        self.missing.setCurrentText(s["missing"]["policy"])

    def store_settings(self) -> bool:
        if not (self.l_abs.is_valid() and self.l_fl.is_valid()):
            QMessageBox.information(self, "eemkit", "Enter both cuvette path lengths (cm). "
                                    "They depend on your measurement and have no default.")
            return False
        files = {k: e.text() for k, e in self.factor_files.items()}
        if bool(files["ex_factors"]) != bool(files["em_factors"]):
            QMessageBox.information(self, "eemkit", "Spectral correction needs both the "
                                    "excitation and the emission file (or neither).")
            return False
        convention = next(k for k, v in CONVENTIONS.items()
                          if v == self.convention.currentText())
        sections = {
            "spectral": {**{k: self.project.relative(v) for k, v in files.items()},
                         "convention": convention},
            "inner_filter": {"absorbance_path_length_cm": self.l_abs.value(),
                             "fluorescence_path_length_cm": self.l_fl.value()},
            "raman": {"ex": self.r_ex.value(), "em_range": [self.r_lo.value(), self.r_hi.value()],
                      "baseline": self.r_base.isChecked()},
            "scatter": {"raman_shift_cm1": self.shift.value(),
                        **{b: [lo.value(), hi.value()] for b, (lo, hi) in self.widths.items()},
                        "zero_below_rayleigh": self.zero_below.value(),
                        "interpolate": False if self.interp.currentIndex() == 0
                        else self.interp.currentText()},
            "crop": {k: w.value() for k, w in self.crop.items()},
            "missing": {"policy": self.missing.currentText()},
        }
        # read the whole form before storing: storing emits signals that reload it
        for name, values in sections.items():
            self.project.set_settings(name, values, "corrected")
        return True

    def set_factor_file(self, key: str, path: str) -> None:
        """Show ``path`` and the range it covers (the file is read to check it)."""
        self.factor_files[key].setText(path)
        info = self.factor_info[key]
        if not path:
            info.setText("")
            return
        try:
            wl, f = C.read_correction_file(path)
        except (OSError, ValueError) as exc:  # FileFormatError is a ValueError
            info.setText(f"cannot read: {exc}")
            return
        info.setText(f"{wl.size} values, {wl.min():g}-{wl.max():g} nm, factors "
                     f"{f.min():.4g}-{f.max():.4g}")

    def choose_factors(self, key: str) -> None:
        start = self.factor_files[key].text() or str(self.project.base)
        path, _ = QFileDialog.getOpenFileName(
            self, "Spectral correction factors", start,
            "Text or CSV (*.csv *.txt *.dat);;All files (*)")
        if path:
            self.set_factor_file(key, path)

    # actions ------------------------------------------------------------ #

    def apply(self) -> None:
        if self.project.raw is None:
            QMessageBox.information(self, "eemkit", "Load the data first (Project tab).")
            return
        if not self.store_settings():
            return
        raw, settings, base = self.project.raw, self.project.settings, self.project.base

        def work(progress, cancelled):
            progress("Spectral correction, inner filter, blank, Raman units", 0, 2)
            after = pipeline.correct_until_raman(raw, settings, base=base)
            progress("Scatter and crop", 1, 2)
            return after, pipeline.finish_corrections(after, settings)

        def done(result):
            self.project.after_raman, self.project.corrected = result
            self.project.changed.emit("corrected")
            self.stage.setCurrentIndex(3)

        self.tasks.run(work, done, "Applying corrections…")

    def _on_changed(self, what: str) -> None:
        if what == "settings":
            self.load_settings()
        if what == "display":
            self.preview()
        if what in ("raw", "corrected", "pairing"):
            ds = self.project.raw
            current = self.sample.currentText()
            self.sample.blockSignals(True)
            self.sample.clear()
            if ds is not None:
                self.sample.addItems([str(x) for x in ds["sample"].values])
                if current:
                    self.sample.setCurrentText(current)
            self.sample.blockSignals(False)
            self.update_summary()
            self.preview()

    def update_summary(self) -> None:
        p = self.project
        lines = []
        if p.raw is not None:
            done = p.after_raman if p.after_raman is not None else p.raw
            lines.append(f"{p.raw.sizes['sample']} samples loaded. Spectral correction: "
                         f"{C.spectral_correction_status(done)}.")
        if p.corrected is not None:
            ife = p.corrected["ife_factor"]
            ra = p.corrected["raman_area"].values
            miss = float(np.isnan(p.corrected["intensity"]).mean()) * 100
            lines.append(f"Inner-filter factor over all cells: median {float(ife.median()):.3f}, "
                         f"max {float(ife.max()):.3f}. Raman area of the blanks: "
                         f"{np.nanmin(ra):.4g}-{np.nanmax(ra):.4g} (CV "
                         f"{np.nanstd(ra) / np.nanmean(ra) * 100:.1f} %). Corrected grid: ex "
                         f"{p.corrected.ex.min().item():g}-{p.corrected.ex.max().item():g}, em "
                         f"{p.corrected.em.min().item():g}-{p.corrected.em.max().item():g} nm; "
                         f"{miss:.1f} % missing cells.")
        self.summary.setText("\n".join(lines))

    def preview(self) -> None:
        name = self.sample.currentText()
        where, var = STAGES[self.stage.currentText()]
        ds = getattr(self.project, where)
        if var == "spectral_correction_ex":
            if ds is None or var not in ds:
                self.plot.clear("No spectral correction applied." if ds is not None else
                                "Apply the corrections to see this step.")
            else:
                self.plot.show_figure(plot.spectral_factors(ds, width=6.0))
            return
        if not name or ds is None or var not in ds or name not in ds["sample"].values:
            self.plot.clear("Apply the corrections to see this step." if name else
                            "Load the data to preview samples.")
            return
        da = ds[var].sel(sample=name)
        if da.isnull().all():
            self.plot.clear("No data for this sample at this step.")
            return
        title = f"{name}: {self.stage.currentText()}"
        vmax = None
        cor = self.project.corrected
        if where != "corrected" and cor is not None and name in cor["sample"].values:
            # scatter outshines fluorescence: cap the colour scale at the maximum of the
            # cells kept after scatter removal
            kept = cor["intensity"].sel(sample=name).notnull()
            vmax = float(da.sel(ex=kept.ex, em=kept.em).where(kept).max())
            title += " (colour scale capped at the fluorescence maximum)"
        fig = plot.eems({title: da}, ncols=1, width=6.0, vmax=vmax,
                        cmap=self.project.eem_colours)
        self.plot.show_figure(fig)
