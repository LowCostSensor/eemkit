"""Absorbance-based inner-filter-effect (IFE) correction.

For a right-angle geometry with central illumination of a square cuvette,

    F_corr(ex, em) = F_obs(ex, em) * 10 ** ((A_ex + A_em) / 2)

where A_ex and A_em are the sample absorbances at the excitation and
emission wavelengths over the fluorescence cuvette path length (Lakowicz,
*Principles of Fluorescence Spectroscopy*, 3rd ed., 2006). Kothawala et al.
(2013, Limnol. Oceanogr. Methods 11:616-630) showed that this
absorbance-based approach is reliable for samples with A254 up to about 1.5
(1 cm path) and recommended dilution above that.
"""

from __future__ import annotations

import warnings

import numpy as np
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.core.history import has_step, with_history
from eemkit.corrections._common import (
    has_data,
    require_not_after,
    require_not_done,
    require_vars,
    resolve_missing,
)
from eemkit.errors import CorrectionError, EEMKitWarning

KOTHAWALA_MAX_A254 = 1.5


def correct_inner_filter(
    ds: xr.Dataset,
    *,
    absorbance_path_length_cm: float,
    fluorescence_path_length_cm: float,
    missing: str = "error",
    max_a254: float = KOTHAWALA_MAX_A254,
) -> xr.Dataset:
    """Correct ``intensity`` for inner-filter effects using the sample absorbance.

    Parameters
    ----------
    absorbance_path_length_cm
        Path length of the cuvette the absorbance was measured in.
    fluorescence_path_length_cm
        Path length of the fluorescence cuvette. Both are required: eemkit
        never assumes a cuvette.
    missing
        Samples without absorbance: ``"error"``, ``"drop"`` or ``"keep"``.
    max_a254
        Samples whose A254 over the fluorescence path exceeds this value get a
        warning (Kothawala et al. 2013 recommend dilution above 1.5).

    Notes
    -----
    The absorbance must already be blank-corrected
    (:func:`~eemkit.corrections.subtract_absorbance_blank`). The applied
    factor is kept as the variable ``ife_factor(sample, ex, em)``.
    """
    step = "correct_inner_filter"
    require_vars(ds, "intensity", "absorbance", step=step)
    require_not_done(ds, step)
    # The water Raman signal inside the sample is attenuated like the DOM
    # fluorescence, so IFE must be corrected before the blank is subtracted.
    for later in ("subtract_blank", "normalize_raman", "remove_scatter"):
        require_not_after(ds, step, later, allow_instrument=later == "subtract_blank")
    if not has_step(ds, "subtract_absorbance_blank"):
        raise CorrectionError(f"{step}: subtract the absorbance blank first")
    for name, val in (("absorbance_path_length_cm", absorbance_path_length_cm),
                      ("fluorescence_path_length_cm", fluorescence_path_length_cm)):
        if not np.isfinite(val) or val <= 0:
            raise CorrectionError(f"{step}: {name} must be a positive number, got {val}")

    wl = ds["wavelength"].values
    for dim in ("ex", "em"):
        lo, hi = ds[dim].values.min(), ds[dim].values.max()
        if lo < wl.min() or hi > wl.max():
            raise CorrectionError(f"{step}: absorbance ({wl.min()}-{wl.max()} nm) does not "
                                  f"cover {dim} {lo}-{hi} nm")

    ds, ok = resolve_missing(ds, has_data(ds["absorbance"]), missing, step, "absorbance")
    a_fl = ds["absorbance"] / absorbance_path_length_cm * fluorescence_path_length_cm
    a_ex = _at(a_fl, ds["ex"])
    a_em = _at(a_fl, ds["em"])
    factor = 10.0 ** ((a_ex + a_em) / 2.0)
    factor = xr.where(ok, factor, 1.0).transpose(SAMPLE_DIM, "ex", "em")

    if 254 >= wl.min() and 254 <= wl.max():
        a254 = _at(a_fl, xr.DataArray([254.0], dims="wavelength")).squeeze(drop=True)
        high = list(ds[SAMPLE_DIM].values[(a254 > max_a254).values & ok.values])
        if high:
            warnings.warn(f"{step}: A254 > {max_a254} for {high}; Kothawala et al. (2013) "
                          "recommend diluting such samples", EEMKitWarning, stacklevel=2)

    out = ds.copy()
    out["intensity"] = (ds["intensity"] * factor).assign_attrs(ds["intensity"].attrs)
    out["ife_factor"] = factor.assign_attrs(
        long_name="inner-filter correction factor 10**((A_ex+A_em)/2)", units="1")
    out = out.assign_coords(ife_corrected=ok)
    return with_history(
        out, step, method="absorbance-based (Kothawala et al. 2013)",
        absorbance_path_length_cm=absorbance_path_length_cm,
        fluorescence_path_length_cm=fluorescence_path_length_cm, missing=missing,
        n_corrected=int(ok.sum()), max_factor=float(factor.max()),
    )


def _at(a: xr.DataArray, wavelengths: xr.DataArray) -> xr.DataArray:
    """Absorbance at the given wavelengths, linear interpolation, renamed to their dim."""
    dim = wavelengths.dims[0]
    vals = np.apply_along_axis(
        lambda row: np.interp(wavelengths.values, a["wavelength"].values, row),
        a.get_axis_num("wavelength"), a.values,
    )
    dims = tuple(dim if d == "wavelength" else d for d in a.dims)
    coords = {d: a[d].values for d in a.dims if d != "wavelength" and d in a.coords}
    coords[dim] = wavelengths.values
    return xr.DataArray(vals, dims=dims, coords=coords)
