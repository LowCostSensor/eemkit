"""Removing bad parts of EEMs by hand ("zap"; drEEM ``zapnoise``, staRdom ``eem_setNA``).

A region is a sample with an excitation range and an emission range; the
values inside become missing (NaN) and the region, with the reason given, is
recorded in the processing history. eemkit never decides by itself what to
remove: look at the data (e.g. the residual EEMs of a PARAFAC model) and list
the regions. The removed cells are kept as the boolean variable ``zapped``,
so they can be filled later by interpolation, separately from the scatter
bands, or left missing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.core.history import with_history
from eemkit.corrections._common import require_not_done, require_vars
from eemkit.errors import CorrectionError

ZAP_VAR = "zapped"


def _range(region: Mapping, key: str, values: np.ndarray, label: str) -> np.ndarray:
    r = region.get(key) or []
    if len(r) == 0:
        return np.ones(values.size, dtype=bool)
    if len(r) != 2 or r[0] is None or r[1] is None or float(r[0]) > float(r[1]):
        raise CorrectionError(f"zap {label}: {key} must be [low, high] in nm or empty, got {r}")
    return (values >= float(r[0])) & (values <= float(r[1]))


def zap(ds: xr.Dataset, regions: Sequence[Mapping]) -> xr.Dataset:
    """Set the listed regions of ``intensity`` to NaN.

    Each region is a mapping with ``sample`` (name), optional ``ex`` and
    ``em`` (``[low, high]`` in nm, inclusive; empty or absent = the whole
    range) and an optional ``reason``. A region that names an unknown sample
    or contains no measured wavelength is an error, so a typo never passes
    silently. The blank is not changed.
    """
    step = "zap"
    require_vars(ds, "intensity", step=step)
    require_not_done(ds, step)
    if not regions:
        raise CorrectionError("zap: no regions given")
    names = [str(s) for s in ds[SAMPLE_DIM].values]
    da = ds["intensity"].transpose(SAMPLE_DIM, "ex", "em")
    ex, em = ds["ex"].values, ds["em"].values
    mask = np.zeros(da.shape, dtype=bool)
    record, problems = [], []
    for k, region in enumerate(regions, 1):
        label = f"region {k}"
        sample = str(region.get("sample", ""))
        if sample not in names:
            problems.append(f"{label}: unknown sample {sample!r}")
            continue
        i = names.index(sample)
        sel_ex = _range(region, "ex", ex, label)
        sel_em = _range(region, "em", em, label)
        if not sel_ex.any() or not sel_em.any():
            problems.append(f"{label} ({sample}): no measured wavelength in ex {region.get('ex')}"
                            f" / em {region.get('em')}")
            continue
        cells = np.outer(sel_ex, sel_em)
        mask[i] |= cells
        record.append({"sample": sample, "ex": list(region.get("ex") or []),
                       "em": list(region.get("em") or []),
                       "reason": str(region.get("reason", "")),
                       "n_values": int((cells & np.isfinite(da.values[i])).sum())})
    if problems:
        raise CorrectionError("zap: " + "; ".join(problems))
    out = ds.copy()
    out["intensity"] = (da.where(~mask)).transpose(*ds["intensity"].dims).assign_attrs(
        ds["intensity"].attrs)
    out[ZAP_VAR] = xr.DataArray(mask, dims=(SAMPLE_DIM, "ex", "em"),
                                coords={SAMPLE_DIM: da[SAMPLE_DIM].values, "ex": ex, "em": em},
                                attrs={"long_name": "values removed by zap"})
    return with_history(out, step, regions=record, n_values=int(sum(r["n_values"]
                                                                   for r in record)))
