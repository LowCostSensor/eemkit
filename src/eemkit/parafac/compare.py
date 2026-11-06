"""Comparing PARAFAC models and their components."""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr
from scipy.optimize import linear_sum_assignment

from eemkit.errors import GridError
from eemkit.parafac.diagnostics import shift_shape_congruence, tucker_congruence


def _same_grid(m1: xr.Dataset, m2: xr.Dataset) -> None:
    for mode in ("ex", "em"):
        a, b = m1[mode].values, m2[mode].values
        if a.shape != b.shape or not np.allclose(a, b):
            raise GridError(f"the two models have different {mode} wavelengths "
                            f"({a.min()}-{a.max()} nm, {a.size} points vs "
                            f"{b.min()}-{b.max()} nm, {b.size} points); crop both datasets "
                            "the same way before fitting")


def compare_models(model1: xr.Dataset, model2: xr.Dataset) -> pd.DataFrame:
    """Pair the components of two models and report how similar they are.

    Components are paired by maximising the product of excitation and
    emission Tucker congruence (the models may have different ranks; the
    extra components of the larger one are listed unpaired). For each pair:
    ``tcc_ex``, ``tcc_em`` (Tucker congruence) and ``ssc_ex``, ``ssc_em``
    (shift- and shape-sensitive congruence, :func:`shift_shape_congruence`).
    Wünsch et al. (2019) judge emission with SSC and excitation with TCC.
    The models must share the same wavelengths.
    """
    _same_grid(model1, model2)
    ex, em = model1["ex"].values, model1["em"].values
    B1, C1 = model1["ex_loadings"].values, model1["em_loadings"].values
    B2, C2 = model2["ex_loadings"].values, model2["em_loadings"].values
    tex, tem = tucker_congruence(B1, B2), tucker_congruence(C1, C2)
    sex, sem = shift_shape_congruence(B1, B2, ex), shift_shape_congruence(C1, C2, em)
    rows, cols = linear_sum_assignment(-(tex * tem))
    c1 = model1["component"].values
    c2 = model2["component"].values
    out = [{"component_1": int(c1[r]), "component_2": int(c2[c]),
            "tcc_ex": tex[r, c], "tcc_em": tem[r, c], "ssc_ex": sex[r, c], "ssc_em": sem[r, c]}
           for r, c in zip(rows, cols, strict=True)]
    for r in sorted(set(range(len(c1))) - set(rows)):
        out.append({"component_1": int(c1[r]), "component_2": None})
    for c in sorted(set(range(len(c2))) - set(cols)):
        out.append({"component_1": None, "component_2": int(c2[c])})
    df = pd.DataFrame(out, columns=["component_1", "component_2", "tcc_ex", "tcc_em",
                                    "ssc_ex", "ssc_em"])
    return df.astype({"component_1": "Int64", "component_2": "Int64"})


def compare_ranks(models: dict[int, xr.Dataset]) -> pd.DataFrame:
    """:func:`compare_models` between each rank and the next one.

    Shows which components stay the same when one more is added and which
    split or change: a component that keeps TCC and SSC near 1 is stable.
    """
    ranks = sorted(models)
    frames = []
    for r1, r2 in zip(ranks[:-1], ranks[1:], strict=True):
        df = compare_models(models[r1], models[r2])
        df.insert(0, "ranks", f"{r1} vs {r2}")
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["ranks", "component_1", "component_2", "tcc_ex", "tcc_em",
                                     "ssc_ex", "ssc_em"])
    return pd.concat(frames, ignore_index=True)


def component_correlations(model: xr.Dataset, method: str = "spearman") -> pd.DataFrame:
    """Correlation between the Fmax of the components across samples.

    Two components whose amounts always rise and fall together (|r| close to
    1) may be one source split in two, or two sources that cannot be told
    apart in this dataset. ``method``: ``"spearman"`` (rank correlation,
    default) or ``"pearson"``.
    """
    if method not in ("spearman", "pearson"):
        raise ValueError("method must be 'spearman' or 'pearson'")
    fmax = model["fmax"].to_pandas()
    fmax.columns = [f"C{c}" for c in fmax.columns]
    return fmax.corr(method=method)
