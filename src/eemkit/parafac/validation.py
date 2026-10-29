"""Split-half validation (Murphy et al. 2013, Anal. Methods 5:6557-6566).

The 'S4C6T3' design: samples are divided into four groups; pairs of groups
form six half-datasets, which make three independent comparisons
(AB vs CD, AC vs BD, AD vs BC). A model is validated when, in every
comparison, each component of one half matches a component of the other half
with Tucker congruence above a threshold in both excitation and emission;
0.95 is commonly used (Lorenzo-Seva & ten Berge 2006, Methodology 2:57-64).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import xarray as xr

from eemkit.core.dataset import SAMPLE_DIM
from eemkit.parafac.diagnostics import match_components
from eemkit.parafac.model import fit_parafac

PAIRS = (((0, 1), (2, 3)), ((0, 2), (1, 3)), ((0, 3), (1, 2)))
LETTERS = "ABCD"


def split_groups(ds: xr.Dataset, *, random_state: int = 0,
                 stratify: str | None = None) -> np.ndarray:
    """Assign each sample to one of 4 groups (0-3).

    Samples are shuffled; with ``stratify`` (a sample coordinate such as
    'campaign') they are dealt round-robin within each stratum, so every group
    holds a similar mix.
    """
    rng = np.random.default_rng(random_state)
    n = ds.sizes[SAMPLE_DIM]
    groups = np.empty(n, dtype=int)
    strata = ds[stratify].values if stratify else np.zeros(n)
    offset = 0
    for s in pd.unique(strata):
        idx = np.flatnonzero(strata == s)
        rng.shuffle(idx)
        groups[idx] = (np.arange(idx.size) + offset) % 4
        offset += idx.size
    return groups


def split_half(
    ds: xr.Dataset,
    rank: int,
    *,
    groups: np.ndarray | None = None,
    stratify: str | None = None,
    split_random_state: int = 0,
    threshold: float = 0.95,
    **fit_kwargs,
) -> xr.Dataset:
    """Run the S4C6T3 split-half validation for one rank.

    ``split_random_state`` seeds the division into groups; ``fit_kwargs``
    (including ``random_state``) go to :func:`fit_parafac` for every half.
    Returns a dataset with ``tcc_ex`` and ``tcc_em`` (test, component), the
    half-model loadings (half, ex|em, component, aligned to the first half of
    each test), ``groups(sample)`` and attrs ``validated`` and ``min_tcc``.
    """
    if groups is None:
        groups = split_groups(ds, random_state=split_random_state, stratify=stratify)
    halves = {}
    for g1, g2 in PAIRS:
        for g in (g1, g2):
            key = "".join(LETTERS[i] for i in g)
            if key not in halves:
                sel = np.isin(groups, g)
                halves[key] = fit_parafac(ds.isel({SAMPLE_DIM: sel}), rank, **fit_kwargs)

    tex, tem, names, ex_l, em_l, half_names = [], [], [], [], [], []
    for g1, g2 in PAIRS:
        k1 = "".join(LETTERS[i] for i in g1)
        k2 = "".join(LETTERS[i] for i in g2)
        m1, m2 = halves[k1], halves[k2]
        order, te, tm = match_components(m1.ex_loadings.values, m1.em_loadings.values,
                                         m2.ex_loadings.values, m2.em_loadings.values)
        tex.append(te)
        tem.append(tm)
        names.append(f"{k1} vs {k2}")
        for k, m, o in ((k1, m1, np.arange(rank)), (k2, m2, order)):
            half_names.append(k)
            ex_l.append(m.ex_loadings.values[:, o])
            em_l.append(m.em_loadings.values[:, o])

    tex, tem = np.array(tex), np.array(tem)
    min_tcc = float(np.minimum(tex, tem).min())
    out = xr.Dataset(
        {
            "tcc_ex": (("test", "component"), tex),
            "tcc_em": (("test", "component"), tem),
            "half_ex_loadings": (("half", "ex", "component"), np.array(ex_l)),
            "half_em_loadings": (("half", "em", "component"), np.array(em_l)),
            "groups": ((SAMPLE_DIM,), groups),
        },
        coords={"test": names, "component": np.arange(1, rank + 1),
                "half": [f"test{i // 2 + 1}:{n}" for i, n in enumerate(half_names)],
                "ex": ds["ex"].values, "em": ds["em"].values,
                SAMPLE_DIM: ds[SAMPLE_DIM].values},
    )
    out.attrs = {"rank": rank, "threshold": threshold, "min_tcc": min_tcc,
                 "validated": int(min_tcc >= threshold), "design": "S4C6T3",
                 "stratify": str(stratify), "split_random_state": split_random_state,
                 "half_explained_pct": json.dumps(
                     {k: round(m.attrs["explained_variance_pct"], 3) for k, m in halves.items()})}
    return out
