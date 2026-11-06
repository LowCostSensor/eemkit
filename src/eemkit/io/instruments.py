"""Readers for EEMs from fluorometers other than the Cary Eclipse, and plain absorbance files.

Every reader returns the same structure as
:func:`eemkit.io.cary_eclipse.read_cary_eclipse`: ``intensity(ex, em)`` in
instrument units, wavelengths ascending, the values exactly as in the file,
and the file and instrument information as attributes. Two attributes matter
for the corrections:

* ``corrected_spectra``: ``"On"`` when the file says the instrument already
  corrected the spectra (eemkit then refuses a second spectral correction);
  absent when the file does not say;
* ``instrument_processing``: text found in the file that describes processing
  done by the instrument software (e.g. Aqualog "Sample - Blank",
  "Normalized by 75.335"), and ``instrument_steps``: the eemkit steps it
  implies (``blank``, ``inner_filter``, ``raman``), comma-separated. eemkit
  never repeats such a step and never skips one silently: the project must
  declare it in ``project.already_done`` (see :mod:`eemkit.pipeline`).

Formats (``project.instrument``):

========================  ===================================================
``aqualog``               Horiba Aqualog ``.dat`` export (excitation in columns)
``fluoromax``             Horiba Fluoromax ``.dat`` matrix (excitation in columns)
``hitachi_f7000``         Hitachi F-7000 ``.TXT`` 3-D scan with header
``shimadzu``              Shimadzu ``.TXT`` blocks of (emission, intensity);
                          the excitation wavelengths must be given
``matrix_csv``            any matrix: first row excitation, first column emission
                          (or the transpose), comma, semicolon or tab separated
========================  ===================================================

Absorbance (``project.absorbance_format``): ``cary60`` or ``two_column``
(:func:`read_two_column_absorbance`).
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import xarray as xr

from eemkit.core.history import with_history
from eemkit.errors import EEMKitWarning, FileFormatError

#: Hitachi F-7000 writes this value where the detector saturated.
HITACHI_OVERRANGE = 9999.9

_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _text(path: Path) -> list[str]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc).splitlines()
        except UnicodeDecodeError:
            continue
    raise FileFormatError(f"{path}: cannot decode the file")  # pragma: no cover


def _split(line: str, sep: str | None = "\t") -> list[str]:
    return [t.strip() for t in (line.split(sep) if sep else line.split())]


def _is_number(token: str) -> bool:
    return bool(_NUMBER.match(token.strip()))


def _floats(tokens: Sequence[str], path: Path, what: str) -> np.ndarray:
    try:
        return np.array([float(t) for t in tokens], dtype=float)
    except ValueError as e:
        raise FileFormatError(f"{path}: {what} is not numeric ({e})") from e


def _dataset(path: Path, ex: np.ndarray, em: np.ndarray, values: np.ndarray,
             fmt: str, step: str, attrs: dict) -> xr.Dataset:
    """intensity(ex, em) with both axes ascending; ``values`` is (em, ex)."""
    if values.shape != (em.size, ex.size):
        raise FileFormatError(f"{path}: {values.shape[0]} x {values.shape[1]} values for "
                              f"{em.size} emission x {ex.size} excitation wavelengths")
    for name, w in (("excitation", ex), ("emission", em)):
        if np.unique(w).size != w.size:
            raise FileFormatError(f"{path}: repeated {name} wavelengths")
    eo, xo = np.argsort(em), np.argsort(ex)
    intensity = values[np.ix_(eo, xo)].T
    ds = xr.Dataset(
        {"intensity": (("ex", "em"), intensity,
                       {"units": "a.u.", "long_name": "fluorescence intensity"})},
        coords={"ex": ("ex", ex[xo], {"units": "nm", "long_name": "excitation wavelength"}),
                "em": ("em", em[eo], {"units": "nm", "long_name": "emission wavelength"})},
        attrs={"sample_name": path.stem, "source_file": str(path), "file_format": fmt,
               **attrs},
    )
    return with_history(ds, step, em_grid="native", tolerance_nm=None)


def _matrix_rows(lines: list[str], path: Path, sep: str | None = "\t"
                 ) -> tuple[list[str], list[list[str]], list[str]]:
    """Header tokens, numeric data rows and the other (text) rows of a matrix file.

    The header is the first row; data rows are rows with the header's number
    of tokens whose tokens are all numbers; any other non-empty row is text.
    """
    rows = [_split(ln, sep) for ln in lines if ln.strip()]
    if not rows:
        raise FileFormatError(f"{path}: empty file")
    header = [t for t in rows[0] if t != ""] if sep is None else rows[0]
    while header and header[-1] == "":
        header = header[:-1]
    data, text = [], []
    for r in rows[1:]:
        r = r[:len(header)] if len(r) > len(header) and all(t == "" for t in r[len(header):]) \
            else r
        if len(r) == len(header) and all(_is_number(t) for t in r):
            data.append(r)
        else:
            text.append(" ".join(t for t in r if t))
    if not data:
        raise FileFormatError(f"{path}: no numeric rows with {len(header)} columns")
    return header, data, text


# --------------------------------------------------------------------------- #
# EEM readers
# --------------------------------------------------------------------------- #

def read_aqualog(path: str | Path) -> xr.Dataset:
    """Horiba Aqualog EEM exported as ``.dat`` (tab separated).

    First row: a label (e.g. ``Sample - Blank``) then the excitation
    wavelengths; then text rows (e.g. ``Normalized by 75.335``) and one row
    per emission wavelength. The label and the text rows are kept in
    ``instrument_processing``; a label mentioning a blank, an inner filter
    (IFE) or Raman units sets ``instrument_steps``.
    """
    path = Path(path)
    header, data, text = _matrix_rows(_text(path), path)
    if len(header) < 3 or not all(_is_number(t) for t in header[1:]):
        raise FileFormatError(f"{path}: first row is not a label followed by excitation "
                              "wavelengths; is this an Aqualog EEM export?")
    ex = _floats(header[1:], path, "excitation row")
    m = _floats([v for r in data for v in r], path, "data").reshape(len(data), len(header))
    notes = [header[0]] + [t for t in text if t and t.lower() != "nm"]
    processing = "; ".join(n for n in notes if n)
    return _dataset(path, ex, m[:, 0], m[:, 1:], "Horiba Aqualog .dat", "read_aqualog",
                    {"instrument": "Horiba Aqualog", "instrument_processing": processing,
                     "instrument_steps": ",".join(_steps_in(processing))})


def _steps_in(text: str) -> list[str]:
    """eemkit steps that a processing description says were already done."""
    t = text.lower()
    steps = []
    if "blank" in t:
        steps.append("blank")
    if "ife" in re.findall(r"[a-z]+", t) or "inner filter" in t or "inner-filter" in t:
        steps.append("inner_filter")
    if "raman" in t or re.search(r"\bru\b", t):
        steps.append("raman")
    return steps


def read_fluoromax(path: str | Path) -> xr.Dataset:
    """Horiba Fluoromax ``.dat`` matrix (tab separated).

    First row: a label then the excitation wavelengths; each following row an
    emission wavelength and its intensities. The file says nothing about the
    instrument's corrections, so ``corrected_spectra`` is not set.
    """
    path = Path(path)
    header, data, text = _matrix_rows(_text(path), path)
    if len(header) < 3 or not all(_is_number(t) for t in header[1:]):
        raise FileFormatError(f"{path}: first row is not a label followed by excitation "
                              "wavelengths; is this a Fluoromax EEM export?")
    ex = _floats(header[1:], path, "excitation row")
    m = _floats([v for r in data for v in r], path, "data").reshape(len(data), len(header))
    attrs = {"instrument": "Horiba Fluoromax", "header_label": header[0]}
    if text:
        attrs["ignored_rows"] = len(text)
    return _dataset(path, ex, m[:, 0], m[:, 1:], "Horiba Fluoromax .dat", "read_fluoromax",
                    attrs)


#: header key -> attribute name, Hitachi F-7000
HITACHI_PARAMS = {
    "Model": "instrument", "Serial Number": "instrument_serial",
    "Measurement type": "scan_mode", "Data mode": "data_mode", "Scan speed": "scan_rate",
    "EX Slit": "ex_slit_nm", "EM Slit": "em_slit_nm", "PMT Voltage": "pmt_voltage",
    "Response": "response", "Corrected spectra": "corrected_spectra",
    "Run Date": "run_date", "Sample": "header_sample",
}


def read_hitachi_f7000(path: str | Path) -> xr.Dataset:
    """Hitachi F-7000 3-D scan exported as ``.TXT``.

    The header (``key:<tab>value`` lines) is kept as attributes; the matrix
    follows ``Data Points`` with excitation in columns. The over-range value
    9999.9, written where the detector saturated, becomes NaN and is counted
    in ``n_saturated`` with a warning. ``Corrected spectra: On`` is kept, so
    eemkit will not apply a second spectral correction.
    """
    path = Path(path)
    lines = _text(path)
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "Data Points")
    except StopIteration:
        raise FileFormatError(f"{path}: no 'Data Points' line; is this a Hitachi F-7000 "
                              "3-D scan export?") from None
    attrs: dict = {}
    for ln in lines[:start]:
        if ":" in ln:
            key, _, value = ln.partition(":")
            key, value = key.strip(), value.strip()
            if key in HITACHI_PARAMS and value:
                attrs[HITACHI_PARAMS[key]] = value.strip("'").strip()
    if attrs.get("scan_mode", "3-D Scan") != "3-D Scan" or \
            attrs.get("data_mode", "Fluorescence") != "Fluorescence":
        raise FileFormatError(f"{path}: not a fluorescence 3-D scan")
    for key in ("ex_slit_nm", "em_slit_nm", "pmt_voltage"):
        if key in attrs:
            attrs[key] = attrs[key].replace("nm", "").replace("V", "").strip()
    rows = [_split(ln) for ln in lines[start + 1:] if ln.strip()]
    ex = _floats([t for t in rows[0] if t], path, "excitation row")
    data = [r for r in rows[1:] if len([t for t in r if t]) == ex.size + 1]
    m = _floats([t for r in data for t in r if t], path, "data").reshape(len(data), ex.size + 1)
    values = m[:, 1:]
    saturated = np.isclose(values, HITACHI_OVERRANGE)
    n_sat = int(saturated.sum())
    values = np.where(saturated, np.nan, values)
    if n_sat:
        warnings.warn(f"{path.name}: {n_sat} saturated value(s) ({HITACHI_OVERRANGE}) set to "
                      "missing", EEMKitWarning, stacklevel=2)
    attrs.update(n_saturated=n_sat, instrument=attrs.get("instrument", "Hitachi F-7000"))
    return _dataset(path, ex, m[:, 0], values, "Hitachi F-7000 .TXT", "read_hitachi_f7000",
                    attrs)


def read_shimadzu(path: str | Path, *, ex_start: float, ex_step: float) -> xr.Dataset:
    """Shimadzu ``.TXT`` EEM: blocks of (emission, intensity) lines, one block per excitation.

    The excitation wavelengths are not in the file: ``ex_start`` and
    ``ex_step`` (nm) must be given (no default), and the number of blocks in
    the file fixes how many there are. Each block must have the same emission
    wavelengths.
    """
    path = Path(path)
    if ex_start is None or ex_step is None or not ex_step > 0:
        raise FileFormatError(f"{path}: Shimadzu files do not store the excitation "
                              "wavelengths; set shimadzu.ex_start and shimadzu.ex_step")
    pairs = [_split(ln, None) for ln in _text(path) if ln.strip()]
    if any(len(p) != 2 or not all(_is_number(t) for t in p) for p in pairs):
        raise FileFormatError(f"{path}: every line must be 'emission intensity'; "
                              "is this a Shimadzu EEM export?")
    m = _floats([t for p in pairs for t in p], path, "data").reshape(-1, 2)
    first = np.flatnonzero(np.isclose(m[:, 0], m[0, 0]))
    n_em = int(first[1]) if first.size > 1 else m.shape[0]
    if m.shape[0] % n_em:
        raise FileFormatError(f"{path}: {m.shape[0]} lines are not whole blocks of {n_em}")
    blocks = m.reshape(-1, n_em, 2)
    if not np.allclose(blocks[:, :, 0], blocks[0, :, 0]):
        raise FileFormatError(f"{path}: the emission wavelengths differ between blocks")
    n_ex = blocks.shape[0]
    ex = float(ex_start) + float(ex_step) * np.arange(n_ex)
    return _dataset(path, ex, blocks[0, :, 0], blocks[:, :, 1].T, "Shimadzu .TXT",
                    "read_shimadzu", {"instrument": "Shimadzu",
                                      "ex_from_settings": f"{ex[0]:g}-{ex[-1]:g} nm, "
                                                          f"step {ex_step:g} ({n_ex} scans)"})


def read_matrix_csv(path: str | Path, *, orientation: str = "em_rows") -> xr.Dataset:
    """Any EEM matrix: first row and first column hold the wavelengths.

    ``orientation="em_rows"``: first row = excitation, first column = emission
    (as Aqualog and Fluoromax); ``"ex_rows"``: the transpose. Separator:
    comma, semicolon or tab, detected from the first line. The top-left cell
    is ignored.
    """
    path = Path(path)
    if orientation not in ("em_rows", "ex_rows"):
        raise ValueError("orientation must be 'em_rows' or 'ex_rows'")
    lines = _text(path)
    first = next((ln for ln in lines if ln.strip()), "")
    sep = max(("\t", ";", ","), key=first.count)
    header, data, text = _matrix_rows(lines, path, sep)
    if len(header) < 3 or not all(_is_number(t) for t in header[1:]):
        raise FileFormatError(f"{path}: the first row must hold the wavelengths of the columns")
    cols = _floats(header[1:], path, "first row")
    m = _floats([v for r in data for v in r], path, "data").reshape(len(data), len(header))
    rows, values = m[:, 0], m[:, 1:]
    if orientation == "em_rows":
        ex, em = cols, rows
    else:
        ex, em, values = rows, cols, values.T
    attrs = {"instrument": "unknown (matrix file)", "matrix_orientation": orientation}
    if text:
        attrs["ignored_rows"] = len(text)
    return _dataset(path, ex, em, values, "EEM matrix (text)", "read_matrix_csv", attrs)


# --------------------------------------------------------------------------- #
# Absorbance
# --------------------------------------------------------------------------- #

def read_two_column_absorbance(path: str | Path) -> xr.Dataset:
    """Absorbance spectrum as two columns: wavelength (nm) and absorbance (decadic).

    Comma, semicolon, tab or space separated; lines that are not two numbers
    (titles, units) are skipped. The wavelengths must not repeat. Returns
    ``absorbance(cycle, wavelength)`` with one cycle, like
    :func:`eemkit.io.cary60.read_cary60`, so the rest of eemkit treats both alike.
    """
    path = Path(path)
    vals = []
    for ln in _text(path):
        toks = [t for t in re.split(r"[,;\t ]+", ln.strip()) if t]
        if len(toks) == 2 and all(_is_number(t) for t in toks):
            vals.append((float(toks[0]), float(toks[1])))
    if len(vals) < 2:
        raise FileFormatError(f"{path}: fewer than two 'wavelength absorbance' lines")
    a = np.array(vals)
    order = np.argsort(a[:, 0])
    wl, ab = a[order, 0], a[order, 1]
    if np.any(np.diff(wl) <= 0):
        raise FileFormatError(f"{path}: repeated wavelengths; is this a single spectrum?")
    ds = xr.Dataset(
        {"absorbance": (("cycle", "wavelength"), ab[None, :],
                        {"units": "1", "long_name": "absorbance (decadic)"})},
        coords={"cycle": ("cycle", [1]),
                "wavelength": ("wavelength", wl, {"units": "nm", "long_name": "wavelength"})},
        attrs={"sample_name": path.stem, "source_file": str(path),
               "file_format": "two-column absorbance (text)"},
    )
    return with_history(ds, "read_two_column_absorbance")
