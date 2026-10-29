"""Fitting PARAFAC models to an EEM dataset and packaging the result."""

from __future__ import annotations

import json
import warnings

import numpy as np
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.core.history import HISTORY_ATTR, get_history, make_entry
from eemkit.errors import EEMKitWarning
from eemkit.parafac._cp import nn_parafac, reconstruct
from eemkit.parafac.diagnostics import core_consistency, leverage

NORMALIZATIONS = ("norm", None)

#: two runs whose SSE differs by less than this fraction are considered the same minimum
SAME_MINIMUM_RTOL = 1e-3


def _sample_scale(X: np.ndarray, normalization: str | None) -> np.ndarray:
    if normalization is None:
        return np.ones(X.shape[0])
    if normalization == "norm":
        s = np.sqrt(np.nansum(X ** 2, axis=(1, 2)))
        if np.any(s == 0):
            raise ValueError("a sample is all zero/NaN and cannot be normalised")
        return s
    raise ValueError(f"normalization must be one of {NORMALIZATIONS}")


def fit_parafac(
    ds: xr.Dataset,
    rank: int,
    *,
    n_init: int = 10,
    normalization: str | None = "norm",
    tol: float = 1e-8,
    max_iter: int = 5000,
    random_state: int = 0,
    variable: str = "intensity",
) -> xr.Dataset:
    """Non-negative PARAFAC of ``ds[variable]`` (sample, ex, em), best of ``n_init`` starts.

    Parameters
    ----------
    rank
        Number of components.
    n_init
        Random starts (seeds ``random_state``, ``random_state + 1``, ...). The
        lowest-SSE fit is kept; all SSEs are stored to judge whether the
        solution is reproducible.
    normalization
        ``"norm"``: each sample is divided by its Frobenius norm before
        fitting and the scores are scaled back afterwards (Murphy et al. 2013);
        ``None``: no scaling.
    tol, max_iter
        Convergence: relative SSE change below ``tol``.

    Returns
    -------
    xarray.Dataset
        ``scores(sample, component)`` in the units of the data (after undoing
        the normalisation), ``ex_loadings(ex, component)`` and
        ``em_loadings(em, component)`` with unit Euclidean norm, ``fmax``
        (sample, component) = maximum fluorescence of each component in each
        sample, leverages for every mode, per-sample residual SSE, and in
        ``attrs`` the fit statistics (SSE, explained variance, core
        consistency, iterations, all starts). Components are sorted by
        decreasing contribution to the modelled sum of squares.
    """
    da = ds[variable].transpose(SAMPLE_DIM, "ex", "em")
    X = da.values.astype(float)
    scale = _sample_scale(X, normalization)
    Xn = X / scale[:, None, None]

    fits = []
    for k in range(n_init):
        fits.append(nn_parafac(Xn, rank, random_state=random_state + k, tol=tol,
                               max_iter=max_iter))
    sses = np.array([f.sse for f in fits])
    best = fits[int(np.argmin(sses))]
    if not best.converged:
        warnings.warn(f"rank {rank}: best start did not converge in {max_iter} iterations",
                      EEMKitWarning, stacklevel=2)

    A, B, C = best.A.copy(), best.B.copy(), best.C.copy()
    contrib = np.array([np.sum(np.einsum("i,j,k->ijk", A[:, f], B[:, f], C[:, f]) ** 2)
                        for f in range(rank)])
    order = np.argsort(-contrib)
    A, B, C = A[:, order], B[:, order], C[:, order]

    observed = np.isfinite(Xn)
    model_n = reconstruct(A, B, C)
    filled = np.where(observed, Xn, model_n)
    cc = core_consistency(filled, A, B, C) if rank > 1 else 100.0
    resid_n = np.where(observed, Xn - model_n, np.nan)
    sse_n = float(np.nansum(resid_n ** 2))
    explained = 100.0 * (1.0 - sse_n / float(np.nansum(Xn ** 2)))

    scores = A * scale[:, None]
    resid = resid_n * scale[:, None, None]
    comp = np.arange(1, rank + 1)
    sample_coords = {c: ds[c] for c in ds.coords
                     if c != SAMPLE_DIM and ds[c].dims == (SAMPLE_DIM,)}
    out = xr.Dataset(
        {
            "scores": ((SAMPLE_DIM, "component"), scores,
                       {"units": da.attrs.get("units", ""),
                        "long_name": "component scores (normalisation undone)"}),
            "ex_loadings": (("ex", "component"), B,
                            {"long_name": "excitation loadings, unit norm"}),
            "em_loadings": (("em", "component"), C,
                            {"long_name": "emission loadings, unit norm"}),
            "fmax": ((SAMPLE_DIM, "component"), scores * B.max(axis=0) * C.max(axis=0),
                     {"units": da.attrs.get("units", ""),
                      "long_name": "maximum fluorescence of each component"}),
            "leverage_sample": ((SAMPLE_DIM,), leverage(A)),
            "leverage_ex": (("ex",), leverage(B)),
            "leverage_em": (("em",), leverage(C)),
            "sse_sample": ((SAMPLE_DIM,), np.nansum(resid ** 2, axis=(1, 2))),
            "sse_sample_normalized": ((SAMPLE_DIM,), np.nansum(resid_n ** 2, axis=(1, 2))),
            "init_sse": (("init",), sses),
            "init_n_iter": (("init",), [f.n_iter for f in fits]),
            "init_converged": (("init",), [f.converged for f in fits]),
        },
        coords={SAMPLE_DIM: da[SAMPLE_DIM].values, "ex": da["ex"].values,
                "em": da["em"].values, "component": comp, "init": np.arange(n_init),
                **sample_coords},
    )
    n_same = int(np.sum(sses <= sses.min() * (1 + SAME_MINIMUM_RTOL)))
    out.attrs = {
        "rank": rank,
        "sse_normalized": sse_n,
        "explained_variance_pct": explained,
        "core_consistency_pct": cc,
        "n_iter": best.n_iter,
        "converged": int(best.converged),
        "n_init": n_init,
        "n_init_at_best_minimum": n_same,
        "normalization": str(normalization),
        "tol": tol,
        "max_iter": max_iter,
        "random_state": random_state,
        "algorithm": "non-negative ALS (HALS updates, EM imputation of missing values)",
        "fraction_missing": float(1 - observed.mean()),
        "spectral_correction": ds.attrs.get("spectral_correction", "none"),
    }
    history = get_history(ds) + [make_entry(
        "fit_parafac", rank=rank, n_init=n_init, normalization=normalization, tol=tol,
        max_iter=max_iter, random_state=random_state, variable=variable)]
    out.attrs[HISTORY_ATTR] = json.dumps(history)
    return out


def model_eem(model: xr.Dataset) -> xr.DataArray:
    """Modelled EEMs (sample, ex, em) in data units."""
    vals = reconstruct(model["scores"].values, model["ex_loadings"].values,
                       model["em_loadings"].values)
    return xr.DataArray(vals, dims=(SAMPLE_DIM, "ex", "em"),
                        coords={SAMPLE_DIM: model[SAMPLE_DIM].values, "ex": model["ex"].values,
                                "em": model["em"].values})


def residuals(model: xr.Dataset, ds: xr.Dataset, variable: str = "intensity") -> xr.DataArray:
    """Data minus model (NaN where data are missing)."""
    data = ds[variable].transpose(SAMPLE_DIM, "ex", "em").sel(
        {SAMPLE_DIM: model[SAMPLE_DIM].values})
    return (data - model_eem(model)).rename("residual")


def fit_ranks(ds: xr.Dataset, ranks, **kwargs) -> dict[int, xr.Dataset]:
    """:func:`fit_parafac` for each rank."""
    return {r: fit_parafac(ds, r, **kwargs) for r in ranks}


def summary_table(models: dict[int, xr.Dataset]):
    """One row per rank with the fit statistics."""
    import pandas as pd

    rows = []
    for r, m in sorted(models.items()):
        a = m.attrs
        rows.append({"rank": r, "explained_pct": a["explained_variance_pct"],
                     "core_consistency_pct": a["core_consistency_pct"],
                     "sse_normalized": a["sse_normalized"], "n_iter": a["n_iter"],
                     "converged": bool(a["converged"]),
                     "starts_at_best": f"{a['n_init_at_best_minimum']}/{a['n_init']}"})
    return pd.DataFrame(rows).set_index("rank")
