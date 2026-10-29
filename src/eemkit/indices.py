"""Fluorescence indices and peak picking.

====================  ===============================================  =========================
index                 definition (defaults)                            reference
====================  ===============================================  =========================
``FI``                I(ex 370, em 470) / I(ex 370, em 520)            Cory & McKnight 2005
``HIX``               H / (H + L) at ex 254; H = area em 435-480,      Ohno 2002
                      L = area em 300-345
``BIX``               I(ex 310, em 380) / I(ex 310, em 430)            Huguet et al. 2009
Coble peaks           B 275/310, T 275/340, A 260/380-460,             Coble 1996
                      M 312/380-420, C 350/420-480 (ex/em, nm);
                      maximum over the emission range
====================  ===============================================  =========================

Excitation wavelengths that are not on the measured grid (e.g. 254, 275 or
312 nm on a 10 nm grid) are handled by ``ex_method``:

* ``"linear"``: linear interpolation between the two neighbouring scans;
* ``"nearest"``: the closest measured excitation;
* ``"exact"``: refuse (raise) unless the excitation was measured.

Emission values off the grid are linearly interpolated; emission areas are
trapezoidal integrals of the piecewise-linear spectrum between the exact
limits. A value that needs a NaN point (e.g. removed scatter) is NaN and
triggers a warning. Ratios are unit-free; peaks are in the units of
``intensity``. Indices depend on instrument spectral response (Cory et al.
2010), so the spectral-correction status travels with every result.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from eemkit.core.history import get_history
from eemkit.errors import EEMKitWarning, IndexComputationError

EX_METHODS = ("linear", "nearest", "exact")

#: Coble (1996) peaks: name -> (ex nm, (em_min, em_max) nm)
COBLE_1996: dict[str, tuple[float, tuple[float, float]]] = {
    "B": (275.0, (310.0, 310.0)),
    "T": (275.0, (340.0, 340.0)),
    "A": (260.0, (380.0, 460.0)),
    "M": (312.0, (380.0, 420.0)),
    "C": (350.0, (420.0, 480.0)),
}


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #

def spectrum_at_ex(da: xr.DataArray, ex: float, ex_method: str) -> xr.DataArray:
    """Emission spectrum (dims ``..., em``) at excitation ``ex``."""
    if ex_method not in EX_METHODS:
        raise ValueError(f"ex_method must be one of {EX_METHODS}")
    # per-scan coordinates (e.g. scan_time(sample, ex)) have no meaning off the scans
    da = da.drop_vars([c for c in da.coords if c != "ex" and "ex" in da[c].dims])
    exs = da["ex"].values
    hit = np.isclose(exs, ex)
    if hit.any():
        return da.sel(ex=exs[hit][0], drop=True)
    if ex_method == "exact":
        raise IndexComputationError(f"excitation {ex} nm was not measured; use ex_method='linear' "
                          "or 'nearest'")
    if ex < exs.min() or ex > exs.max():
        raise IndexComputationError(f"excitation {ex} nm is outside the measured {exs.min()}-"
                          f"{exs.max()} nm")
    if ex_method == "nearest":
        return da.sel(ex=exs[np.argmin(np.abs(exs - ex))], drop=True)
    hi = exs[exs > ex].min()
    lo = exs[exs < ex].max()
    w = (ex - lo) / (hi - lo)
    return (1 - w) * da.sel(ex=lo, drop=True) + w * da.sel(ex=hi, drop=True)


def _interp_em(spec: xr.DataArray, em: float) -> xr.DataArray:
    grid = spec["em"].values
    if em < grid.min() or em > grid.max():
        raise IndexComputationError(f"emission {em} nm is outside {grid.min()}-{grid.max()} nm")
    hit = np.isclose(grid, em)
    if hit.any():
        return spec.sel(em=grid[hit][0], drop=True)
    hi = grid[grid > em].min()
    lo = grid[grid < em].max()
    w = (em - lo) / (hi - lo)
    return (1 - w) * spec.sel(em=lo, drop=True) + w * spec.sel(em=hi, drop=True)


def _em_window(spec: xr.DataArray, lo: float, hi: float) -> xr.DataArray:
    """Spectrum on [lo, hi] including the interpolated end points."""
    grid = spec["em"].values
    inner = grid[(grid > lo) & (grid < hi)]
    parts = [_interp_em(spec, lo).expand_dims(em=[lo]),
             spec.sel(em=inner),
             _interp_em(spec, hi).expand_dims(em=[hi])] if hi > lo else \
        [_interp_em(spec, lo).expand_dims(em=[lo])]
    return xr.concat(parts, dim="em")


def emission_area(spec: xr.DataArray, lo: float, hi: float) -> xr.DataArray:
    """Trapezoidal integral of ``spec`` over emission ``lo``-``hi`` (exact limits)."""
    win = _em_window(spec, lo, hi)
    vals = np.trapezoid(win.values, win["em"].values, axis=win.get_axis_num("em"))
    dims = [d for d in win.dims if d != "em"]
    return xr.DataArray(vals, dims=dims,
                        coords={d: win[d].values for d in dims if d in win.coords})


def emission_max(spec: xr.DataArray, lo: float, hi: float) -> xr.DataArray:
    """Maximum of ``spec`` over emission ``lo``-``hi``; NaN if any point there is NaN."""
    win = _em_window(spec, lo, hi)
    return win.max("em", skipna=False)


def _warn_nan(result: xr.DataArray, name: str) -> None:
    if "sample" in result.dims and result.isnull().any():
        bad = list(result["sample"].values[result.isnull().values])
        warnings.warn(f"{name}: NaN for {len(bad)} sample(s) (missing data in the window, "
                      f"e.g. removed scatter): {bad[:5]}", EEMKitWarning, stacklevel=3)


# --------------------------------------------------------------------------- #
# Indices
# --------------------------------------------------------------------------- #

def fluorescence_index(ds: xr.Dataset, *, ex: float = 370.0,
                       em: tuple[float, float] = (470.0, 520.0),
                       ex_method: str = "exact") -> xr.DataArray:
    """FI = I(ex, em[0]) / I(ex, em[1]) (Cory & McKnight 2005)."""
    spec = spectrum_at_ex(ds["intensity"], ex, ex_method)
    fi = _interp_em(spec, em[0]) / _interp_em(spec, em[1])
    _warn_nan(fi, "FI")
    return fi.rename("FI")


def humification_index(ds: xr.Dataset, *, ex: float = 254.0,
                       high: tuple[float, float] = (435.0, 480.0),
                       low: tuple[float, float] = (300.0, 345.0),
                       ex_method: str) -> xr.DataArray:
    """HIX = H / (H + L) with emission areas H and L at ``ex`` (Ohno 2002).

    ``ex_method`` has no default because the standard 254 nm is rarely on the
    measured grid and the choice must be explicit.
    """
    spec = spectrum_at_ex(ds["intensity"], ex, ex_method)
    h = emission_area(spec, *high)
    lo_ = emission_area(spec, *low)
    hix = h / (h + lo_)
    _warn_nan(hix, "HIX")
    return hix.rename("HIX")


def biological_index(ds: xr.Dataset, *, ex: float = 310.0, em_num: float = 380.0,
                     em_den: float | tuple[float, float] = 430.0,
                     ex_method: str = "exact") -> xr.DataArray:
    """BIX = I(ex, em_num) / I(ex, em_den) (Huguet et al. 2009).

    If ``em_den`` is a ``(min, max)`` range, the denominator is the maximum
    over that range (as in the beta:alpha 'freshness' index).
    """
    spec = spectrum_at_ex(ds["intensity"], ex, ex_method)
    den = emission_max(spec, *em_den) if isinstance(em_den, tuple) else _interp_em(spec, em_den)
    bix = _interp_em(spec, em_num) / den
    _warn_nan(bix, "BIX")
    return bix.rename("BIX")


def peaks(ds: xr.Dataset, definitions: Mapping[str, tuple[float, tuple[float, float]]],
          *, ex_method: str) -> xr.Dataset:
    """Peak intensities: for each name, max over the emission range at the given excitation."""
    out = {}
    for name, (ex, (lo, hi)) in definitions.items():
        spec = spectrum_at_ex(ds["intensity"], ex, ex_method)
        v = emission_max(spec, lo, hi)
        _warn_nan(v, f"peak {name}")
        out[name] = v.assign_attrs(ex_nm=ex, em_nm=[lo, hi],
                                   units=ds["intensity"].attrs.get("units", ""))
    return xr.Dataset(out)


def coble_peaks(ds: xr.Dataset, *, ex_method: str) -> xr.Dataset:
    """The five peaks of Coble (1996); see :data:`COBLE_1996`."""
    return peaks(ds, COBLE_1996, ex_method=ex_method)


# --------------------------------------------------------------------------- #
# Table and export
# --------------------------------------------------------------------------- #

def compute_indices(
    ds: xr.Dataset,
    *,
    ex_method: str,
    fi: Mapping | None = None,
    hix: Mapping | None = None,
    bix: Mapping | None = None,
    peak_definitions: Mapping[str, tuple[float, tuple[float, float]]] | None = None,
) -> pd.DataFrame:
    """All indices in one table (one row per sample) with the settings in ``df.attrs``.

    ``fi``, ``hix``, ``bix`` are keyword overrides for the respective
    functions; ``peak_definitions`` defaults to :data:`COBLE_1996`.
    ``ex_method`` applies to every index and peak.
    """
    fi, hix, bix = dict(fi or {}), dict(hix or {}), dict(bix or {})
    peak_definitions = dict(peak_definitions or COBLE_1996)
    cols = {
        "FI": fluorescence_index(ds, ex_method=ex_method, **fi),
        "HIX": humification_index(ds, ex_method=ex_method, **hix),
        "BIX": biological_index(ds, ex_method=ex_method, **bix),
    }
    pk = peaks(ds, peak_definitions, ex_method=ex_method)
    cols.update({f"peak_{k}": pk[k] for k in pk.data_vars})
    df = pd.DataFrame({k: v.to_series() for k, v in cols.items()})
    df.index.name = "sample"
    df.attrs["settings"] = {
        "ex_method": ex_method,
        "FI": {"reference": "Cory & McKnight 2005", "ex": 370.0, "em": [470.0, 520.0], **fi},
        "HIX": {"reference": "Ohno 2002", "ex": 254.0, "high": [435.0, 480.0],
                "low": [300.0, 345.0], "integration": "trapezoidal", **hix},
        "BIX": {"reference": "Huguet et al. 2009", "ex": 310.0, "em_num": 380.0,
                "em_den": 430.0, **bix},
        "peaks": {"reference": "Coble 1996" if peak_definitions == COBLE_1996 else "custom",
                  "definitions": {k: [v[0], list(v[1])] for k, v in peak_definitions.items()},
                  "units": ds["intensity"].attrs.get("units", "")},
        "spectral_correction": ds.attrs.get("spectral_correction", "none"),
        "processing_history": get_history(ds),
    }
    return df


def export_indices(df: pd.DataFrame, path: str | Path, ds: xr.Dataset | None = None,
                   metadata: tuple[str, ...] = ()) -> tuple[Path, Path]:
    """Write the table as CSV plus a JSON sidecar (``<name>.json``) with all settings.

    ``metadata`` lists ``sample`` coordinates of ``ds`` (e.g. river, site) to
    prepend as columns.
    """
    path = Path(path)
    out = df.copy()
    if ds is not None:
        for name in reversed(metadata):
            out.insert(0, name, ds[name].to_series().reindex(out.index).values)
    out.to_csv(path, float_format="%.6g")
    side = path.with_suffix(".json")
    side.write_text(json.dumps(df.attrs.get("settings", {}), indent=2, default=str),
                    encoding="utf-8")
    return path, side
