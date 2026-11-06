"""Dilution correction and zap, alone and through the pipeline (synthetic project)."""

import warnings

import numpy as np
import pandas as pd
import pytest
from test_pipeline import make_project

from eemkit import corrections as C
from eemkit import pipeline
from eemkit.core.history import get_history, has_step
from eemkit.errors import CorrectionError, EEMKitWarning, SettingsError
from eemkit.io.discover import scan_folder, suggest_pairing


@pytest.fixture
def project(tmp_path):
    data = make_project(tmp_path)
    draft = suggest_pairing(scan_folder(data))
    draft["include"] = "yes"
    s = pipeline.default_settings()
    s["project"].update(data_root=str(data), pairing=str(tmp_path / "pairing.csv"))
    s["inner_filter"].update(absorbance_path_length_cm=1.0, fluorescence_path_length_cm=1.0)
    return s, draft, tmp_path


def _run(s, draft, tmp_path, **columns):
    table = draft.copy()
    for name, values in columns.items():
        table[name] = values
    table.to_csv(tmp_path / "pairing.csv", index=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        after = pipeline.correct_until_raman(pipeline.load(s), s)
        cdom = pipeline.compute_absorbance(after, s)
    return after, cdom


# --------------------------------------------------------------------------- #
# Dilution
# --------------------------------------------------------------------------- #

def test_without_dilution_columns_nothing_changes(project):
    after, _ = _run(*project)
    assert not has_step(after, "match_absorbance_dilution")
    assert not has_step(after, "correct_dilution")


def test_eem_and_absorbance_diluted_alike(project):
    s, draft, tmp = project
    base, cdom0 = _run(s, draft, tmp, dilution_factor="")
    f = ["2"] + [""] * (len(draft) - 1)  # first sample diluted 1:2 for both measurements
    after, cdom = _run(s, draft, tmp, dilution_factor=f, abs_dilution_factor=f)
    first = after.sample.values[0]
    np.testing.assert_allclose(after.intensity.sel(sample=first),
                               2 * base.intensity.sel(sample=first), rtol=1e-12)
    np.testing.assert_allclose(after.intensity.isel(sample=slice(1, None)),
                               base.intensity.isel(sample=slice(1, None)))
    # same solution in both instruments: the inner-filter factor does not change
    np.testing.assert_allclose(after.ife_factor, base.ife_factor)
    assert cdom.loc[first, "a254"] == pytest.approx(2 * cdom0.loc[first, "a254"])
    assert cdom.loc[first, "S275_295"] == pytest.approx(cdom0.loc[first, "S275_295"])
    assert cdom.loc[first, "E2_E3"] == pytest.approx(cdom0.loc[first, "E2_E3"])
    steps = [e["step"] for e in get_history(after)]
    assert steps.index("match_absorbance_dilution") < steps.index("correct_inner_filter")
    assert steps.index("normalize_raman") < steps.index("correct_dilution")


def test_absorbance_measured_on_a_dilution_is_rescaled_for_the_inner_filter(project):
    s, draft, tmp = project
    base, cdom0 = _run(s, draft, tmp, dilution_factor="")
    f = ["4"] + [""] * (len(draft) - 1)  # absorbance of S1 measured 1:4, EEM undiluted
    after, cdom = _run(s, draft, tmp, abs_dilution_factor=f)
    first = after.sample.values[0]
    np.testing.assert_allclose(after.absorbance.sel(sample=first),
                               4 * base.absorbance.sel(sample=first))
    assert float(after.ife_factor.sel(sample=first).max()) > float(
        base.ife_factor.sel(sample=first).max())
    assert cdom.loc[first, "a254"] == pytest.approx(4 * cdom0.loc[first, "a254"])


@pytest.mark.parametrize("bad", ["0.5", "abc", "-2"])
def test_invalid_dilution_factors_are_errors(project, bad):
    s, draft, tmp = project
    f = [bad] + [""] * (len(draft) - 1)
    with pytest.raises(CorrectionError, match="dilution factor must be a number >= 1"):
        _run(s, draft, tmp, dilution_factor=f)


def test_dilution_order_is_enforced(project):
    s, draft, tmp = project
    after, _ = _run(s, draft, tmp, dilution_factor="")
    with pytest.raises(CorrectionError, match="already been applied"):
        C.correct_dilution(after)
    raw = pipeline.load(s)
    with pytest.raises(CorrectionError, match="Raman units first"):
        C.correct_dilution(raw)


# --------------------------------------------------------------------------- #
# Zap
# --------------------------------------------------------------------------- #

def test_zap_removes_the_region_and_records_it(project):
    s, draft, tmp = project
    after, _ = _run(s, draft, tmp)
    first = str(after.sample.values[0])
    z = C.zap(after, [{"sample": first, "ex": [250, 270], "em": [300, 320], "reason": "spike"},
                      {"sample": str(after.sample.values[1]), "ex": [300, 300]}])
    cell = z.intensity.sel(sample=first, ex=slice(250, 270), em=slice(300, 320))
    assert cell.isnull().all() and int(z.zapped.sel(sample=first).sum()) == cell.size
    whole_scan = z.intensity.sel(sample=after.sample.values[1], ex=300)
    assert whole_scan.isnull().all()  # empty em range = the whole emission scan
    assert np.isfinite(z.intensity.sel(sample=after.sample.values[2])).all()
    entry = get_history(z)[-1]
    assert entry["step"] == "zap" and entry["params"]["regions"][0]["reason"] == "spike"


@pytest.mark.parametrize("region, message", [
    ({"sample": "nope"}, "unknown sample"),
    ({"sample": "S1", "ex": [800, 900]}, "no measured wavelength"),
    ({"sample": "S1", "em": [400, 300]}, r"\[low, high\]"),
])
def test_zap_rejects_mistakes(project, region, message):
    after, _ = _run(*project)
    with pytest.raises(CorrectionError, match=message):
        C.zap(after, [region])


def test_zap_from_settings_empties_indices_and_survives_export(project):
    s, draft, tmp = project
    first = str(draft["sample_id"].iloc[0])
    s["zap"]["regions"] = [{"sample": first, "ex": [250, 260], "em": [300, 480],
                            "reason": "test"}]
    p = pipeline.save_settings(s, tmp / "project.toml")  # inline tables round-trip
    s = pipeline.load_settings(p)
    assert s["zap"]["regions"][0]["em"] == [300, 480]
    after, _ = _run(s, draft, tmp)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", EEMKitWarning)
        idx = pipeline.compute_indices(after, s)
    assert any("HIX: NaN for 1 sample(s)" in str(w.message) for w in caught)
    assert np.isnan(idx.loc[first, "HIX"])  # never computed on missing or filled data
    assert np.isfinite(idx.drop(index=first)["HIX"]).all()

    s["scatter"]["interpolate"] = "em"
    cor = pipeline.finish_corrections(after, s)
    zapped = cor.zapped.sel(sample=first)
    # scatter interpolation on, zap interpolation off: the zapped cells stay missing
    assert int(cor.intensity.sel(sample=first).where(zapped).notnull().sum()) == 0
    assert int(zapped.sum()) > 0
    s["zap"]["interpolate"] = "em"
    filled = pipeline.finish_corrections(after, s)
    inside = filled.intensity.sel(sample=first).where(zapped)
    assert int(inside.notnull().sum()) > 0  # the zapped cells between data are filled
    paths = pipeline.export_results(tmp / "out", s, corrected=filled, figures=False)
    assert any(p.name == "corrected_eems.nc" for p in paths)
    s["zap"]["interpolate"] = "sideways"
    with pytest.raises(SettingsError, match="zap.interpolate"):
        pipeline.finish_corrections(after, s)
    assert isinstance(pd.read_csv(tmp / "pairing.csv"), pd.DataFrame)
