"""Signal of each PARAFAC component in a filter-based optical channel.

A sensor with an LED and an emission filter does not record an EEM: it records
one number per sample, the fluorescence excited by the LED and passed by the
filter. A fitted PARAFAC model says how much of that number each component
accounts for. The modelled EEM of a sample is

    X(ex, em) = sum_f  score_f * exload_f(ex) * emload_f(em)

so the part of a channel's signal that comes from component f is

    score_f * (LED-weighted excitation loading) * (filter-weighted emission integral).

Loadings of an eemkit model have unit norm and the scores carry the scale, so
the result is in the units of the data multiplied by nm (the emission
integral); ``reduce="mean"`` divides by the filter's integrated transmission
instead and returns data units.

No threshold or decision is made here: the numbers say whether a channel (e.g.
a tryptophan-like "T" channel) follows the component it is meant to follow or
a humic one.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.errors import SettingsError


def _profile(spec, name: str, kind: str):
    """(wavelengths, weights) of an LED or a filter given as a number, a band or a table."""
    if np.ndim(spec) == 0:                                    # a single wavelength
        return np.array([float(spec)]), np.array([1.0])
    if len(spec) != 2:
        raise SettingsError(f"channel {name!r}, {kind}: give a wavelength, a band (low, high) "
                            "or a table (wavelengths, weights)")
    a, b = spec
    if np.ndim(a) == 0 and np.ndim(b) == 0:                   # a band (low, high)
        lo, hi = float(a), float(b)
        if not lo < hi:
            raise SettingsError(f"channel {name!r}, {kind}: band {lo}-{hi} nm is empty")
        return np.array([lo, hi]), np.array([1.0, 1.0])
    wl, w = np.asarray(a, float), np.asarray(b, float)
    if wl.ndim != 1 or wl.shape != w.shape or wl.size < 2 or np.any(np.diff(wl) <= 0):
        raise SettingsError(f"channel {name!r}, {kind}: a table needs increasing wavelengths "
                            "and one weight each")
    if np.any(w < 0) or not np.any(w > 0):
        raise SettingsError(f"channel {name!r}, {kind}: weights must be >= 0 and not all zero")
    return wl, w


def _check_range(wl: np.ndarray, grid: np.ndarray, name: str, kind: str, mode: str) -> None:
    if wl.min() < grid.min() or wl.max() > grid.max():
        raise SettingsError(
            f"channel {name!r}, {kind}: {wl.min():g}-{wl.max():g} nm is outside the "
            f"{mode} range of the model ({grid.min():g}-{grid.max():g} nm)")


def _trapz(y: np.ndarray, x: np.ndarray) -> float:
    """Trapezoid rule (numpy.trapezoid needs numpy 2; eemkit supports 1.24)."""
    return float(np.sum((y[1:] + y[:-1]) * np.diff(x)) / 2)


def _weighted_ex(loadings: np.ndarray, grid: np.ndarray, wl, w) -> np.ndarray:
    """Excitation loadings averaged with the LED's spectrum (weights sum to 1)."""
    if wl.size == 1:
        return np.array([np.interp(wl[0], grid, loadings[:, f])
                         for f in range(loadings.shape[1])])
    fine = np.union1d(grid[(grid >= wl.min()) & (grid <= wl.max())], wl)
    wf = np.interp(fine, wl, w)
    return np.array([_trapz(wf * np.interp(fine, grid, loadings[:, f]), fine)
                     for f in range(loadings.shape[1])]) / _trapz(wf, fine)


def _filter_em(loadings: np.ndarray, grid: np.ndarray, wl, w):
    """Emission integral of each loading over the filter, and the integral of the filter."""
    fine = np.union1d(grid[(grid >= wl.min()) & (grid <= wl.max())], wl)
    wf = np.interp(fine, wl, w)                  # a band (low, high) is flat: weights 1, 1
    ints = np.array([_trapz(wf * np.interp(fine, grid, loadings[:, f]), fine)
                     for f in range(loadings.shape[1])])
    return ints, _trapz(wf, fine)


def component_signals(model: xr.Dataset, channels: Mapping[str, Mapping],
                      reduce: str = "integral") -> xr.Dataset:
    """Signal each component gives in each LED + filter channel, for every sample.

    ``channels`` maps a channel name to ``{"ex": ..., "em": ...}``:

    * ``ex``, the LED: one wavelength (nm), a band ``(low, high)`` (flat
      spectrum), or a table ``(wavelengths, weights)`` of its emission
      spectrum. A band or table is averaged with the weights (scaled to sum
      to one), so a wide LED is not counted as a single line.
    * ``em``, the filter: a band ``(low, high)`` in nm (flat transmission), or a
      table ``(wavelengths, transmission)``.

    The emission loadings are integrated over the filter with the trapezoid
    rule on the union of the model's grid and the band edges (the edges are
    interpolated, so a band need not fall on grid points). With
    ``reduce="integral"`` (default) the result is in data units x nm; with
    ``reduce="mean"`` the integral is divided by the filter's integrated
    transmission (data units).

    Returns a dataset with ``signal`` (sample, channel, component), ``total``
    (sample, channel; the sum over components), ``share`` (sample, channel,
    component; signal over total, NaN where the total is zero) and
    ``sensitivity`` (channel, component; signal per unit of score, which tells
    which components a channel can see at all, independent of the samples).
    Ranges outside the excitation or emission range of the model raise an
    error; the model is not extrapolated.
    """
    if reduce not in ("integral", "mean"):
        raise SettingsError("reduce must be 'integral' or 'mean'")
    if not channels:
        raise SettingsError("give at least one channel")
    ex, em = model["ex"].values.astype(float), model["em"].values.astype(float)
    B, C = model["ex_loadings"].values, model["em_loadings"].values
    scores = model["scores"].values
    names, sens, extent = list(channels), [], []
    for name in names:
        spec = channels[name]
        if "ex" not in spec or "em" not in spec:
            raise SettingsError(f"channel {name!r} needs 'ex' (LED) and 'em' (filter)")
        wl_ex, w_ex = _profile(spec["ex"], name, "LED")
        wl_em, w_em = _profile(spec["em"], name, "filter")
        if wl_em.size == 1:
            raise SettingsError(f"channel {name!r}, filter: give a band (low, high) or a "
                                "table, not a single wavelength")
        _check_range(wl_ex, ex, name, "LED", "excitation")
        _check_range(wl_em, em, name, "filter", "emission")
        ex_eff = _weighted_ex(B, ex, wl_ex, w_ex)
        em_int, area = _filter_em(C, em, wl_em, w_em)
        if reduce == "mean":
            em_int = em_int / area
        sens.append(ex_eff * em_int)
        extent.append((wl_ex.min(), wl_ex.max(), wl_em.min(), wl_em.max()))
    sens = np.array(sens)                                    # (channel, component)
    signal = scores[:, None, :] * sens[None, :, :]             # (sample, channel, component)
    total = signal.sum(axis=2)
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(total[:, :, None] != 0, signal / total[:, :, None], np.nan)
    units = model["scores"].attrs.get("units", "")
    unit = (f"{units} nm" if units else "nm") if reduce == "integral" else units
    dims = (SAMPLE_DIM, "channel", "component")
    ext = np.array(extent, float)
    coords = {SAMPLE_DIM: model[SAMPLE_DIM].values, "channel": names,
              "component": model["component"].values,
              # where each channel sits (nm): LED range and filter range, for the figures
              "ex_min": ("channel", ext[:, 0]), "ex_max": ("channel", ext[:, 1]),
              "em_min": ("channel", ext[:, 2]), "em_max": ("channel", ext[:, 3])}
    out = xr.Dataset(
        {"signal": (dims, signal, {"units": unit, "long_name": "signal of each component"}),
         "total": ((SAMPLE_DIM, "channel"), total, {"units": unit}),
         "share": (dims, share, {"long_name": "share of the channel signal"}),
         "sensitivity": (("channel", "component"), sens,
                         {"units": unit, "long_name": "signal per unit score"})},
        coords=coords)
    out.attrs = {"reduce": reduce, "source": "eemkit.parafac.component_signals"}
    return out
