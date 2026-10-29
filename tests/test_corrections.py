import numpy as np
import pytest
import xarray as xr

from eemkit import CorrectionError, EEMKitWarning, get_history
from eemkit import corrections as C
from eemkit.core.history import with_history

EX = np.arange(250.0, 451.0, 50.0)  # 250, 300, 350, 400, 450
EM = np.arange(250.0, 601.0, 2.0)
WL = np.arange(200.0, 701.0, 1.0)


def make_ds(n=2, intensity=5.0, blank=1.0, absorbance=0.1, blank_abs=0.02):
    s = [f"s{i}" for i in range(n)]
    shape = (n, EX.size, EM.size)
    ds = xr.Dataset(
        {
            "intensity": (("sample", "ex", "em"), np.full(shape, intensity),
                          {"units": "a.u."}),
            "blank_intensity": (("sample", "ex", "em"), np.full(shape, blank)),
            "absorbance": (("sample", "wavelength"), np.full((n, WL.size), absorbance)),
            "blank_absorbance": (("sample", "wavelength"), np.full((n, WL.size), blank_abs)),
        },
        coords={"sample": s, "ex": EX, "em": EM, "wavelength": WL},
    )
    return with_history(ds, "load_dataset")


def steps(ds):
    return [h["step"] for h in get_history(ds)]


# --- blank -------------------------------------------------------------------

def test_subtract_blank():
    out = C.subtract_blank(make_ds())
    np.testing.assert_allclose(out["intensity"], 4.0)
    np.testing.assert_allclose(out["blank_intensity"], 1.0)  # kept for Raman
    assert out["blank_subtracted"].all()
    assert steps(out)[-1] == "subtract_blank"
    with pytest.raises(CorrectionError, match="already"):
        C.subtract_blank(out)


@pytest.mark.parametrize("policy, n_left, value", [("keep", 2, 5.0), ("drop", 1, None)])
def test_subtract_blank_missing_policies(policy, n_left, value):
    ds = make_ds()
    ds["blank_intensity"][1] = np.nan
    with pytest.raises(CorrectionError, match="s1"):
        C.subtract_blank(ds)
    out = C.subtract_blank(ds, missing=policy)
    assert out.sizes["sample"] == n_left
    np.testing.assert_allclose(out["intensity"].sel(sample="s0"), 4.0)
    if value is not None:
        np.testing.assert_allclose(out["intensity"].sel(sample="s1"), value)
        assert not bool(out["blank_subtracted"].sel(sample="s1"))


def test_subtract_absorbance_blank():
    out = C.subtract_absorbance_blank(make_ds())
    np.testing.assert_allclose(out["absorbance"], 0.08)
    np.testing.assert_allclose(out["blank_absorbance"], 0.02)


# --- inner filter --------------------------------------------------------------

def test_inner_filter_factor():
    ds = C.subtract_absorbance_blank(make_ds(absorbance=0.12, blank_abs=0.02))  # A = 0.10
    out = C.correct_inner_filter(ds, absorbance_path_length_cm=5.0,
                                 fluorescence_path_length_cm=1.0)
    # A over 1 cm = 0.02, factor = 10 ** ((0.02 + 0.02) / 2)
    np.testing.assert_allclose(out["ife_factor"], 10 ** 0.02)
    np.testing.assert_allclose(out["intensity"], 5.0 * 10 ** 0.02)
    np.testing.assert_allclose(out["blank_intensity"], 1.0)
    p = get_history(out)[-1]["params"]
    assert (p["absorbance_path_length_cm"], p["fluorescence_path_length_cm"]) == (5.0, 1.0)


def test_inner_filter_uses_wavelength_dependent_absorbance():
    ds = make_ds(blank_abs=0.0)
    ds["absorbance"] = ds["absorbance"] * 0 + xr.DataArray(0.001 * (700 - WL), dims="wavelength",
                                                          coords={"wavelength": WL})
    ds = C.subtract_absorbance_blank(ds)
    out = C.correct_inner_filter(ds, absorbance_path_length_cm=1, fluorescence_path_length_cm=1)
    f = out["ife_factor"].sel(sample="s0", ex=300.0, em=400.0)
    assert float(f) == pytest.approx(10 ** ((0.4 + 0.3) / 2))


def test_inner_filter_requires_path_lengths_and_order():
    ds = make_ds()
    with pytest.raises(CorrectionError, match="absorbance blank"):
        C.correct_inner_filter(ds, absorbance_path_length_cm=1, fluorescence_path_length_cm=1)
    ds = C.subtract_absorbance_blank(ds)
    with pytest.raises(TypeError):
        C.correct_inner_filter(ds)  # no default cuvette
    with pytest.raises(CorrectionError, match="positive"):
        C.correct_inner_filter(ds, absorbance_path_length_cm=0, fluorescence_path_length_cm=1)
    with pytest.raises(CorrectionError, match="before subtract_blank"):
        C.correct_inner_filter(C.subtract_blank(ds), absorbance_path_length_cm=1,
                               fluorescence_path_length_cm=1)


def test_inner_filter_warns_on_high_a254():
    ds = C.subtract_absorbance_blank(make_ds(absorbance=2.0, blank_abs=0.0))
    with pytest.warns(EEMKitWarning, match="Kothawala"):
        C.correct_inner_filter(ds, absorbance_path_length_cm=1, fluorescence_path_length_cm=1)


def test_inner_filter_missing_absorbance():
    ds = make_ds()
    ds["absorbance"][0] = np.nan
    ds = C.subtract_absorbance_blank(ds)
    with pytest.raises(CorrectionError, match="s0"):
        C.correct_inner_filter(ds, absorbance_path_length_cm=1, fluorescence_path_length_cm=1)
    out = C.correct_inner_filter(ds, absorbance_path_length_cm=1,
                                 fluorescence_path_length_cm=1, missing="keep")
    np.testing.assert_allclose(out["intensity"].sel(sample="s0"), 5.0)
    assert not bool(out["ife_corrected"].sel(sample="s0"))


# --- Raman ---------------------------------------------------------------------

def test_raman_area_exact_for_piecewise_linear_and_off_grid_limits():
    blank = make_ds()["blank_intensity"].copy()
    blank.loc[dict(ex=350.0)] = 2.0 * EM  # linear in em
    area = C.raman_area(blank, ex=350, em_range=(381, 426))
    np.testing.assert_allclose(area, 426 ** 2 - 381 ** 2)  # integral of 2x


def test_raman_area_baseline():
    blank = make_ds()["blank_intensity"].copy()
    blank.loc[dict(ex=350.0)] = 3.0  # flat: nothing above the baseline
    np.testing.assert_allclose(C.raman_area(blank, ex=350, em_range=(381, 426), baseline=True),
                               0, atol=1e-9)
    np.testing.assert_allclose(C.raman_area(blank, ex=350, em_range=(381, 426)), 3 * 45)


def test_raman_area_errors():
    blank = make_ds()["blank_intensity"]
    with pytest.raises(CorrectionError, match="not measured"):
        C.raman_area(blank, ex=355, em_range=(381, 426))
    with pytest.raises(CorrectionError, match="outside"):
        C.raman_area(blank, ex=350, em_range=(200, 426))
    holed = blank.copy()
    holed.loc[dict(ex=350.0, em=400.0)] = np.nan
    with pytest.raises(CorrectionError, match="NaN inside"):
        C.raman_area(holed, ex=350, em_range=(381, 426))


def test_normalize_raman():
    ds = C.subtract_blank(make_ds())
    out = C.normalize_raman(ds, ex=350, em_range=(381, 426))
    np.testing.assert_allclose(out["raman_area"], 45.0)
    np.testing.assert_allclose(out["intensity"], 4.0 / 45.0)
    np.testing.assert_allclose(out["blank_intensity"], 1.0 / 45.0)
    assert out["intensity"].attrs["units"] == "R.U."
    with pytest.raises(CorrectionError, match="before normalize_raman"):
        C.subtract_blank(C.normalize_raman(make_ds(), ex=350, em_range=(381, 426)))


# --- scatter -------------------------------------------------------------------

def test_raman_emission_line():
    assert C.raman_emission(350, 3400) == pytest.approx(1e7 / (1e7 / 350 - 3400))
    assert 396 < C.raman_emission(350, 3400) < 398


def test_scatter_mask_bands():
    m = C.scatter_mask(EX, EM, {"rayleigh1": (10, 10), "rayleigh2": (5, 5)})
    assert bool(m.sel(ex=300, em=300)) and bool(m.sel(ex=300, em=310))
    assert not bool(m.sel(ex=300, em=312))
    assert bool(m.sel(ex=250, em=500)) and not bool(m.sel(ex=250, em=510))
    with pytest.raises(ValueError, match="raman_shift"):
        C.scatter_mask(EX, EM, {"raman1": (5, 5)})
    with pytest.raises(ValueError, match="unknown"):
        C.scatter_mask(EX, EM, {"tyndall": (5, 5)})


def test_remove_scatter_and_zero_region():
    ds = make_ds()
    out = C.remove_scatter(ds, widths={"rayleigh1": (10, 10), "raman1": (8, 8)},
                           raman_shift_cm1=3400, zero_below_rayleigh=10)
    v = out["intensity"].sel(sample="s0")
    assert np.isnan(v.sel(ex=350, em=350)) and np.isnan(v.sel(ex=350, em=398))
    assert v.sel(ex=350, em=330) == 0.0  # below Rayleigh -> zero
    assert v.sel(ex=350, em=450) == 5.0
    assert out["scatter_mask"].dims == ("ex", "em")
    with pytest.raises(CorrectionError, match="before remove_scatter"):
        C.normalize_raman(out, ex=350, em_range=(381, 426))


@pytest.mark.parametrize("method", ["em", "ex", "both"])
def test_interpolate_missing_recovers_a_plane(method):
    ds = make_ds()
    plane = 0.01 * ds["ex"] + 0.02 * ds["em"]
    ds["intensity"] = (ds["intensity"] * 0 + plane).transpose("sample", "ex", "em")
    out = C.remove_scatter(ds, widths={"raman1": (6, 6)}, raman_shift_cm1=3400)
    assert np.isnan(out["intensity"]).any()
    filled = C.interpolate_missing(out, method=method)
    got, want = filled["intensity"].values, ds["intensity"].values
    ok = np.isfinite(got)
    np.testing.assert_allclose(got[ok], want[ok])
    assert (filled["n_interpolated"] > 0).all()
    # along ex, the Raman band at the first excitation (250 nm) has no lower neighbour
    assert (filled["n_still_missing"] > 0).all() if method == "ex" else ok.all()


def test_interpolate_leaves_edge_gaps():
    ds = make_ds()
    out = C.remove_scatter(ds, widths={"rayleigh1": (0, 10)})  # touches em=250 at ex=250
    filled = C.interpolate_missing(out, method="em")
    assert np.isnan(filled["intensity"].sel(ex=250, em=250)).all()
    assert (filled["n_still_missing"] > 0).all()


def test_interpolate_requires_scatter_removal():
    with pytest.raises(CorrectionError, match="remove_scatter"):
        C.interpolate_missing(make_ds(), method="em")


# --- spectral correction and crop ----------------------------------------------

def test_spectral_correction_from_files(write):
    ex_file = write("ex.csv", "Wavelength;Factor\n200;1\n500;4\n")
    em_file = write("em.txt", "200 2\n700 2\n")
    ds = make_ds()
    assert C.spectral_correction_status(ds) == "none"
    out = C.apply_spectral_correction(ds, ex_factors=ex_file, em_factors=em_file)
    # ex factor at 350 = 1 + 3 * 150/300 = 2.5; em factor 2
    np.testing.assert_allclose(out["intensity"].sel(ex=350), 5.0 * 2.5 * 2)
    np.testing.assert_allclose(out["blank_intensity"].sel(ex=350), 1.0 * 2.5 * 2)
    assert C.spectral_correction_status(out).startswith("applied")


def test_spectral_correction_coverage_and_order(write):
    short = (np.array([300.0, 400.0]), np.array([1.0, 1.0]))
    full = (np.array([200.0, 700.0]), np.array([1.0, 1.0]))
    with pytest.raises(CorrectionError, match="cover"):
        C.apply_spectral_correction(make_ds(), ex_factors=short, em_factors=full)
    with pytest.raises(CorrectionError, match="before subtract_blank"):
        C.apply_spectral_correction(C.subtract_blank(make_ds()), ex_factors=full,
                                    em_factors=full)


def test_crop():
    out = C.crop(make_ds(), ex=(300, None), em=(None, 500))
    assert out["ex"].values.tolist() == [300, 350, 400, 450]
    assert out["em"].values.max() == 500
    assert out.sizes["wavelength"] == WL.size
    with pytest.raises(CorrectionError):
        C.crop(make_ds(), ex=(460, 470))


def test_full_recommended_sequence():
    ds = make_ds(absorbance=0.03, blank_abs=0.01)
    ds = C.subtract_absorbance_blank(ds)
    ds = C.correct_inner_filter(ds, absorbance_path_length_cm=1, fluorescence_path_length_cm=1)
    ds = C.subtract_blank(ds)
    ds = C.normalize_raman(ds, ex=350, em_range=(381, 426))
    ds = C.remove_scatter(ds, widths={"rayleigh1": (10, 10)})
    ds = C.crop(ds, ex=(300, 450))
    assert steps(ds)[1:] == ["subtract_absorbance_blank", "correct_inner_filter",
                             "subtract_blank", "normalize_raman", "remove_scatter", "crop"]
    expected = (5.0 * 10 ** 0.02 - 1.0) / 45.0
    assert float(ds["intensity"].sel(sample="s0", ex=400, em=500)) == pytest.approx(expected)
