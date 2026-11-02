"""The open project: settings, pairing table and the results of each step."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import xarray as xr
from PySide6.QtCore import QObject, Signal

from eemkit import pipeline

STAGES = ("pairing", "raw", "corrected", "indices", "exploration", "final")
#: Settings that hold file paths, as (section, key).
PATH_SETTINGS = (("project", "data_root"), ("project", "pairing"), ("project", "output_dir"),
                 ("spectral", "ex_factors"), ("spectral", "em_factors"))


class Project(QObject):
    """Holds everything the tabs share and announces what changed.

    A result is dropped (and ``changed`` emitted) whenever something it
    depends on changes, so a tab never shows results computed from settings
    or data that are no longer current.
    """

    changed = Signal(str)  # one of STAGES, "settings", or "display" (redraw only)

    def __init__(self):
        super().__init__()
        self.path: Path | None = None  # the project's settings TOML
        self.settings: dict = pipeline.default_settings()
        self.inventory: pd.DataFrame | None = None
        self.pairing: pd.DataFrame | None = None
        self.raw: xr.Dataset | None = None
        self.after_raman: xr.Dataset | None = None
        self.corrected: xr.Dataset | None = None
        self.indices: pd.DataFrame | None = None
        self.exploration: pipeline.Exploration | None = None
        self.model: xr.Dataset | None = None
        self.split: xr.Dataset | None = None
        self.dirty = False

    # paths -------------------------------------------------------------- #

    @property
    def base(self) -> Path:
        """Folder relative paths in the settings are resolved against."""
        return self.path.parent if self.path else Path.cwd()

    def resolve(self, key: str, section: str = "project") -> Path | None:
        v = self.settings[section].get(key, "")
        if not v:
            return None
        p = Path(v)
        # normpath, not resolve(): folds "config/../data" without following drive mappings
        return p if p.is_absolute() else Path(os.path.normpath(self.base / p))

    def in_data_root(self, path: str | Path) -> bool:
        """True if ``path`` lies in the (read-only) data folder."""
        root = self.resolve("data_root")
        return root is not None and Path(path).resolve().is_relative_to(root.resolve())

    def relative(self, path: str | Path) -> str:
        """``path`` relative to the project file when it lies below it; '' stays ''."""
        if not str(path):
            return ""
        p = Path(path)
        if self.path is not None:
            try:
                p = p.resolve().relative_to(self.base.resolve())
            except ValueError:
                pass
        return p.as_posix()

    def set_path_setting(self, key: str, path: str | Path, section: str = "project") -> None:
        """Store ``path`` relative to the project file when it lies below it."""
        self.settings[section][key] = self.relative(path)
        self.dirty = True

    # invalidation ------------------------------------------------------- #

    def invalidate(self, stage: str) -> None:
        """Drop the results of ``stage`` and of every later stage."""
        later = STAGES[STAGES.index(stage):]
        if "raw" in later:
            self.raw = None
        if "corrected" in later:
            self.after_raman = self.corrected = None
        if "indices" in later:
            self.indices = None
        if "exploration" in later:
            self.exploration = None
        if "final" in later:
            self.model = self.split = None
        for s in later:
            self.changed.emit(s)

    def set_settings(self, section: str, values: dict, invalidates: str | None) -> None:
        """Update one settings section; drop results that depended on it."""
        old = self.settings.get(section, {})
        new = {**old, **values}
        if new == old:
            return
        self.settings[section] = new
        self.dirty = True
        self.changed.emit("settings")
        if invalidates:
            self.invalidate(invalidates)

    @property
    def eem_colours(self) -> str:
        """Name of the EEM colour map (a key of :data:`eemkit.plot.COLORMAPS`)."""
        return self.settings["display"]["eem_colours"]

    def set_eem_colours(self, name: str) -> None:
        if name != self.eem_colours:
            self.set_settings("display", {"eem_colours": name}, None)
            self.changed.emit("display")

    # files -------------------------------------------------------------- #

    def save(self, path: str | Path | None = None) -> Path:
        if path is not None:
            old_base = self.base
            self.path = Path(path)
            for section, key in PATH_SETTINGS:  # re-express paths against the new folder
                v = self.settings[section].get(key, "")
                if v:
                    self.set_path_setting(key, v if Path(v).is_absolute() else old_base / v,
                                          section)
        if self.path is None:
            raise ValueError("no project file chosen")
        pipeline.save_settings(self.settings, self.path)
        self.dirty = False
        return self.path

    def open(self, path: str | Path) -> None:
        self.settings = pipeline.load_settings(path)
        self.path = Path(path)
        self.inventory = self.pairing = None
        self.invalidate("pairing")
        self.dirty = False
        self.changed.emit("settings")
        self.changed.emit("display")
