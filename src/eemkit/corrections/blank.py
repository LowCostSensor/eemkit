"""Blank subtraction for EEMs and absorbance spectra."""

from __future__ import annotations

import xarray as xr

from eemkit.core.history import with_history
from eemkit.corrections._common import (
    has_data,
    require_not_after,
    require_not_done,
    require_vars,
    resolve_missing,
)


def subtract_blank(ds: xr.Dataset, missing: str = "error") -> xr.Dataset:
    """Subtract the paired blank EEM from each sample EEM.

    ``intensity`` becomes ``intensity - blank_intensity``; ``blank_intensity``
    is kept unchanged (it is still needed for Raman normalisation). The
    coordinate ``blank_subtracted(sample)`` records which samples were
    corrected.

    Parameters
    ----------
    missing
        What to do with samples that have no blank: ``"error"`` (default),
        ``"drop"`` them, or ``"keep"`` them uncorrected.
    """
    step = "subtract_blank"
    require_vars(ds, "intensity", "blank_intensity", step=step)
    require_not_done(ds, step)
    require_not_after(ds, step, "normalize_raman")
    require_not_after(ds, step, "remove_scatter")
    ds, ok = resolve_missing(ds, has_data(ds["blank_intensity"]), missing, step, "blank EEM")

    out = ds.copy()
    out["intensity"] = xr.where(ok, ds["intensity"] - ds["blank_intensity"], ds["intensity"],
                                keep_attrs=True)
    out = out.assign_coords(blank_subtracted=ok)
    return with_history(out, step, missing=missing, n_corrected=int(ok.sum()),
                        n_uncorrected=int((~ok).sum()))


def subtract_absorbance_blank(ds: xr.Dataset, missing: str = "error") -> xr.Dataset:
    """Subtract the paired absorbance blank: ``absorbance - blank_absorbance``.

    Coordinate ``absorbance_blank_subtracted(sample)`` records which samples
    were corrected. ``missing`` as in :func:`subtract_blank`; samples without
    any absorbance are left alone.
    """
    step = "subtract_absorbance_blank"
    require_vars(ds, "absorbance", "blank_absorbance", step=step)
    require_not_done(ds, step)
    require_not_after(ds, step, "correct_inner_filter")
    has_abs = has_data(ds["absorbance"])
    ds, ok = resolve_missing(ds, has_data(ds["blank_absorbance"]) | ~has_abs, missing, step,
                             "absorbance blank")
    ok = ok & has_data(ds["absorbance"])

    out = ds.copy()
    out["absorbance"] = xr.where(ok, ds["absorbance"] - ds["blank_absorbance"],
                                 ds["absorbance"], keep_attrs=True)
    out = out.assign_coords(absorbance_blank_subtracted=ok)
    return with_history(out, step, missing=missing, n_corrected=int(ok.sum()))
