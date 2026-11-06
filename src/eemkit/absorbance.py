"""Chromophoric DOM (CDOM) metrics from absorbance spectra.

=================  ===================================================  ==========================
metric             definition (defaults)                                reference
=================  ===================================================  ==========================
``a254``, ``a350``  Napierian absorption coefficient a = ln(10) A / l    Green & Blough 1994
                   (m^-1, path length l in m)
``S275_295``       slope of ln a(lambda) against lambda, 275-295 nm      Helms et al. 2008
``S350_400``       the same over 350-400 nm (nm^-1, reported positive)  Helms et al. 2008
``SR``             S275_295 / S350_400                                  Helms et al. 2008
``E2_E3``          A(250) / A(365)                                      De Haan & De Boer 1987
``SUVA254``        A(254) / l (m^-1, decadic) / DOC (mg L^-1)           Weishaar et al. 2003
=================  ===================================================  ==========================

Before any metric, each spectrum is corrected for its baseline offset by
subtracting its mean absorbance over ``baseline`` (default 680-700 nm, where
CDOM does not absorb; Green & Blough 1994, Helms et al. 2008). The absorbance
must already be blank-corrected
(:func:`~eemkit.corrections.subtract_absorbance_blank`).

Low signal is never turned into a number: a metric that would need a
non-positive absorbance, or a slope whose log-linear fit has R^2 below
``min_r2``, is NaN, and the reason is written in the ``cdom_notes`` column.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence

import numpy as np
import pandas as pd
import xarray as xr

from eemkit.core.history import get_history, has_step
from eemkit.errors import EEMKitWarning, IndexComputationError

LN10 = float(np.log(10.0))

#: Default slope ranges in nm (Helms et al. 2008).
SLOPE_RANGES: dict[str, tuple[float, float]] = {"S275_295": (275.0, 295.0),
                                                "S350_400": (350.0, 400.0)}

#: Default wavelengths in nm.
COEFFICIENTS: tuple[float, ...] = (254.0, 350.0)
E2_E3: tuple[float, float] = (250.0, 365.0)

COLUMNS = ("a254", "a350", "S275_295", "S350_400", "SR", "E2_E3", "SUVA254")


def baseline_corrected(absorbance: xr.DataArray,
                       baseline: tuple[float, float] | None) -> xr.DataArray:
    """Each spectrum minus its mean over ``baseline`` (nm); unchanged if ``None``."""
    if baseline is None:
        return absorbance
    lo, hi = baseline
    wl = absorbance["wavelength"].values
    inside = (wl >= lo) & (wl <= hi)
    if not inside.any():
        raise IndexComputationError(f"baseline range {lo}-{hi} nm is outside the measured "
                                    f"{wl.min()}-{wl.max()} nm")
    offset = absorbance.isel(wavelength=np.flatnonzero(inside)).mean("wavelength")
    return absorbance - offset


def _at(spec: np.ndarray, wl: np.ndarray, lam: float) -> float:
    """Linear interpolation of one spectrum at ``lam`` nm (no extrapolation)."""
    if lam < wl.min() or lam > wl.max():
        raise IndexComputationError(f"{lam} nm is outside the measured {wl.min()}-{wl.max()} nm")
    order = np.argsort(wl)
    return float(np.interp(lam, wl[order], spec[order]))


def spectral_slope(a: np.ndarray, wl: np.ndarray, lo: float, hi: float,
                   min_r2: float) -> tuple[float, float, str]:
    """Slope S (nm^-1, positive for decreasing a) of ln a against wavelength on [lo, hi].

    Linear least squares on the measured points in the range (Helms et al.
    2008). Returns ``(S, R2, note)``; ``S`` is NaN with a note when a value in
    the range is not positive, when there are fewer than 3 points, or when
    ``R2 < min_r2``.
    """
    sel = (wl >= lo) & (wl <= hi)
    x, y = wl[sel], a[sel]
    name = f"{lo:g}-{hi:g} nm"
    if x.size < 3:
        return np.nan, np.nan, f"fewer than 3 points in {name}"
    if not np.all(np.isfinite(y)):
        return np.nan, np.nan, f"missing absorbance in {name}"
    if np.any(y <= 0):
        return np.nan, np.nan, f"a <= 0 in {name}"
    ly = np.log(y)
    slope, icept = np.polyfit(x, ly, 1)
    resid = ly - (slope * x + icept)
    ss_tot = float(np.sum((ly - ly.mean()) ** 2))
    r2 = 1.0 - float(np.sum(resid ** 2)) / ss_tot if ss_tot > 0 else np.nan
    if not np.isfinite(r2) or r2 < min_r2:
        return np.nan, r2, f"R2 {r2:.3f} < {min_r2:g} in {name}"
    return float(-slope), r2, ""


def undiluted_factor(ds: xr.Dataset) -> np.ndarray:
    """Factor that turns ``ds["absorbance"]`` into the absorbance of the undiluted sample.

    After :func:`eemkit.corrections.match_absorbance_dilution` the absorbance
    refers to the EEM's dilution (coordinate ``absorbance_dilution``);
    otherwise to the ``abs_dilution_factor`` column (1 when absent).
    """
    from eemkit.corrections.dilution import ABS_COLUMN, ABS_REFERS_TO, dilution_factors

    if ABS_REFERS_TO in ds.coords:
        return np.asarray(ds[ABS_REFERS_TO].values, dtype=float)
    return dilution_factors(ds, ABS_COLUMN)


def compute_absorbance_metrics(
    ds: xr.Dataset,
    *,
    absorbance_path_length_cm: float,
    baseline: tuple[float, float] | None = (680.0, 700.0),
    min_r2: float = 0.95,
    coefficients: Sequence[float] = COEFFICIENTS,
    slopes: dict[str, tuple[float, float]] | None = None,
    e2_e3: tuple[float, float] = E2_E3,
    doc: str | None = None,
) -> pd.DataFrame:
    """CDOM metrics, one row per sample, with the settings in ``df.attrs``.

    Parameters
    ----------
    ds
        Dataset with ``absorbance(sample, wavelength)``, blank-corrected.
    absorbance_path_length_cm
        Path length of the absorbance cuvette. Required: eemkit never assumes
        a cuvette.
    baseline
        Wavelength range (nm) whose mean is subtracted from each spectrum;
        ``None`` for no baseline correction.
    min_r2
        Smallest R^2 of the log-linear fit for a slope to be reported. This is
        an eemkit quality threshold, not a value from the literature; report
        the value used.
    coefficients
        Wavelengths (nm) of the Napierian absorption coefficients ``a<nm>``.
    slopes
        ``{name: (lo, hi)}``; default :data:`SLOPE_RANGES`. ``SR`` is computed
        when both default ranges are present.
    e2_e3
        The two wavelengths of the E2:E3 ratio.
    doc
        Name of a ``sample`` coordinate holding DOC in mg L^-1; ``SUVA254``
        is computed only when it is given.

    Notes
    -----
    Values that cannot be computed are NaN and the reasons are joined in the
    ``cdom_notes`` column, so low-signal spectra are never reported as
    numbers.
    """
    if "absorbance" not in ds:
        raise IndexComputationError("no absorbance in the dataset")
    if not has_step(ds, "subtract_absorbance_blank"):
        raise IndexComputationError("subtract the absorbance blank first "
                                    "(eemkit.corrections.subtract_absorbance_blank)")
    if not np.isfinite(absorbance_path_length_cm) or absorbance_path_length_cm <= 0:
        raise IndexComputationError("absorbance_path_length_cm must be a positive number")
    if doc is not None and doc not in ds.coords:
        raise IndexComputationError(f"no sample column {doc!r} for DOC")
    slopes = dict(SLOPE_RANGES if slopes is None else slopes)
    path_m = absorbance_path_length_cm / 100.0

    A = baseline_corrected(ds["absorbance"].transpose("sample", "wavelength"), baseline)
    # diluted samples: report the undiluted sample (slopes, SR and E2:E3 do not change)
    dil = undiluted_factor(ds)
    A = A * xr.DataArray(dil, dims="sample")
    wl = A["wavelength"].values
    rows, notes = [], []
    for i in range(A.sizes["sample"]):
        spec = A.values[i]
        row: dict[str, float] = {}
        why: list[str] = []
        if not np.any(np.isfinite(spec)):
            notes.append("no absorbance")
            rows.append({})
            continue
        for lam in coefficients:
            v = _at(spec, wl, lam)
            ok = v > 0
            row[f"a{lam:g}"] = LN10 * v / path_m if ok else np.nan
            if not ok:
                why.append(f"A({lam:g}) <= 0")
        a = LN10 * spec / path_m
        for name, (lo, hi) in slopes.items():
            s, r2, note = spectral_slope(a, wl, lo, hi, min_r2)
            row[name], row[f"{name}_R2"] = s, r2
            if note:
                why.append(f"{name}: {note}")
        if {"S275_295", "S350_400"} <= set(slopes):
            row["SR"] = row["S275_295"] / row["S350_400"]
        num, den = _at(spec, wl, e2_e3[0]), _at(spec, wl, e2_e3[1])
        row["E2_E3"] = num / den if num > 0 and den > 0 else np.nan
        if not (num > 0 and den > 0):
            why.append(f"E2_E3: A({e2_e3[0]:g}) or A({e2_e3[1]:g}) <= 0")
        if doc is not None:
            c = pd.to_numeric(str(ds[doc].values[i]).strip().replace(",", "."),
                              errors="coerce")
            a254_dec = _at(spec, wl, 254.0) / path_m
            ok = np.isfinite(c) and c > 0 and a254_dec > 0
            row["SUVA254"] = a254_dec / c if ok else np.nan
            if not ok:
                why.append("SUVA254: DOC missing or not positive, or A(254) <= 0")
        rows.append(row)
        notes.append("; ".join(why))

    df = pd.DataFrame(rows, index=pd.Index(A["sample"].values, name="sample"))
    df["cdom_notes"] = notes
    n_bad = int((df["cdom_notes"] != "").sum())
    if n_bad:
        warnings.warn(f"CDOM metrics: {n_bad} sample(s) with values left empty (low signal); "
                      "see the cdom_notes column", EEMKitWarning, stacklevel=2)
    df.attrs["settings"] = {
        "absorption_coefficient": "Napierian, a = ln(10) A / l, m^-1 (Green & Blough 1994)",
        "absorbance_path_length_cm": absorbance_path_length_cm,
        "baseline_nm": list(baseline) if baseline is not None else None,
        "slopes": {"ranges_nm": {k: list(v) for k, v in slopes.items()},
                   "fit": "linear least squares of ln a (Helms et al. 2008)",
                   "min_r2": min_r2},
        "E2_E3_nm": list(e2_e3),
        "dilution": "absorbance multiplied by the dilution it refers to (undiluted sample)"
        if np.any(dil != 1) else "none",
        "SUVA254": {"doc_column": doc, "units": "L mg^-1 m^-1",
                    "reference": "Weishaar et al. 2003"} if doc else None,
        "processing_history": get_history(ds),
    }
    return df
