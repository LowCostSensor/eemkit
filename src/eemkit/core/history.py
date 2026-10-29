"""Processing history (provenance) stored in dataset attributes.

Every function that changes data appends one entry to ``ds.attrs["eemkit_history"]``,
a JSON-encoded list, so the record survives a round trip through netCDF.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
import xarray as xr

HISTORY_ATTR = "eemkit_history"


def get_history(ds: xr.Dataset | xr.DataArray) -> list[dict[str, Any]]:
    """Return the list of processing steps applied to ``ds``, oldest first."""
    return json.loads(ds.attrs.get(HISTORY_ATTR, "[]"))


def make_entry(step: str, **params: Any) -> dict[str, Any]:
    """One history record: step name, parameters, eemkit version, UTC time."""
    from eemkit import __version__

    return {
        "step": step,
        "params": _jsonable(params),
        "eemkit_version": __version__,
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def with_history(ds: xr.Dataset, step: str, **params: Any) -> xr.Dataset:
    """Return a shallow copy of ``ds`` with one history entry appended."""
    out = ds.copy()
    out.attrs[HISTORY_ATTR] = json.dumps(get_history(ds) + [make_entry(step, **params)])
    return out


def same_history(a: list[dict], b: list[dict]) -> bool:
    """Compare two histories ignoring timestamps."""
    strip = [{k: v for k, v in e.items() if k != "time"} for e in a]
    return strip == [{k: v for k, v in e.items() if k != "time"} for e in b]


def describe_grid(grid: np.ndarray) -> dict[str, Any]:
    """Compact, JSON-friendly description of a wavelength grid."""
    g = np.asarray(grid, dtype=float)
    steps = np.diff(g)
    regular = steps.size > 0 and np.allclose(steps, steps[0])
    return {
        "start": float(g[0]),
        "stop": float(g[-1]),
        "n": int(g.size),
        "step": float(steps[0]) if regular else None,
    }


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return describe_grid(obj) if obj.ndim == 1 and obj.size > 1 else obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)
