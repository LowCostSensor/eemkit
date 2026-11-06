"""SSC, EEMqual, model comparison and projection of new samples."""

import json
import warnings

import numpy as np
import pytest
from test_parafac import EM, EX, gauss, synthetic

from eemkit import EEMKitWarning, GridError
from eemkit import parafac as P

WL = np.arange(300.0, 601.0, 1.0)


# --------------------------------------------------------------------------- #
# Shift- and shape-sensitive congruence
# --------------------------------------------------------------------------- #

def test_ssc_of_identical_spectra_is_one():
    p = np.column_stack([gauss(WL, 420, 30), gauss(WL, 480, 50)])
    np.testing.assert_allclose(np.diag(P.shift_shape_congruence(p, p, WL)), 1)


def test_ssc_penalises_a_shift_by_its_share_of_the_range():
    p = gauss(WL, 420, 30)[:, None]
    q = gauss(WL, 430, 30)[:, None]  # same shape, 10 nm later, inside the range
    tcc = P.tucker_congruence(p, q)[0, 0]
    ssc = P.shift_shape_congruence(p, q, WL)[0, 0]
    assert tcc > 0.97  # TCC barely notices a 10 nm shift
    assert ssc == pytest.approx(tcc - 10 / 300, abs=1e-4)


def test_ssc_penalises_a_wider_peak():
    p = gauss(WL, 450, 25)[:, None]
    q = gauss(WL, 450, 40)[:, None]  # same maximum, wider
    tcc = P.tucker_congruence(p, q)[0, 0]
    ssc = P.shift_shape_congruence(p, q, WL)[0, 0]
    # beta = difference of the max-normalised areas, sqrt(2 pi) (40 - 25), over the range
    assert ssc == pytest.approx(tcc - np.sqrt(2 * np.pi) * 15 / 300, abs=1e-3)


def test_ssc_is_close_to_stardoms_sum_on_a_1nm_grid():
    p = gauss(WL, 400, 20)[:, None]
    q = gauss(WL, 470, 45)[:, None]
    span = WL[-1] - WL[0]
    tcc = P.tucker_congruence(p, q)[0, 0]
    alpha = abs(WL[p.argmax()] - WL[q.argmax()]) / span
    beta_sum = abs((p / p.max()).sum() - (q / q.max()).sum()) / span  # staRdom's ssc()
    ours = P.shift_shape_congruence(p, q, WL)[0, 0]
    assert abs(ours - (tcc - alpha - beta_sum)) <= 1 / span


def test_ssc_input_checks():
    p = gauss(WL, 420, 30)[:, None]
    with pytest.raises(ValueError, match="rows"):
        P.shift_shape_congruence(p, p[:-1], WL)
    with pytest.raises(ValueError, match="positive maximum"):
        P.shift_shape_congruence(p, np.zeros_like(p), WL)


# --------------------------------------------------------------------------- #
# Comparing models
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def models():
    ds, *_ = synthetic(n=40, noise=0.01)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", EEMKitWarning)
        return ds, {r: P.fit_parafac(ds, r, n_init=2, max_iter=1500, n_jobs=1) for r in (2, 3)}


def test_compare_a_model_with_itself(models):
    _, m = models
    df = P.compare_models(m[3], m[3])
    assert list(df["component_2"]) == [1, 2, 3]
    np.testing.assert_allclose(df[["tcc_ex", "tcc_em", "ssc_ex", "ssc_em"]], 1, atol=1e-12)


def test_compare_models_of_different_rank_lists_the_extra_component(models):
    _, m = models
    df = P.compare_models(m[3], m[2])
    assert len(df) == 3 and df["component_2"].isna().sum() == 1
    ranks = P.compare_ranks(m)
    assert set(ranks["ranks"]) == {"2 vs 3"} and len(ranks) == 3


def test_compare_models_needs_the_same_wavelengths(models):
    ds, m = models
    other = P.fit_parafac(ds.isel(em=slice(0, -5)), 2, n_init=1, max_iter=300, n_jobs=1)
    with pytest.raises(GridError, match="em wavelengths"):
        P.compare_models(m[2], other)


def test_component_correlations(models):
    _, m = models
    r = P.component_correlations(m[3])
    assert r.shape == (3, 3) and list(r.columns) == ["C1", "C2", "C3"]
    np.testing.assert_allclose(np.diag(r), 1)
    with pytest.raises(ValueError):
        P.component_correlations(m[3], method="kendall")


def test_split_half_reports_ssc():
    ds, *_ = synthetic(n=48, noise=0.02)
    sh = P.split_half(ds, 3, stratify="campaign", n_init=2, max_iter=1500)
    assert sh.ssc_em.shape == (3, 3)
    assert 0.9 < sh.attrs["min_ssc_em"] <= 1
    assert (sh.ssc_em <= sh.tcc_em + 1e-12).all()  # SSC is never above TCC


# --------------------------------------------------------------------------- #
# EEMqual
# --------------------------------------------------------------------------- #

def test_eemqual_is_the_product_and_ignores_negative_core_consistency(models):
    _, m = models

    class Split:
        attrs = {"min_tcc": 0.98}

    q = P.eemqual(m[3], Split)
    a = m[3].attrs
    assert q["eemqual"] == pytest.approx(
        a["explained_variance_pct"] / 100 * a["core_consistency_pct"] / 100 * 0.98)
    bad = m[3].copy()
    bad.attrs = {**a, "core_consistency_pct": -250.0}
    assert P.eemqual(bad, Split)["eemqual"] == 0


# --------------------------------------------------------------------------- #
# Projection of new samples
# --------------------------------------------------------------------------- #

def test_projecting_the_model_samples_gives_back_their_scores(models):
    ds, m = models
    proj = P.project_samples(m[3], ds)
    np.testing.assert_allclose(proj.scores, m[3].scores, rtol=2e-3, atol=1e-6)
    assert not proj.outside_model_range.any()
    assert proj.attrs["model_max_relative_sse"] == pytest.approx(
        float((m[3].sse_sample / m[3].data_sumsq).max()))
    assert "project_samples" in proj.attrs["eemkit_history"]


def test_new_samples_get_true_scores_and_an_odd_one_is_flagged():
    train, *_ = synthetic(n=40, noise=0.005, seed=1)
    new, A, B, C = synthetic(n=6, noise=0.005, seed=2, outlier=True)  # sample 0 is odd
    model = P.fit_parafac(train, 3, n_init=2, max_iter=2000, n_jobs=1)
    with pytest.warns(EEMKitWarning, match=r"worse than any sample.*s0"):
        proj = P.project_samples(model, new)
    assert list(proj.outside_model_range.values) == [True] + [False] * 5
    # the clean samples: projected Fmax matches the true maximum of each component
    true_fmax = A * B.max(axis=0) * C.max(axis=0)
    order, *_ = P.match_components(B, C, model.ex_loadings.values, model.em_loadings.values)
    np.testing.assert_allclose(proj.fmax.values[1:, order], true_fmax[1:], rtol=0.03)


def test_projection_checks_grid_and_processing(models):
    ds, m = models
    with pytest.raises(GridError, match="wavelengths"):
        P.project_samples(m[2], ds.isel(ex=slice(2, None)))
    other = ds.copy()  # same grid, but processed differently: warning
    other.attrs["eemkit_history"] = json.dumps([{"step": "crop", "params": {"ex": [250, None]},
                                                 "eemkit_version": "0", "time": ""}])
    with pytest.warns(EEMKitWarning, match="processed differently"):
        P.project_samples(m[2], other)
    assert EX.size == m[2].sizes["ex"] and EM.size == m[2].sizes["em"]
