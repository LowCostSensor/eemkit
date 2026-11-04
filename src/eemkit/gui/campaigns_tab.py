"""Tab 5: differences between campaigns, along sites and with covariates."""

from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from eemkit import pipeline, plot
from eemkit.gui.common import DataFrameModel, PlotPanel, TaskBar, note, pair, primary
from eemkit.gui.state import Project

NONE = "(none)"


def _table_view(model: DataFrameModel) -> QTableView:
    v = QTableView()
    v.setModel(model)
    return v


class CampaignsTab(QWidget):
    def __init__(self, project: Project, tasks: TaskBar, parent=None):
        super().__init__(parent)
        self.project, self.tasks = project, tasks

        self.value = QComboBox()
        self.group = QComboBox()
        self.time = QComboBox()
        self.site = QComboBox()
        self.position = QComboBox()
        self.sites_file = QLineEdit()
        self.cov_file = QLineEdit()
        for e in (self.sites_file, self.cov_file):
            e.setReadOnly(True)
            e.setPlaceholderText("optional")
        b_sites = QPushButton("Choose…")
        b_sites.clicked.connect(lambda: self.choose_table("sites_table"))
        b_cov = QPushButton("Choose…")
        b_cov.clicked.connect(lambda: self.choose_table("covariates_table"))
        b_clear = QPushButton("Clear tables")
        b_clear.clicked.connect(self.clear_tables)

        g_cols = QGroupBox("Sample columns")
        f = QFormLayout(g_cols)
        f.addRow("Variable", self.value)
        f.addRow("Group (e.g. river)", self.group)
        f.addRow("Time (e.g. campaign)", self.time)
        f.addRow("Site", self.site)
        f.addRow(note("Replicates are averaged per site and time before any test, so they "
                      "are never counted as independent samples."))
        g_opt = QGroupBox("Optional tables")
        f = QFormLayout(g_opt)
        f.addRow("Site table", pair(self.sites_file, b_sites))
        f.addRow("Position along the river", self.position)
        f.addRow("Covariate table", pair(self.cov_file, b_cov))
        f.addRow("", b_clear)
        f.addRow(note("Site table: CSV with the group and site columns plus e.g. latitude, "
                      "longitude, distance_km. Covariate table: CSV with the group and time "
                      "columns, written exactly as in the samples (e.g. 2024-05), plus e.g. "
                      "discharge, rainfall. Rows are joined only on exact matches; missing "
                      "rows are reported."))

        self.b_run = primary(QPushButton("Analyse"))
        self.b_run.clicked.connect(self.analyse)
        self.b_save = QPushButton("Save to output folder")
        self.b_save.clicked.connect(self.save)

        self.warn = QLabel("")
        self.warn.setWordWrap(True)
        self.warn.setProperty("role", "warning")
        self.warn.hide()
        self.models = {k: DataFrameModel() for k in ("kruskal", "pairwise", "spatial",
                                                     "covariates", "design", "units")}
        self.plots = {k: PlotPanel() for k in ("time", "sites", "composition")}
        views = QTabWidget()
        views.addTab(self.plots["time"], "Over time")
        views.addTab(self.plots["sites"], "Along sites")
        views.addTab(self.plots["composition"], "PARAFAC composition")
        tests = QWidget()
        tl = QVBoxLayout(tests)
        for title, key in (("Kruskal–Wallis between times, within each group", "kruskal"),
                           ("Dunn's pairwise comparisons (Holm-adjusted p)", "pairwise")):
            tl.addWidget(QLabel(f"<b>{title}</b>"))
            tl.addWidget(_table_view(self.models[key]), 1)
        views.addTab(tests, "Tests")
        corr = QWidget()
        cl = QVBoxLayout(corr)
        for title, key in (("Spearman correlation with position", "spatial"),
                           ("Spearman correlation with covariates", "covariates")):
            cl.addWidget(QLabel(f"<b>{title}</b>"))
            cl.addWidget(_table_view(self.models[key]), 1)
        views.addTab(corr, "Correlations")
        views.addTab(_table_view(self.models["design"]), "Design")
        views.addTab(_table_view(self.models["units"]), "Site means")
        self.views = views

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(g_cols)
        ll.addWidget(g_opt)
        buttons = QHBoxLayout()
        buttons.addWidget(self.b_run)
        buttons.addWidget(self.b_save)
        ll.addLayout(buttons)
        ll.addStretch(1)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(self.warn)
        rl.addWidget(views, 1)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        QVBoxLayout(self).addWidget(split)
        project.changed.connect(self._on_changed)
        tasks.busy_changed.connect(lambda b: self.b_run.setEnabled(not b))
        self.refresh_columns()

    # columns ------------------------------------------------------------- #

    def table(self) -> pd.DataFrame | None:
        p = self.project
        if p.indices is None and p.model is None:
            return None
        return pipeline.sample_table(p.indices, p.model)

    def _site_table_columns(self) -> list[str]:
        path = self.project.resolve("sites_table", "campaigns")
        if path is None or not path.is_file():
            return []
        try:
            return list(pipeline.read_table(path).columns)
        except Exception:  # noqa: BLE001 - an unreadable table offers no columns
            return []

    def refresh_columns(self) -> None:
        df = self.table()
        c = self.project.settings["campaigns"]
        cols = [] if df is None else list(df.reset_index().columns)
        numeric = [] if df is None else [k for k in df.columns
                                         if pd.api.types.is_numeric_dtype(df[k])]
        labels = [k for k in cols if k not in numeric and k not in ("sample", "cdom_notes")]
        for box, items, want in ((self.value, numeric, self.value.currentText()),
                                 (self.group, labels, c.get("group")),
                                 (self.time, labels, c.get("time")),
                                 (self.site, [NONE] + labels, c.get("site") or NONE),
                                 (self.position, [NONE] + self._site_table_columns() + numeric,
                                  c.get("position") or NONE)):
            box.blockSignals(True)
            box.clear()
            box.addItems(list(dict.fromkeys(items)))
            if want:
                box.setCurrentText(want)
            box.blockSignals(False)
        self.sites_file.setText(c.get("sites_table", ""))
        self.cov_file.setText(c.get("covariates_table", ""))

    def _on_changed(self, what: str) -> None:
        if what in ("settings", "indices", "final"):
            self.refresh_columns()
        if what in ("indices", "final", "campaigns") and self.project.campaign is None:
            self._clear_results("Choose the columns and press Analyse.")

    def choose_table(self, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose table", str(self.project.base),
                                              "Tables (*.csv *.txt)")
        if path:
            self.set_table(key, path)

    def set_table(self, key: str, path: str) -> None:
        self.project.set_path_setting(key, path, "campaigns")
        self.project.invalidate("campaigns")
        self.refresh_columns()

    def clear_tables(self) -> None:
        self.project.set_settings("campaigns", {"sites_table": "", "covariates_table": ""},
                                  "campaigns")
        self.refresh_columns()

    # analysis ------------------------------------------------------------ #

    def _store(self) -> None:
        def val(box):
            t = box.currentText()
            return "" if t == NONE else t
        self.project.set_settings("campaigns", {
            "group": val(self.group), "time": val(self.time), "site": val(self.site),
            "position": val(self.position)}, "campaigns")

    def analyse(self) -> None:
        df = self.table()
        if df is None:
            QMessageBox.information(self, "eemkit", "Compute the indices (or fit the final "
                                    "PARAFAC model) first.")
            return
        self._store()
        value, settings, base = self.value.currentText(), self.project.settings, self.project.base

        def work(progress, cancelled):
            return pipeline.campaign_analysis(df, value, settings, base)

        def done(res):
            self.project.campaign = res
            self.project.changed.emit("campaigns")
            self.show_results()

        if not value:
            QMessageBox.information(self, "eemkit", "Choose a variable.")
            return
        self.tasks.run(work, done, "Comparing campaigns…")

    def _clear_results(self, message: str) -> None:
        for m in self.models.values():
            m.set_frame(pd.DataFrame())
        for p in self.plots.values():
            p.clear(message)
        self.warn.hide()

    def show_results(self) -> None:
        res = self.project.campaign
        if res is None:
            return
        c = self.project.settings["campaigns"]
        self.warn.setText("⚠ " + "\n⚠ ".join(res.warnings) if res.warnings else "")
        self.warn.setVisible(bool(res.warnings))
        for key, df in (("kruskal", res.kruskal), ("pairwise", res.pairwise),
                        ("spatial", res.spatial), ("covariates", res.covariates),
                        ("design", res.design.reset_index() if res.design is not None else None),
                        ("units", res.units)):
            self.models[key].set_frame(df if df is not None else pd.DataFrame())
        self.plots["time"].show_figure(plot.campaign_series(res.units, res.value,
                                                            group=c["group"], time=c["time"]))
        if res.spatial is not None:
            self.plots["sites"].show_figure(plot.along_sites(res.units, res.value, c["position"],
                                                             group=c["group"]))
        else:
            self.plots["sites"].clear("Choose a position column (e.g. distance_km from a site "
                                      "table) to see the variable along the sites.")
        pct = [k for k in res.units.columns if k.endswith("_pct") and not k.endswith("cv_pct")]
        if pct:
            self.plots["composition"].show_figure(plot.composition(
                res.units, pct, group=c["group"], time=c["time"]))
        else:
            self.plots["composition"].clear("Fit the final PARAFAC model to see the share of "
                                            "each component.")

    def save(self) -> None:
        res, out = self.project.campaign, self.project.resolve("output_dir")
        if res is None:
            QMessageBox.information(self, "eemkit", "Run the analysis first.")
            return
        if out is None or self.project.in_data_root(out):
            QMessageBox.information(self, "eemkit", "Choose an output folder outside the data "
                                    "folder (Project tab).")
            return
        written = pipeline.export_campaigns(out / "campaigns" / res.value, res,
                                            self.project.settings)
        QMessageBox.information(self, "eemkit", f"Wrote {len(written)} files to "
                                f"{out / 'campaigns' / res.value}.")
