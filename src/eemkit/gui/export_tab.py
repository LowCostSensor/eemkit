"""Tab 5: write results, OpenFluor file, figures and the processing record."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eemkit import pipeline
from eemkit.gui.common import TaskBar, note
from eemkit.gui.state import Project
from eemkit.parafac.export import METADATA_KEYS

#: OpenFluor fields the user can fill; the others are derived from the model.
USER_FIELDS = ("name", "creator", "email", "doi", "reference", "fluorometer", "sources",
               "ecozones", "methods", "preprocess", "validation", "description")


class ExportTab(QWidget):
    def __init__(self, project: Project, tasks: TaskBar, parent=None):
        super().__init__(parent)
        self.project, self.tasks = project, tasks

        self.what = {k: QCheckBox(label) for k, label in (
            ("corrected", "Corrected EEMs (netCDF, with processing history)"),
            ("indices", "Fluorescence indices (CSV)"),
            ("exploration", "Exploratory PARAFAC summary (CSV)"),
            ("model", "Final model: Fmax, loadings, OpenFluor file, model (netCDF)"),
            ("figures", "Figures (PDF and PNG)"))}
        g_what = QGroupBox("Write")
        v = QVBoxLayout(g_what)
        for box in self.what.values():
            box.setChecked(True)
            v.addWidget(box)
        v.addWidget(note("settings.toml and processing_record.json (software versions, every "
                         "processing step and its parameters) are always written, so the "
                         "analysis can be repeated with eemkit.pipeline."))

        self.meta = {k: QLineEdit() for k in USER_FIELDS}
        for e in self.meta.values():
            e.setPlaceholderText("?")
            e.editingFinished.connect(self.store_metadata)
        g_of = QGroupBox("OpenFluor metadata (Murphy et al. 2014)")
        f = QFormLayout(g_of)
        for k, e in self.meta.items():
            f.addRow(k, e)
        f.addRow(note("Empty fields are written as '?'. Check the file against the current "
                      "OpenFluor template before uploading."))

        self.b_export = QPushButton("Export to the output folder")
        self.b_export.clicked.connect(self.export)
        self.b_open = QPushButton("Open output folder")
        self.b_open.clicked.connect(self.open_folder)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.b_export)
        buttons.addWidget(self.b_open)
        buttons.addStretch(1)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(g_what, 1)
        top.addWidget(g_of, 1)
        lay.addLayout(top)
        lay.addLayout(buttons)
        lay.addWidget(self.log, 1)
        project.changed.connect(lambda w: self.load_settings() if w == "settings" else None)
        tasks.busy_changed.connect(lambda b: self.b_export.setEnabled(not b))
        self.load_settings()

    def load_settings(self) -> None:
        of = self.project.settings["parafac"]["final"].get("openfluor", {})
        for k, e in self.meta.items():
            e.setText(str(of.get(k, "")))

    def store_metadata(self) -> None:
        final = dict(self.project.settings["parafac"]["final"])
        final["openfluor"] = {k: e.text().strip() for k, e in self.meta.items()
                              if e.text().strip()}
        if final != self.project.settings["parafac"]["final"]:
            self.project.settings["parafac"]["final"] = final
            self.project.dirty = True

    def open_folder(self) -> None:
        out = self.project.resolve("output_dir")
        if out is not None and out.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def export(self) -> None:
        out = self.project.resolve("output_dir")
        if out is None:
            QMessageBox.information(self, "eemkit", "Choose an output folder (Project tab).")
            return
        if self.project.in_data_root(out):
            QMessageBox.warning(self, "eemkit", "The output folder is inside the read-only data "
                                "folder; choose another one.")
            return
        self.store_metadata()
        p, w = self.project, {k: b.isChecked() for k, b in self.what.items()}
        meta = {k: v for k, v in p.settings["parafac"]["final"].get("openfluor", {}).items()
                if k in METADATA_KEYS}
        args = dict(corrected=p.corrected if w["corrected"] else None,
                    indices=p.indices if w["indices"] else None,
                    exploration=p.exploration if w["exploration"] else None,
                    model=p.model if w["model"] else None,
                    split=p.split if w["model"] else None, openfluor=meta)
        missing = [k for k in ("corrected", "indices", "exploration", "model")
                   if w[k] and getattr(p, k) is None]
        settings = p.settings

        def work(progress, cancelled):
            progress("Writing files", 0, 0)
            return pipeline.export_results(out, settings, figures=False, **args)

        def done(paths):
            if w["figures"]:  # matplotlib stays in the GUI thread
                paths += pipeline.export_figures(out / "figures", settings, args["exploration"],
                                                 args["model"], args["split"])
            self.log.appendPlainText(f"Wrote {len(paths)} files to {out}:")
            for path in paths:
                self.log.appendPlainText(f"  {path.relative_to(out)}")
            if missing:
                self.log.appendPlainText(f"Not computed yet, so not written: {', '.join(missing)}")

        self.tasks.run(work, done, "Exporting…")
