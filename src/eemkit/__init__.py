"""eemkit: EEM processing and PARAFAC modelling of dissolved organic matter fluorescence."""

__version__ = "0.1.0.dev0"

from eemkit.core.dataset import stack
from eemkit.core.grid import infer_common_grid, regular_grid, resample
from eemkit.core.history import get_history
from eemkit.errors import (
    EEMKitError,
    EEMKitWarning,
    FileFormatError,
    GridError,
    PairingError,
)
from eemkit.io.cary60 import mean_cycles, read_cary60
from eemkit.io.cary_eclipse import read_cary_eclipse
from eemkit.io.loader import load_dataset
from eemkit.io.pairing import read_pairing

__all__ = [
    "EEMKitError",
    "EEMKitWarning",
    "FileFormatError",
    "GridError",
    "PairingError",
    "__version__",
    "get_history",
    "infer_common_grid",
    "load_dataset",
    "mean_cycles",
    "read_cary60",
    "read_cary_eclipse",
    "read_pairing",
    "regular_grid",
    "resample",
    "stack",
]
