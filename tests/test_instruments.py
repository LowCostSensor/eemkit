"""Readers for other fluorometers (example files of the R package eemR) and the
'already done by the instrument' rule."""

import shutil
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from eemkit import EEMKitWarning, pipeline
from eemkit.core.history import get_history
from eemkit.errors import FileFormatError, SettingsError
from eemkit.io import instruments as I
from eemkit.io.discover import scan_folder

DATA = Path(__file__).parent / "data" / "eemR"


# --------------------------------------------------------------------------- #
# Readers
# --------------------------------------------------------------------------- #

def test_aqualog_reads_orientation_and_processing():
    ds = I.read_aqualog(DATA / "aqualog" / "sample4.dat")
    assert ds.sizes == {"ex": 113, "em": 250}
    assert float(ds.ex[0]) == 240 and float(ds.ex[-1]) == 800  # ascending, file is descending
    # first data row of the file: em 245.719, first column = ex 800
    assert float(ds.intensity.sel(ex=800, em=245.719)) == pytest.approx(-0.943302431047735)
    assert ds.attrs["instrument_processing"] == "Sample - Blank; Normalized by 75.335"
    assert ds.attrs["instrument_steps"] == "blank"
    assert "corrected_spectra" not in ds.attrs


def test_fluoromax():
    ds = I.read_fluoromax(DATA / "fluoromax4" / "f1.dat")
    assert ds.sizes == {"ex": 43, "em": 116}
    assert float(ds.intensity.sel(ex=240, em=320)) == pytest.approx(5665.56186)
    assert "instrument_steps" not in ds.attrs


def test_hitachi_saturation_and_header():
    with pytest.warns(EEMKitWarning, match="289 saturated"):
        ds = I.read_hitachi_f7000(DATA / "hitachi-f7000-fl" / "hitachi1.TXT")
    assert ds.sizes == {"ex": 51, "em": 176}
    assert int(ds.intensity.isnull().sum()) == 289 == ds.attrs["n_saturated"]
    assert float(ds.intensity.sel(ex=200, em=250)) == pytest.approx(140.4)
    assert ds.attrs["corrected_spectra"] == "On" and ds.attrs["ex_slit_nm"] == "5.0"
    assert ds.attrs["pmt_voltage"] == "700"
    assert "operator" not in " ".join(ds.attrs).lower()  # no personal names copied


def test_shimadzu_needs_the_excitation_wavelengths():
    path = DATA / "shimadzu" / "shimadzu.TXT"
    with pytest.raises(FileFormatError, match="ex_start"):
        I.read_shimadzu(path, ex_start=None, ex_step=None)
    ds = I.read_shimadzu(path, ex_start=220, ex_step=5)
    assert ds.sizes == {"ex": 45, "em": 181}
    assert float(ds.ex[-1]) == 440 and float(ds.intensity.sel(ex=220, em=240)) == 0.000023


@pytest.mark.parametrize("sep", [",", ";", "\t"])
def test_matrix_csv_both_orientations(tmp_path, sep):
    ex, em = np.array([250.0, 260.0, 270.0]), np.array([300.0, 310.0])
    vals = np.arange(6.0).reshape(2, 3)  # (em, ex)
    lines = [sep.join(["em/ex"] + [f"{x:g}" for x in ex])]
    lines += [sep.join([f"{w:g}"] + [f"{v:g}" for v in row]) for w, row in zip(em, vals,
                                                                                 strict=True)]
    p = tmp_path / "m.csv"
    p.write_text("\n".join(lines))
    ds = I.read_matrix_csv(p)
    assert float(ds.intensity.sel(ex=270, em=300)) == 2.0
    q = tmp_path / "t.csv"  # the transpose: excitation in rows
    lines = [sep.join(["ex/em"] + [f"{w:g}" for w in em])]
    lines += [sep.join([f"{x:g}"] + [f"{v:g}" for v in vals[:, j]]) for j, x in enumerate(ex)]
    q.write_text("\n".join(lines))
    dt = I.read_matrix_csv(q, orientation="ex_rows")
    np.testing.assert_array_equal(dt.intensity.values, ds.intensity.values)


def test_two_column_absorbance(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Sample A\nnm;Abs\n" + "\n".join(f"{w};{0.01 * (700 - w) / 100:.4f}"
                                                   for w in range(700, 199, -1)))
    ds = I.read_two_column_absorbance(p)
    assert ds.sizes == {"cycle": 1, "wavelength": 501}
    assert float(ds.wavelength[0]) == 200 and float(ds.absorbance.sel(wavelength=254)[0]) \
        == pytest.approx(0.0446)
    p.write_text("200 0.1\n200 0.2\n")
    with pytest.raises(FileFormatError, match="repeated"):
        I.read_two_column_absorbance(p)


def test_wrong_format_is_refused():
    with pytest.raises(FileFormatError):
        I.read_hitachi_f7000(DATA / "fluoromax4" / "f1.dat")
    with pytest.raises(FileFormatError):
        I.read_shimadzu(DATA / "fluoromax4" / "f1.dat", ex_start=240, ex_step=5)


# --------------------------------------------------------------------------- #
# A small Aqualog project through the pipeline
# --------------------------------------------------------------------------- #

def _abs_text(scale: float) -> str:
    return "\n".join(f"{w}\t{scale * np.exp(-0.015 * (w - 200)):.6f}" for w in range(200, 901))


@pytest.fixture
def aqualog_project(tmp_path):
    data = tmp_path / "data"
    (data / "eem").mkdir(parents=True)
    (data / "abs").mkdir()
    for name in ("A", "B"):
        shutil.copy(DATA / "aqualog" / "sample4.dat", data / "eem" / f"{name}.dat")
        (data / "abs" / f"{name}.txt").write_text(_abs_text(0.2 if name == "A" else 0.3))
    (data / "abs" / "blank.txt").write_text(_abs_text(0.0))
    pd.DataFrame({"sample_id": ["A", "B"], "include": ["yes", "yes"],
                  "eem_file": ["eem/A.dat", "eem/B.dat"], "eem_blank_file": ["", ""],
                  "abs_file": ["abs/A.txt", "abs/B.txt"],
                  "abs_blank_file": ["abs/blank.txt"] * 2}).to_csv(tmp_path / "pairing.csv",
                                                                   index=False)
    s = pipeline.default_settings()
    s["project"].update(data_root=str(data), pairing=str(tmp_path / "pairing.csv"),
                        instrument="aqualog", absorbance_format="two_column")
    s["inner_filter"].update(absorbance_path_length_cm=1.0, fluorescence_path_length_cm=1.0)
    return s, data, tmp_path


def test_aqualog_blank_already_subtracted_must_be_declared(aqualog_project):
    s, *_ = aqualog_project
    raw = pipeline.load(s)
    assert raw.attrs["spectral_correction"].startswith("unknown")
    with pytest.raises(SettingsError, match=r"already did: 'blank' in 2 file\(s\)"):
        pipeline.correct_until_raman(raw, s)
    s["project"]["already_done"] = ["blank"]
    with pytest.raises(SettingsError, match="add 'raman'"):
        pipeline.correct_until_raman(raw, s)
    s["project"]["already_done"] = ["blank", "spectral"]
    with pytest.raises(SettingsError, match="unknown step"):
        pipeline.correct_until_raman(raw, s)


def test_aqualog_declared_steps_are_recorded_not_repeated(aqualog_project):
    s, *_ = aqualog_project
    s["project"]["already_done"] = ["blank", "raman"]
    raw = pipeline.load(s)
    with pytest.warns(EEMKitWarning, match="subtracted the blank before"):
        after = pipeline.correct_until_raman(raw, s)
    hist = {e["step"]: e["params"] for e in get_history(after)}
    assert hist["subtract_blank"]["done_by"] == "instrument software"
    assert "Sample - Blank" in hist["subtract_blank"]["file_header"]
    assert hist["normalize_raman"]["done_by"] == "instrument software"
    assert "done_by" not in hist["correct_inner_filter"]  # eemkit did this one
    assert after.intensity.attrs["units"] == "R.U. (instrument software)"
    expected = raw.intensity * after.ife_factor
    np.testing.assert_allclose(after.intensity, expected)  # only the inner filter applied
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cdom = pipeline.compute_absorbance(after, s)
    assert cdom.loc["B", "a254"] > cdom.loc["A", "a254"] > 0


def test_declared_blank_with_paired_blank_is_an_error(aqualog_project):
    s, data, tmp = aqualog_project
    table = pd.read_csv(tmp / "pairing.csv", dtype=str, keep_default_na=False)
    table["eem_blank_file"] = "eem/A.dat"
    table.to_csv(tmp / "pairing.csv", index=False)
    s["project"]["already_done"] = ["blank", "raman"]
    with pytest.raises(SettingsError, match="blank files are paired"):
        pipeline.correct_until_raman(pipeline.load(s), s)


def test_scan_folder_with_another_instrument(aqualog_project):
    s, data, _ = aqualog_project
    inv = scan_folder(data, instrument="aqualog", absorbance_format="two_column")
    kinds = dict(zip(inv["file"], inv["kind"], strict=True))
    assert kinds == {"abs/A.txt": "absorbance", "abs/B.txt": "absorbance",
                     "abs/blank.txt": "absorbance", "eem/A.dat": "eem", "eem/B.dat": "eem"}
    assert bool(inv.set_index("file").loc["abs/blank.txt", "is_blank"])


def test_shimadzu_settings_are_required():
    s = pipeline.default_settings()
    s["project"]["instrument"] = "shimadzu"
    with pytest.raises(SettingsError, match="shimadzu.ex_start"):
        pipeline.reader_options(s)
    s["shimadzu"].update(ex_start=220, ex_step=5)
    assert pipeline.reader_options(s) == {"ex_start": 220.0, "ex_step": 5.0}
