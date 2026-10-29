"""Builders for synthetic Cary CSV files that mimic the real exports byte for byte."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

ECLIPSE_PARAMS = {
    "Instrument": "Cary Eclipse",
    "Instrument Serial Number": "MY0000TEST",
    "Data mode": "Fluorescence",
    "Scan mode": "Emission",
    "X Mode": "Wavelength (nm)",
    "Start (nm)": "250.00",
    "Stop (nm)": "600.00",
    "Ex. Wavelength (nm)": "200.00",
    "Ex. Slit (nm)": "5",
    "Em. Slit (nm)": "5",
    "Scan rate (nm/min)": "1200.00",
    "Data interval (nm)": "2.0000",
    "Averaging Time (s)": "0.1000",
    "Excitation filter": "Auto",
    "Emission filter": "Open",
    "PMT voltage (V)": "Medium",
    "Corrected spectra": "OFF",
    "3-D Mode": "ON",
    "Ex.  Stop (nm)": "450.00",
    "Ex.  Increment (nm)": "10.00",
}

CARY60_PARAMS = {
    "Instrument": "Cary 60",
    "Instrument Version": "2.00",
    "Start (nm)": "900.0",
    "Stop (nm)": "200.0",
    "X Mode": "Nanometers",
    "Y Mode": "Abs",
    "UV-Vis Scan Rate (nm/min)": "600.000",
    "UV-Vis Data Interval (nm)": "1.00",
    "UV-Vis Ave. Time (sec)": "0.1000",
    "Beam Mode": "Dual Beam",
    "Baseline Correction": "Off",
    "Cycle Mode": "On",
    "Cycle Count": "3",
    "Cycle Time (min)": "0.00",
}

# Irregular emission axis as exported by the Cary Eclipse (first points of a real file)
EM_IRREGULAR = np.array([250.0, 252.0299988, 254.0599976, 255.9299927, 257.9599915, 260.0])


def _block(label: str, minute: int, params: dict[str, str], pad: int) -> list[str]:
    lines = [f"{label},", label, f"Collection Time: 4/30/2024 10:{minute:02d}:46 AM",
             "Operator Name  :", "Scan Software Version: 1.2(147)", "Parameter List :"]
    # Cary Eclipse pads keys to a column; Cary 60 separates them with exactly two spaces
    lines += [f"{k:<{pad}}{v}" if pad else f"{k}  {v}" for k, v in params.items()]
    lines += ["Method Log     :", r"Method Name    : C:\Users\Test\method",
              "Date/Time stamp: 4/30/2024 10:50:28 AM", "Method Modifications:",
              "Data interval: Changed: 4/30/2024 10:18:29 AM, Old:   1.00, New:   2.00",
              "End Method Modifications", ""]
    return lines


def eclipse_text(
    name: str = "S1",
    ex=(200.0, 210.0, 220.0),
    em=EM_IRREGULAR,
    intensity: np.ndarray | None = None,
    em_per_ex: list[np.ndarray] | None = None,
    log: bool = True,
    params: dict[str, str] | None = None,
    per_scan_params: list[dict[str, str]] | None = None,
) -> str:
    ex = list(ex)
    em_cols = em_per_ex or [np.asarray(em)] * len(ex)
    n = len(em_cols[0])
    if intensity is None:
        intensity = np.add.outer(np.arange(len(ex)) * 100.0, np.arange(n, dtype=float))
    labels = [f"{name}_EX_{e:.2f}" for e in ex]
    out = ["".join(f"{lab},," for lab in labels),
           "Wavelength (nm),Intensity (a.u.)," * len(ex)]
    for i in range(n):
        out.append("".join(f"{em_cols[j][i]:.10g},{intensity[j][i]:.10g},"
                           for j in range(len(ex))))
    out.append("")
    if log:
        for j, lab in enumerate(labels):
            p = dict(ECLIPSE_PARAMS, **(params or {}))
            if per_scan_params:
                p.update(per_scan_params[j])
            out += _block(lab, 59 - len(ex) + j, p, pad=32)
    return "\r\n".join(out) + "\r\n"


def cary60_text(
    name: str = "S1",
    n_cycles: int = 3,
    wl: np.ndarray | None = None,
    absorbance: np.ndarray | None = None,
    log: bool = True,
    params: dict[str, str] | None = None,
    y_title: str = "Abs",
) -> str:
    if wl is None:
        wl = np.arange(900, 199, -1) + 0.0048 * np.sin(np.arange(701))
    if absorbance is None:
        base = 0.05 + 2.0 * np.exp(-0.015 * (np.asarray(wl) - 200))
        absorbance = np.vstack([base + 0.001 * k for k in range(n_cycles)])
    labels = [f"{name}_{k + 1}" for k in range(n_cycles)]
    out = ["".join(f"{lab},," for lab in labels).removesuffix(","),
           f"Wavelength (nm),{y_title}," * n_cycles]
    for i, w in enumerate(wl):
        out.append("".join(f"{w:.10g},{absorbance[k][i]:.10g}," for k in range(n_cycles)))
    out.append("")
    if log:
        for k, lab in enumerate(labels):
            out += _block(lab, 10 + k, dict(CARY60_PARAMS, **(params or {})), pad=0)
    return "\r\n".join(out) + "\r\n"


@pytest.fixture
def write(tmp_path: Path):
    """write(name, text, encoding='utf-8') -> Path"""

    def _write(name: str, text: str, encoding: str = "utf-8") -> Path:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode(encoding))
        return p

    return _write


@pytest.fixture
def real_data_root() -> Path:
    root = os.environ.get("EEMKIT_TEST_DATA")
    if not root or not Path(root).is_dir():
        pytest.skip("set EEMKIT_TEST_DATA to the real dataset root to run this test")
    return Path(root)
