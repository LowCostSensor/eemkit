import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from eemkit import EEMKitWarning
from eemkit import indices as I
from eemkit.errors import IndexComputationError

EX = np.arange(240.0, 451.0, 10.0)
EM = np.arange(250.0, 601.0, 2.0)


def make_ds(fn, n=2):
    """EEM whose value is fn(ex, em) (times sample number + 1)."""
    ex = xr.DataArray(EX, dims="ex", coords={"ex": EX})
    em = xr.DataArray(EM, dims="em", coords={"em": EM})
    base = fn(ex, em).transpose("ex", "em")
    scale = xr.DataArray(np.arange(1, n + 1.0), dims="sample",
                         coords={"sample": [f"s{i}" for i in range(n)]})
    ds = xr.Dataset({"intensity": (scale * base).assign_attrs(units="R.U.")})
    return ds.assign_coords(river=("sample", ["A", "B"][:n]))


def test_fi_on_grid():
    ds = make_ds(lambda ex, em: 1000.0 / em + 0 * ex)
    fi = I.fluorescence_index(ds)
    np.testing.assert_allclose(fi, 520 / 470)


def test_bix_point_and_range():
    ds = make_ds(lambda ex, em: em + 0 * ex)
    np.testing.assert_allclose(I.biological_index(ds), 380 / 430)
    np.testing.assert_allclose(I.biological_index(ds, em_den=(420.0, 435.0)), 380 / 435)


def test_hix_exact_areas_and_off_grid_excitation():
    # constant over em, linear in ex: H and L areas are both 45 * value -> HIX 0.5
    ds = make_ds(lambda ex, em: ex + 0 * em)
    for m in ("linear", "nearest"):
        np.testing.assert_allclose(I.humification_index(ds, ex_method=m), 0.5)
    # emission-dependent: f = em -> H = (480^2-435^2)/2, L = (345^2-300^2)/2
    ds = make_ds(lambda ex, em: em + 0 * ex)
    h, low = (480**2 - 435**2) / 2, (345**2 - 300**2) / 2
    np.testing.assert_allclose(I.humification_index(ds, ex_method="linear"), h / (h + low))


def test_hix_requires_explicit_choice_for_off_grid():
    ds = make_ds(lambda ex, em: ex + em)
    with pytest.raises(TypeError):
        I.humification_index(ds)
    with pytest.raises(IndexComputationError, match="not measured"):
        I.humification_index(ds, ex_method="exact")


def test_excitation_interpolation_methods():
    ds = make_ds(lambda ex, em: ex + 0 * em)
    lin = I.spectrum_at_ex(ds["intensity"], 254.0, "linear").sel(sample="s0")
    near = I.spectrum_at_ex(ds["intensity"], 254.0, "nearest").sel(sample="s0")
    np.testing.assert_allclose(lin, 254.0)
    np.testing.assert_allclose(near, 250.0)
    with pytest.raises(IndexComputationError, match="outside"):
        I.spectrum_at_ex(ds["intensity"], 230.0, "linear")


def test_coble_peaks_are_maxima_over_ranges():
    ds = make_ds(lambda ex, em: np.exp(-((em - 440) / 30) ** 2) * (ex / 100))
    pk = I.coble_peaks(ds, ex_method="linear").sel(sample="s0")
    assert float(pk["C"]) == pytest.approx(3.5)  # max at em 440 within 420-480, ex 350
    assert float(pk["A"]) == pytest.approx(2.6)
    assert float(pk["M"]) == pytest.approx(3.12 * np.exp(-((420 - 440) / 30) ** 2))
    assert pk["C"].attrs["units"] == "R.U."


def test_nan_in_window_gives_nan_and_warning():
    ds = make_ds(lambda ex, em: em + 0 * ex)
    ds["intensity"].loc[dict(ex=370.0, em=470.0)] = np.nan
    with pytest.warns(EEMKitWarning, match="FI"):
        fi = I.fluorescence_index(ds)
    assert fi.isnull().all()


def test_compute_and_export(tmp_path):
    ds = make_ds(lambda ex, em: 1000.0 / em + ex / 1000)
    ds.attrs["spectral_correction"] = "none"
    df = I.compute_indices(ds, ex_method="linear")
    assert list(df.columns) == ["FI", "HIX", "BIX", "peak_B", "peak_T", "peak_A",
                                "peak_M", "peak_C"]
    assert df.attrs["settings"]["spectral_correction"] == "none"
    csv, side = I.export_indices(df, tmp_path / "idx.csv", ds, metadata=("river",))
    back = pd.read_csv(csv, index_col="sample")
    assert list(back.columns[:2]) == ["river", "FI"]
    assert back.loc["s1", "river"] == "B"
    meta = json.loads(side.read_text())
    assert meta["ex_method"] == "linear" and meta["HIX"]["reference"] == "Ohno 2002"


def test_per_scan_coordinates_do_not_break_peaks():
    ds = make_ds(lambda ex, em: em + 0 * ex)
    t = np.zeros((2, EX.size), dtype="datetime64[s]") + np.arange(EX.size).astype("timedelta64[s]")
    ds = ds.assign_coords(eem_scan_time=(("sample", "ex"), t))
    df = I.compute_indices(ds, ex_method="linear")
    assert df.notna().all().all()


def test_overrides_are_recorded():
    ds = make_ds(lambda ex, em: em + 0 * ex)
    df = I.compute_indices(ds, ex_method="linear", bix={"em_den": (420.0, 435.0)})
    np.testing.assert_allclose(df["BIX"], 380 / 435)
    assert df.attrs["settings"]["BIX"]["em_den"] == (420.0, 435.0)
