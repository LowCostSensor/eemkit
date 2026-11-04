"""Tab 1: data folder, file inventory and the pairing table."""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from eemkit import pipeline
from eemkit.errors import EEMKitWarning
from eemkit.gui.common import (
    EXCLUDED,
    SUGGESTED,
    ChoiceDelegate,
    DataFrameModel,
    TaskBar,
    note,
    pair,
    primary,
)
from eemkit.gui.state import Project
from eemkit.io.discover import scan_folder, suggest_pairing
from eemkit.io.pairing import read_pairing

FILE_KINDS = {"eem_file": "eem", "eem_blank_file": "eem", "abs_file": "absorbance",
              "abs_blank_file": "absorbance"}


def _pairing_colour(row: pd.Series):
    if str(row.get("include", "")).lower() not in ("yes", "y", "true", "1", "si", "sì"):
        return EXCLUDED
    if row.get("pairing_status", "") == "suggested":
        return SUGGESTED
    return None


class ProjectTab(QWidget):
    def __init__(self, project: Project, tasks: TaskBar, parent=None):
        super().__init__(parent)
        self.project, self.tasks = project, tasks

        self.data_root = QLineEdit()
        self.pairing_path = QLineEdit()
        self.output_dir = QLineEdit()
        for edit in (self.data_root, self.pairing_path, self.output_dir):
            edit.setReadOnly(True)
        b_root = QPushButton("Choose…")
        b_root.clicked.connect(self.choose_data_root)
        b_pair = QPushButton("Open…")
        b_pair.clicked.connect(self.open_pairing)
        b_out = QPushButton("Choose…")
        b_out.clicked.connect(self.choose_output)
        paths = QGroupBox("Project")
        form = QFormLayout(paths)
        form.addRow("Data folder", pair(self.data_root, b_root))
        form.addRow("", note("Read only: eemkit never writes, renames or moves anything in the "
                             "data folder."))
        form.addRow("Pairing table", pair(self.pairing_path, b_pair))
        form.addRow("Output folder", pair(self.output_dir, b_out))

        self.b_scan = QPushButton("1. Scan data folder")
        self.b_scan.clicked.connect(self.scan)
        self.b_suggest = QPushButton("2. Draft pairing from scan")
        self.b_suggest.clicked.connect(self.suggest)
        self.b_include = QPushButton("Include selected rows")
        self.b_include.clicked.connect(lambda: self.set_include(True))
        self.b_exclude = QPushButton("Exclude selected rows")
        self.b_exclude.clicked.connect(lambda: self.set_include(False))
        self.b_save = QPushButton("Save pairing table")
        self.b_save.clicked.connect(self.save_pairing)
        self.b_load = primary(QPushButton("3. Check and load data"))
        self.b_load.clicked.connect(self.load_data)
        self.b_load.setDefault(True)
        buttons = QHBoxLayout()
        for b in (self.b_scan, self.b_suggest, self.b_include, self.b_exclude, self.b_save,
                  self.b_load):
            buttons.addWidget(b)
        buttons.addStretch(1)

        self.pairing_model = DataFrameModel(row_colour=_pairing_colour)
        self.pairing_model.edited.connect(self._pairing_edited)
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.pairing_model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter rows…")
        self.filter.textChanged.connect(self.proxy.setFilterFixedString)
        self.pairing_view = QTableView()
        self.pairing_view.setModel(self.proxy)
        self.pairing_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pairing_view.setSortingEnabled(True)
        self.pairing_view.sortByColumn(-1, Qt.AscendingOrder)  # file order until a click
        pairing_box = QWidget()
        pl = QVBoxLayout(pairing_box)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(note("One row per sample. Rows drafted from the scan are yellow and start "
                          "excluded: check each pairing, then include it. Grey rows are not "
                          "used. Double-click a cell to edit it."))
        pl.addWidget(self.filter)
        pl.addWidget(self.pairing_view)

        self.files_model = DataFrameModel()
        files_view = QTableView()
        files_view.setModel(self.files_model)
        files_view.setSortingEnabled(True)

        inner = QTabWidget()
        inner.addTab(pairing_box, "Pairing table")
        inner.addTab(files_view, "Files found")
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setPlaceholderText("Problems and warnings appear here.")
        split = QSplitter(Qt.Vertical)
        split.addWidget(inner)
        split.addWidget(self.messages)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)

        lay = QVBoxLayout(self)
        lay.addWidget(paths)
        lay.addLayout(buttons)
        lay.addWidget(split, 1)
        project.changed.connect(self._on_changed)
        tasks.busy_changed.connect(self._busy)
        self.refresh_paths()

    # ------------------------------------------------------------------ #

    def _busy(self, busy: bool) -> None:
        for b in (self.b_scan, self.b_suggest, self.b_load):
            b.setEnabled(not busy)

    def _on_changed(self, what: str) -> None:
        if what == "settings":
            self.refresh_paths()
            path = self.project.resolve("pairing")
            if self.project.pairing is None and path is not None and path.is_file():
                self._read_pairing(path)
        if what == "pairing" and self.project.pairing is None:
            self.pairing_model.set_frame(pd.DataFrame())

    def refresh_paths(self) -> None:
        for key, edit in (("data_root", self.data_root), ("pairing", self.pairing_path),
                          ("output_dir", self.output_dir)):
            p = self.project.resolve(key)
            edit.setText(str(p) if p else "")

    def say(self, text: str) -> None:
        self.messages.appendPlainText(text)

    # ------------------------------------------------------------------ #

    def choose_data_root(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Data folder (read only)",
                                             self.data_root.text())
        if d:
            self.project.set_path_setting("data_root", d)
            self.project.invalidate("pairing")
            self.project.changed.emit("settings")

    def choose_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.output_dir.text())
        if d:
            if self.project.in_data_root(d):
                QMessageBox.warning(self, "eemkit", "The output folder must not be inside the "
                                    "data folder, which is read only.")
                return
            self.project.set_path_setting("output_dir", d)
            self.project.changed.emit("settings")

    def open_pairing(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Pairing table", self.pairing_path.text(),
                                              "CSV (*.csv)")
        if path and self._read_pairing(Path(path)):
            self.project.set_path_setting("pairing", path)
            self.project.changed.emit("settings")

    def _read_pairing(self, path: Path) -> bool:
        try:
            df = read_pairing(path, check_files=False)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            QMessageBox.warning(self, "eemkit", str(exc))
            return False
        df["include"] = df["include"].map({True: "yes", False: "no"})
        self._set_pairing(df)
        self.say(f"Opened {path}: {len(df)} rows, {int((df['include'] == 'yes').sum())} "
                 "included.")
        return True

    def _set_pairing(self, df: pd.DataFrame) -> None:
        self.project.pairing = df
        self.pairing_model.set_frame(df)
        self.pairing_model.editable = set(df.columns)
        self.pairing_view.setItemDelegateForColumn(
            list(df.columns).index("include"), ChoiceDelegate(lambda: ["yes", "no"], self))
        for col, kind in FILE_KINDS.items():
            if col in df.columns:
                self.pairing_view.setItemDelegateForColumn(
                    list(df.columns).index(col),
                    ChoiceDelegate(lambda k=kind: self._files_of(k), self))
        self.pairing_view.resizeColumnsToContents()
        self.project.invalidate("raw")

    def _files_of(self, kind: str) -> list[str]:
        inv = self.project.inventory
        if inv is None:
            return []
        return list(inv.loc[inv["kind"] == kind, "file"])

    def _pairing_edited(self) -> None:
        self.project.dirty = True
        self.project.invalidate("raw")

    def scan(self) -> None:
        root = self.project.resolve("data_root")
        if root is None or not root.is_dir():
            QMessageBox.information(self, "eemkit", "Choose the data folder first.")
            return

        def work(progress, cancelled):
            return scan_folder(root, progress=lambda i, n: progress("Scanning files", i, n))

        def done(inv):
            self.project.inventory = inv
            self.files_model.set_frame(inv)
            counts = inv["kind"].value_counts().to_dict()
            self.say(f"Scanned {root}: {len(inv)} CSV files, {counts.get('eem', 0)} EEM, "
                     f"{counts.get('absorbance', 0)} absorbance, {counts.get('unknown', 0)} not "
                     f"recognised; {int(inv['is_blank'].sum())} look like blanks.")
            for _, r in inv[inv["kind"] == "unknown"].iterrows():
                self.say(f"  not used: {r['file']}: {r['problem']}")

        self.tasks.run(work, done, "Scanning data folder…")

    def suggest(self) -> None:
        if self.project.inventory is None:
            QMessageBox.information(self, "eemkit", "Scan the data folder first.")
            return
        if self.project.pairing is not None and len(self.project.pairing):
            ok = QMessageBox.question(self, "eemkit", "Replace the current pairing table with a "
                                      "new draft?")
            if ok != QMessageBox.Yes:
                return
        draft = suggest_pairing(self.project.inventory)
        self._set_pairing(draft)
        self.project.dirty = True
        n_abs = int((draft["abs_file"] != "").sum())
        self.say(f"Drafted {len(draft)} rows ({n_abs} with an absorbance match). All rows are "
                 "excluded until you check and include them.")

    def set_include(self, include: bool) -> None:
        df = self.project.pairing
        rows = {self.proxy.mapToSource(i).row() for i in
                self.pairing_view.selectionModel().selectedRows()}
        if df is None or not rows:
            return
        idx = df.index[sorted(rows)]
        df.loc[idx, "include"] = "yes" if include else "no"
        if include and "pairing_status" in df.columns:
            df.loc[idx, "pairing_status"] = "checked"
        self.pairing_model.set_frame(df)
        self._pairing_edited()

    def save_pairing(self) -> bool:
        df = self.project.pairing
        if df is None:
            return False
        path = self.project.resolve("pairing")
        if path is None:
            name, _ = QFileDialog.getSaveFileName(self, "Save pairing table", "pairing.csv",
                                                  "CSV (*.csv)")
            if not name:
                return False
            path = Path(name)
            self.project.set_path_setting("pairing", path)
            self.project.changed.emit("settings")
        if self.project.in_data_root(path):
            QMessageBox.warning(self, "eemkit", "The pairing table cannot be saved inside the "
                                "read-only data folder.")
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        self.say(f"Saved {path}")
        return True

    def load_data(self) -> None:
        if self.project.pairing is not None and not self.save_pairing():
            return
        settings, base = self.project.settings, self.project.base

        def work(progress, cancelled):
            progress("Reading files", 0, 0)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", EEMKitWarning)
                ds = pipeline.load(settings, base)
            return ds, [str(w.message) for w in caught]

        def done(result):
            ds, warns = result
            self.project.raw = ds
            self.project.changed.emit("raw")
            n = ds.sizes["sample"]
            nb = int(ds["blank_intensity"].notnull().any(("ex", "em")).sum()) \
                if "blank_intensity" in ds else 0
            na = int(ds["absorbance"].notnull().any("wavelength").sum()) \
                if "absorbance" in ds else 0
            self.say(f"Loaded {n} samples (ex {ds.ex.min().item():g}-{ds.ex.max().item():g} nm, "
                     f"em {ds.em.min().item():g}-{ds.em.max().item():g} nm); {nb} with a blank "
                     f"EEM, {na} with absorbance.")
            for w in warns:
                self.say(f"  warning: {w}")

        self.tasks.run(work, done, "Loading data…")
