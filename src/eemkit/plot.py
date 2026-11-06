"""Publication figures for EEMs, PARAFAC models and indices (requires matplotlib).

Install with ``pip install eemkit[plot]``. Every function draws on matplotlib
axes and returns the figure, so figures can be adjusted before saving;
:func:`save` writes a vector PDF and a 300 dpi PNG side by side.

Colour rules: EEM intensities use one sequential hue by default (light = low,
:data:`SEQUENTIAL`); ``cmap="eclipse"`` gives instead the violet-to-red
rainbow of the Cary Eclipse software (:data:`ECLIPSE`), familiar on screen but
not perceptually ordered (Crameri et al. 2020). Groups and components use a
fixed categorical order (:data:`CATEGORICAL`) and also differ in marker or
line style, so identity never relies on colour alone. Missing cells (removed
scatter) are shown in light grey.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

try:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.ticker import MaxNLocator
except ImportError as exc:  # pragma: no cover
    raise ImportError("eemkit.plot needs matplotlib: pip install eemkit[plot]") from exc

#: Fixed categorical order (colour-vision-deficiency safe for up to 3 entries
#: in any combination; up to 8 when only neighbours are compared).
CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6",
               "#e34948")
MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, MISSING = "#e1e0d9", "#c3c2b7", "#ecebe6"
_BLUES = ("#ffffff", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95",
          "#0d366b")
#: Sequential colour map for intensities (white -> dark blue).
SEQUENTIAL = LinearSegmentedColormap.from_list("eemkit_blues", _BLUES)
_ECLIPSE = ("#4b0f8c", "#2a3bd6", "#1c9be6", "#22b14c", "#b5d334", "#f5e31a", "#f7941d",
            "#d7191c")
#: Rainbow colour map of the Cary Eclipse contour plots (violet, blue, green, yellow, red).
ECLIPSE = LinearSegmentedColormap.from_list("eemkit_eclipse", _ECLIPSE)
#: EEM colour maps by the names used in settings files.
COLORMAPS = {"blues": SEQUENTIAL, "eclipse": ECLIPSE}
#: Diverging colour map for residuals (blue = model above data, orange = below, white = 0).
DIVERGING = LinearSegmentedColormap.from_list(
    "eemkit_diverging", ("#0d366b", "#3987e5", "#cde2fb", "#ffffff", "#fbd5c0", "#eb6834",
                         "#8a3110"))

#: Figure widths (inches) for one and two journal columns (85 and 180 mm).
SINGLE_COLUMN, DOUBLE_COLUMN = 85 / 25.4, 180 / 25.4

_RC = {
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7,
    "ytick.labelsize": 7, "legend.fontsize": 7, "legend.frameon": False,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK_2, "axes.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlecolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.5, "lines.linewidth": 1.4,
    "savefig.dpi": 300, "savefig.bbox": "tight", "pdf.fonttype": 42, "svg.fonttype": "none",
    "figure.facecolor": "white", "axes.facecolor": "white",
}


@contextmanager
def style():
    """Context manager applying the eemkit figure style to matplotlib."""
    with mpl.rc_context(_RC):
        yield


def save(fig, path: str | Path, formats: Sequence[str] = ("pdf", "png")) -> list[Path]:
    """Save ``fig`` as ``path`` with each suffix in ``formats``; returns the paths."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = [path.with_suffix(f".{f}") for f in formats]
    for p in out:
        fig.savefig(p)
    return out


def _colour(i: int) -> str:
    if i >= len(CATEGORICAL):
        raise ValueError(f"at most {len(CATEGORICAL)} categories can be coloured; "
                         "group the rest or use separate panels")
    return CATEGORICAL[i]


# --------------------------------------------------------------------------- #
# EEMs
# --------------------------------------------------------------------------- #

def add_colorbar(cs, ax, label: str = ""):
    """A thin colour bar for ``cs`` beside ``ax`` (an axes or a list of axes)."""
    cb = cs.axes.figure.colorbar(cs, ax=ax, shrink=0.9, pad=0.02, aspect=25)
    cb.outline.set_visible(False)
    lo, hi = cs.levels[0], cs.levels[-1]
    ticks = MaxNLocator(5).tick_values(lo, hi)
    cb.set_ticks(ticks[(ticks >= lo) & (ticks <= hi + 1e-12 * abs(hi))])
    cb.ax.tick_params(labelsize=6)
    if label:
        cb.set_label(label, fontsize=7)
    return cb


def _cmap(cmap):
    if not isinstance(cmap, str):
        return cmap
    if cmap not in COLORMAPS:
        raise ValueError(f"unknown EEM colour map {cmap!r}; choose one of {sorted(COLORMAPS)}")
    return COLORMAPS[cmap]


def eem(ax, da: xr.DataArray, *, vmax: float | None = None, levels: int = 16,
        colorbar: bool = True, label: str | None = None, cmap="blues"):
    """Filled contours of one EEM (dims ``ex``, ``em``): emission on x, excitation on y.

    The colour scale runs from 0 to ``vmax`` (default: the EEM maximum); values
    outside share the end colours, so a ``vmax`` below the scatter peaks keeps
    the fluorescence readable. NaN cells (removed scatter) stay grey.
    ``cmap`` is a name in :data:`COLORMAPS` or a matplotlib colour map.
    Returns the contour set.
    """
    da = da.transpose("ex", "em")
    vmax = float(da.max()) if vmax is None else vmax
    ax.set_facecolor(MISSING)
    cs = ax.contourf(da["em"], da["ex"], da.values, levels=np.linspace(0, vmax, levels + 1),
                     cmap=_cmap(cmap), extend="both")
    ax.set_xlabel("Emission (nm)")
    ax.set_ylabel("Excitation (nm)")
    if colorbar:
        add_colorbar(cs, ax, label if label is not None else da.attrs.get("units", ""))
    return cs


def eems(panels: Mapping[str, xr.DataArray], *, ncols: int = 3, shared_scale: bool = False,
         vmax: float | Mapping[str, float] | None = None, width: float = DOUBLE_COLUMN,
         cmap="blues"):
    """Small multiples of EEMs, one titled panel per mapping entry.

    ``vmax`` (one value, or one per panel title) caps the colour scale;
    ``shared_scale`` uses the largest maximum for every panel instead.
    """
    n = len(panels)
    nrows = int(np.ceil(n / ncols))
    with style():
        fig, axes = plt.subplots(nrows, ncols, figsize=(width, width / ncols * 0.85 * nrows),
                                 squeeze=False, layout="constrained")
        if shared_scale:
            vmax = max(float(d.max()) for d in panels.values())
        one_scale = vmax is not None and not isinstance(vmax, Mapping)
        for ax, (title, da) in zip(axes.flat, panels.items(), strict=False):
            cs = eem(ax, da, vmax=vmax.get(title) if isinstance(vmax, Mapping) else vmax,
                     colorbar=not one_scale, cmap=cmap)
            ax.set_title(title, loc="left")
        if one_scale:
            add_colorbar(cs, list(axes.flat[:n]),
                         next(iter(panels.values())).attrs.get("units", ""))
        for ax in axes.flat[n:]:
            ax.set_visible(False)
    return fig


def spectral_factors(ds: xr.Dataset, *, width: float = SINGLE_COLUMN):
    """The excitation and emission correction factors applied to ``ds``.

    Needs the ``spectral_correction_ex`` and ``spectral_correction_em``
    variables written by :func:`eemkit.corrections.apply_spectral_correction`.
    """
    with style():
        fig, ax = plt.subplots(figsize=(width, width * 0.7), layout="constrained")
        for k, (dim, label, ls) in enumerate((("ex", "Excitation", (0, (3, 1.5))),
                                              ("em", "Emission", "-"))):
            f = ds[f"spectral_correction_{dim}"]
            ax.plot(f[dim], f, color=_colour(k), ls=ls, label=label)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Correction factor (multiplier)")
        ax.yaxis.grid(True)
        ax.legend()
    return fig


# --------------------------------------------------------------------------- #
# PARAFAC
# --------------------------------------------------------------------------- #

def _halves_aligned(model: xr.Dataset, split: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    """Split-half loadings reordered to the components of ``model``."""
    from eemkit.parafac.diagnostics import match_components

    ex_out, em_out = [], []
    for h in range(split.sizes["half"]):
        ex_h = split["half_ex_loadings"].values[h]
        em_h = split["half_em_loadings"].values[h]
        order, _, _ = match_components(model["ex_loadings"].values, model["em_loadings"].values,
                                       ex_h, em_h)
        ex_out.append(ex_h[:, order])
        em_out.append(em_h[:, order])
    return np.array(ex_out), np.array(em_out)


def components(model: xr.Dataset, split_half: xr.Dataset | None = None, *,
               names: Sequence[str] | None = None, width: float = DOUBLE_COLUMN,
               cmap="blues"):
    """One column per component: its EEM (top) and its loadings (bottom).

    Loadings are scaled to a maximum of 1; with ``split_half``, the loadings of
    every half-model are drawn as thin grey lines behind the final model.
    """
    r = model.sizes["component"]
    names = list(names) if names is not None else [f"C{c + 1}" for c in range(r)]
    ex, em = model["ex"].values, model["em"].values
    exl, eml = model["ex_loadings"].values, model["em_loadings"].values
    exl, eml = exl / exl.max(0), eml / eml.max(0)
    halves = _halves_aligned(model, split_half) if split_half is not None else None
    with style():
        fig, axes = plt.subplots(2, r, figsize=(width, width / r * 1.9), squeeze=False,
                                 layout="constrained", height_ratios=[1.1, 1])
        for f in range(r):
            ax = axes[0, f]
            comp = xr.DataArray(np.outer(exl[:, f], eml[:, f]), dims=("ex", "em"),
                                coords={"ex": ex, "em": em})
            cs = eem(ax, comp, vmax=1.0, colorbar=False, cmap=cmap)
            ax.set_title(names[f], loc="left")
            if f:
                ax.set_ylabel("")
            ax = axes[1, f]
            if halves is not None:
                for h in range(halves[0].shape[0]):
                    hx, hm = halves[0][h][:, f], halves[1][h][:, f]
                    ax.plot(ex, hx / hx.max(), color=AXIS, lw=0.6, zorder=1)
                    ax.plot(em, hm / hm.max(), color=AXIS, lw=0.6, zorder=1)
            ax.plot(ex, exl[:, f], color=_colour(f), ls=(0, (3, 1.5)), label="Excitation",
                    zorder=2)
            ax.plot(em, eml[:, f], color=_colour(f), label="Emission", zorder=2)
            ax.set_ylim(0, 1.05)
            ax.set_xlabel("Wavelength (nm)")
            ax.set_ylabel("Loading (max = 1)" if f == 0 else "")
            ax.yaxis.grid(True)
        add_colorbar(cs, list(axes[0]), "Relative intensity")
        handles = [mpl.lines.Line2D([], [], color=INK_2, ls=(0, (3, 1.5)), label="Excitation"),
                   mpl.lines.Line2D([], [], color=INK_2, label="Emission")]
        if halves is not None:
            handles.append(mpl.lines.Line2D([], [], color=AXIS, lw=0.8,
                                            label="Split-half models"))
        fig.legend(handles=handles, loc="outside lower center", ncols=len(handles))
    return fig


def rank_diagnostics(table: pd.DataFrame, *, threshold: float = 0.95,
                     chosen: int | None = None, width: float = DOUBLE_COLUMN):
    """Explained variance, core consistency and split-half congruence against rank.

    ``table`` is indexed by rank with columns ``explained_pct``,
    ``core_consistency_pct`` and ``split_half_min_tcc`` (as written by
    :func:`eemkit.parafac.summary_table` plus the split-half results, e.g.
    :func:`eemkit.pipeline.explore`). One panel per measure: no shared
    y-axis between different quantities.
    """
    cols = [("explained_pct", "Explained variance (%)"),
            ("core_consistency_pct", "Core consistency (%)"),
            ("split_half_min_tcc", "Split-half min. Tucker congruence")]
    ranks = table.index.values
    with style():
        fig, axes = plt.subplots(1, 3, figsize=(width, width / 3.3), layout="constrained")
        for ax, (col, title) in zip(axes, cols, strict=True):
            y = table[col].values
            ax.plot(ranks, y, color=CATEGORICAL[0], marker="o", ms=4)
            ax.set_title(title, loc="left")
            ax.set_xlabel("Number of components")
            ax.set_xticks(ranks)
            ax.yaxis.grid(True)
            if chosen is not None and chosen in ranks:
                ax.plot([chosen], table.loc[chosen, col], marker="o", ms=8, mfc="none",
                        mec=INK, mew=1)
        lowest = float(np.nanmin(table["core_consistency_pct"]))
        axes[1].set_ylim(max(-100, lowest - 5), 105)
        if lowest < -100:
            axes[1].text(0.98, 0.97, "values below −100 %\nare off the axis", ha="right",
                         va="top", transform=axes[1].transAxes, color=MUTED, fontsize=6)
        axes[2].axhline(threshold, color=INK_2, lw=0.8, zorder=1)
        axes[2].text(0.98, threshold - 0.02, f"validation threshold {threshold}", ha="right",
                     va="top", transform=axes[2].get_yaxis_transform(), color=INK_2,
                     fontsize=6)
        axes[2].set_ylim(0, 1.02)
    return fig


def _groups(values: np.ndarray) -> list:
    return list(pd.unique(pd.Series(values).astype(str)))


def _stagger(ax, points: list[tuple[float, float, str]], min_gap_pt: float = 8.0) -> None:
    """Annotate points, pushing labels upward so that none overlap vertically."""
    to_pt = ax.transData.transform
    placed: list[tuple[float, float]] = []
    for x, y, text in sorted(points, key=lambda p: p[1]):
        px, py = to_pt((x, y))
        dy = 2.0
        while any(abs(px - qx) < 90 and abs(py + dy - qy) < min_gap_pt for qx, qy in placed):
            dy += min_gap_pt
        placed.append((px, py + dy))
        ax.annotate(text, (x, y), xytext=(4, dy), textcoords="offset points", fontsize=6,
                    color=INK_2, va="bottom",
                    arrowprops={"arrowstyle": "-", "color": AXIS, "lw": 0.5} if dy > 2 else None)


def leverage(model: xr.Dataset, *, by: str | None = None, n_label: int = 5,
             width: float = SINGLE_COLUMN):
    """Sample leverage against normalised residual sum of squares (outlier check).

    The ``n_label`` samples furthest out (leverage and residual each scaled to
    their maximum) are labelled.
    """
    lev = model["leverage_sample"].values
    sse = model["sse_sample_normalized"].values
    with style():
        fig, ax = plt.subplots(figsize=(width, width * 0.85), layout="constrained")
        groups = model[by].values.astype(str) if by else np.full(lev.size, "")
        for k, g in enumerate(_groups(groups)):
            sel = groups == g
            ax.scatter(lev[sel], sse[sel], s=14, color=_colour(k), marker=MARKERS[k],
                       edgecolors="white", linewidths=0.5, label=g or None)
        ax.set_xlabel("Sample leverage")
        ax.set_ylabel("Residual sum of squares (normalised)")
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.grid(True)
        fig.canvas.draw()  # fixes the data -> points transform used for label spacing
        score = lev / lev.max() + sse / sse.max()
        _stagger(ax, [(lev[i], sse[i], str(model["sample"].values[i]))
                      for i in np.argsort(-score)[:n_label]])
        if by:
            fig.legend(loc="outside upper center", ncols=len(_groups(groups)))
    return fig


def residual_eems(model: xr.Dataset, ds: xr.Dataset, samples: Sequence[str] | None = None, *,
                  n: int = 3, variable: str = "intensity", width: float = DOUBLE_COLUMN,
                  cmap="blues"):
    """Measured, modelled and residual EEM of a few samples (one column each).

    Default: the ``n`` samples with the highest relative residual
    (:func:`eemkit.parafac.sample_diagnostics`). Measured and modelled share
    one colour scale per sample; the residual (data - model) uses a diverging
    scale centred on 0, so structure left in it (a peak, a scatter band) shows
    what the model misses.
    """
    from eemkit.parafac.model import model_eem
    from eemkit.parafac.outliers import sample_diagnostics

    if samples is None:
        samples = list(sample_diagnostics(model).sort_values(
            "relative_sse", ascending=False).index[:n])
    samples = [str(s) for s in samples]
    names = [str(s) for s in model["sample"].values]
    missing = [s for s in samples if s not in names]
    if missing:
        raise ValueError(f"samples not in the model: {missing}")
    data = ds[variable].transpose("sample", "ex", "em").sel(
        sample=[model["sample"].values[names.index(s)] for s in samples],
        ex=model["ex"].values, em=model["em"].values)
    fit = model_eem(model).sel(sample=data["sample"].values)
    units = data.attrs.get("units", "")
    k = len(samples)
    with style():
        fig, axes = plt.subplots(3, k, figsize=(width, width / max(k, 2) * 2.4), squeeze=False,
                                 layout="constrained")
        for j in range(k):
            meas = data.isel(sample=j)
            mod = fit.isel(sample=j).where(np.isfinite(meas))
            vmax = float(np.nanmax(meas.values))
            for i, (da, title) in enumerate(((meas, "measured"), (mod, "model"))):
                cs = eem(axes[i, j], da, vmax=vmax, colorbar=(j == k - 1), label=units,
                         cmap=cmap)
                axes[i, j].set_title(f"{samples[j]}: {title}" if i == 0 else title, loc="left")
            res = (meas - mod).transpose("ex", "em")
            lim = float(np.nanmax(np.abs(res.values))) or 1.0
            ax = axes[2, j]
            ax.set_facecolor(MISSING)
            cs = ax.contourf(res["em"], res["ex"], res.values, cmap=DIVERGING,
                             levels=np.linspace(-lim, lim, 17), extend="both")
            ax.set_title(f"residual (max |r| = {lim:.3g})", loc="left")
            ax.set_xlabel("Emission (nm)")
            ax.set_ylabel("Excitation (nm)")
            if j == k - 1:
                add_colorbar(cs, ax, units)
            for i in range(3):
                if j:
                    axes[i, j].set_ylabel("")
                if i < 2:
                    axes[i, j].set_xlabel("")
    return fig


def spectral_residuals(residuals: xr.Dataset, *, width: float = DOUBLE_COLUMN):
    """Relative residual and mean residual against excitation and emission wavelength.

    ``residuals`` is the output of :func:`eemkit.parafac.spectral_residuals`.
    A wavelength with a high relative residual or a mean residual far from 0
    is fitted badly in every sample: often a scatter band not fully removed,
    or the edge of the instrument's range.
    """
    units = residuals.attrs.get("units", "")
    with style():
        fig, axes = plt.subplots(2, 2, figsize=(width, width * 0.55), layout="constrained",
                                 sharex="col")
        for j, (mode, label) in enumerate((("ex", "Excitation"), ("em", "Emission"))):
            wl = residuals[mode].values
            axes[0, j].plot(wl, residuals[f"relative_sse_{mode}"], color=_colour(j))
            axes[0, j].set_title(f"{label}: residual / data sum of squares", loc="left")
            axes[0, j].set_ylim(bottom=0)
            axes[1, j].axhline(0, color=AXIS, lw=0.8)
            axes[1, j].plot(wl, residuals[f"bias_{mode}"], color=_colour(j))
            axes[1, j].set_title(f"{label}: mean residual (data − model)", loc="left")
            axes[1, j].set_xlabel(f"{label} wavelength (nm)")
            axes[1, j].set_ylabel(units)
            for i in range(2):
                axes[i, j].yaxis.grid(True)
    return fig


def campaign_series(units: pd.DataFrame, value: str, *, group: str, time: str,
                    width: float = SINGLE_COLUMN * 1.4):
    """``value`` over time, one line per group: mean +/- SD across sites.

    ``units`` holds one row per site and time (replicate means, as returned by
    :func:`eemkit.campaigns.site_means`); its points are drawn behind the means.
    """
    return scores_over(units, [value], x=time, by=group, width=width, ncols=1, xlabel=time)


def along_sites(units: pd.DataFrame, value: str, position: str, *, group: str,
                width: float = SINGLE_COLUMN * 1.4):
    """``value`` against site position (e.g. distance from the source), one series per group."""
    groups = _groups(units[group].values)
    with style():
        fig, ax = plt.subplots(figsize=(width, width * 0.7), layout="constrained")
        for k, g in enumerate(groups):
            sub = units[units[group].astype(str) == g].sort_values(position)
            ax.scatter(sub[position], sub[value], s=14, color=_colour(k), marker=MARKERS[k],
                       edgecolors="white", linewidths=0.5, label=g)
        ax.set_xlabel(position)
        ax.set_ylabel(value)
        ax.yaxis.grid(True)
        fig.legend(loc="outside upper center", ncols=len(groups))
    return fig


def composition(units: pd.DataFrame, pct_columns: Sequence[str], *, group: str, time: str,
                width: float = DOUBLE_COLUMN):
    """Mean share (%) of each PARAFAC component per time, one panel per group (stacked bars)."""
    groups = _groups(units[group].values)
    with style():
        fig, axes = plt.subplots(1, len(groups), figsize=(width, width / 3.2), squeeze=False,
                                 layout="constrained", sharey=True)
        for ax, g in zip(axes.flat, groups, strict=True):
            sub = units[units[group].astype(str) == g]
            mean = sub.groupby(sub[time].astype(str))[list(pct_columns)].mean().sort_index()
            bottom = np.zeros(len(mean))
            for k, col in enumerate(pct_columns):
                ax.bar(range(len(mean)), mean[col], bottom=bottom, color=_colour(k), width=0.7,
                       edgecolor="white", linewidth=0.5, label=col.removesuffix("_pct"))
                bottom += mean[col].fillna(0).to_numpy()
            ax.set_xticks(range(len(mean)), mean.index, rotation=45, ha="right")
            ax.set_title(g, loc="left")
            ax.set_ylim(0, 100)
        axes[0, 0].set_ylabel("Share of total Fmax (%)")
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside upper center", ncols=len(pct_columns))
    return fig


def scores_over(df: pd.DataFrame, columns: Sequence[str], *, x: str, by: str,
                titles: Sequence[str] | None = None, ylabel: str = "",
                x_order: Sequence | None = None, x_labels: Mapping[str, str] | None = None,
                xlabel: str = "", width: float = DOUBLE_COLUMN, ncols: int | None = None):
    """Mean +/- standard deviation of each column per (x, by) group, one panel per column.

    Typical use: Fmax or indices over sampling campaigns (``x``), one line per
    river (``by``). Replicates and sites are pooled in each group; individual
    samples are drawn as faint points behind the means. ``x_labels`` maps
    x values to shorter tick labels.
    """
    titles = list(titles) if titles is not None else list(columns)
    x_order = list(x_order) if x_order is not None else sorted(df[x].astype(str).unique())
    ticks = [(x_labels or {}).get(v, v) for v in x_order]
    pos = {v: i for i, v in enumerate(x_order)}
    groups = _groups(df[by].values)
    ncols = ncols or len(columns)
    nrows = int(np.ceil(len(columns) / ncols))
    with style():
        fig, axes = plt.subplots(nrows, ncols, figsize=(width, width / ncols * 0.9 * nrows),
                                 squeeze=False, layout="constrained")
        offs = np.linspace(-0.12, 0.12, len(groups)) if len(groups) > 1 else [0.0]
        for ax, col, title in zip(axes.flat, columns, titles, strict=False):
            for k, g in enumerate(groups):
                sub = df[df[by].astype(str) == g]
                xs = sub[x].astype(str).map(pos).to_numpy(float) + offs[k]
                ax.scatter(xs, sub[col], s=5, color=_colour(k), alpha=0.25, linewidths=0)
                stats = sub.groupby(sub[x].astype(str))[col].agg(["mean", "std"])
                stats = stats.reindex([v for v in x_order if v in stats.index])
                xm = stats.index.map(pos).to_numpy(float) + offs[k]
                ax.errorbar(xm, stats["mean"], yerr=stats["std"], color=_colour(k),
                            marker=MARKERS[k], ms=4, lw=1.2, capsize=0, elinewidth=0.8,
                            mec="white", mew=0.5, label=g)
            ax.set_title(title, loc="left")
            long = max(len(t) for t in ticks) > 4
            ax.set_xticks(range(len(x_order)), ticks, rotation=45 if long else 0,
                          ha="right" if long else "center")
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            ax.set_ylim(bottom=0)
            ax.yaxis.grid(True)
        for ax in axes.flat[len(columns):]:
            ax.set_visible(False)
        handles, labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside upper center", ncols=len(groups))
    return fig
