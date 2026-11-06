"""Correction for diluted samples.

Optically dense samples are diluted before measurement (Kothawala et al.
2013 recommend it above A254 = 1.5 in a 1 cm cuvette). The dilution factor
of each sample is read from two optional pairing-table columns:

* ``dilution_factor``: dilution of the solution measured in the fluorometer;
* ``abs_dilution_factor``: dilution of the solution measured in the
  spectrophotometer, which may differ (e.g. absorbance on the undiluted
  sample, EEM on a 1:2 dilution).

A factor is final volume / sample volume (1 = undiluted, 2 = one part sample
plus one part water); an empty cell means 1. Two steps use them:

1. :func:`match_absorbance_dilution`, before the inner-filter correction:
   the absorbance is rescaled to the dilution of the EEM, so the correction
   uses the absorbance of the solution that was in the fluorescence cuvette
   (absorbance is proportional to concentration, Beer-Lambert);
2. :func:`correct_dilution`, after Raman normalisation: the EEM is multiplied
   by ``dilution_factor`` so it describes the undiluted sample (as staRdom's
   ``eem_dilution``). The blank is not multiplied.

CDOM metrics (:func:`eemkit.absorbance.compute_absorbance_metrics`) are
reported for the undiluted sample; slopes, SR and E2:E3 do not depend on
dilution.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.core.history import has_step, with_history
from eemkit.corrections._common import require_not_after, require_not_done, require_vars
from eemkit.errors import CorrectionError

EEM_COLUMN = "dilution_factor"
ABS_COLUMN = "abs_dilution_factor"
#: coordinate written by match_absorbance_dilution: the dilution the absorbance now refers to
ABS_REFERS_TO = "absorbance_dilution"


def dilution_factors(ds: xr.Dataset, column: str) -> np.ndarray:
    """The factors of one pairing-table column, as numbers; 1 where empty or absent.

    Raises :class:`~eemkit.errors.CorrectionError` for text that is not a
    number or for a factor below 1, naming the samples.
    """
    n = ds.sizes[SAMPLE_DIM]
    if column not in ds.coords:
        return np.ones(n)
    out, bad = np.ones(n), []
    for i, v in enumerate(ds[column].values):
        text = "" if v is None else str(v).strip().replace(",", ".")
        if text in ("", "nan", "None"):
            continue
        try:
            f = float(text)
        except ValueError:
            bad.append(f"{ds[SAMPLE_DIM].values[i]} ({v!r})")
            continue
        if not np.isfinite(f) or f < 1:
            bad.append(f"{ds[SAMPLE_DIM].values[i]} ({v!r})")
        out[i] = f
    if bad:
        raise CorrectionError(f"{column}: a dilution factor must be a number >= 1 (final volume "
                              f"/ sample volume; empty = undiluted); check {bad[:10]}")
    return out


def has_dilution_columns(ds: xr.Dataset) -> bool:
    """True when the pairing table has either dilution column."""
    return EEM_COLUMN in ds.coords or ABS_COLUMN in ds.coords


def match_absorbance_dilution(ds: xr.Dataset) -> xr.Dataset:
    """Rescale each absorbance spectrum to the dilution of its EEM.

    ``absorbance *= abs_dilution_factor / dilution_factor``. Run after
    :func:`~eemkit.corrections.subtract_absorbance_blank` and before
    :func:`~eemkit.corrections.correct_inner_filter`. The coordinate
    ``absorbance_dilution(sample)`` records the dilution the absorbance now
    refers to, so the CDOM metrics can be reported for the undiluted sample.
    """
    step = "match_absorbance_dilution"
    require_vars(ds, "absorbance", step=step)
    require_not_done(ds, step)
    require_not_after(ds, step, "correct_inner_filter")
    if not has_step(ds, "subtract_absorbance_blank"):
        raise CorrectionError(f"{step}: subtract the absorbance blank first")
    f_eem = dilution_factors(ds, EEM_COLUMN)
    f_abs = dilution_factors(ds, ABS_COLUMN)
    ratio = xr.DataArray(f_abs / f_eem, dims=SAMPLE_DIM)
    out = ds.copy()
    out["absorbance"] = (ds["absorbance"] * ratio).assign_attrs(ds["absorbance"].attrs)
    out = out.assign_coords({ABS_REFERS_TO: (SAMPLE_DIM, f_eem)})
    changed = f_abs != f_eem
    return with_history(out, step, rule="absorbance x abs_dilution_factor / dilution_factor "
                        "(Beer-Lambert)", n_rescaled=int(changed.sum()))


def correct_dilution(ds: xr.Dataset) -> xr.Dataset:
    """Multiply each EEM by its ``dilution_factor`` (the undiluted sample's fluorescence).

    Run after :func:`~eemkit.corrections.normalize_raman` and before
    :func:`~eemkit.corrections.remove_scatter`. Only ``intensity`` is
    multiplied; the coordinate ``dilution_factor_applied(sample)`` records the
    factors.
    """
    step = "correct_dilution"
    require_vars(ds, "intensity", step=step)
    require_not_done(ds, step)
    require_not_after(ds, step, "remove_scatter")
    if not has_step(ds, "normalize_raman"):
        raise CorrectionError(f"{step}: normalise to Raman units first, so the blank and the "
                              "Raman area refer to the solution that was measured")
    f = dilution_factors(ds, EEM_COLUMN)
    out = ds.copy()
    out["intensity"] = (ds["intensity"] * xr.DataArray(f, dims=SAMPLE_DIM)).assign_attrs(
        ds["intensity"].attrs)
    out = out.assign_coords(dilution_factor_applied=(SAMPLE_DIM, f))
    return with_history(out, step, rule="intensity x dilution_factor (final / sample volume)",
                        n_diluted=int((f != 1).sum()), max_factor=float(f.max()))
