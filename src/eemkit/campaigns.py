"""Comparing sampling campaigns, sites and rivers.

Works on any per-sample table (indices, CDOM metrics, PARAFAC Fmax) with
columns that name the *group* (e.g. river), the *site* and the *time* (e.g.
campaign). The statistical unit is the mean of the replicates of one site at
one time (:func:`site_means`), so replicates are never counted as independent
samples.

* :func:`design_table` and :func:`confounding` show which groups were sampled
  at which times, and say when group and time cannot be separated (for
  example rivers that were sampled in different months);
* :func:`compare_times`: within each group, Kruskal-Wallis test between times
  (Kruskal & Wallis 1952) and Dunn's pairwise test (Dunn 1964) with Holm's
  correction (Holm 1979);
* :func:`spatial_trend`: Spearman correlation with a site position (e.g.
  distance from the source), per group;
* :func:`covariate_correlations`: Spearman correlation with covariates per
  group and time (e.g. discharge, rainfall);
* :func:`composition`: the share of each PARAFAC component in total Fmax.

Optional tables are joined explicitly on their key columns
(:func:`join_sites`, :func:`join_covariates`); rows that do not match are
reported, never guessed.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

from eemkit.errors import SettingsError


def _check_columns(df: pd.DataFrame, cols: Sequence[str]) -> None:
    missing = [c for c in cols if c and c not in df.columns]
    if missing:
        raise SettingsError(f"no column {missing} in the table (columns: {list(df.columns)})")


def _time_order(values) -> list:
    return sorted(pd.unique(pd.Series(values).astype(str)))


# --------------------------------------------------------------------------- #
# Units and composition
# --------------------------------------------------------------------------- #

def site_means(df: pd.DataFrame, values: Sequence[str], *, group: str, time: str,
               site: str | None = None) -> pd.DataFrame:
    """Mean, standard deviation and coefficient of variation of the replicates.

    One row per (group, site, time); ``n`` is the number of replicates. Without
    ``site`` all samples of a group at one time are pooled.
    """
    keys = [group] + ([site] if site else []) + [time]
    _check_columns(df, list(keys) + list(values))
    data = df[keys + list(values)].copy()
    for k in keys:
        data[k] = data[k].astype(str)
    g = data.groupby(keys, sort=True)
    mean = g[list(values)].mean()
    sd = g[list(values)].std(ddof=1).add_suffix("_sd")
    with np.errstate(divide="ignore", invalid="ignore"):
        cv = (100 * g[list(values)].std(ddof=1) / mean.abs()).add_suffix("_cv_pct")
    out = pd.concat([mean, sd, cv], axis=1)
    out.insert(0, "n", g.size())
    return out.reset_index()


def composition(df: pd.DataFrame, fmax_columns: Sequence[str]) -> pd.DataFrame:
    """Percentage of each component in the summed Fmax of each sample."""
    _check_columns(df, fmax_columns)
    f = df[list(fmax_columns)].astype(float)
    total = f.sum(axis=1, min_count=len(fmax_columns))
    out = f.div(total, axis=0) * 100
    out.columns = [f"{c.removesuffix('_Fmax')}_pct" for c in fmax_columns]
    return out


# --------------------------------------------------------------------------- #
# Design
# --------------------------------------------------------------------------- #

def design_table(units: pd.DataFrame, *, group: str, time: str) -> pd.DataFrame:
    """Number of units for every (time, group) combination."""
    _check_columns(units, [group, time])
    t = pd.crosstab(units[time].astype(str), units[group].astype(str))
    return t.reindex(_time_order(units[time]))


def confounding(units: pd.DataFrame, *, group: str, time: str) -> list[str]:
    """Plain-language warnings when group and time effects cannot be separated."""
    t = design_table(units, group=group, time=time) > 0
    msgs = []
    groups = list(t.columns)
    for a, b in combinations(groups, 2):
        shared = t.index[t[a] & t[b]].tolist()
        if not shared:
            msgs.append(f"{a} and {b} were never sampled at the same {time}: differences "
                        f"between them cannot be separated from differences between "
                        f"{time} values.")
    if len(groups) > 1 and (t.sum(axis=1) <= 1).all():
        msgs.insert(0, f"Every {time} contains a single {group}: {group} and {time} are "
                       "completely confounded; compare times within each group only.")
    return msgs


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def _holm(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    out = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    if not ok.any():
        return out
    pv = p[ok]
    order = np.argsort(pv)
    m = pv.size
    adj = np.minimum(1.0, np.maximum.accumulate((m - np.arange(m)) * pv[order]))
    res = np.empty(m)
    res[order] = adj
    out[ok] = res
    return out


def dunn(values: Sequence[float], labels: Sequence[str]) -> pd.DataFrame:
    """Dunn's (1964) pairwise test after Kruskal-Wallis, with tie correction and Holm.

    Returns one row per pair: mean ranks, z, two-sided p and Holm-adjusted p.
    """
    v = np.asarray(values, dtype=float)
    lab = np.asarray(labels).astype(str)
    ok = np.isfinite(v)
    v, lab = v[ok], lab[ok]
    n = v.size
    ranks = stats.rankdata(v)
    _, counts = np.unique(v, return_counts=True)
    tie = np.sum(counts ** 3 - counts) / (12.0 * (n - 1)) if n > 1 else 0.0
    levels = _time_order(lab)
    rows = []
    for a, b in combinations(levels, 2):
        ra, rb = ranks[lab == a], ranks[lab == b]
        se = np.sqrt((n * (n + 1) / 12.0 - tie) * (1 / ra.size + 1 / rb.size))
        z = (ra.mean() - rb.mean()) / se if se > 0 else np.nan
        p = 2 * stats.norm.sf(abs(z)) if np.isfinite(z) else np.nan
        rows.append({"a": a, "b": b, "n_a": ra.size, "n_b": rb.size, "mean_rank_a": ra.mean(),
                     "mean_rank_b": rb.mean(), "z": z, "p": p})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["p_holm"] = _holm(out["p"].to_numpy())
    return out


def compare_times(units: pd.DataFrame, value: str, *, group: str,
                  time: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Within each group, differences of ``value`` between times.

    Returns ``(kruskal, pairwise)``: one Kruskal-Wallis row per group (H,
    degrees of freedom, p, number of units and times, or a note when the test
    cannot be run) and Dunn's pairwise comparisons with Holm-adjusted p.
    """
    _check_columns(units, [group, time, value])
    kw_rows, pair_rows = [], []
    for g, sub in units.groupby(units[group].astype(str), sort=True):
        sub = sub[np.isfinite(sub[value].astype(float))]
        samples = [s[value].astype(float).to_numpy()
                   for _, s in sub.groupby(sub[time].astype(str), sort=True)]
        row = {group: g, "n_units": len(sub), "n_times": len(samples),
               "H": np.nan, "df": np.nan, "p": np.nan, "note": ""}
        if len(samples) < 2:
            row["note"] = "fewer than 2 times with data"
        elif len(sub) - len(samples) < 1:
            row["note"] = "one unit per time: no replication between sites"
        else:
            try:
                h, p = stats.kruskal(*samples)
                row.update(H=float(h), df=len(samples) - 1, p=float(p))
            except ValueError as exc:  # e.g. all values identical
                row["note"] = str(exc)
        kw_rows.append(row)
        if np.isfinite(row["p"]):
            d = dunn(sub[value].astype(float), sub[time].astype(str))
            d.insert(0, group, g)
            pair_rows.append(d)
    kw = pd.DataFrame(kw_rows)
    pairs = pd.concat(pair_rows, ignore_index=True) if pair_rows else pd.DataFrame()
    kw.attrs["method"] = ("Kruskal-Wallis between times within each group (Kruskal & Wallis "
                          "1952); Dunn's pairwise test (Dunn 1964), Holm-adjusted (Holm 1979); "
                          "unit = mean of the replicates of one site at one time")
    return kw, pairs


def _spearman(x, y) -> dict:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 3 or np.ptp(x[ok]) == 0 or np.ptp(y[ok]) == 0:
        return {"n": n, "rho": np.nan, "p": np.nan,
                "note": "fewer than 3 pairs or no variation"}
    rho, p = stats.spearmanr(x[ok], y[ok])
    return {"n": n, "rho": float(rho), "p": float(p), "note": ""}


def spatial_trend(units: pd.DataFrame, value: str, position: str, *, group: str,
                  time: str | None = None) -> pd.DataFrame:
    """Spearman correlation between ``value`` and a site ``position`` within each group.

    With ``time``, also one row per (group, time). ``position`` is any number
    that orders the sites, e.g. distance from the source in km.
    """
    _check_columns(units, [group, value, position] + ([time] if time else []))
    rows = []
    for g, sub in units.groupby(units[group].astype(str), sort=True):
        rows.append({group: g, **({time: "all"} if time else {}),
                     **_spearman(sub[position], sub[value])})
        if time:
            for t, s2 in sub.groupby(sub[time].astype(str), sort=True):
                rows.append({group: g, time: t, **_spearman(s2[position], s2[value])})
    return pd.DataFrame(rows)


def covariate_correlations(units: pd.DataFrame, value: str, covariates: Sequence[str], *,
                           group: str) -> pd.DataFrame:
    """Spearman correlation between ``value`` and each covariate, per group and overall."""
    _check_columns(units, [group, value] + list(covariates))
    rows = []
    for c in covariates:
        rows.append({group: "all", "covariate": c, **_spearman(units[c], units[value])})
        for g, sub in units.groupby(units[group].astype(str), sort=True):
            rows.append({group: g, "covariate": c, **_spearman(sub[c], sub[value])})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Optional tables
# --------------------------------------------------------------------------- #

def _join(units: pd.DataFrame, table: pd.DataFrame, keys: Sequence[str],
          what: str) -> tuple[pd.DataFrame, list[str]]:
    _check_columns(table, keys)
    t = table.copy()
    for k in keys:
        t[k] = t[k].astype(str).str.strip()
    dup = t.duplicated(list(keys))
    if dup.any():
        raise SettingsError(f"{what}: duplicate rows for {t.loc[dup, list(keys)].values.tolist()}")
    left = units.copy()
    for k in keys:
        left[k] = left[k].astype(str).str.strip()
    merged = left.merge(t, on=list(keys), how="left", indicator=True)
    unmatched = merged.loc[merged["_merge"] == "left_only", list(keys)].drop_duplicates()
    notes = [f"{what}: no row for " + ", ".join(f"{k}={r[k]}" for k in keys)
             for _, r in unmatched.iterrows()]
    return merged.drop(columns="_merge"), notes


def join_sites(units: pd.DataFrame, sites: pd.DataFrame, *, group: str,
               site: str) -> tuple[pd.DataFrame, list[str]]:
    """Add the columns of a site table (e.g. latitude, longitude, distance) by (group, site)."""
    return _join(units, sites, [group, site], "site table")


def join_covariates(units: pd.DataFrame, covariates: pd.DataFrame, *, group: str,
                    time: str) -> tuple[pd.DataFrame, list[str]]:
    """Add the columns of a covariate table (e.g. discharge, rainfall) by (group, time).

    The time values must be written exactly as in the sample table (e.g.
    ``2024-05`` for a campaign); no date matching is attempted.
    """
    return _join(units, covariates, [group, time], "covariate table")
