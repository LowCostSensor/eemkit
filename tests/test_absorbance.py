"""CDOM metrics on synthetic exponential spectra with known slopes."""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from eemkit.absorbance import (
    LN10,
    baseline_corrected,
    compute_absorbance_metrics,
    spectral_slope,
)
from eemkit.core.history import with_history
from eemkit.errors import EEMKitWarning, IndexComputationError

WL = np.arange(200.0, 801.0)
L_CM = 1.0


def _absorbance(a350: float, s: float, offset: float = 0.0) -> np.ndarray:
    """Decadic absorbance in a 1 cm cell of a(lambda) = a350 exp(-s (lambda - 350)) m^-1."""
    a = a350 * np.exp(-s * (WL - 350.0))
    return a * (L_CM / 100) / LN10 + offset


def _dataset(spectra: list[np.ndarray], doc=None, blank_done: bool = True) -> xr.Dataset:
    ds = xr.Dataset({"absorbance": (("sample", "wavelength"), np.array(spectra))},
                    coords={"sample": [f"S{i}" for i in range(len(spectra))], "wavelength": WL})
    if doc is not None:
        ds = ds.assign_coords(DOC=("sample", np.array(doc, dtype=object)))
    return with_history(ds, "subtract_absorbance_blank") if blank_done else ds


def test_known_spectrum_gives_known_metrics():
    ds = _dataset([_absorbance(2.0, 0.02, offset=0.004)])
    df = compute_absorbance_metrics(ds, absorbance_path_length_cm=L_CM)
    row = df.iloc[0]
    # the 680-700 nm baseline removes the offset; the residual exponential there is ~1e-5
    assert row["a350"] == pytest.approx(2.0, rel=2e-3)
    assert row["a254"] == pytest.approx(2.0 * np.exp(0.02 * 96), rel=2e-3)
    assert row["S275_295"] == pytest.approx(0.02, rel=1e-3)
    assert row["S350_400"] == pytest.approx(0.02, rel=1e-2)
    assert row["SR"] == pytest.approx(1.0, rel=1e-2)
    assert row["E2_E3"] == pytest.approx(np.exp(0.02 * 115), rel=1e-2)
    assert row["cdom_notes"] == "" and "SUVA254" not in df
    assert df.attrs["settings"]["baseline_nm"] == [680.0, 700.0]


def test_without_baseline_correction_an_offset_biases_the_slope():
    ds = _dataset([_absorbance(2.0, 0.02, offset=0.004)])
    off = compute_absorbance_metrics(ds, absorbance_path_length_cm=L_CM, baseline=None)
    assert off["S350_400"].iloc[0] < 0.019


def test_low_signal_is_empty_with_a_reason():
    rng = np.random.default_rng(0)
    weak = 0.0005 * rng.standard_normal(WL.size)  # noise only
    ds = _dataset([_absorbance(2.0, 0.02), weak])
    with pytest.warns(EEMKitWarning, match="1 sample"):
        df = compute_absorbance_metrics(ds, absorbance_path_length_cm=L_CM)
    bad = df.loc["S1"]
    assert np.isnan(bad["S350_400"]) and np.isnan(bad["SR"])
    assert "S350_400" in bad["cdom_notes"]
    assert df.loc["S0", "cdom_notes"] == ""


def test_r2_threshold_is_applied():
    a = 2.0 * np.exp(-0.02 * (WL - 350.0))
    a_noisy = a * (1 + 0.2 * np.sin(WL / 3.0))
    s, r2, note = spectral_slope(a_noisy, WL, 350, 400, min_r2=0.99)
    assert np.isnan(s) and r2 < 0.99 and "R2" in note
    s, r2, note = spectral_slope(a, WL, 350, 400, min_r2=0.99)
    assert s == pytest.approx(0.02) and note == ""


def test_suva_needs_doc_and_uses_decadic_absorbance():
    ds = _dataset([_absorbance(2.0, 0.02), _absorbance(2.0, 0.02)], doc=["2,5", ""])
    with pytest.warns(EEMKitWarning):
        df = compute_absorbance_metrics(ds, absorbance_path_length_cm=L_CM, doc="DOC")
    a254_decadic_per_m = df.loc["S0", "a254"] / LN10
    assert df.loc["S0", "SUVA254"] == pytest.approx(a254_decadic_per_m / 2.5, rel=1e-3)
    assert np.isnan(df.loc["S1", "SUVA254"]) and "DOC" in df.loc["S1", "cdom_notes"]


def test_refuses_without_blank_or_path_length():
    ds = _dataset([_absorbance(2.0, 0.02)], blank_done=False)
    with pytest.raises(IndexComputationError, match="blank"):
        compute_absorbance_metrics(ds, absorbance_path_length_cm=L_CM)
    ds = _dataset([_absorbance(2.0, 0.02)])
    with pytest.raises(IndexComputationError, match="path_length"):
        compute_absorbance_metrics(ds, absorbance_path_length_cm=0)
    with pytest.raises(IndexComputationError, match="baseline"):
        baseline_corrected(ds["absorbance"], (900.0, 950.0))
