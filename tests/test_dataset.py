import numpy as np
import pytest
import xarray as xr

from eemkit import GridError, get_history, load_dataset, read_cary_eclipse, stack
from tests.conftest import cary60_text, eclipse_text

EM_1NM = np.arange(250.0, 260.01, 1.03)


@pytest.fixture
def project(write, tmp_path):
    write("fl/S1.csv", eclipse_text("S1"))
    write("fl/S2.csv", eclipse_text("S2", intensity=np.full((3, 6), 7.0)))
    write("fl/S3.csv", eclipse_text("S3", em=EM_1NM))  # finer, slightly shorter axis
    write("fl/Blank.csv", eclipse_text("Blank", intensity=np.ones((3, 6))))
    write("ab/S1.csv", cary60_text("S1"))
    write("ab/S2.csv", cary60_text("S2"))
    write("ab/Blank.csv", cary60_text("Blank", absorbance=np.full((3, 701), 0.04)))
    return write("pairing.csv", "\n".join([
        "sample_id,eem_file,eem_blank_file,abs_file,abs_blank_file,include,river,site",
        "A,fl/S1.csv,fl/Blank.csv,ab/S1.csv,ab/Blank.csv,yes,Merse,1",
        "B,fl/S2.csv,fl/Blank.csv,ab/S2.csv,ab/Blank.csv,yes,Merse,2",
        "C,fl/S3.csv,,,,yes,Orcia,1bis",
        "D,fl/S1.csv,,,,no,Orcia,9",
    ]))


def test_load_dataset_structure(project):
    ds = load_dataset(project)
    assert list(ds.sample.values) == ["A", "B", "C"]
    assert ds["intensity"].dims == ("sample", "ex", "em")
    # common grid: coarsest step (2 nm) over the overlap of all axes (S3 stops at 259.27)
    np.testing.assert_allclose(ds.em, [250, 252, 254, 256, 258])
    assert ds["blank_intensity"].sel(sample="A").mean() == 1.0
    assert np.isnan(ds["blank_intensity"].sel(sample="C")).all()
    assert np.isnan(ds["absorbance"].sel(sample="C")).all()
    assert ds["blank_absorbance"].sel(sample="B").values[0] == pytest.approx(0.04)
    assert ds.sizes["wavelength"] == 701 and ds.wavelength[0] == 200
    assert list(ds.river.values) == ["Merse", "Merse", "Orcia"]
    assert list(ds.eem_sample_name.values) == ["S1", "S2", "S3"]
    assert ds.attrs["eem_instrument"] == "Cary Eclipse"
    assert ds.attrs["abs_instrument"] == "Cary 60"
    assert ds.attrs["eem_corrected_spectra"] == "OFF"
    assert ds.eem_scan_time.dims == ("sample", "ex")
    assert "scan_time" not in ds.coords  # only the per-sample, prefixed version


def test_load_dataset_history(project):
    ds = load_dataset(project)
    steps = [h["step"] for h in get_history(ds)]
    assert steps == ["read_cary_eclipse", "resample", "load_dataset"]
    params = get_history(ds)[-1]["params"]
    assert params["em_grid"] == {"start": 250.0, "stop": 258.0, "n": 5, "step": 2.0}
    assert params["em_grid_inferred"] is True
    assert params["n_with_eem_blank"] == 2


def test_explicit_grids(project):
    ds = load_dataset(project, em_grid=np.array([251.0, 255.0]),
                      wavelength_grid=np.arange(250.0, 451.0, 50))
    np.testing.assert_allclose(ds.em, [251, 255])
    assert ds.sizes["wavelength"] == 5
    assert get_history(ds)[-1]["params"]["em_grid_inferred"] is False


def test_netcdf_round_trip(project, tmp_path):
    ds = load_dataset(project)
    path = tmp_path / "ds.nc"
    ds.to_netcdf(path, engine="scipy")
    back = xr.load_dataset(path, engine="scipy")
    xr.testing.assert_allclose(back["intensity"], ds["intensity"])
    assert get_history(back) == get_history(ds)
    assert list(back.river.values) == ["Merse", "Merse", "Orcia"]


def test_stack_rejects_different_grids(write):
    a = read_cary_eclipse(write("a.csv", eclipse_text("a")))
    b = read_cary_eclipse(write("b.csv", eclipse_text("b", em=EM_1NM)))
    with pytest.raises(GridError, match="common grid"):
        stack([a, b], ["a", "b"])


def test_stack_with_missing_item_and_varying_attrs(write):
    a = read_cary_eclipse(write("a.csv", eclipse_text("a")))
    b = read_cary_eclipse(write("b.csv", eclipse_text("b", params={"PMT voltage (V)": "High"})))
    ds = stack([a, None, b], ["a", "x", "b"], prefix="eem_")
    assert np.isnan(ds["intensity"].sel(sample="x")).all()
    assert list(ds.eem_pmt_voltage.values) == ["Medium", "", "High"]
    assert ds.attrs["eem_instrument"] == "Cary Eclipse"
    assert np.isnat(ds.eem_scan_time.sel(sample="x")).all()


def test_excitation_mismatch_is_an_error(write):
    write("fl/S1.csv", eclipse_text("S1"))
    write("fl/S2.csv", eclipse_text("S2", ex=(200, 210, 230)))
    p = write("pairing.csv", "sample_id,eem_file,include\nA,fl/S1.csv,yes\nB,fl/S2.csv,yes\n")
    with pytest.raises(GridError, match="excitation"):
        load_dataset(p)
