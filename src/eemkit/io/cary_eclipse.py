"""Reader for Agilent Cary Eclipse 3-D (EEM) CSV exports."""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import xarray as xr

from eemkit.core.grid import DEFAULT_TOLERANCE, interp_on_grid
from eemkit.core.history import with_history
from eemkit.errors import EEMKitWarning, FileFormatError
from eemkit.io._cary_csv import common_params, parse_cary_csv, scan_times, time_attrs

LABEL_RE = re.compile(r"^(?P<name>.*)_EX_(?P<ex>[0-9]+(?:\.[0-9]+)?)$")

#: dataset attribute -> key in the 'Parameter List' of the scan log
LOG_PARAMS = {
    "instrument": "Instrument",
    "instrument_serial": "Instrument Serial Number",
    "data_mode": "Data mode",
    "scan_mode": "Scan mode",
    "em_start_nm": "Start (nm)",
    "em_stop_nm": "Stop (nm)",
    "ex_slit_nm": "Ex. Slit (nm)",
    "em_slit_nm": "Em. Slit (nm)",
    "scan_rate_nm_per_min": "Scan rate (nm/min)",
    "data_interval_nm": "Data interval (nm)",
    "averaging_time_s": "Averaging Time (s)",
    "ex_filter": "Excitation filter",
    "em_filter": "Emission filter",
    "pmt_voltage": "PMT voltage (V)",
    "corrected_spectra": "Corrected spectra",
}


def read_cary_eclipse(
    path: str | Path,
    em_grid: np.ndarray | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> xr.Dataset:
    """Read one EEM exported by the Cary Eclipse software as CSV with log.

    Parameters
    ----------
    path
        CSV file with one emission scan per excitation wavelength.
    em_grid
        If given, each emission scan is linearly interpolated onto this grid
        (nm). If omitted, the native emission axis is kept, which requires all
        scans of the file to share it.
    tolerance
        See :func:`eemkit.core.grid.interp_on_grid`; used only with ``em_grid``.

    Returns
    -------
    xarray.Dataset
        ``intensity`` with dims ``(ex, em)`` in instrument units, coordinate
        ``scan_time(ex)`` and the instrument settings as attributes. Values
        are exactly as exported: no correction of any kind is applied.
    """
    path = Path(path)
    raw = parse_cary_csv(path)

    names, ex = [], []
    for lab in raw.labels:
        m = LABEL_RE.match(lab)
        if not m:
            raise FileFormatError(
                f"{path}: column label {lab!r} is not '<sample>_EX_<nm>'; "
                "is this a Cary Eclipse 3-D scan?"
            )
        names.append(m.group("name"))
        ex.append(float(m.group("ex")))
    if len(set(names)) > 1:
        raise FileFormatError(f"{path}: several sample names in one file: {sorted(set(names))}")
    if len(set(ex)) != len(ex):
        raise FileFormatError(f"{path}: duplicated excitation wavelengths")
    if raw.titles[:2] != ["Wavelength (nm)", "Intensity (a.u.)"]:
        raise FileFormatError(f"{path}: unexpected column titles {raw.titles[:2]}")

    order = np.argsort(ex)
    ex_arr = np.asarray(ex)[order]
    x, y = raw.x[:, order], raw.y[:, order]
    labels = [raw.labels[i] for i in order]

    if em_grid is None:
        keep = ~np.all(np.isnan(x), axis=1)
        x, y = x[keep], y[keep]
        em = x[:, 0]
        if not np.allclose(x, em[:, None], atol=1e-6, equal_nan=True) or np.isnan(em).any():
            raise FileFormatError(
                f"{path}: the emission axis differs between excitation scans; "
                "pass em_grid= to resample each scan onto a common grid"
            )
        em_order = np.argsort(em)
        em, intensity = em[em_order], y[em_order].T
        if np.any(np.diff(em) <= 0):
            raise FileFormatError(f"{path}: repeated emission wavelengths")
    else:
        em = np.asarray(em_grid, dtype=float)
        intensity = np.vstack(
            [interp_on_grid(x[:, j], y[:, j], em, tolerance) for j in range(len(ex_arr))]
        )

    logs = [raw.log_for(lab) for lab in labels]
    missing = [lab for lab, lg in zip(labels, logs, strict=True) if lg is None]
    if missing:
        warnings.warn(f"{path.name}: no log block for {len(missing)} scan(s), e.g. {missing[0]}",
                      EEMKitWarning, stacklevel=2)
    present = [lg for lg in logs if lg is not None]
    times = scan_times(logs)

    attrs = {
        "sample_name": names[0],
        "source_file": str(path),
        "file_format": "Cary Eclipse CSV (ASCII with log)",
        **common_params(path, present, LOG_PARAMS),
        **time_attrs(times),
        "method_name": "|".join(dict.fromkeys(lg.method_name for lg in present)),
    }
    if attrs.get("data_mode", "Fluorescence") != "Fluorescence" or \
            attrs.get("scan_mode", "Emission") != "Emission":
        raise FileFormatError(f"{path}: not a fluorescence emission scan")

    ds = xr.Dataset(
        {"intensity": (("ex", "em"), intensity,
                       {"units": "a.u.", "long_name": "fluorescence intensity"})},
        coords={
            "ex": ("ex", ex_arr, {"units": "nm", "long_name": "excitation wavelength"}),
            "em": ("em", em, {"units": "nm", "long_name": "emission wavelength"}),
            "scan_time": ("ex", times),
        },
        attrs=attrs,
    )
    return with_history(ds, "read_cary_eclipse",
                        em_grid=em if em_grid is not None else "native",
                        tolerance_nm=tolerance if em_grid is not None else None)
