import warnings

import numpy as np
import pytest
import xarray as xr

from eemkit import EEMKitWarning
from eemkit import parafac as P
from eemkit.parafac._cp import khatri_rao, reconstruct, unfold

EX = np.arange(240.0, 451.0, 10.0)
EM = np.arange(250.0, 601.0, 4.0)
# (ex centre, ex width, em centre, em width) of three humic/protein-like components
TRUE = [(250, 30, 450, 50), (320, 25, 410, 40), (280, 15, 340, 25)]


def gauss(x, c, w):
    return np.exp(-0.5 * ((x - c) / w) ** 2)


def synthetic(n=40, noise=0.01, missing=True, seed=0, outlier=False):
    rng = np.random.default_rng(seed)
    B = np.column_stack([gauss(EX, c, w) for c, w, _, _ in TRUE])
    C = np.column_stack([gauss(EM, c, w) for _, _, c, w in TRUE])
    A = rng.lognormal(0, 0.5, (n, 3))
    X = reconstruct(A, B, C)
    if outlier:
        X[0] += 5 * np.outer(gauss(EX, 400, 10), gauss(EM, 550, 10))
    X += noise * X.max() * rng.standard_normal(X.shape)
    if missing:
        band = np.abs(EM[None, :] - EX[:, None]) <= 12  # Rayleigh-like band
        X[:, band] = np.nan
    ds = xr.Dataset({"intensity": (("sample", "ex", "em"), X, {"units": "R.U."})},
                    coords={"sample": [f"s{i}" for i in range(n)], "ex": EX, "em": EM,
                            "campaign": ("sample", np.repeat(["a", "b"], n // 2))})
    ds.attrs["spectral_correction"] = "none"
    return ds, A, B, C


def test_khatri_rao_matches_unfolding():
    rng = np.random.default_rng(1)
    A, B, C = rng.random((4, 2)), rng.random((3, 2)), rng.random((5, 2))
    X = reconstruct(A, B, C)
    np.testing.assert_allclose(unfold(X, 0), A @ khatri_rao(B, C).T)
    np.testing.assert_allclose(unfold(X, 1), B @ khatri_rao(A, C).T)
    np.testing.assert_allclose(unfold(X, 2), C @ khatri_rao(A, B).T)


@pytest.mark.parametrize("missing", [False, True])
def test_recovers_true_components(missing):
    ds, A, B, C = synthetic(noise=0.0, missing=missing)
    res = P.nn_parafac(ds["intensity"].values, 3, random_state=0, tol=1e-10, max_iter=3000)
    order, tex, tem = P.match_components(B, C, res.B, res.C)
    assert tex.min() > 0.999 and tem.min() > 0.999
    assert (res.A >= 0).all() and (res.B >= 0).all() and (res.C >= 0).all()


def test_fit_parafac_outputs_and_units():
    ds, A, B, C = synthetic()
    m = P.fit_parafac(ds, 3, n_init=3, max_iter=2000)
    assert m.attrs["explained_variance_pct"] > 99
    assert m.attrs["core_consistency_pct"] > 90
    assert m.attrs["n_init_at_best_minimum"] >= 2
    np.testing.assert_allclose(np.linalg.norm(m.ex_loadings, axis=0), 1)
    # normalisation is undone: the model reproduces the data in data units
    resid = P.residuals(m, ds)
    assert float(np.nanmax(np.abs(resid))) < 0.06 * float(np.nanmax(ds.intensity))
    np.testing.assert_allclose(m.leverage_sample.sum(), 3, rtol=1e-6)
    assert list(m.campaign.values[:2]) == ["a", "a"]
    # components sorted by decreasing contribution
    contrib = [(m.scores[:, f] ** 2).sum() for f in range(3)]
    assert contrib[0] >= contrib[-1]


def test_core_consistency_drops_when_overfactored():
    ds, *_ = synthetic(noise=0.02)
    cc = {r: P.fit_parafac(ds, r, n_init=3, max_iter=2000).attrs["core_consistency_pct"]
          for r in (3, 5)}
    assert cc[3] > 90 and cc[5] < cc[3] - 20


def test_outlier_has_highest_residual_and_leverage():
    ds, *_ = synthetic(outlier=True)
    m = P.fit_parafac(ds, 3, n_init=2, max_iter=2000)
    assert int(np.argmax(m.sse_sample.values)) == 0


def test_core_consistency_exact_model_is_100():
    ds, A, B, C = synthetic(noise=0.0, missing=False)
    X = ds.intensity.values
    assert P.core_consistency(X, A, B, C) == pytest.approx(100, abs=1e-6)
    with pytest.raises(ValueError):
        P.core_consistency(np.where(X > 0.5, np.nan, X), A, B, C)


def test_tucker_and_matching():
    x = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    np.testing.assert_allclose(np.diag(P.tucker_congruence(x, x)), 1)
    order, te, tm = P.match_components(x, x, x[:, ::-1], x[:, ::-1])
    assert list(order) == [1, 0]
    np.testing.assert_allclose(te, 1)


def test_split_half_validates_true_rank_only():
    ds, *_ = synthetic(n=48, noise=0.02)
    sh3 = P.split_half(ds, 3, stratify="campaign", n_init=3, max_iter=2000)
    assert sh3.attrs["validated"] == 1 and sh3.attrs["min_tcc"] > 0.95
    assert sh3.tcc_ex.shape == (3, 3)
    g = sh3.groups.values
    assert set(g) == {0, 1, 2, 3} and abs(np.bincount(g) - 12).max() <= 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", EEMKitWarning)  # over-factored models converge slowly
        sh5 = P.split_half(ds, 5, stratify="campaign", n_init=3, max_iter=2000)
    assert sh5.attrs["validated"] == 0


def test_openfluor_export(tmp_path):
    ds, *_ = synthetic(n=20)
    m = P.fit_parafac(ds, 3, n_init=1, max_iter=500)
    path = P.to_openfluor(m, tmp_path / "model.txt", name="Test", creator="me")
    lines = path.read_text().splitlines()
    assert "name\tTest" in lines and "nSample\t20" in lines and "unit\tR.U." in lines
    ex_rows = [line.split("\t") for line in lines if line.startswith("Ex\t")]
    em_rows = [line.split("\t") for line in lines if line.startswith("Em\t")]
    assert len(ex_rows) == EX.size and len(em_rows) == EM.size and len(ex_rows[0]) == 5
    assert max(float(r[2]) for r in ex_rows) == pytest.approx(1)
    with pytest.raises(ValueError, match="unknown"):
        P.to_openfluor(m, tmp_path / "x.txt", colour="red")


def test_agrees_with_tensorly_on_complete_data():
    tl = pytest.importorskip("tensorly")
    from tensorly.decomposition import non_negative_parafac_hals

    ds, A, B, C = synthetic(noise=0.01, missing=False)
    X = ds.intensity.values
    ours = P.nn_parafac(X, 3, random_state=0, tol=1e-10, max_iter=3000)
    cp = non_negative_parafac_hals(tl.tensor(X), rank=3, n_iter_max=3000, tol=1e-10,
                                   random_state=0, init="random")
    _, tB, tC = cp.factors
    _, tex, tem = P.match_components(ours.B, ours.C, np.asarray(tB), np.asarray(tC))
    assert tex.min() > 0.999 and tem.min() > 0.999
    sse_tl = float(np.sum((X - tl.cp_to_tensor(cp)) ** 2))
    assert ours.sse <= sse_tl * 1.001
