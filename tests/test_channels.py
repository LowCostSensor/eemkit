import numpy as np
import pytest
import xarray as xr

from eemkit import SettingsError
from eemkit import parafac as P
from eemkit.parafac.channels import _trapz

EX = np.arange(240.0, 451.0, 10.0)
EM = np.arange(250.0, 601.0, 5.0)


def gauss(x, c, w):
    return np.exp(-0.5 * ((x - c) / w) ** 2)


def unit(v):
    return v / np.linalg.norm(v, axis=0)


def make_model(n=6, seed=0, em_loadings=None):
    """A model with known loadings: humic-like C1, humic-like C2, tryptophan-like C3."""
    rng = np.random.default_rng(seed)
    B = unit(np.column_stack([gauss(EX, 250, 30), gauss(EX, 330, 25), gauss(EX, 280, 12)]))
    C = unit(np.column_stack([gauss(EM, 450, 50), gauss(EM, 410, 40), gauss(EM, 345, 20)])
             if em_loadings is None else em_loadings)
    A = rng.lognormal(0, 0.5, (n, 3))
    return xr.Dataset(
        {"scores": (("sample", "component"), A, {"units": "R.U."}),
         "ex_loadings": (("ex", "component"), B),
         "em_loadings": (("em", "component"), C)},
        coords={"sample": [f"s{i}" for i in range(n)], "ex": EX, "em": EM,
                "component": [1, 2, 3]})


def test_total_is_the_integral_of_the_modelled_eem():
    m = make_model()
    eem = P.model_eem(m)
    ch = {"T": {"ex": 280.0, "em": (330.0, 370.0)}}
    out = P.component_signals(m, ch)
    band = (EM >= 330) & (EM <= 370)
    expect = [_trapz(eem.sel(sample=s, ex=280.0).values[band], EM[band])
              for s in m["sample"].values]
    np.testing.assert_allclose(out["total"].sel(channel="T"), expect, rtol=1e-12)
    np.testing.assert_allclose(out["signal"].sum("component"), out["total"])
    assert out["signal"].attrs["units"] == "R.U. nm"
    assert out["signal"].dims == ("sample", "channel", "component")


def test_signal_is_score_times_loadings():
    m = make_model()
    out = P.component_signals(m, {"T": {"ex": 280.0, "em": (330.0, 370.0)}})
    band = (EM >= 330) & (EM <= 370)
    f = 2                                               # C3 (index 2)
    em_int = _trapz(m["em_loadings"].values[band, f], EM[band])
    ex_val = float(m["ex_loadings"].sel(ex=280.0).values[f])
    np.testing.assert_allclose(out["signal"].values[:, 0, f],
                               m["scores"].values[:, f] * ex_val * em_int, rtol=1e-12)
    np.testing.assert_allclose(out["sensitivity"].values[0, f], ex_val * em_int, rtol=1e-12)


def test_a_channel_on_the_protein_peak_follows_the_protein_component():
    m = make_model()
    out = P.component_signals(m, {"T": {"ex": 280.0, "em": (335.0, 355.0)},
                                  "H": {"ex": 330.0, "em": (430.0, 470.0)}})
    share = out["share"]
    assert float(share.sel(channel="T", component=3).min()) > 0.5
    assert float(share.sel(channel="H", component=3).max()) < 0.1
    np.testing.assert_allclose(share.sum("component"), 1.0)
    sens = out["sensitivity"]
    assert int(sens.sel(channel="T").argmax("component")) == 2


def test_band_edges_between_grid_points_are_interpolated():
    # linear emission loadings: the trapezoid rule is exact, also between grid points
    C = np.column_stack([EM / 600, 2 - EM / 600, np.full_like(EM, 0.5)])
    m = make_model(em_loadings=C)
    Cn = m["em_loadings"].values
    lo, hi = 332.5, 371.5
    out = P.component_signals(m, {"x": {"ex": 280.0, "em": (lo, hi)}})
    for f in range(3):
        slope = (Cn[1, f] - Cn[0, f]) / 5
        icpt = Cn[0, f] - slope * EM[0]
        exact = icpt * (hi - lo) + slope * (hi ** 2 - lo ** 2) / 2
        got = out["sensitivity"].values[0, f] / float(m["ex_loadings"].sel(ex=280.0)[f])
        assert got == pytest.approx(exact, rel=1e-10)


def test_mean_is_the_integral_over_the_filter_area():
    m = make_model()
    ch = {"T": {"ex": 280.0, "em": (330.0, 370.0)}}
    i = P.component_signals(m, ch)
    mean = P.component_signals(m, ch, reduce="mean")
    np.testing.assert_allclose(mean["signal"], i["signal"] / 40.0, rtol=1e-12)
    assert mean["signal"].attrs["units"] == "R.U."


def test_filter_table_and_flat_band_agree_when_transmission_is_one():
    m = make_model()
    band = P.component_signals(m, {"T": {"ex": 280.0, "em": (330.0, 370.0)}})
    table = P.component_signals(m, {"T": {"ex": 280.0,
                                          "em": ([330.0, 370.0], [1.0, 1.0])}})
    np.testing.assert_allclose(table["signal"], band["signal"])
    half = P.component_signals(m, {"T": {"ex": 280.0, "em": ([330.0, 370.0], [0.5, 0.5])}})
    np.testing.assert_allclose(half["signal"], 0.5 * band["signal"])


def test_led_table_is_a_weighted_average_of_the_loadings():
    m = make_model()
    two = P.component_signals(m, {"x": {"ex": ([270.0, 290.0], [1.0, 1.0]),
                                        "em": (330.0, 370.0)}})
    line = {w: P.component_signals(m, {"x": {"ex": w, "em": (330.0, 370.0)}})
            for w in (270.0, 280.0, 290.0)}
    # flat LED over 270-290 nm, trapezoid on the 10 nm grid: (a + 2 b + c) / 4
    expect = (line[270.0]["sensitivity"] + 2 * line[280.0]["sensitivity"]
              + line[290.0]["sensitivity"]) / 4
    np.testing.assert_allclose(two["sensitivity"], expect, rtol=1e-12)
    # a very narrow LED is the single line (the loadings are linear between grid points,
    # so a window of 0.02 nm around a grid point differs from the line by ~0.01 nm of slope)
    narrow = P.component_signals(m, {"x": {"ex": ([279.99, 280.01], [1, 1]),
                                           "em": (330.0, 370.0)}})
    np.testing.assert_allclose(narrow["sensitivity"], line[280.0]["sensitivity"], rtol=1e-3)


def test_share_is_nan_where_the_total_is_zero():
    m = make_model()
    m["scores"].values[0] = 0.0
    out = P.component_signals(m, {"T": {"ex": 280.0, "em": (330.0, 370.0)}})
    assert np.isnan(out["share"].values[0]).all()
    assert np.isfinite(out["share"].values[1:]).all()


@pytest.mark.parametrize("channels, match", [
    ({"x": {"ex": 200.0, "em": (330.0, 370.0)}}, "outside the excitation range"),
    ({"x": {"ex": 280.0, "em": (330.0, 700.0)}}, "outside the emission range"),
    ({"x": {"ex": 280.0, "em": 350.0}}, "not a single wavelength"),
    ({"x": {"ex": 280.0, "em": (370.0, 330.0)}}, "is empty"),
    ({"x": {"ex": 280.0}}, "needs 'ex'"),
    ({"x": {"ex": 280.0, "em": ([330.0, 370.0], [0.0, 0.0])}}, "weights"),
    ({"x": {"ex": 280.0, "em": ([370.0, 330.0], [1.0, 1.0])}}, "increasing"),
    ({}, "at least one channel"),
])
def test_bad_channels_are_rejected(channels, match):
    with pytest.raises(SettingsError, match=match):
        P.component_signals(make_model(), channels)


def test_bad_reduce_is_rejected():
    with pytest.raises(SettingsError, match="reduce"):
        P.component_signals(make_model(), {"x": {"ex": 280.0, "em": (330.0, 370.0)}},
                            reduce="sum")


def test_works_on_a_fitted_model():
    m0 = make_model(n=30)
    X = P.model_eem(m0).values
    ds = xr.Dataset({"intensity": (("sample", "ex", "em"), X, {"units": "R.U."})},
                    coords={"sample": m0["sample"].values, "ex": EX, "em": EM})
    ds.attrs["spectral_correction"] = "none"
    fit = P.fit_parafac(ds, 3, n_init=3, max_iter=2000)
    ch = {"T": {"ex": 280.0, "em": (330.0, 370.0)}}
    out = P.component_signals(fit, ch)
    # whatever the component order, the sum is the modelled signal of the sample
    band = (EM >= 330) & (EM <= 370)
    ref = [_trapz(P.model_eem(fit).sel(sample=s, ex=280.0).values[band], EM[band])
           for s in fit["sample"].values]
    np.testing.assert_allclose(out["total"].sel(channel="T"), ref, rtol=1e-10)
    # and the model describes the data: same signal as the data themselves
    data = [_trapz(ds["intensity"].sel(sample=s, ex=280.0).values[band], EM[band])
            for s in fit["sample"].values]
    np.testing.assert_allclose(out["total"].sel(channel="T"), data, rtol=0.05)
