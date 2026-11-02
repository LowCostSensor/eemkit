import numpy as np
import pytest
from conftest import cary60_text

from eemkit import EEMKitWarning, FileFormatError, get_history, mean_cycles, read_cary60


def test_reads_cycles_ascending_and_metadata(write):
    ds = read_cary60(write("A.csv", cary60_text()))
    assert ds["absorbance"].dims == ("cycle", "wavelength")
    assert ds.sizes == {"cycle": 3, "wavelength": 701}
    assert np.all(np.diff(ds.wavelength) > 0)
    assert ds.wavelength[0] == pytest.approx(200, abs=0.01)
    a = ds.attrs
    assert (a["instrument"], a["beam_mode"], a["baseline_correction"]) == \
        ("Cary 60", "Dual Beam", "Off")
    assert a["cycle_count"] == "3"
    # the file is written from 900 nm down; the first data row must end up last
    assert ds["absorbance"].values[0, -1] == pytest.approx(0.05 + 2 * np.exp(-0.015 * 700),
                                                          abs=1e-4)


def test_mean_cycles(write):
    ds = mean_cycles(read_cary60(write("A.csv", cary60_text())))
    assert ds["absorbance"].dims == ("wavelength",)
    np.testing.assert_allclose(ds["absorbance_sd"], 0.001, rtol=1e-6)
    assert ds.attrs["n_cycles"] == 3
    assert [h["step"] for h in get_history(ds)] == ["read_cary60", "mean_cycles"]


def test_single_cycle_has_nan_sd(write):
    with pytest.warns(EEMKitWarning, match="log says 3 cycles"):
        ds = mean_cycles(read_cary60(write("A.csv", cary60_text(n_cycles=1))))
    assert np.isnan(ds["absorbance_sd"]).all()


def test_wavelength_axis_differing_between_cycles(write):
    text = cary60_text()
    lines = text.split("\r\n")
    toks = lines[2].split(",")
    toks[2] = "901"
    lines[2] = ",".join(toks)
    with pytest.raises(FileFormatError, match="differs between cycles"):
        read_cary60(write("A.csv", "\r\n".join(lines)))


def test_not_absorbance_mode(write):
    with pytest.raises(FileFormatError, match="absorbance mode"):
        read_cary60(write("A.csv", cary60_text(y_title="%T")))


def test_eclipse_file_is_rejected(write):
    from conftest import eclipse_text

    with pytest.raises(FileFormatError):
        read_cary60(write("A.csv", eclipse_text()))
