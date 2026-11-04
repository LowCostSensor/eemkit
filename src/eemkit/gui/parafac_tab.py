"""Tab 4: exploratory PARAFAC models, outliers, and the final model."""

from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from eemkit import pipeline, plot
from eemkit.gui.common import DataFrameModel, PlotPanel, TaskBar, note, pair, primary, spin
from eemkit.gui.state import Project


def _int_spin(value: int, lo: int, hi: int) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(int(value))
    return s


def _sci(value: float) -> QLineEdit:
    e = QLineEdit(f"{float(value):g}")
    e.setMaximumWidth(90)
    return e


def _float(edit: QLineEdit) -> float:
    return float(edit.text().strip().replace(",", "."))


class ParafacTab(QWidget):
    def __init__(self, project: Project, tasks: TaskBar, parent=None):
        super().__init__(parent)
        self.project, self.tasks = project, tasks
        p = pipeline.DEFAULTS["parafac"]

        self.r_from = _int_spin(2, 1, 20)
        self.r_to = _int_spin(7, 1, 20)
        self.n_init = _int_spin(p["n_init"], 1, 500)
        self.norm = QComboBox()
        self.norm.addItems(["norm", "none"])
        self.tol = _sci(p["tol"])
        self.max_iter = _int_spin(p["max_iter"], 10, 1_000_000)
        self.seed = _int_spin(p["random_state"], 0, 2**31 - 1)
        g_exp = QGroupBox("Exploratory models (Murphy et al. 2013)")
        f = QFormLayout(g_exp)
        f.addRow("Components", pair(self.r_from, QLabel("to"), self.r_to))
        f.addRow("Random starts", self.n_init)
        f.addRow("Sample scaling", self.norm)
        f.addRow("Convergence (rel. SSE change)", self.tol)
        f.addRow("Max iterations", self.max_iter)
        f.addRow("Random seed", self.seed)

        sh = p["split_half"]
        self.sh_init = _int_spin(sh["n_init"], 1, 500)
        self.sh_strat = QLineEdit()
        self.sh_strat.setPlaceholderText("e.g. river, campaign")
        self.sh_thr = spin(sh["threshold"], 0.5, 1.0, 0.01, 2)
        self.sh_seed = _int_spin(sh["random_state"], 0, 2**31 - 1)
        g_sh = QGroupBox("Split-half validation (S4C6T3)")
        f = QFormLayout(g_sh)
        f.addRow("Random starts per half", self.sh_init)
        f.addRow("Balance halves by", self.sh_strat)
        f.addRow("Tucker congruence threshold", self.sh_thr)
        f.addRow("Split seed", self.sh_seed)

        self.excluded = QListWidget()
        self.excluded.setMaximumHeight(110)
        self.b_unexclude = QPushButton("Put back selected")
        self.b_unexclude.clicked.connect(self.unexclude)
        g_exc = QGroupBox("Samples left out of the model")
        v = QVBoxLayout(g_exc)
        v.addWidget(self.excluded)
        v.addWidget(self.b_unexclude)
        v.addWidget(note("Add samples from the Outliers view. Record why in your notes: "
                         "the list is saved in the project file."))

        self.b_explore = primary(QPushButton("Run exploratory models"))
        self.b_explore.clicked.connect(self.explore)

        fin = p["final"]
        self.f_rank = _int_spin(3, 1, 20)
        self.f_init = _int_spin(fin["n_init"], 1, 500)
        self.f_tol = _sci(fin["tol"])
        self.f_iter = _int_spin(fin["max_iter"], 10, 1_000_000)
        g_fin = QGroupBox("Final model")
        f = QFormLayout(g_fin)
        f.addRow("Components", self.f_rank)
        f.addRow("Random starts", self.f_init)
        f.addRow("Convergence", self.f_tol)
        f.addRow("Max iterations", self.f_iter)
        self.b_final = primary(QPushButton("Fit final model"))
        self.b_final.clicked.connect(self.fit_final)
        f.addRow(self.b_final)

        form = QWidget()
        fl = QVBoxLayout(form)
        for w in (g_exp, g_sh, g_exc, self.b_explore, g_fin):
            fl.addWidget(w)
        fl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(form)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(360)

        # results
        self.summary_model = DataFrameModel()
        summary_view = QTableView()
        summary_view.setModel(self.summary_model)
        self.diag_plot = PlotPanel()
        page_summary = QWidget()
        v = QVBoxLayout(page_summary)
        v.addWidget(summary_view, 1)
        v.addWidget(self.diag_plot, 2)

        self.load_rank = QComboBox()
        self.load_rank.currentIndexChanged.connect(self.draw_loadings)
        self.load_plot = PlotPanel()
        page_load = QWidget()
        v = QVBoxLayout(page_load)
        v.addWidget(pair(QLabel("Model"), self.load_rank))
        v.addWidget(self.load_plot, 1)

        self.out_rank = QComboBox()
        self.out_rank.currentIndexChanged.connect(self.draw_outliers)
        self.out_by = QComboBox()
        self.out_by.currentIndexChanged.connect(self.draw_outliers)
        self.out_plot = PlotPanel()
        self.out_model = DataFrameModel(float_format="{:.4f}")
        self.out_view = QTableView()
        self.out_view.setModel(self.out_model)
        self.out_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        b_exclude = QPushButton("Leave selected samples out")
        b_exclude.clicked.connect(self.exclude_selected)
        page_out = QWidget()
        v = QVBoxLayout(page_out)
        v.addWidget(pair(QLabel("Model"), self.out_rank, QLabel("colour by"), self.out_by))
        h = QSplitter()
        h.addWidget(self.out_plot)
        side = QWidget()
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(self.out_view, 1)
        sv.addWidget(b_exclude)
        h.addWidget(side)
        v.addWidget(h, 1)

        self.final_plot = PlotPanel()
        self.final_text = QLabel("")
        self.final_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        page_final = QWidget()
        v = QVBoxLayout(page_final)
        v.addWidget(self.final_text)
        v.addWidget(self.final_plot, 1)

        self.results = QTabWidget()
        self.results.addTab(page_summary, "Number of components")
        self.results.addTab(page_load, "Components by model")
        self.results.addTab(page_out, "Outliers")
        self.results.addTab(page_final, "Final model")

        split = QSplitter()
        split.addWidget(scroll)
        split.addWidget(self.results)
        split.setStretchFactor(1, 1)
        QVBoxLayout(self).addWidget(split)
        project.changed.connect(self._on_changed)
        tasks.busy_changed.connect(self._busy)
        self.load_settings()

    # settings ----------------------------------------------------------- #

    def _busy(self, busy: bool) -> None:
        self.b_explore.setEnabled(not busy)
        self.b_final.setEnabled(not busy)

    def load_settings(self) -> None:
        p = self.project.settings["parafac"]
        ranks = [int(r) for r in p["ranks"]] or [2, 7]
        self.r_from.setValue(min(ranks))
        self.r_to.setValue(max(ranks))
        self.n_init.setValue(int(p["n_init"]))
        self.norm.setCurrentText(p["normalization"] or "none")
        self.tol.setText(f"{float(p['tol']):g}")
        self.max_iter.setValue(int(p["max_iter"]))
        self.seed.setValue(int(p["random_state"]))
        sh = p["split_half"]
        self.sh_init.setValue(int(sh["n_init"]))
        self.sh_strat.setText(", ".join(sh["stratify"]))
        self.sh_thr.setValue(float(sh["threshold"]))
        self.sh_seed.setValue(int(sh["random_state"]))
        self.excluded.clear()
        self.excluded.addItems([str(s) for s in p["exclude"]])
        fin = p["final"]
        if fin.get("rank"):
            self.f_rank.setValue(int(fin["rank"]))
        self.f_init.setValue(int(fin["n_init"]))
        self.f_tol.setText(f"{float(fin['tol']):g}")
        self.f_iter.setValue(int(fin["max_iter"]))

    def _exploration_settings(self) -> dict | None:
        try:
            tol = _float(self.tol)
        except ValueError:
            QMessageBox.information(self, "eemkit", "Convergence must be a number, e.g. 1e-6.")
            return None
        if self.r_to.value() < self.r_from.value():
            QMessageBox.information(self, "eemkit", "The component range is empty.")
            return None
        old = self.project.settings["parafac"]
        return {**old, "ranks": list(range(self.r_from.value(), self.r_to.value() + 1)),
                "n_init": self.n_init.value(),
                "normalization": None if self.norm.currentText() == "none" else "norm",
                "tol": tol, "max_iter": self.max_iter.value(), "random_state": self.seed.value(),
                "exclude": [self.excluded.item(i).text() for i in range(self.excluded.count())],
                "split_half": {**old["split_half"], "n_init": self.sh_init.value(),
                               "stratify": [s.strip() for s in self.sh_strat.text().split(",")
                                            if s.strip()],
                               "threshold": self.sh_thr.value(),
                               "random_state": self.sh_seed.value()}}

    def _store(self, values: dict) -> None:
        old = self.project.settings["parafac"]
        same_model = {k: v for k, v in old.items() if k != "final"} == \
            {k: v for k, v in values.items() if k != "final"}
        self.project.set_settings("parafac", values, None if same_model else "exploration")
        if values.get("final") != old.get("final") and same_model:
            self.project.invalidate("final")

    # actions ------------------------------------------------------------ #

    def _input(self) -> object | None:
        if self.project.corrected is None:
            QMessageBox.information(self, "eemkit", "Apply the corrections first.")
            return None
        try:
            return pipeline.parafac_input(self.project.corrected, self.project.settings)
        except Exception as exc:  # noqa: BLE001 - settings problems shown to the user
            QMessageBox.warning(self, "eemkit", str(exc))
            return None

    def explore(self) -> None:
        values = self._exploration_settings()
        if values is None:
            return
        self._store(values)
        ds = self._input()
        if ds is None:
            return
        settings = self.project.settings

        def work(progress, cancelled):
            return pipeline.explore(ds, settings, progress=progress, cancelled=cancelled)

        def done(exploration):
            self.project.exploration = exploration
            self.project.changed.emit("exploration")
            self.show_exploration()

        n = len(values["ranks"])
        self.tasks.run(work, done, f"Fitting {n} models with split-half validation…")

    def fit_final(self) -> None:
        values = self._exploration_settings()
        if values is None:
            return
        try:
            values["final"] = {**values["final"], "rank": self.f_rank.value(),
                               "n_init": self.f_init.value(), "tol": _float(self.f_tol),
                               "max_iter": self.f_iter.value()}
        except ValueError:
            QMessageBox.information(self, "eemkit", "Convergence must be a number, e.g. 1e-8.")
            return
        self._store(values)
        ds = self._input()
        if ds is None:
            return
        settings = self.project.settings

        def work(progress, cancelled):
            return pipeline.fit_final(ds, settings, progress=progress, cancelled=cancelled)

        def done(result):
            self.project.model, self.project.split = result
            self.project.changed.emit("final")
            self.show_final()
            self.results.setCurrentIndex(3)

        self.tasks.run(work, done, "Fitting the final model…")

    def exclude_selected(self) -> None:
        rows = sorted({i.row() for i in self.out_view.selectionModel().selectedRows()})
        df = self.out_model.df
        if not rows or df.empty:
            return
        current = {self.excluded.item(i).text() for i in range(self.excluded.count())}
        for name in df.index[rows]:
            if name not in current:
                self.excluded.addItem(str(name))
        self._store(self._exploration_settings() or self.project.settings["parafac"])
        QMessageBox.information(self, "eemkit", "Samples set aside. Run the exploratory models "
                                "again to see the effect.")

    def unexclude(self) -> None:
        for item in self.excluded.selectedItems():
            self.excluded.takeItem(self.excluded.row(item))
        values = self._exploration_settings()
        if values is not None:
            self._store(values)

    # views -------------------------------------------------------------- #

    def _on_changed(self, what: str) -> None:
        if what == "settings":
            self.load_settings()
        if what in ("exploration", "corrected") and self.project.exploration is None:
            self.summary_model.set_frame(pd.DataFrame())
            for panel in (self.diag_plot, self.load_plot, self.out_plot):
                panel.clear("Run the exploratory models.")
            self.out_model.set_frame(pd.DataFrame())
        if what in ("final", "corrected") and self.project.model is None:
            self.final_plot.clear("Fit the final model.")
            self.final_text.setText("")
        if what == "display":
            self.draw_loadings()
            if self.project.model is not None:
                self.show_final()

    def show_exploration(self) -> None:
        ex = self.project.exploration
        t = ex.table.copy()
        self.summary_model.set_frame(t.round(4))
        fig = plot.rank_diagnostics(
            t, threshold=self.project.settings["parafac"]["split_half"]["threshold"], width=7.5)
        self.diag_plot.show_figure(fig)
        ranks = [str(r) for r in ex.models]
        meta = [c for c in next(iter(ex.models.values())).coords
                if c not in ("sample", "ex", "em", "component", "init", "stratum")
                and next(iter(ex.models.values()))[c].dims == ("sample",)
                and not c.endswith(("_file", "_time")) and not c.startswith(("eem_", "abs_"))]
        for box, items in ((self.load_rank, ranks), (self.out_rank, ranks),
                           (self.out_by, ["(none)"] + meta)):
            box.blockSignals(True)
            box.clear()
            box.addItems(items)
            box.blockSignals(False)
        self.draw_loadings()
        self.draw_outliers()

    def draw_loadings(self) -> None:
        ex = self.project.exploration
        if ex is None or not self.load_rank.currentText():
            return
        r = int(self.load_rank.currentText())
        self.load_plot.show_figure(plot.components(ex.models[r], ex.splits[r], width=8.0,
                                                   cmap=self.project.eem_colours))

    def draw_outliers(self) -> None:
        ex = self.project.exploration
        if ex is None or not self.out_rank.currentText():
            return
        m = ex.models[int(self.out_rank.currentText())]
        by = self.out_by.currentText()
        by = None if by in ("", "(none)") or m[by].to_series().nunique() > len(plot.CATEGORICAL) \
            else by
        self.out_plot.show_figure(plot.leverage(m, by=by, width=5.0))
        df = pd.DataFrame({"leverage": m["leverage_sample"].values,
                           "residual SS": m["sse_sample_normalized"].values},
                          index=m["sample"].values).sort_values("leverage", ascending=False)
        self.out_model.set_frame(df)

    def show_final(self) -> None:
        m, sh = self.project.model, self.project.split
        a = m.attrs
        verdict = "VALIDATED" if sh.attrs["validated"] else "NOT validated"
        self.final_text.setText(
            f"{m.sizes['component']} components, {m.sizes['sample']} samples. Explained variance "
            f"{a['explained_variance_pct']:.3f} %, core consistency {a['core_consistency_pct']:.1f}"
            f" %, {a['n_init_at_best_minimum']}/{a['n_init']} starts at the best minimum. "
            f"Split-half minimum Tucker congruence {sh.attrs['min_tcc']:.4f}: {verdict}.")
        self.final_plot.show_figure(plot.components(m, sh, width=8.0,
                                                    cmap=self.project.eem_colours))
