import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from test_parafac import synthetic

from eemkit import parafac as P
from eemkit import plot


@pytest.fixture(scope="module")
def fitted():
    ds, *_ = synthetic(n=24)
    model = P.fit_parafac(ds, 3, n_init=2, max_iter=1500)
    split = P.split_half(ds, 3, n_init=1, max_iter=1500)
    return ds, model, split


@pytest.fixture(autouse=True)
def _close():
    yield
    plt.close("all")


def test_eems_small_multiples_keep_missing_cells(fitted):
    ds, *_ = fitted
    fig = plot.eems({s: ds.intensity.sel(sample=s) for s in ds.sample.values[:4]}, ncols=3)
    shown = [ax for ax in fig.axes if ax.get_visible() and ax.get_label() != "<colorbar>"]
    assert len(shown) == 4
    assert shown[0].get_title(loc="left") == "s0"
    assert matplotlib.colors.same_color(shown[0].get_facecolor(), plot.MISSING)


def test_eem_colour_maps(fitted):
    ds, model, _ = fitted
    fig, ax = plt.subplots()
    cs = plot.eem(ax, ds.intensity.isel(sample=0), cmap="eclipse")
    assert cs.cmap is plot.ECLIPSE
    lo, hi = plot.ECLIPSE(0.0), plot.ECLIPSE(1.0)
    assert lo[2] > lo[1] and hi[0] > 0.8 > hi[2]  # violet at the bottom, red at the top
    fig = plot.components(model, cmap="eclipse")
    assert fig.axes[0].collections[0].cmap is plot.ECLIPSE
    with pytest.raises(ValueError, match="colour map"):
        plot.eem(ax, ds.intensity.isel(sample=0), cmap="jet!")


def test_spectral_factors_plot():
    import xarray as xr
    ds = xr.Dataset({"spectral_correction_ex": ("ex", [1.0, 1.2]),
                     "spectral_correction_em": ("em", [1.0, 0.9, 0.8])},
                    coords={"ex": [250.0, 300.0], "em": [300.0, 350.0, 400.0]})
    fig = plot.spectral_factors(ds)
    assert len(fig.axes[0].lines) == 2


def test_components_draw_split_half_halves(fitted):
    _, model, split = fitted
    fig = plot.components(model, split, names=["A", "B", "C"])
    loading_axes = [ax for ax in fig.axes if ax.get_ylabel().startswith("Loading")]
    assert len(loading_axes) == 1
    ax = loading_axes[0]
    # 6 halves x (ex, em) grey lines + final ex and em
    assert len(ax.lines) == 6 * 2 + 2
    assert [t.get_text() for t in fig.legends[0].get_texts()][-1] == "Split-half models"


def test_rank_diagnostics_uses_one_axis_per_measure():
    table = pd.DataFrame({"explained_pct": [97.0, 99.0, 99.3],
                          "core_consistency_pct": [99.0, 85.0, -400.0],
                          "split_half_min_tcc": [0.99, 0.99, 0.2]}, index=[2, 3, 4])
    fig = plot.rank_diagnostics(table, chosen=3)
    assert len(fig.axes) == 3  # no twin y-axes
    assert fig.axes[1].get_ylim()[0] == -100


def test_leverage_legend_lists_groups(fitted):
    _, model, _ = fitted
    fig = plot.leverage(model, by="campaign", n_label=2)
    assert [t.get_text() for t in fig.legends[0].get_texts()] == ["a", "b"]
    assert len(fig.axes[0].texts) == 2


def test_scores_over_groups_and_order():
    df = pd.DataFrame({"x": ["2024-06", "2024-05", "2024-06", "2024-05"] * 2,
                       "river": ["R1"] * 4 + ["R2"] * 4,
                       "v": np.arange(8.0)})
    fig = plot.scores_over(df, ["v"], x="x", by="river", ylabel="R.U.",
                           x_labels={"2024-05": "May"})
    ax = fig.axes[0]
    assert [t.get_text() for t in ax.get_xticklabels()] == ["May", "2024-06"]
    assert [t.get_text() for t in fig.legends[0].get_texts()] == ["R1", "R2"]


def test_eems_per_panel_vmax_caps_the_scale(fitted):
    ds, *_ = fitted
    da = ds.intensity.isel(sample=0)
    fig = plot.eems({"a": da, "b": da}, ncols=2, vmax={"a": 1.0})
    cs = [c for c in fig.axes[0].collections]
    assert cs[0].levels[-1] == pytest.approx(1.0)


def test_too_many_categories_refused():
    with pytest.raises(ValueError, match="at most 8"):
        plot._colour(8)


def test_save_writes_vector_and_raster(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    paths = plot.save(fig, tmp_path / "sub" / "fig")
    assert [p.suffix for p in paths] == [".pdf", ".png"]
    assert all(p.stat().st_size > 0 for p in paths)
