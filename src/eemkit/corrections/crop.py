"""Restricting EEMs to a wavelength window."""

from __future__ import annotations

import xarray as xr

from eemkit.core.history import with_history
from eemkit.errors import CorrectionError


def crop(
    ds: xr.Dataset,
    *,
    ex: tuple[float | None, float | None] | None = None,
    em: tuple[float | None, float | None] | None = None,
) -> xr.Dataset:
    """Keep ``ex`` and ``em`` within the given inclusive ``(min, max)`` limits.

    ``None`` leaves a limit (or a whole axis) unchanged. Absorbance, which
    lives on its own ``wavelength`` axis, is not affected.
    """
    sel = {}
    for dim, lim in (("ex", ex), ("em", em)):
        if lim is None:
            continue
        lo, hi = lim
        sel[dim] = slice(lo, hi)
    out = ds.sel(sel)
    for dim in sel:
        if out.sizes[dim] == 0:
            raise CorrectionError(f"crop: no {dim} wavelength within {sel[dim]}")
    return with_history(out, "crop", ex=list(ex) if ex else None, em=list(em) if em else None,
                        n_ex=out.sizes["ex"], n_em=out.sizes["em"])
