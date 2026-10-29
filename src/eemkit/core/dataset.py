"""Combining single measurements into a multi-sample dataset.

A single measurement (one EEM, one absorbance spectrum) is an
``xarray.Dataset`` whose attributes describe the file and the instrument.
:func:`stack` puts many of them along a new ``sample`` dimension:

* data variables gain the ``sample`` dimension; a missing measurement
  (``None``) becomes all-NaN;
* coordinates such as ``scan_time(ex)`` become ``(sample, ex)``;
* attributes equal for every sample stay dataset attributes, the others
  become ``sample`` coordinates, so nothing is lost;
* the processing history is kept once if it is the same for every sample.

A ``prefix`` keeps EEM and absorbance metadata apart in the same dataset
(both have e.g. an ``instrument`` attribute).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import numpy as np
import xarray as xr

from eemkit.core.history import HISTORY_ATTR, get_history, same_history
from eemkit.errors import GridError

SAMPLE_DIM = "sample"


def stack(
    items: Sequence[xr.Dataset | None],
    sample_ids: Sequence[str],
    prefix: str = "",
) -> xr.Dataset:
    """Stack single measurements that share the same grid along ``sample``."""
    if len(items) != len(sample_ids):
        raise ValueError("items and sample_ids differ in length")
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("sample_ids are not unique")
    present = [it for it in items if it is not None]
    if not present:
        raise ValueError("nothing to stack: every item is None")
    ref = present[0]

    for it in present[1:]:
        for dim in ref.dims:
            if dim not in it.dims or it.sizes[dim] != ref.sizes[dim] or \
                    not np.allclose(it[dim].values, ref[dim].values):
                raise GridError(
                    f"'{it.attrs.get('source_file', '?')}' is not on the same '{dim}' grid as "
                    f"'{ref.attrs.get('source_file', '?')}'; resample to a common grid first"
                )

    # index values only: ref[d] would also drag along coordinates such as scan_time(ex)
    out = xr.Dataset(coords={d: (d, ref[d].values, ref[d].attrs) for d in ref.dims})
    out = out.assign_coords({SAMPLE_DIM: (SAMPLE_DIM, np.asarray(sample_ids, dtype=object))})

    def stacked(name: str, template: xr.DataArray) -> np.ndarray:
        fill = np.array("NaT", dtype=template.dtype) if template.dtype.kind == "M" else np.nan
        return np.stack([it[name].values if it is not None
                         else np.full(template.shape, fill, dtype=template.dtype)
                         for it in items])

    for name, var in ref.data_vars.items():
        out[name] = ((SAMPLE_DIM, *var.dims), stacked(name, var), var.attrs)
    for name, coord in ref.coords.items():
        if name in ref.dims:
            continue
        out = out.assign_coords(
            {prefix + name: ((SAMPLE_DIM, *coord.dims), stacked(name, coord), coord.attrs)}
        )

    keys = [k for k in dict.fromkeys(k for it in present for k in it.attrs) if k != HISTORY_ATTR]
    for key in keys:
        vals = [str(it.attrs.get(key, "")) if it is not None else "" for it in items]
        present_vals = {str(it.attrs.get(key, "")) for it in present}
        if len(present_vals) == 1 and all(it.attrs.get(key) is not None for it in present):
            out.attrs[prefix + key] = present[0].attrs[key]
        else:
            out = out.assign_coords({prefix + key: (SAMPLE_DIM, np.asarray(vals, dtype=object))})

    histories = [get_history(it) for it in present]
    if all(same_history(histories[0], h) for h in histories[1:]):
        out.attrs[HISTORY_ATTR] = json.dumps(histories[0])
    else:
        out = out.assign_coords({prefix + "history": (SAMPLE_DIM, np.asarray(
            [json.dumps(get_history(it)) if it is not None else "" for it in items],
            dtype=object))})
    return out
