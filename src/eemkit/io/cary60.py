"""Reader for Agilent Cary 60 UV-Vis absorbance CSV exports."""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import xarray as xr

from eemkit.core.history import with_history
from eemkit.errors import EEMKitWarning, FileFormatError
from eemkit.io._cary_csv import common_params, parse_cary_csv, scan_times, time_attrs

LABEL_RE = re.compile(r"^(?P<name>.*)_(?P<cycle>[0-9]+)$")

LOG_PARAMS = {
    "instrument": "Instrument",
    "start_nm": "Start (nm)",
    "stop_nm": "Stop (nm)",
    "y_mode": "Y Mode",
    "scan_rate_nm_per_min": "UV-Vis Scan Rate (nm/min)",
    "data_interval_nm": "UV-Vis Data Interval (nm)",
    "averaging_time_s": "UV-Vis Ave. Time (sec)",
    "beam_mode": "Beam Mode",
    "baseline_correction": "Baseline Correction",
    "cycle_mode": "Cycle Mode",
    "cycle_count": "Cycle Count",
}


def read_cary60(path: str | Path) -> xr.Dataset:
    """Read one absorbance measurement (one or more cycles) from a Cary 60 CSV.

    Returns
    -------
    xarray.Dataset
        ``absorbance`` with dims ``(cycle, wavelength)``, wavelength ascending
        (the instrument scans downwards), coordinate ``scan_time(cycle)`` and
        the instrument settings as attributes. Values are as exported: no
        blank subtraction, baseline or path-length normalisation.
    """
    path = Path(path)
    raw = parse_cary_csv(path)

    names, cycles = [], []
    for lab in raw.labels:
        m = LABEL_RE.match(lab)
        if not m:
            raise FileFormatError(f"{path}: column label {lab!r} is not '<sample>_<cycle>'")
        names.append(m.group("name"))
        cycles.append(int(m.group("cycle")))
    if len(set(names)) > 1:
        raise FileFormatError(f"{path}: several sample names in one file: {sorted(set(names))}")
    if len(set(cycles)) != len(cycles):
        raise FileFormatError(f"{path}: duplicated cycle numbers")
    if raw.titles[:2] != ["Wavelength (nm)", "Abs"]:
        raise FileFormatError(f"{path}: unexpected column titles {raw.titles[:2]} "
                              "(expected absorbance mode)")

    x, y = raw.x, raw.y
    keep = ~np.all(np.isnan(x), axis=1)
    x, y = x[keep], y[keep]
    wl = x[:, 0]
    if np.isnan(wl).any() or not np.allclose(x, wl[:, None], atol=1e-6, equal_nan=True):
        raise FileFormatError(f"{path}: the wavelength axis differs between cycles")
    order = np.argsort(wl)
    wl, absorb = wl[order], y[order].T
    if np.any(np.diff(wl) <= 0):
        raise FileFormatError(f"{path}: repeated wavelengths")

    logs = [raw.log_for(lab) for lab in raw.labels]
    present = [lg for lg in logs if lg is not None]
    if len(present) < len(logs):
        warnings.warn(f"{path.name}: no log block for {len(logs) - len(present)} cycle(s)",
                      EEMKitWarning, stacklevel=2)
    times = scan_times(logs)
    attrs = {
        "sample_name": names[0],
        "source_file": str(path),
        "file_format": "Cary 60 CSV (ASCII with log)",
        **common_params(path, present, LOG_PARAMS),
        **time_attrs(times),
        "method_name": "|".join(dict.fromkeys(lg.method_name for lg in present)),
    }
    if "cycle_count" in attrs and attrs["cycle_count"] != str(len(cycles)):
        warnings.warn(f"{path.name}: log says {attrs['cycle_count']} cycles, "
                      f"file contains {len(cycles)}", EEMKitWarning, stacklevel=2)

    ds = xr.Dataset(
        {"absorbance": (("cycle", "wavelength"), absorb,
                        {"units": "1", "long_name": "absorbance (decadic)"})},
        coords={
            "cycle": ("cycle", np.asarray(cycles)),
            "wavelength": ("wavelength", wl, {"units": "nm", "long_name": "wavelength"}),
            "scan_time": ("cycle", times),
        },
        attrs=attrs,
    )
    return with_history(ds, "read_cary60")


def mean_cycles(ds: xr.Dataset) -> xr.Dataset:
    """Average repeated cycles: returns ``absorbance`` and ``absorbance_sd`` (wavelength).

    The standard deviation uses ``ddof=1`` and is NaN for a single cycle.
    """
    a = ds["absorbance"]
    n = a.sizes["cycle"]
    out = xr.Dataset(
        {
            "absorbance": a.mean("cycle").assign_attrs(a.attrs),
            "absorbance_sd": (a.std("cycle", ddof=1) if n > 1
                              else xr.full_like(a.isel(cycle=0, drop=True), np.nan))
            .assign_attrs(units="1", long_name="standard deviation between cycles"),
        },
        attrs=dict(ds.attrs, n_cycles=n),
    )
    return with_history(out, "mean_cycles", n_cycles=n)
