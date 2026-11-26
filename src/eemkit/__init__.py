"""eemkit: EEM processing and PARAFAC modelling of dissolved organic matter fluorescence."""

__version__ = "0.5.0"

import importlib
from typing import TYPE_CHECKING

from eemkit.errors import (
    Cancelled,
    CorrectionError,
    EEMKitError,
    EEMKitWarning,
    FileFormatError,
    GridError,
    PairingError,
    SettingsError,
)

#: Subpackages and functions available as ``eemkit.<name>``. They are imported on
#: first use (PEP 562), so that ``import eemkit.gui`` can show the start-up screen
#: before numpy, pandas, xarray and scipy are loaded.
_SUBMODULES = ("corrections", "indices", "parafac", "pipeline")
_FUNCTIONS = {
    "stack": "eemkit.core.dataset",
    "infer_common_grid": "eemkit.core.grid",
    "regular_grid": "eemkit.core.grid",
    "resample": "eemkit.core.grid",
    "get_history": "eemkit.core.history",
    "mean_cycles": "eemkit.io.cary60",
    "read_cary60": "eemkit.io.cary60",
    "read_cary_eclipse": "eemkit.io.cary_eclipse",
    "scan_folder": "eemkit.io.discover",
    "suggest_pairing": "eemkit.io.discover",
    "load_dataset": "eemkit.io.loader",
    "read_pairing": "eemkit.io.pairing",
}


def __getattr__(name: str):
    if name in _SUBMODULES:
        value = importlib.import_module(f"eemkit.{name}")
    elif name in _FUNCTIONS:
        value = getattr(importlib.import_module(_FUNCTIONS[name]), name)
    else:
        raise AttributeError(f"module 'eemkit' has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


if TYPE_CHECKING:  # the same names, for type checkers and editors
    from eemkit import corrections, indices, parafac, pipeline
    from eemkit.core.dataset import stack
    from eemkit.core.grid import infer_common_grid, regular_grid, resample
    from eemkit.core.history import get_history
    from eemkit.io.cary60 import mean_cycles, read_cary60
    from eemkit.io.cary_eclipse import read_cary_eclipse
    from eemkit.io.discover import scan_folder, suggest_pairing
    from eemkit.io.loader import load_dataset
    from eemkit.io.pairing import read_pairing

__all__ = [
    "Cancelled",
    "CorrectionError",
    "EEMKitError",
    "EEMKitWarning",
    "FileFormatError",
    "GridError",
    "PairingError",
    "SettingsError",
    "__version__",
    "corrections",
    "get_history",
    "indices",
    "infer_common_grid",
    "load_dataset",
    "mean_cycles",
    "parafac",
    "pipeline",
    "read_cary60",
    "read_cary_eclipse",
    "read_pairing",
    "regular_grid",
    "resample",
    "scan_folder",
    "stack",
    "suggest_pairing",
]
