"""Low-level parser shared by the Cary Eclipse and Cary 60 CSV readers.

Both Agilent/Varian Cary programs export "ASCII with log" files laid out as::

    row 1   one label per scan, each followed by an empty cell
    row 2   column titles, two per scan (x, y)
    rows    data, until the first empty line
    rest    one log block per scan: the scan label, 'Collection Time: ...',
            a 'Parameter List :' section of 'key<2+ spaces>value' lines,
            then 'Method Log :' with the method history
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from eemkit.errors import EEMKitWarning, FileFormatError

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
TIME_FORMATS = ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S")


@dataclass
class ScanLog:
    label: str
    collection_time: datetime | None
    params: dict[str, str] = field(default_factory=dict)
    method_name: str = ""


@dataclass
class CaryCSV:
    path: Path
    labels: list[str]
    titles: list[str]
    x: np.ndarray  # (n_rows, n_scans)
    y: np.ndarray  # (n_rows, n_scans)
    logs: list[ScanLog]
    encoding: str

    def log_for(self, label: str) -> ScanLog | None:
        return next((lg for lg in self.logs if lg.label == label), None)


def read_text(path: Path) -> tuple[list[str], str]:
    raw = Path(path).read_bytes()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc).splitlines(), enc
        except UnicodeDecodeError:
            continue
    raise AssertionError("latin-1 decodes any byte string")


def parse_cary_csv(path: str | Path) -> CaryCSV:
    """Parse a Cary 'ASCII with log' CSV into labels, x/y arrays and scan logs.

    Empty cells become NaN; any other non-numeric cell is an error.
    """
    path = Path(path)
    lines, enc = read_text(path)
    if len(lines) < 3:
        raise FileFormatError(f"{path}: too short to be a Cary CSV export")
    labels = [t.strip() for t in lines[0].split(",") if t.strip()]
    if not labels:
        raise FileFormatError(f"{path}: first row has no scan labels")
    n = len(labels)
    titles = [t.strip() for t in lines[1].split(",")][: 2 * n]

    rows = []
    i = 2
    while i < len(lines) and lines[i].strip():
        rows.append(lines[i])
        i += 1
    if not rows:
        raise FileFormatError(f"{path}: no data rows")

    data = np.full((len(rows), 2 * n), np.nan)
    for r, row in enumerate(rows):
        toks = row.split(",")
        if any(t.strip() for t in toks[2 * n:]):
            raise FileFormatError(
                f"{path}, line {r + 3}: more values than the {n} labelled scans"
            )
        for c, tok in enumerate(toks[: 2 * n]):
            tok = tok.strip()
            if not tok:
                continue
            try:
                data[r, c] = float(tok)
            except ValueError:
                raise FileFormatError(
                    f"{path}, line {r + 3}, column {c + 1}: not a number: {tok!r}"
                ) from None

    return CaryCSV(path, labels, titles, data[:, 0::2], data[:, 1::2],
                   parse_log(lines[i + 1:]), enc)


def parse_log(lines: list[str]) -> list[ScanLog]:
    logs: list[ScanLog] = []
    current: ScanLog | None = None
    in_params = False
    prev = ""
    for line in lines:
        s = line.rstrip()
        if s.startswith("Collection Time:"):
            current = ScanLog(prev.strip().rstrip(","), parse_time(s.split(":", 1)[1].strip()))
            logs.append(current)
            in_params = False
        elif current is not None:
            if s.startswith("Parameter List"):
                in_params = True
            elif s.startswith("Method Log"):
                in_params = False
            elif s.startswith("Method Name"):
                current.method_name = s.split(":", 1)[1].strip()
            elif in_params:
                parts = re.split(r"\s{2,}", s.strip())
                if len(parts) >= 2:
                    current.params[" ".join(parts[:-1])] = parts[-1].strip()
        if s.strip():
            prev = s
    return logs


def parse_time(text: str) -> datetime | None:
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def common_params(
    path: Path, logs: list[ScanLog], keys: dict[str, str]
) -> dict[str, str]:
    """Map attribute names to log values that are shared by all scans.

    A parameter that differs between scans is kept as 'v1|v2' with a warning;
    one that is absent from every log is omitted.
    """
    out = {}
    for attr, key in keys.items():
        vals = [lg.params[key] for lg in logs if key in lg.params]
        if not vals:
            continue
        uniq = list(dict.fromkeys(vals))
        if len(uniq) > 1:
            warnings.warn(f"{path.name}: '{key}' differs between scans: {uniq}",
                          EEMKitWarning, stacklevel=3)
        out[attr] = "|".join(uniq)
    return out


def scan_times(logs: list[ScanLog | None]) -> np.ndarray:
    return np.array(
        [np.datetime64(lg.collection_time, "s") if lg and lg.collection_time
         else np.datetime64("NaT", "s") for lg in logs]
    )


def time_attrs(times: np.ndarray) -> dict[str, str]:
    valid = times[~np.isnat(times)]
    if valid.size == 0:
        return {}
    return {"collection_start": str(valid.min()), "collection_end": str(valid.max())}
