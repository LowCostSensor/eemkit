"""Normalisation to Raman units (Lawaetz & Stedmon 2009, Appl. Spectrosc. 63:936-940).

Intensities are divided by the area of the water Raman peak of a pure-water
blank measured in the same session, integrated over emission at a fixed
excitation. Lawaetz & Stedmon used excitation 350 nm and emission 381-426 nm.
Without instrument spectral correction the result is internally consistent
but not comparable with Raman units from other instruments.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from eemkit.core.history import with_history
from eemkit.corrections._common import (
    require_not_after,
    require_not_done,
    require_vars,
    resolve_missing,
)
from eemkit.errors import CorrectionError


def raman_area(
    blank: xr.DataArray,
    *,
    ex: float,
    em_range: tuple[float, float],
    baseline: bool = False,
) -> xr.DataArray:
    """Integrated water Raman peak of ``blank`` (dims ``..., ex, em``).

    The spectrum at excitation ``ex`` (which must be measured) is treated as
    piecewise linear and integrated exactly from ``em_range[0]`` to
    ``em_range[1]``, so the limits need not be grid points. With
    ``baseline=True`` the straight line joining the spectrum at the two limits
    is subtracted first. Result in intensity units x nm; NaN for an all-NaN
    spectrum (no blank).
    """
    exs = blank["ex"].values
    if not np.any(np.isclose(exs, ex)):
        raise CorrectionError(f"raman_area: excitation {ex} nm is not measured "
                              f"({exs.min()}-{exs.max()} nm)")
    lo, hi = em_range
    em = blank["em"].values
    if not (em.min() <= lo < hi <= em.max()):
        raise CorrectionError(f"raman_area: {lo}-{hi} nm is outside the emission range "
                              f"{em.min()}-{em.max()} nm")
    spec = blank.sel(ex=exs[np.isclose(exs, ex)][0])
    inside = (em > lo) & (em < hi)
    x = np.concatenate([[lo], em[inside], [hi]])
    # grid points that enter the integral, including the neighbours of each limit
    used = slice(np.searchsorted(em, lo, side="right") - 1, np.searchsorted(em, hi) + 1)

    def area_of(row: np.ndarray) -> float:
        if np.isnan(row).all():
            return np.nan
        if np.isnan(row[used]).any():
            raise CorrectionError("raman_area: NaN inside the integration range "
                                  "(was scatter removed before normalising?)")
        y = np.concatenate([[np.interp(lo, em, row)], row[inside], [np.interp(hi, em, row)]])
        if baseline:
            y = y - (y[0] + (y[-1] - y[0]) * (x - x[0]) / (x[-1] - x[0]))
        return float(np.trapezoid(y, x))

    axis = spec.get_axis_num("em")
    area = np.apply_along_axis(area_of, axis, spec.values)
    dims = tuple(d for d in spec.dims if d != "em")
    return xr.DataArray(area, dims=dims, coords={d: spec[d].values for d in dims})


def normalize_raman(
    ds: xr.Dataset,
    *,
    ex: float,
    em_range: tuple[float, float],
    baseline: bool = False,
    missing: str = "error",
) -> xr.Dataset:
    """Divide ``intensity`` and ``blank_intensity`` by the blank's Raman area.

    Each sample is normalised with its own paired blank. The area (a.u. nm)
    is stored as the coordinate ``raman_area(sample)`` and the intensity
    units become ``R.U.``. ``missing`` controls samples without a blank.
    """
    step = "normalize_raman"
    require_vars(ds, "intensity", "blank_intensity", step=step)
    require_not_done(ds, step)
    require_not_after(ds, step, "remove_scatter")
    area = raman_area(ds["blank_intensity"], ex=ex, em_range=em_range, baseline=baseline)
    ds, ok = resolve_missing(ds, np.isfinite(area), missing, step, "blank for the Raman area")
    area = area.sel(sample=ds["sample"].values)
    if ((area <= 0) & ok).any():
        bad = list(ds["sample"].values[((area <= 0) & ok).values])
        raise CorrectionError(f"{step}: non-positive Raman area for {bad}")

    scale = xr.where(ok, area, 1.0)
    units = "R.U." if bool(ok.all()) else "R.U. (a.u. where raman_normalized is False)"
    out = ds.copy()
    for name in ("intensity", "blank_intensity"):
        out[name] = (ds[name] / scale).assign_attrs(ds[name].attrs, units=units)
    out = out.assign_coords(raman_area=area.where(ok).assign_attrs(units="a.u. nm"),
                            raman_normalized=ok)
    return with_history(out, step, method="Lawaetz & Stedmon (2009)", ex=ex,
                        em_range=list(em_range), baseline=baseline, missing=missing,
                        n_normalized=int(ok.sum()))
