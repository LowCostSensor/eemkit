"""Helpers shared by the correction functions."""

from __future__ import annotations

import numpy as np
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.core.history import has_step
from eemkit.errors import CorrectionError

MISSING_POLICIES = ("error", "keep", "drop")


def require_vars(ds: xr.Dataset, *names: str, step: str) -> None:
    missing = [n for n in names if n not in ds.data_vars]
    if missing:
        raise CorrectionError(f"{step}: dataset has no {missing}")


def require_not_done(ds: xr.Dataset, step: str) -> None:
    if has_step(ds, step):
        raise CorrectionError(f"{step} has already been applied to this dataset")


def require_not_after(ds: xr.Dataset, step: str, later: str) -> None:
    if has_step(ds, later):
        raise CorrectionError(f"{step} must be applied before {later}")


def resolve_missing(
    ds: xr.Dataset, available: xr.DataArray, policy: str, step: str, what: str
) -> tuple[xr.Dataset, xr.DataArray]:
    """Apply the policy for samples that lack an input (``available`` is False).

    'error' raises listing the samples, 'drop' removes them, 'keep' leaves
    them uncorrected. Returns the (possibly reduced) dataset and the mask of
    samples that will be corrected.
    """
    if policy not in MISSING_POLICIES:
        raise ValueError(f"missing must be one of {MISSING_POLICIES}")
    lacking = list(ds[SAMPLE_DIM].values[~available.values])
    if lacking and policy == "error":
        raise CorrectionError(
            f"{step}: {len(lacking)} sample(s) have no {what}: {lacking[:10]}"
            + (" ..." if len(lacking) > 10 else "")
            + "; fix the pairing table or pass missing='keep' or 'drop'"
        )
    if lacking and policy == "drop":
        ds = ds.sel({SAMPLE_DIM: available.values})
        available = available.sel({SAMPLE_DIM: available.values})
    return ds, available


def has_data(da: xr.DataArray) -> xr.DataArray:
    """Per-sample flag: True where the array is not entirely NaN."""
    dims = [d for d in da.dims if d != SAMPLE_DIM]
    return np.isfinite(da).any(dims)
