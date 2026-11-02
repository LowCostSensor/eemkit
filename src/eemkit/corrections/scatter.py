"""Removal of Rayleigh and Raman scatter, and interpolation of the gaps.

Four bands are handled, each centred on a line of the (ex, em) plane:

==============  ===========================================
band            centre (nm)
==============  ===========================================
``rayleigh1``   em = ex
``raman1``      em = 1e7 / (1e7 / ex - shift)
``rayleigh2``   em = 2 ex
``raman2``      em = 2 * raman1 centre
==============  ===========================================

``shift`` is the O-H stretching Raman shift of water in cm^-1. Each band is
removed between ``centre - below`` and ``centre + above``. Optionally the
region below first-order Rayleigh (em < ex - offset), where no fluorescence
can occur, is set to zero; Thygesen et al. (2004, Chemometr. Intell. Lab.
Syst. 71:97-106) showed that such zeros stabilise PARAFAC.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import xarray as xr

from eemkit.core.history import has_step, with_history
from eemkit.corrections._common import require_not_done, require_vars
from eemkit.errors import CorrectionError

BANDS = ("rayleigh1", "raman1", "rayleigh2", "raman2")


def raman_emission(ex: np.ndarray, shift_cm1: float) -> np.ndarray:
    """Emission wavelength (nm) of the water Raman line excited at ``ex`` (nm)."""
    ex = np.asarray(ex, dtype=float)
    return 1e7 / (1e7 / ex - shift_cm1)


def scatter_mask(
    ex: np.ndarray,
    em: np.ndarray,
    widths: Mapping[str, tuple[float, float]],
    raman_shift_cm1: float | None = None,
) -> xr.DataArray:
    """Boolean (ex, em) mask, True inside any of the bands listed in ``widths``.

    ``widths`` maps band names to ``(below, above)`` in nm. A Raman band
    requires ``raman_shift_cm1``.
    """
    unknown = set(widths) - set(BANDS)
    if unknown:
        raise ValueError(f"unknown scatter band(s) {sorted(unknown)}; use {BANDS}")
    if any(b.startswith("raman") for b in widths) and raman_shift_cm1 is None:
        raise ValueError("raman_shift_cm1 is required to remove Raman scatter")
    ex = np.asarray(ex, dtype=float)
    em = np.asarray(em, dtype=float)
    centres = {"rayleigh1": ex, "rayleigh2": 2 * ex}
    if raman_shift_cm1 is not None:
        r = raman_emission(ex, raman_shift_cm1)
        centres.update(raman1=r, raman2=2 * r)
    mask = np.zeros((ex.size, em.size), dtype=bool)
    for band, (below, above) in widths.items():
        if below < 0 or above < 0:
            raise ValueError(f"{band}: widths must be non-negative")
        c = centres[band][:, None]
        mask |= (em[None, :] >= c - below) & (em[None, :] <= c + above)
    return xr.DataArray(mask, dims=("ex", "em"), coords={"ex": ex, "em": em})


def remove_scatter(
    ds: xr.Dataset,
    *,
    widths: Mapping[str, tuple[float, float]],
    raman_shift_cm1: float | None = None,
    zero_below_rayleigh: float | None = None,
    variables: tuple[str, ...] = ("intensity",),
) -> xr.Dataset:
    """Set scatter bands to NaN (and optionally the region below Rayleigh to 0).

    Parameters
    ----------
    widths
        ``{band: (below_nm, above_nm)}`` for the bands to remove; see module doc.
    raman_shift_cm1
        Raman shift of water, needed for Raman bands.
    zero_below_rayleigh
        If given, intensities at ``em < ex - zero_below_rayleigh`` are set to 0
        instead of NaN (applied after the bands, so it never overrides a band
        lying above that limit).
    variables
        Data variables to process.

    Notes
    -----
    The removed region is stored as ``scatter_mask(ex, em)``.
    """
    step = "remove_scatter"
    require_vars(ds, *variables, step=step)
    require_not_done(ds, step)
    mask = scatter_mask(ds["ex"].values, ds["em"].values, widths, raman_shift_cm1)
    out = ds.copy()
    zero = None
    if zero_below_rayleigh is not None:
        zero = ds["em"] < ds["ex"] - zero_below_rayleigh
    for name in variables:
        v = ds[name].where(~mask)
        if zero is not None:
            v = xr.where(zero, 0.0, v)
        out[name] = v.transpose(*ds[name].dims).assign_attrs(ds[name].attrs)
    out["scatter_mask"] = mask.assign_attrs(long_name="removed scatter region")
    return with_history(out, step, widths={k: list(v) for k, v in widths.items()},
                        raman_shift_cm1=raman_shift_cm1,
                        zero_below_rayleigh=zero_below_rayleigh, variables=list(variables))


INTERP_METHODS = ("em", "ex", "both")


def _fill_rows(a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Linear interpolation of interior NaN gaps along the last axis (no extrapolation)."""
    out = a.copy()
    for row in out.reshape(-1, a.shape[-1]):
        ok = np.isfinite(row)
        if ok.sum() < 2 or ok.all():
            continue
        lo, hi = np.flatnonzero(ok)[[0, -1]]
        gap = ~ok
        gap[:lo] = gap[hi + 1:] = False
        row[gap] = np.interp(x[gap], x[ok], row[ok])
    return out


def interpolate_missing(
    ds: xr.Dataset,
    *,
    method: str,
    variables: tuple[str, ...] = ("intensity",),
) -> xr.Dataset:
    """Fill NaN gaps in each EEM by linear interpolation between measured points.

    Parameters
    ----------
    method
        ``"em"``: along emission within each excitation scan; ``"ex"``: along
        excitation at each emission wavelength; ``"both"``: mean of the two
        estimates where both exist, otherwise whichever exists.

    Notes
    -----
    Only gaps bracketed by measured values are filled; gaps at the edge of
    the EEM stay NaN. The coordinates ``n_interpolated(sample)`` and
    ``n_still_missing(sample)`` count filled and remaining values.
    """
    step = "interpolate_missing"
    require_vars(ds, *variables, step=step)
    if not has_step(ds, "remove_scatter"):
        raise CorrectionError(f"{step}: nothing to interpolate; run remove_scatter first")
    if method not in INTERP_METHODS:
        raise ValueError(f"method must be one of {INTERP_METHODS}")
    ex, em = ds["ex"].values, ds["em"].values
    out = ds.copy()
    counts: dict[str, list[int]] = {}
    for name in variables:
        da = ds[name].transpose(..., "ex", "em")
        vals = da.values
        along_em = _fill_rows(vals, em)
        along_ex = np.swapaxes(_fill_rows(np.swapaxes(vals, -1, -2), ex), -1, -2)
        if method == "em":
            new = along_em
        elif method == "ex":
            new = along_ex
        else:
            with np.errstate(invalid="ignore"):
                new = np.where(np.isfinite(along_em) & np.isfinite(along_ex),
                               (along_em + along_ex) / 2,
                               np.where(np.isfinite(along_em), along_em, along_ex))
        gap_before = np.isnan(vals).reshape(-1, ex.size * em.size).sum(axis=1)
        gap_after = np.isnan(new).reshape(-1, ex.size * em.size).sum(axis=1)
        vals = new
        filled = [int(v) for v in gap_before - gap_after]
        left = [int(v) for v in gap_after]
        out[name] = (da.dims, vals, da.attrs)
        out[name] = out[name].transpose(*ds[name].dims)
        counts[name] = filled
        if name == "intensity" and "sample" in da.dims:
            out = out.assign_coords(n_interpolated=("sample", filled),
                                    n_still_missing=("sample", left))
    return with_history(out, step, method=method, variables=list(variables),
                        total_interpolated={k: int(sum(v)) for k, v in counts.items()})
