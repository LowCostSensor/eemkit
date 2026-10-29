"""Smoke tests on a real Cary Eclipse / Cary 60 dataset (skipped without EEMKIT_TEST_DATA).

Every CSV below the root is classified by its first data-row title and read;
the test checks invariants that hold for any well-formed export.
"""

import warnings

import numpy as np
import pytest

from eemkit import mean_cycles, read_cary60, read_cary_eclipse

pytestmark = pytest.mark.realdata


def _csv_files(root, title):
    out = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() != ".csv" or not p.is_file():
            continue
        with open(p, encoding="latin-1") as fh:
            fh.readline()
            if fh.readline().startswith(title):
                out.append(p)
    return out


def test_every_cary_eclipse_file(real_data_root):
    files = _csv_files(real_data_root, "Wavelength (nm),Intensity")
    assert files, "no Cary Eclipse CSV found"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for p in files:
            ds = read_cary_eclipse(p)
            assert ds.sizes["ex"] >= 2 and ds.sizes["em"] >= 2, p
            assert np.all(np.diff(ds.ex) > 0) and np.all(np.diff(ds.em) > 0), p
            assert np.isfinite(ds["intensity"]).mean() > 0.99, p
            assert ds.attrs["instrument"] == "Cary Eclipse", p
            assert not np.isnat(ds.scan_time.values).any(), p


def test_every_cary60_file(real_data_root):
    files = _csv_files(real_data_root, "Wavelength (nm),Abs")
    assert files, "no Cary 60 CSV found"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for p in files:
            ds = mean_cycles(read_cary60(p))
            assert np.all(np.diff(ds.wavelength) > 0), p
            assert np.isfinite(ds["absorbance"]).all(), p
            assert ds.attrs["instrument"] == "Cary 60", p
