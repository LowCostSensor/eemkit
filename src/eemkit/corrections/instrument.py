"""Corrections already done by the instrument software.

Some instruments export EEMs that are already processed: an Aqualog export
can be blank-subtracted ("Sample - Blank"), corrected for the inner filter or
normalised. Correcting such data again would be wrong, and skipping a
correction silently would be wrong too. So eemkit:

* reads what each file says about its processing (attribute
  ``instrument_steps``, see :mod:`eemkit.io.instruments`);
* stops with an error when a file says a step was done that the project does
  not declare in ``project.already_done`` (:func:`check_declared`);
* for each declared step, writes a history entry with the step's own name
  and ``done_by = "instrument software"`` instead of running it
  (:func:`mark_done`), so the record is complete and the step cannot be run
  a second time.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.core.history import with_history
from eemkit.corrections._common import require_not_done
from eemkit.errors import SettingsError

#: names used in ``project.already_done`` -> eemkit step they replace
STEPS = {"blank": "subtract_blank", "inner_filter": "correct_inner_filter",
         "raman": "normalize_raman"}


def _per_sample(ds: xr.Dataset, name: str) -> list[str]:
    if name in ds.coords and ds[name].dims == (SAMPLE_DIM,):
        return [str(v) for v in ds[name].values]
    return [str(ds.attrs.get(name, ""))] * ds.sizes[SAMPLE_DIM]


def stated_steps(ds: xr.Dataset) -> dict[str, list[str]]:
    """Steps the sample files say were done, with the samples that say so."""
    out: dict[str, list[str]] = {}
    for sample, steps in zip(ds[SAMPLE_DIM].values, _per_sample(ds, "eem_instrument_steps"),
                             strict=True):
        for s in filter(None, steps.split(",")):
            out.setdefault(s, []).append(str(sample))
    return out


def processing_text(ds: xr.Dataset) -> str:
    """The processing descriptions found in the files (distinct values)."""
    return " | ".join(dict.fromkeys(t for t in _per_sample(ds, "eem_instrument_processing")
                                    if t))


def check_declared(ds: xr.Dataset, declared: list[str]) -> None:
    """Raise :class:`~eemkit.errors.SettingsError` unless files and settings agree.

    Every step a file states must be declared; a declared ``blank`` cannot
    have blank files paired; Raman units cannot be computed from a blank that
    the instrument already subtracted.
    """
    unknown = sorted(set(declared) - set(STEPS))
    if unknown:
        raise SettingsError(f"project.already_done: unknown step(s) {unknown}; "
                            f"use {sorted(STEPS)}")
    stated = stated_steps(ds)
    missing = {s: v for s, v in stated.items() if s not in declared}
    if missing:
        detail = "; ".join(f"'{s}' in {len(v)} file(s), e.g. {v[0]}" for s, v in missing.items())
        raise SettingsError(
            f"the instrument software already did: {detail} (file header: "
            f"{processing_text(ds)!r}). eemkit will not repeat it, nor skip it unless you say "
            f"so: add {sorted(missing)} to project.already_done, or export unprocessed data")
    if "blank" in declared and "blank_intensity" in ds and \
            bool(np.isfinite(ds["blank_intensity"]).any()):
        raise SettingsError("project.already_done says the instrument subtracted the blank, "
                            "but blank files are paired in the pairing table; remove them or "
                            "remove 'blank' from already_done")
    if "blank" in declared and "raman" not in declared:
        raise SettingsError("Raman units are computed from the water blank, which the "
                            "instrument already subtracted: if the instrument also normalised "
                            "to Raman units, add 'raman' to project.already_done")


def mark_done(ds: xr.Dataset, key: str) -> xr.Dataset:
    """History entry for a step done by the instrument software (nothing is computed)."""
    step = STEPS[key]
    require_not_done(ds, step)
    out = ds
    if key == "raman":
        out = ds.copy()
        out["intensity"] = ds["intensity"].assign_attrs(
            {**ds["intensity"].attrs, "units": "R.U. (instrument software)"})
    return with_history(out, step, done_by="instrument software",
                        declared_in="project.already_done",
                        file_header=processing_text(ds) or "not stated in the files")
