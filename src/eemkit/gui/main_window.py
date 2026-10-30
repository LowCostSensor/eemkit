"""The main window: one tab per step, a File menu and the shared progress bar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QTabWidget

from eemkit import __version__
from eemkit.gui.common import TaskBar
from eemkit.gui.corrections_tab import CorrectionsTab
from eemkit.gui.export_tab import ExportTab
from eemkit.gui.indices_tab import IndicesTab
from eemkit.gui.parafac_tab import ParafacTab
from eemkit.gui.project_tab import ProjectTab
from eemkit.gui.state import Project
from eemkit.pipeline import versions

ABOUT = f"""<b>eemkit {__version__}</b><br>
Processing and PARAFAC modelling of fluorescence excitation-emission matrices
(EEMs) of dissolved organic matter.<br><br>
Every result can be reproduced from the saved project file with
<code>eemkit.pipeline</code>.<br><br>
Methods: inner filter, Kothawala et al. 2013; Raman units, Lawaetz &amp; Stedmon 2009;
PARAFAC and split-half validation, Murphy et al. 2013; core consistency,
Bro &amp; Kiers 2003."""


class MainWindow(QMainWindow):
    def __init__(self, project_file: str | Path | None = None):
        super().__init__()
        self.project = Project()
        self.tasks = TaskBar()
        self.tabs = QTabWidget()
        self.project_tab = ProjectTab(self.project, self.tasks)
        self.corrections_tab = CorrectionsTab(self.project, self.tasks)
        self.indices_tab = IndicesTab(self.project, self.tasks)
        self.parafac_tab = ParafacTab(self.project, self.tasks)
        self.export_tab = ExportTab(self.project, self.tasks)
        for tab, name in ((self.project_tab, "1  Project and pairing"),
                          (self.corrections_tab, "2  Corrections"),
                          (self.indices_tab, "3  Indices"),
                          (self.parafac_tab, "4  PARAFAC"),
                          (self.export_tab, "5  Export")):
            self.tabs.addTab(tab, name)
        self.setCentralWidget(self.tabs)
        self.statusBar().addPermanentWidget(self.tasks, 1)
        self._menus()
        self.project.changed.connect(lambda _: self._title())
        self.resize(1400, 900)
        if project_file:
            self.open_project(project_file)
        self._title()

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
        h = self.menuBar().addMenu("&Help")
        act = QAction("&About eemkit", self)
        act.triggered.connect(self.about)
        h.addAction(act)

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
