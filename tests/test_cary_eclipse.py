import numpy as np
import pytest

from eemkit import EEMKitWarning, FileFormatError, get_history, read_cary_eclipse
from tests.conftest import EM_IRREGULAR, eclipse_text


def test_reads_values_axes_and_metadata(write):
    ds = read_cary_eclipse(write("S1.csv", eclipse_text()))
    assert ds["intensity"].dims == ("ex", "em")
    np.testing.assert_allclose(ds.ex, [200, 210, 220])
    np.testing.assert_allclose(ds.em, EM_IRREGULAR, rtol=0, atol=1e-6)
    assert ds["intensity"].sel(ex=210).values[3] == 103.0
    a = ds.attrs
    assert a["sample_name"] == "S1"
    assert a["instrument"] == "Cary Eclipse"
    assert (a["ex_slit_nm"], a["em_slit_nm"], a["pmt_voltage"]) == ("5", "5", "Medium")
    assert a["corrected_spectra"] == "OFF"
    assert a["data_interval_nm"] == "2.0000"
    assert a["collection_start"] == "2024-04-30T10:56:46"
    assert a["collection_end"] == "2024-04-30T10:58:46"
    assert ds.scan_time.dtype.kind == "M"
    assert get_history(ds)[0]["step"] == "read_cary_eclipse"


def test_excitations_sorted_whatever_the_file_order(write):
    inten = np.array([[1.0] * 6, [2.0] * 6, [3.0] * 6])
    ds = read_cary_eclipse(write("S.csv", eclipse_text(ex=(220, 200, 210), intensity=inten)))
    np.testing.assert_allclose(ds.ex, [200, 210, 220])
    np.testing.assert_allclose(ds["intensity"].values[:, 0], [2, 3, 1])
    t = ds.scan_time.values  # 220 nm was scanned first, then 200, then 210
    assert t[2] < t[0] < t[1]


def test_resampling_at_read_time(write):
    ds = read_cary_eclipse(write("S.csv", eclipse_text()), em_grid=np.arange(250, 262, 2.0))
    np.testing.assert_allclose(ds.em, [250, 252, 254, 256, 258, 260])
    # intensity is linear in the point index, so check against interpolation of the index
    expected = np.interp([250, 252, 254, 256, 258, 260], EM_IRREGULAR, np.arange(6.0))
    np.testing.assert_allclose(ds["intensity"].sel(ex=200), expected)


def test_emission_axis_differing_between_scans(write):
    em2 = EM_IRREGULAR + 0.5
    text = eclipse_text(ex=(200, 210), em_per_ex=[EM_IRREGULAR, em2])
    path = write("S.csv", text)
    with pytest.raises(FileFormatError, match="em_grid"):
        read_cary_eclipse(path)
    ds = read_cary_eclipse(path, em_grid=np.arange(252, 260, 2.0))
    assert np.isfinite(ds["intensity"]).all()


def test_grid_outside_measured_range_is_nan(write):
    ds = read_cary_eclipse(write("S.csv", eclipse_text()), em_grid=np.array([240.0, 250.05, 262]))
    v = ds["intensity"].sel(ex=200).values
    assert np.isnan(v[0]) and np.isfinite(v[1]) and np.isnan(v[2])


def test_trailing_empty_cells_become_nan(write):
    text = eclipse_text(ex=(200, 210)).replace("260,5,260,105,", "260,5,260,,")
    ds = read_cary_eclipse(write("S.csv", text))
    assert np.isnan(ds["intensity"].sel(ex=210).values[-1])


def test_non_numeric_cell_is_an_error(write):
    text = eclipse_text().replace("252.0299988,1,", "252.0299988,abc,", 1)
    with pytest.raises(FileFormatError, match="not a number"):
        read_cary_eclipse(write("S.csv", text))


@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp1252"])
def test_encodings(write, encoding):
    ds = read_cary_eclipse(write("S.csv", eclipse_text(name="Campione è"), encoding))
    assert ds.attrs["sample_name"] == "Campione è"


def test_header_name_differs_from_file_name_is_kept_not_fixed(write):
    ds = read_cary_eclipse(write("FARMA 32.csv", eclipse_text(name="FARMA 33")))
    assert ds.attrs["sample_name"] == "FARMA 33"
    assert ds.attrs["source_file"].endswith("FARMA 32.csv")


def test_missing_log_warns_but_reads(write):
    with pytest.warns(EEMKitWarning, match="no log block"):
        ds = read_cary_eclipse(write("S.csv", eclipse_text(log=False)))
    assert "instrument" not in ds.attrs
    assert np.isnat(ds.scan_time.values).all()


def test_parameter_changing_between_scans_warns(write):
    text = eclipse_text(per_scan_params=[{}, {"PMT voltage (V)": "High"}, {}])
    with pytest.warns(EEMKitWarning, match="PMT voltage"):
        ds = read_cary_eclipse(write("S.csv", text))
    assert ds.attrs["pmt_voltage"] == "Medium|High"


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda t: t.replace("S1_EX_210.00", "S2_EX_210.00", 2), "several sample names"),
        (lambda t: t.replace("S1_EX_210.00", "S1_EX_200.00", 2), "duplicated excitation"),
        (lambda t: t.replace("S1_EX_210.00", "S1_210", 2), "<sample>_EX_<nm>"),
        (lambda t: t.replace("Intensity (a.u.)", "Abs", 1), "column titles"),
        (lambda t: t.split("\r\n", 2)[0] + "\r\n", "too short"),
        (lambda t: "\r\n".join(t.split("\r\n")[:2]) + "\r\n\r\nx\r\n", "no data rows"),
        (lambda t: t.replace("250,0,", "250,0,250,1,", 1), "more values"),
        (lambda t: t.replace("Fluorescence", "Phosphorescence"), "not a fluorescence"),
    ],
)
def test_malformed_files(write, mutate, match):
    with pytest.raises(FileFormatError, match=match):
        read_cary_eclipse(write("S.csv", mutate(eclipse_text())))
