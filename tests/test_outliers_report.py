"""Outlier diagnostics, their figures and the HTML report."""

import warnings

import matplotlib
import numpy as np
import pandas as pd
import pytest
from test_parafac import synthetic

from eemkit import EEMKitWarning, pipeline, plot
from eemkit import parafac as P
from eemkit.report import write_report

matplotlib.use("Agg")


@pytest.fixture(scope="module")
def fitted():
    ds, *_ = synthetic(n=40, noise=0.01, outlier=True)  # sample s0 has an extra peak
    ds = ds.assign_coords(eem_file=("sample", [f"C:/data/{s}.csv" for s in ds.sample.values]),
                          river=("sample", np.repeat(["Farma", "Merse"], 20)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", EEMKitWarning)
        model = P.fit_parafac(ds, 3, n_init=2, max_iter=1500, n_jobs=1)
        split = P.split_half(ds, 3, n_init=1, max_iter=800, n_jobs=1)
    return ds, model, split


def test_sample_diagnostics_puts_the_odd_sample_first(fitted):
    _, model, _ = fitted
    d = P.sample_diagnostics(model)
    assert d.index[0] == "s0" and d.iloc[0]["residual_rank"] == 1
    assert {"leverage", "sse", "relative_sse", "leverage_rank", "residual_rank"} <= set(d)
    assert "river" in d and "eem_file" not in d  # labels kept, file paths left out
    np.testing.assert_allclose(d.loc["s0", "relative_sse"],
                               float(model.sse_sample[0] / model.data_sumsq[0]))


def test_spectral_residuals_add_up_to_the_model_residual(fitted):
    ds, model, _ = fitted
    sr = P.spectral_residuals(model, ds)
    total = float(model.sse_sample.sum())
    assert float(sr.sse_ex.sum()) == pytest.approx(total, rel=1e-9)
    assert float(sr.sse_em.sum()) == pytest.approx(total, rel=1e-9)
    assert sr.bias_em.sizes["em"] == ds.sizes["em"] and np.isfinite(sr.relative_sse_ex).all()
    # the extra peak of s0 (em 550 nm) is under-fitted: positive mean residual there
    assert float(sr.bias_em.sel(em=550, method="nearest")) > 0


def test_outlier_figures(fitted):
    ds, model, _ = fitted
    fig = plot.residual_eems(model, ds, n=2)
    assert len(fig.axes) >= 6
    assert fig.axes[0].get_title(loc="left") == "s0: measured"
    plot.spectral_residuals(P.spectral_residuals(model, ds))
    with pytest.raises(ValueError, match="not in the model"):
        plot.residual_eems(model, ds, samples=["nope"])
    matplotlib.pyplot.close("all")


def test_report_contains_every_section(fitted, tmp_path):
    ds, model, split = fitted
    s = pipeline.default_settings()
    s["parafac"]["final"]["rank"] = 3
    table = P.summary_table({3: model})
    table["split_half_min_tcc"] = split.attrs["min_tcc"]
    table["split_half_validated"] = bool(split.attrs["validated"])
    table["eemqual"] = P.eemqual(model, split)["eemqual"]
    exploration = pipeline.Exploration({3: model}, {3: split}, table)
    indices = pd.DataFrame({"HIX": np.linspace(1, 2, 40), "cdom_notes": [""] * 39 + ["low"]},
                           index=ds.sample.values)
    path = write_report(tmp_path / "r" / "report.html", s, corrected=ds, indices=indices,
                        exploration=exploration, model=model, split=split, title="Test <run>")
    text = path.read_text(encoding="utf-8")
    for anchor in ("samples", "indices", "exploration", "model", "outliers", "reproduce"):
        assert f'id="{anchor}"' in text
    assert text.count("data:image/png;base64,") >= 5
    assert "Test &lt;run&gt;" in text  # escaped
    assert "1 sample(s) have CDOM values left empty" in text
    assert "C:/data/" not in text  # no file paths in the page
    assert "Samples by river" in text and "EEMqual" in text


def test_report_with_only_settings(tmp_path):
    path = write_report(tmp_path / "report.html", pipeline.default_settings())
    text = path.read_text(encoding="utf-8")
    assert 'id="reproduce"' in text and 'id="model"' not in text
