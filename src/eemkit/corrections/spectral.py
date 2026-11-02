"""Instrument spectral correction (excitation and emission correction factors).

The Cary Eclipse was operated with 'Corrected spectra OFF', so intensities
contain the wavelength response of lamp, monochromators and detector.
Correction factors are instrument-specific and must be measured (e.g. with
certified reference fluorophores); eemkit ships none and never invents them.

Factors are read from two-column text files (wavelength in nm, factor) and
applied **multiplicatively** by default: ``F_corr = F_obs * Xc(ex) * Mc(em)``.
If your files hold divisors (e.g. an instrument response or lamp reference
spectrum), pass ``convention="divide"``: ``F_corr = F_obs / Xr(ex) / Mr(em)``.
Until applied, ``ds.attrs["spectral_correction"]`` is ``"none"``; data
recorded with the instrument's own correction ON are refused.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from eemkit.core.history import with_history
from eemkit.corrections._common import require_not_after, require_not_done, require_vars
from eemkit.errors import CorrectionError, FileFormatError

NOT_CORRECTED = "none"


def read_correction_file(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Read ``wavelength, factor`` pairs; header lines and ``,;`` or whitespace separators ok."""
    path = Path(path)
    wl, f = [], []
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        toks = [t for t in line.replace(";", ",").replace("\t", ",").replace(" ", ",")
                .split(",") if t]
        if not toks:
            continue
        try:
            w, v = float(toks[0]), float(toks[1])
        except (ValueError, IndexError):
            if wl:
                raise FileFormatError(f"{path}, line {n}: expected 'wavelength, factor'") \
                    from None
            continue  # header
        wl.append(w)
        f.append(v)
    if len(wl) < 2:
        raise FileFormatError(f"{path}: fewer than two numeric rows")
    order = np.argsort(wl)
    return np.asarray(wl)[order], np.asarray(f)[order]


def apply_spectral_correction(
    ds: xr.Dataset,
    *,
    ex_factors: str | Path | tuple[np.ndarray, np.ndarray],
    em_factors: str | Path | tuple[np.ndarray, np.ndarray],
    variables: tuple[str, ...] = ("intensity", "blank_intensity"),
    convention: str = "multiply",
) -> xr.Dataset:
    """Multiply (or divide) EEMs by excitation and emission correction factors.

    Factors are linearly interpolated onto the ``ex`` and ``em`` grids, which
    they must cover (no extrapolation). ``convention`` says what the files
    hold: ``"multiply"`` (correction factors) or ``"divide"`` (response
    spectra). The stored ``spectral_correction_ex/em`` variables are always
    the multipliers actually applied. Must precede every other correction.
    """
    step = "apply_spectral_correction"
    if convention not in ("multiply", "divide"):
        raise ValueError(f"{step}: convention must be 'multiply' or 'divide', not {convention!r}")
    variables = tuple(v for v in variables if v in ds.data_vars)
    require_vars(ds, "intensity", step=step)
    require_not_done(ds, step)
    if spectral_correction_status(ds) != NOT_CORRECTED:
        raise CorrectionError(f"{step}: the data are already spectrally corrected "
                              f"({spectral_correction_status(ds)})")
    for later in ("correct_inner_filter", "subtract_blank", "normalize_raman", "remove_scatter"):
        require_not_after(ds, step, later)

    sources = {}
    curves = {}
    for dim, spec in (("ex", ex_factors), ("em", em_factors)):
        if isinstance(spec, (str, Path)):
            sources[dim] = str(spec)
            spec = read_correction_file(spec)
        else:
            sources[dim] = "array"
        wl, f = (np.asarray(a, dtype=float) for a in spec)
        grid = ds[dim].values
        if grid.min() < wl.min() - 1e-6 or grid.max() > wl.max() + 1e-6:
            raise CorrectionError(f"{step}: {dim} factors cover {wl.min()}-{wl.max()} nm, "
                                  f"grid needs {grid.min()}-{grid.max()} nm")
        on_grid = np.interp(grid, wl, f)
        if not np.all(np.isfinite(on_grid) & (on_grid > 0)):
            raise CorrectionError(f"{step}: {dim} factors must be positive over "
                                  f"{grid.min()}-{grid.max()} nm")
        if convention == "divide":
            on_grid = 1.0 / on_grid
        curves[dim] = xr.DataArray(on_grid, dims=dim, coords={dim: grid})

    out = ds.copy()
    for name in variables:
        out[name] = (ds[name] * curves["ex"] * curves["em"]).transpose(*ds[name].dims) \
            .assign_attrs(ds[name].attrs)
    out["spectral_correction_ex"] = curves["ex"]
    out["spectral_correction_em"] = curves["em"]
    out.attrs["spectral_correction"] = (f"applied (ex: {sources['ex']}; em: {sources['em']}; "
                                        f"{convention})")
    return with_history(out, step, ex_factors=sources["ex"], em_factors=sources["em"],
                        convention=convention)


def spectral_correction_status(ds: xr.Dataset) -> str:
    """'none' or a description of the applied correction."""
    return ds.attrs.get("spectral_correction", NOT_CORRECTED)
