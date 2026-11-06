"""Fitting PARAFAC models to an EEM dataset and packaging the result."""

from __future__ import annotations

import json
import os
import warnings
from concurrent.futures import ThreadPoolExecutor

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


def _n_workers(n_jobs: int | None) -> int:
    if n_jobs is None:
        return os.cpu_count() or 1
    if n_jobs < 1:
        raise ValueError("n_jobs must be None or at least 1")
    return int(n_jobs)


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
    n_jobs: int | None = None,
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
    n_jobs
        Random starts run at the same time, in threads; ``None`` uses every
        processor, ``1`` runs them one after the other. Each start has its own
        seed, so the result does not depend on ``n_jobs``.
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

    def start(k: int):
        return nn_parafac(Xn, rank, random_state=random_state + k, tol=tol, max_iter=max_iter)

    workers = min(n_init, _n_workers(n_jobs))
    if workers > 1:
        # numpy releases the GIL in its array operations, so threads run the
        # starts in parallel; map keeps the order of the seeds
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fits = list(pool.map(start, range(n_init)))
    else:
        fits = [start(k) for k in range(n_init)]
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
            "data_sumsq": ((SAMPLE_DIM,), np.nansum(X ** 2, axis=(1, 2)),
                           {"long_name": "sum of squares of the observed data"}),
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


#: history parameters that describe the samples rather than the method
_SAMPLE_PARAMS = ("missing", "max_factor", "em_grid_inferred", "wavelength_grid_inferred")
#: steps after the corrections, not part of how the EEMs were processed
_MODEL_STEPS = ("fit_parafac", "project_samples")


def _method_steps(history: list[dict]) -> list[tuple[str, dict]]:
    """The processing steps and their method parameters, without counts and times."""
    return [(e["step"], {k: v for k, v in e["params"].items()
                         if not k.startswith("n_") and k not in _SAMPLE_PARAMS})
            for e in history if e["step"] not in _MODEL_STEPS]


def _relative_sse_of_model(model: xr.Dataset) -> np.ndarray | None:
    """Residual / data sum of squares of every sample the model was fitted to."""
    if "data_sumsq" in model:
        return model["sse_sample"].values / model["data_sumsq"].values
    if model.attrs.get("normalization") == "norm":  # models saved before data_sumsq
        return model["sse_sample_normalized"].values
    return None


def project_samples(model: xr.Dataset, ds: xr.Dataset, variable: str = "intensity"
                    ) -> xr.Dataset:
    """Scores of new samples on a fitted model, with its spectra kept fixed.

    The excitation and emission loadings of ``model`` are not changed; for
    each sample of ``ds`` the scores are the non-negative least-squares fit
    of its observed (non-NaN) values (as drEEM's ``projectmodel`` and
    staRdom's ``A_missing``). Dividing a sample by a constant divides its
    scores by the same constant, so the per-sample normalisation used to fit
    the model does not change the projected scores, which are in data units
    like the model's.

    ``ds`` must be on the model's wavelengths (wider data are cut to them)
    and should be processed as the model's data were: a warning says when its
    processing history differs.

    Returns ``scores``, ``fmax``, ``sse_sample`` and ``relative_sse`` (residual
    over data sum of squares) for every new sample, and
    ``outside_model_range``: True when ``relative_sse`` is above the highest
    value among the samples used to fit the model, i.e. the model describes
    that sample worse than any sample it was built on. ``attrs`` hold that
    maximum and the model's main statistics.
    """
    from scipy.optimize import nnls

    from eemkit.errors import GridError

    try:
        da = ds[variable].transpose(SAMPLE_DIM, "ex", "em").sel(
            ex=model["ex"].values, em=model["em"].values)
    except KeyError as e:
        raise GridError("the new samples do not contain all the model's wavelengths "
                        f"({model['ex'].values.min()}-{model['ex'].values.max()} nm ex, "
                        f"{model['em'].values.min()}-{model['em'].values.max()} nm em): "
                        "process them with the same grid and crop") from e
    model_steps = _method_steps(json.loads(model.attrs.get(HISTORY_ATTR, "[]")))
    if _method_steps(get_history(ds)) != model_steps:
        warnings.warn("project_samples: the new samples were processed differently from the "
                      "model's data (compare their processing histories); their scores may "
                      "not be comparable", EEMKitWarning, stacklevel=2)

    B, C = model["ex_loadings"].values, model["em_loadings"].values
    design = np.einsum("jf,kf->jkf", B, C).reshape(-1, B.shape[1])
    X = da.values.astype(float)
    n = X.shape[0]
    scores = np.full((n, B.shape[1]), np.nan)
    sse = np.full(n, np.nan)
    sumsq = np.full(n, np.nan)
    for i in range(n):
        x = X[i].ravel()
        obs = np.isfinite(x)
        if not obs.any():
            continue
        a, _ = nnls(design[obs], x[obs])
        scores[i] = a
        sse[i] = float(np.sum((x[obs] - design[obs] @ a) ** 2))
        sumsq[i] = float(np.sum(x[obs] ** 2))
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = sse / sumsq
    ref = _relative_sse_of_model(model)
    limit = float(np.max(ref)) if ref is not None else np.nan
    outside = rel > limit if ref is not None else np.zeros(n, dtype=bool)
    if outside.any():
        names = [str(s) for s in da[SAMPLE_DIM].values[outside]]
        warnings.warn(f"project_samples: {len(names)} sample(s) fitted worse than any sample of "
                      f"the model: {names}", EEMKitWarning, stacklevel=2)

    sample_coords = {c: ds[c] for c in ds.coords
                     if c != SAMPLE_DIM and ds[c].dims == (SAMPLE_DIM,)}
    units = da.attrs.get("units", "")
    out = xr.Dataset(
        {
            "scores": ((SAMPLE_DIM, "component"), scores, {"units": units}),
            "fmax": ((SAMPLE_DIM, "component"), scores * B.max(axis=0) * C.max(axis=0),
                     {"units": units, "long_name": "maximum fluorescence of each component"}),
            "sse_sample": ((SAMPLE_DIM,), sse),
            "relative_sse": ((SAMPLE_DIM,), rel,
                             {"long_name": "residual sum of squares / data sum of squares"}),
            "outside_model_range": ((SAMPLE_DIM,), outside),
        },
        coords={SAMPLE_DIM: da[SAMPLE_DIM].values, "component": model["component"].values,
                **sample_coords},
    )
    out.attrs = {
        "rank": int(model.attrs["rank"]),
        "model_max_relative_sse": limit,
        "model_explained_variance_pct": model.attrs["explained_variance_pct"],
        "model_n_samples": int(model.sizes[SAMPLE_DIM]),
        "method": "non-negative least squares with fixed excitation and emission loadings",
    }
    history = get_history(ds) + [make_entry(
        "project_samples", rank=int(model.attrs["rank"]), variable=variable,
        model_samples=int(model.sizes[SAMPLE_DIM]))]
    out.attrs[HISTORY_ATTR] = json.dumps(history)
    return out


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
