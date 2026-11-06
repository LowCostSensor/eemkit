"""Outlier diagnostics of a PARAFAC model: which samples and wavelengths fit badly.

Murphy et al. (2013) check every model for samples with high leverage (they
pull the model towards themselves) and for samples or wavelengths with large
residuals (the model does not describe them). These functions give the
numbers; they set no threshold, because what counts as an outlier depends on
the dataset: look at the samples at the top of the lists, at their residual
EEMs (:func:`eemkit.plot.residual_eems`), and decide.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.parafac.model import model_eem


def sample_labels(ds: xr.Dataset) -> list[str]:
    """Text columns that describe the samples (e.g. river, site, campaign).

    File paths, instrument method names and the per-file metadata of the
    readers (``eem_*``, ``abs_*``) are left out.
    """
    return [c for c in ds.coords
            if c != SAMPLE_DIM and ds[c].dims == (SAMPLE_DIM,) and ds[c].dtype.kind in "OUS"
            and not c.startswith(("eem_", "abs_")) and not c.endswith("_file")]


def sample_diagnostics(model: xr.Dataset) -> pd.DataFrame:
    """One row per sample: leverage, residual sums of squares and their ranks.

    Columns: ``leverage``; ``sse`` (data units squared); ``relative_sse``
    (residual over the sample's data sum of squares, comparable between
    samples of different intensity); ``leverage_rank`` and ``residual_rank``
    (1 = highest). Rows are sorted by the better of the two ranks, then by
    ``relative_sse``, so the samples to inspect first come first. Sample columns of the model
    (e.g. river, campaign) are kept in front.
    """
    lev = model["leverage_sample"].values
    sse = model["sse_sample"].values
    if "data_sumsq" in model:
        rel = sse / model["data_sumsq"].values
    else:  # models saved before data_sumsq: only exact for normalization="norm"
        rel = model["sse_sample_normalized"].values
    df = pd.DataFrame({"leverage": lev, "sse": sse, "relative_sse": rel},
                      index=pd.Index(model[SAMPLE_DIM].values, name=SAMPLE_DIM))
    df["leverage_rank"] = df["leverage"].rank(ascending=False, method="min").astype(int)
    df["residual_rank"] = df["relative_sse"].rank(ascending=False, method="min").astype(int)
    for c in reversed(sample_labels(model)):
        df.insert(0, c, model[c].values)
    order = np.minimum(df["leverage_rank"], df["residual_rank"])
    return df.iloc[np.lexsort((-df["relative_sse"].values, order.values))]


def spectral_residuals(model: xr.Dataset, ds: xr.Dataset, variable: str = "intensity"
                       ) -> xr.Dataset:
    """Residuals summed over samples, for each excitation and each emission wavelength.

    ``sse_ex(ex)`` and ``sse_em(em)``: residual sum of squares over all samples
    and the other wavelength; ``relative_sse_ex`` and ``relative_sse_em``: the
    same divided by the data sum of squares at that wavelength;
    ``bias_ex``/``bias_em``: mean residual (data - model), which shows a
    systematic misfit (e.g. scatter left in the data) rather than noise; and
    the wavelength leverages of the model. Missing values are skipped.
    ``ds`` is the dataset the model was fitted to (the model's samples are
    taken from it).
    """
    data = ds[variable].transpose(SAMPLE_DIM, "ex", "em").sel(
        {SAMPLE_DIM: model[SAMPLE_DIM].values, "ex": model["ex"].values,
         "em": model["em"].values})
    x = data.values.astype(float)
    r = x - model_eem(model).values
    obs = np.isfinite(r)
    r0 = np.where(obs, r, 0.0)
    x0 = np.where(obs, x, 0.0)
    out = xr.Dataset(coords={"ex": model["ex"].values, "em": model["em"].values})
    for mode, axes in (("ex", (0, 2)), ("em", (0, 1))):
        sse = (r0 ** 2).sum(axis=axes)
        ssd = (x0 ** 2).sum(axis=axes)
        n = obs.sum(axis=axes)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[f"sse_{mode}"] = ((mode,), sse)
            out[f"relative_sse_{mode}"] = ((mode,), np.where(ssd > 0, sse / ssd, np.nan))
            out[f"bias_{mode}"] = ((mode,), np.where(n > 0, r0.sum(axis=axes) / n, np.nan))
        out[f"leverage_{mode}"] = ((mode,), model[f"leverage_{mode}"].values)
    out.attrs["units"] = data.attrs.get("units", "")
    return out
