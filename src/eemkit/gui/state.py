"""The open project: settings, pairing table and the results of each step."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import xarray as xr
from PySide6.QtCore import QObject, Signal

from eemkit import pipeline

STAGES = ("pairing", "raw", "corrected", "indices", "exploration", "final")


class Project(QObject):
    """Holds everything the tabs share and announces what changed.

    A result is dropped (and ``changed`` emitted) whenever something it
    depends on changes, so a tab never shows results computed from settings
    or data that are no longer current.
    """

    changed = Signal(str)  # one of STAGES, or "settings"

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

    def resolve(self, key: str) -> Path | None:
        v = self.settings["project"].get(key, "")
        if not v:
            return None
        p = Path(v)
        return p if p.is_absolute() else self.base / p

    def in_data_root(self, path: str | Path) -> bool:
        """True if ``path`` lies in the (read-only) data folder."""
        root = self.resolve("data_root")
        return root is not None and Path(path).resolve().is_relative_to(root.resolve())

    def set_path_setting(self, key: str, path: str | Path) -> None:
        """Store ``path`` relative to the project file when it lies below it."""
        p = Path(path)
        if self.path is not None:
            try:
                p = p.resolve().relative_to(self.base.resolve())
            except ValueError:
                pass
        self.settings["project"][key] = p.as_posix() if str(p) else ""
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

    # files -------------------------------------------------------------- #

    def save(self, path: str | Path | None = None) -> Path:
        if path is not None:
            old_base = self.base
            self.path = Path(path)
            for key in ("data_root", "pairing", "output_dir"):
                v = self.settings["project"].get(key, "")
                if v and not Path(v).is_absolute():
                    self.set_path_setting(key, old_base / v)
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
