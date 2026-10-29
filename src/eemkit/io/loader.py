"""Build one multi-sample dataset from a pairing table."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM, stack
from eemkit.core.grid import DEFAULT_TOLERANCE, infer_common_grid, resample
from eemkit.core.history import HISTORY_ATTR, describe_grid, get_history, make_entry
from eemkit.errors import GridError
from eemkit.io.cary60 import mean_cycles, read_cary60
from eemkit.io.cary_eclipse import read_cary_eclipse
from eemkit.io.pairing import read_pairing

READERS = {"cary_eclipse": read_cary_eclipse}
ABS_READERS = {"cary60": read_cary60}


def load_dataset(
    pairing: str | Path | pd.DataFrame,
    data_root: str | Path | None = None,
    em_grid: np.ndarray | None = None,
    wavelength_grid: np.ndarray | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
    eem_format: str = "cary_eclipse",
    abs_format: str = "cary60",
) -> xr.Dataset:
    """Read every included row of a pairing table into one dataset.

    Parameters
    ----------
    pairing
        Path to the pairing CSV, or a table already returned by
        :func:`eemkit.io.pairing.read_pairing`.
    data_root
        Folder the file paths are relative to (see ``read_pairing``).
    em_grid, wavelength_grid
        Common emission grid for EEMs and wavelength grid for absorbance (nm).
        If omitted they are inferred with
        :func:`eemkit.core.grid.infer_common_grid` from all files read, and
        the choice is recorded in the history.
    tolerance
        Edge tolerance of the linear resampling (nm).

    Returns
    -------
    xarray.Dataset
        Dimensions ``sample``, ``ex``, ``em`` and, when any absorbance is
        paired, ``wavelength``. Variables:

        * ``intensity`` (sample, ex, em): raw sample EEMs on ``em_grid``
        * ``blank_intensity`` (sample, ex, em): the paired blank, NaN if none
        * ``absorbance``, ``absorbance_sd`` (sample, wavelength): mean and SD
          of the instrument cycles, NaN if none
        * ``blank_absorbance`` (sample, wavelength)

        All pairing-table columns become ``sample`` coordinates. File and
        instrument metadata are prefixed ``eem_``, ``eem_blank_``, ``abs_``
        and ``abs_blank_``.
    """
    table = pairing if isinstance(pairing, pd.DataFrame) else read_pairing(pairing, data_root)
    root = Path(data_root if data_root is not None else table.attrs.get("data_root", "."))
    rows = table[table["include"]].reset_index(drop=True)
    if rows.empty:
        raise ValueError("no included rows in the pairing table")
    ids = list(rows["sample_id"])

    read_eem = READERS[eem_format]
    read_abs = ABS_READERS[abs_format]
    cache: dict[str, xr.Dataset] = {}

    def load(col: str, reader) -> list[xr.Dataset | None]:
        out = []
        for rel in rows[col]:
            if not rel:
                out.append(None)
                continue
            if rel not in cache:
                cache[rel] = reader(root / rel)
            out.append(cache[rel])
        return out

    eems = load("eem_file", read_eem)
    eem_blanks = load("eem_blank_file", read_eem)
    abss = [mean_cycles(a) if a is not None else None for a in load("abs_file", read_abs)]
    abs_blanks = [mean_cycles(a) if a is not None else None
                  for a in load("abs_blank_file", read_abs)]

    all_eems = [e for e in eems + eem_blanks if e is not None]
    ex0 = all_eems[0]["ex"].values
    for e in all_eems:
        if e.sizes["ex"] != ex0.size or not np.allclose(e["ex"].values, ex0):
            raise GridError(f"{e.attrs['source_file']}: excitation wavelengths differ from "
                            f"{all_eems[0].attrs['source_file']}")
    em_inferred = em_grid is None
    if em_inferred:
        em_grid = infer_common_grid(e["em"].values for e in all_eems)

    def on_grid(items, dim, grid):
        return [resample(it, dim, grid, tolerance) if it is not None else None for it in items]

    ds = stack(on_grid(eems, "em", em_grid), ids, prefix="eem_")
    history = get_history(ds)
    ds.attrs.pop(HISTORY_ATTR, None)
    if any(b is not None for b in eem_blanks):
        blanks = stack(on_grid(eem_blanks, "em", em_grid), ids, prefix="eem_blank_")
        ds["blank_intensity"] = blanks["intensity"]
        ds = _merge_meta(ds, blanks, "eem_blank_")

    params = {"em_grid": describe_grid(em_grid), "em_grid_inferred": em_inferred,
              "tolerance_nm": tolerance, "n_samples": len(ids),
              "n_with_eem_blank": sum(b is not None for b in eem_blanks),
              "n_with_absorbance": sum(a is not None for a in abss)}

    all_abs = [a for a in abss + abs_blanks if a is not None]
    if all_abs:
        wl_inferred = wavelength_grid is None
        if wl_inferred:
            wavelength_grid = infer_common_grid(a["wavelength"].values for a in all_abs)
        params.update(wavelength_grid=describe_grid(wavelength_grid),
                      wavelength_grid_inferred=wl_inferred)
        for items, prefix, names in (
            (abss, "abs_", {"absorbance": "absorbance", "absorbance_sd": "absorbance_sd"}),
            (abs_blanks, "abs_blank_", {"absorbance": "blank_absorbance"}),
        ):
            if all(it is None for it in items):
                continue
            part = stack(on_grid(items, "wavelength", wavelength_grid), ids, prefix=prefix)
            for src, dst in names.items():
                ds[dst] = part[src]
            ds = _merge_meta(ds, part, prefix)

    meta = {c: (SAMPLE_DIM, rows[c].to_numpy(dtype=object))
            for c in rows.columns if c not in ("sample_id", "include")}
    ds = ds.assign_coords(meta)
    ds.attrs["pairing_source"] = table.attrs.get("source", "")
    ds.attrs["data_root"] = str(root)
    ds.attrs[HISTORY_ATTR] = json.dumps(history + [make_entry("load_dataset", **params)])
    return ds


def _merge_meta(ds: xr.Dataset, part: xr.Dataset, prefix: str) -> xr.Dataset:
    """Copy the prefixed coordinates and attributes of ``part`` into ``ds``.

    The history of ``part`` is kept as ``<prefix>history``.
    """
    ds = ds.assign_coords({k: v for k, v in part.coords.items() if k not in part.dims})
    for k, v in part.attrs.items():
        ds.attrs[f"{prefix}history" if k == HISTORY_ATTR else k] = v
    return ds
