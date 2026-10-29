"""Wavelength grids and resampling of spectra onto them."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import xarray as xr

from eemkit.core.history import with_history
from eemkit.errors import GridError

#: Grid points this far (nm) outside the measured range take the edge value
#: instead of NaN. Absorbs the ~0.02 nm jitter of instrument wavelength axes.
DEFAULT_TOLERANCE = 0.1


def regular_grid(start: float, stop: float, step: float) -> np.ndarray:
    """Evenly spaced grid from ``start`` to ``stop`` inclusive.

    ``stop - start`` must be a whole number of steps.
    """
    if step <= 0 or stop <= start:
        raise GridError(f"invalid grid {start}..{stop} step {step}")
    n = (stop - start) / step
    if not np.isclose(n, round(n), atol=1e-6):
        raise GridError(f"{start}..{stop} is not a whole number of {step} nm steps")
    return np.round(start + step * np.arange(round(n) + 1), 10)


def interp_on_grid(
    x: np.ndarray, y: np.ndarray, grid: np.ndarray, tolerance: float = DEFAULT_TOLERANCE
) -> np.ndarray:
    """Linearly interpolate the spectrum ``y(x)`` onto ``grid``.

    NaN pairs are dropped and ``x`` may be in any order. Grid points farther
    than ``tolerance`` outside the measured range are NaN (no extrapolation).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    grid = np.asarray(grid, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 2:
        return np.full(grid.shape, np.nan)
    xs, ys = x[ok], y[ok]
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    if np.any(np.diff(xs) == 0):
        raise GridError("duplicate wavelengths in spectrum")
    out = np.interp(grid, xs, ys)
    out[(grid < xs[0] - tolerance) | (grid > xs[-1] + tolerance)] = np.nan
    return out


def resample(
    ds: xr.Dataset, dim: str, grid: np.ndarray, tolerance: float = DEFAULT_TOLERANCE
) -> xr.Dataset:
    """Resample every data variable of ``ds`` along ``dim`` onto ``grid``.

    Linear interpolation; recorded in the processing history.
    """
    grid = np.asarray(grid, dtype=float)
    old = ds[dim].values
    out = ds.drop_dims(dim)
    for name, var in ds.data_vars.items():
        if dim not in var.dims:
            out[name] = var
            continue
        moved = np.moveaxis(var.values, var.dims.index(dim), -1)
        flat = moved.reshape(-1, moved.shape[-1])
        res = np.stack([interp_on_grid(old, row, grid, tolerance) for row in flat])
        res = np.moveaxis(res.reshape(moved.shape[:-1] + (grid.size,)), -1, var.dims.index(dim))
        out[name] = (var.dims, res, var.attrs)
    out = out.assign_coords({dim: (dim, grid, ds[dim].attrs)})
    out.attrs = dict(ds.attrs)
    # the native axis is left out on purpose: it is in the source file, and keeping
    # the entry identical across samples lets a stacked dataset hold one history
    return with_history(out, "resample", dim=dim, grid=grid, method="linear",
                        tolerance_nm=tolerance)


def infer_common_grid(axes: Iterable[np.ndarray], decimals: int = 0) -> np.ndarray:
    """Propose a regular grid covered by every axis in ``axes``.

    The step is the coarsest of the median native steps (rounded to
    ``decimals``), so no axis is resampled to a finer resolution than it was
    measured at. Start and stop are the overlap of all axes, snapped inward
    onto multiples of the step.
    """
    axes = [np.asarray(a, dtype=float) for a in axes]
    if not axes:
        raise GridError("no axes given")
    step = max(round(float(np.median(np.abs(np.diff(a)))), decimals) for a in axes)
    if step <= 0:
        raise GridError("cannot infer a positive step")
    lo = max(np.nanmin(a) for a in axes)
    hi = min(np.nanmax(a) for a in axes)
    start = np.ceil(round(lo / step - DEFAULT_TOLERANCE / step, 6)) * step
    stop = np.floor(round(hi / step + DEFAULT_TOLERANCE / step, 6)) * step
    return regular_grid(start, stop, step)
