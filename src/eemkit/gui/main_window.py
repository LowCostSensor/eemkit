"""The main window: a sidebar of steps, one page per step, menus and the shared progress bar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from eemkit import __version__
from eemkit.gui import theme
from eemkit.gui.campaigns_tab import CampaignsTab
from eemkit.gui.common import TaskBar
from eemkit.gui.corrections_tab import CorrectionsTab
from eemkit.gui.export_tab import ExportTab
from eemkit.gui.indices_tab import IndicesTab
from eemkit.gui.parafac_tab import ParafacTab
from eemkit.gui.project_tab import ProjectTab
from eemkit.gui.state import Project
from eemkit.pipeline import versions

#: Sidebar entries: (title, one-line description).
STEPS = (("Project and pairing", "Data folder, pairing table"),
         ("Corrections", "Inner filter, Raman units, scatter"),
         ("Indices and CDOM", "FI, HIX, BIX, peaks, absorbance"),
         ("PARAFAC", "Models, validation, outliers"),
         ("Rivers and dates", "Campaigns, sites, covariates"),
         ("Export", "Tables, figures, OpenFluor"))
THEME_NAMES = {"system": "Follow the system", "light": "Light", "dark": "Dark"}

ABOUT = f"""<b>eemkit {__version__}</b><br>
Processing and PARAFAC modelling of fluorescence excitation-emission matrices
(EEMs) of dissolved organic matter.<br><br>
Every result can be reproduced from the saved project file with
<code>eemkit.pipeline</code>.<br><br>
Methods: inner filter, Kothawala et al. 2013; Raman units, Lawaetz &amp; Stedmon 2009;
PARAFAC and split-half validation, Murphy et al. 2013; core consistency,
Bro &amp; Kiers 2003."""

#: Choices of the View > EEM colours menu (names of eemkit.plot.COLORMAPS).
EEM_COLOURS = {"eclipse": "Cary Eclipse (violet, blue, green, yellow, red)",
               "blues": "Single-hue blue (perceptually ordered, for print)"}


class MainWindow(QMainWindow):
    def __init__(self, project_file: str | Path | None = None):
        super().__init__()
        self.project = Project()
        self.tasks = TaskBar()
        self.project_tab = ProjectTab(self.project, self.tasks)
        self.corrections_tab = CorrectionsTab(self.project, self.tasks)
        self.indices_tab = IndicesTab(self.project, self.tasks)
        self.parafac_tab = ParafacTab(self.project, self.tasks)
        self.campaigns_tab = CampaignsTab(self.project, self.tasks)
        self.export_tab = ExportTab(self.project, self.tasks)
        self.pages = QStackedWidget()
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for i, (page, (title, _)) in enumerate(zip(
                (self.project_tab, self.corrections_tab, self.indices_tab, self.parafac_tab,
                 self.campaigns_tab, self.export_tab), STEPS, strict=True)):
            self.pages.addWidget(page)
            self.nav.addItem(QListWidgetItem(f"{i + 1}   {title}"))
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.summary = QLabel("")
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(250)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        brand = QLabel("eemkit")
        brand.setObjectName("brand")
        tagline = QLabel("EEM processing and PARAFAC")
        tagline.setObjectName("tagline")
        for w in (brand, tagline):
            sl.addWidget(w)
        sl.addWidget(self.nav, 1)
        sl.addWidget(self.summary)
        central = QWidget()
        cl = QHBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(sidebar)
        cl.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.statusBar().addPermanentWidget(self.tasks, 1)
        self._menus()
        self.project.changed.connect(lambda _: self._title())
        self.project.changed.connect(lambda _: self._status())
        self.resize(1440, 900)
        if project_file:
            self.open_project(project_file)
        self._title()
        self._status()

    def _status(self) -> None:
        """Mark finished steps in the sidebar and summarise the project under it."""
        p = self.project
        done = (p.raw is not None, p.corrected is not None, p.indices is not None,
                p.model is not None, p.campaign is not None, False)
        partial = (p.pairing is not None, p.after_raman is not None, False,
                   p.exploration is not None, False, False)
        for i, (title, desc) in enumerate(STEPS):
            mark = "  ✓" if done[i] else ("  •" if partial[i] else "")
            item = self.nav.item(i)
            item.setText(f"{i + 1}   {title}{mark}")
            item.setToolTip(desc)
        lines = []
        if p.pairing is not None and "include" in p.pairing:
            inc = int((p.pairing["include"].astype(str).str.lower() == "yes").sum())
            lines.append(f"{len(p.pairing)} rows in the pairing table, {inc} included")
        if p.raw is not None:
            lines.append(f"{p.raw.sizes['sample']} samples loaded")
        if p.model is not None:
            lines.append(f"Final model: {p.model.sizes['component']} components")
        self.summary.setText("\n".join(lines) or "Open a project or choose a data folder.")

    def _menus(self) -> None:
        m = self.menuBar().addMenu("&File")
        for text, key, slot in (("&New project", QKeySequence.New, self.new_project),
                                ("&Open project…", QKeySequence.Open, self.open_dialog),
                                ("&Save project", QKeySequence.Save, self.save_project),
                                ("Save project &as…", QKeySequence.SaveAs, self.save_as),
                                (None, None, None),
                                ("&Quit", QKeySequence.Quit, self.close)):
            if text is None:
                m.addSeparator()
                continue
            act = QAction(text, self)
            act.setShortcut(key)
            act.triggered.connect(slot)
            m.addAction(act)
        view = self.menuBar().addMenu("&View")
        t = view.addMenu("&Theme")
        tgroup = QActionGroup(self)
        self.theme_actions = {}
        current = theme.saved_theme()
        for name, text in THEME_NAMES.items():
            act = QAction(text, self, checkable=True)
            act.setChecked(name == current)
            act.triggered.connect(lambda _, n=name: self.set_theme(n))
            tgroup.addAction(act)
            t.addAction(act)
            self.theme_actions[name] = act
        v = view.addMenu("&EEM colours")
        group = QActionGroup(self)
        self.colour_actions = {}
        for name, text in EEM_COLOURS.items():
            act = QAction(text, self, checkable=True)
            act.triggered.connect(lambda _, n=name: self.project.set_eem_colours(n))
            group.addAction(act)
            v.addAction(act)
            self.colour_actions[name] = act
        self.project.changed.connect(self._sync_colours)
        self._sync_colours("display")
        h = self.menuBar().addMenu("&Help")
        act = QAction("&About eemkit", self)
        act.triggered.connect(self.about)
        h.addAction(act)

    def set_theme(self, name: str) -> None:
        """Switch the light/dark theme; a user preference, not part of the project."""
        theme.save_theme(name)
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, name)

    def _sync_colours(self, what: str) -> None:
        if what in ("settings", "display"):
            act = self.colour_actions.get(self.project.eem_colours)
            if act is not None:
                act.setChecked(True)

    def _title(self) -> None:
        name = self.project.path.name if self.project.path else "untitled project"
        self.setWindowTitle(f"eemkit - {name}{' *' if self.project.dirty else ''}")

    # project files ------------------------------------------------------- #

    def _confirm_discard(self) -> bool:
        if not self.project.dirty:
            return True
        ans = QMessageBox.question(self, "eemkit", "Save the changes to the project first?",
                                   QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ans == QMessageBox.Save:
            return self.save_project()
        return ans == QMessageBox.Discard

    def new_project(self) -> None:
        if self._confirm_discard():
            self.project.__init__()  # reset in place: the tabs keep their reference
            self.project.invalidate("pairing")
            self.project.changed.emit("settings")
            self.project.changed.emit("display")

    def open_dialog(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "eemkit project (*.toml)")
        if path:
            self.open_project(path)

    def open_project(self, path: str | Path) -> None:
        try:
            self.project.open(path)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            QMessageBox.warning(self, "eemkit", f"Cannot open {path}:\n{exc}")
        self._title()

    def save_project(self) -> bool:
        if self.project.path is None:
            return self.save_as()
        self.project.save()
        self._title()
        return True

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "project.toml",
                                              "eemkit project (*.toml)")
        if not path:
            return False
        if self.project.in_data_root(path):
            QMessageBox.warning(self, "eemkit", "The data folder is read only; save the project "
                                "elsewhere.")
            return False
        self.project.save(path)
        self.project.changed.emit("settings")
        self._title()
        return True

    def about(self) -> None:
        v = ", ".join(f"{k} {x}" for k, x in versions().items())
        QMessageBox.about(self, "About eemkit", f"{ABOUT}<br><br><small>{v}</small>")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self.tasks.busy:
            self.tasks.cancel()
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
