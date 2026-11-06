"""Find measurement files in a data folder and draft a pairing table from them.

:func:`scan_folder` classifies every CSV from its first two lines (scan labels
and column titles), without reading the data, and never writes anything.

:func:`suggest_pairing` drafts a pairing table from that inventory. The draft
is a starting point for a person to check: every row is written with
``include = no`` and ``pairing_status = suggested``, and each choice it made
(or could not make) is explained in ``pairing_notes``. :func:`load_dataset`
reads only rows that someone has switched to ``include = yes``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from eemkit.io import cary60, cary_eclipse

#: Sample or file names matching this (case-insensitive) are treated as blanks.
DEFAULT_BLANK_PATTERN = r"blank|bianc|milli-?q|\bmq\b|ultrapure"

INVENTORY_COLUMNS = ("file", "kind", "sample_name", "n_scans", "first_x", "last_x",
                     "is_blank", "problem")


def _head(path: Path, n: int = 2) -> list[str]:
    raw = path.open("rb").read(65536)
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc).splitlines()[:n]
        except UnicodeDecodeError:
            continue
    return []  # pragma: no cover - latin-1 decodes anything


def classify(path: str | Path) -> dict:
    """Kind of one CSV ('eem', 'absorbance' or 'unknown') from its header lines."""
    path = Path(path)
    out = {"kind": "unknown", "sample_name": "", "n_scans": 0, "first_x": None,
           "last_x": None, "problem": ""}
    try:
        lines = _head(path)
    except OSError as exc:
        out["problem"] = f"cannot read: {exc}"
        return out
    if len(lines) < 2:
        out["problem"] = "fewer than two lines"
        return out
    labels = [t.strip() for t in lines[0].split(",") if t.strip()]
    titles = [t.strip() for t in lines[1].split(",")][:2]
    out["n_scans"] = len(labels)
    for kind, regex, title, xgroup in (
        ("eem", cary_eclipse.LABEL_RE, "Intensity (a.u.)", "ex"),
        ("absorbance", cary60.LABEL_RE, "Abs", "cycle"),
    ):
        matches = [regex.match(lab) for lab in labels]
        if labels and all(matches) and titles == ["Wavelength (nm)", title]:
            names = {m.group("name") for m in matches}
            if len(names) > 1:
                out["problem"] = f"several sample names: {sorted(names)}"
                return out
            xs = sorted(float(m.group(xgroup)) for m in matches)
            out.update(kind=kind, sample_name=names.pop(), first_x=xs[0], last_x=xs[-1])
            return out
    out["problem"] = f"not a Cary Eclipse 3-D or Cary 60 absorbance export (titles {titles})"
    return out


#: file suffixes looked at for each EEM format
SUFFIXES = {"cary_eclipse": (".csv",), "aqualog": (".dat",), "fluoromax": (".dat",),
            "hitachi_f7000": (".txt",), "shimadzu": (".txt",),
            "matrix_csv": (".csv", ".txt", ".dat")}
ABS_SUFFIXES = {"cary60": (".csv",), "two_column": (".csv", ".txt")}


def classify_with(path: str | Path, instrument: str, absorbance_format: str,
                  reader_options: dict | None = None) -> dict:
    """Like :func:`classify`, for any format: the file is read with the format's reader.

    A file that the EEM reader accepts is an 'eem' (sample name = file name);
    otherwise one that the absorbance reader accepts is 'absorbance';
    otherwise 'unknown', with the readers' complaint in ``problem``.
    """
    import warnings

    from eemkit.io.loader import ABS_READERS, READERS

    path = Path(path)
    if instrument == "cary_eclipse" and absorbance_format == "cary60":
        return classify(path)
    out = {"kind": "unknown", "sample_name": "", "n_scans": 0, "first_x": None,
           "last_x": None, "problem": ""}
    problems = []
    suffix = path.suffix.lower()
    if suffix in SUFFIXES.get(instrument, ()):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ds = READERS[instrument](path, **(reader_options or {}))
            ex = ds["ex"].values
            out.update(kind="eem", sample_name=str(ds.attrs.get("sample_name", path.stem)),
                       n_scans=int(ex.size), first_x=float(ex[0]), last_x=float(ex[-1]))
            return out
        except Exception as exc:  # noqa: BLE001 - any failure means "not this format"
            problems.append(f"{instrument}: {exc}")
    if suffix in ABS_SUFFIXES.get(absorbance_format, ()):
        try:
            ds = ABS_READERS[absorbance_format](path)
            wl = ds["wavelength"].values
            out.update(kind="absorbance", sample_name=str(ds.attrs.get("sample_name",
                                                                       path.stem)),
                       n_scans=int(ds.sizes.get("cycle", 1)), first_x=float(wl[0]),
                       last_x=float(wl[-1]))
            return out
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{absorbance_format}: {exc}")
    out["problem"] = "; ".join(problems) or f"not a {instrument} or {absorbance_format} file"
    return out


def scan_folder(
    root: str | Path,
    *,
    blank_pattern: str = DEFAULT_BLANK_PATTERN,
    progress: Callable[[int, int], None] | None = None,
    instrument: str = "cary_eclipse",
    absorbance_format: str = "cary60",
    reader_options: dict | None = None,
) -> pd.DataFrame:
    """Classify the measurement files below ``root`` (recursively); read-only.

    With the default formats (Cary Eclipse and Cary 60) every ``*.csv`` is
    classified from its first two lines. For other instruments the files with
    the format's suffixes are read with its reader (:func:`classify_with`).
    Returns one row per file with :data:`INVENTORY_COLUMNS`; ``file`` is
    relative to ``root`` with forward slashes. ``first_x``/``last_x`` are
    the excitation range (EEM), the cycle numbers (Cary 60) or the wavelength
    range (two-column absorbance).
    """
    root = Path(root)
    suffixes = set(SUFFIXES.get(instrument, ())) | set(ABS_SUFFIXES.get(absorbance_format, ()))
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)
    blank = re.compile(blank_pattern, re.IGNORECASE)
    rows = []
    for i, p in enumerate(files):
        info = classify_with(p, instrument, absorbance_format, reader_options)
        rel = p.relative_to(root).as_posix()
        info["file"] = rel
        info["is_blank"] = bool(blank.search(info["sample_name"]) or blank.search(p.name))
        rows.append(info)
        if progress:
            progress(i + 1, len(files))
    return pd.DataFrame(rows, columns=list(INVENTORY_COLUMNS))


def _key(name: str) -> str:
    return re.sub(r"[\s_\-.]+", "", name).lower()


def _folder(file: str) -> str:
    parent = Path(file).parent.as_posix()
    return "" if parent == "." else parent


def _unique_in_folder(candidates: pd.DataFrame, folder: str) -> tuple[str, str]:
    """(file, note) for the single candidate in ``folder``, else ('', reason)."""
    here = candidates[candidates["folder"] == folder]
    if len(here) == 1:
        return here["file"].iloc[0], ""
    if len(here) > 1:
        return "", f"{len(here)} candidates in {folder or '.'}"
    return "", f"none in {folder or '.'}"


def suggest_pairing(inventory: pd.DataFrame) -> pd.DataFrame:
    """Draft a pairing table from :func:`scan_folder` output, for a person to check.

    One row per non-blank EEM. Suggestions, all marked as such:

    * ``abs_file``: the non-blank absorbance file with the same sample name
      (ignoring case, spaces, ``_``, ``-`` and ``.``), preferring the EEM's
      folder; left empty if there is no single match;
    * ``eem_blank_file``: the only blank EEM in the EEM's folder;
    * ``abs_blank_file``: the only blank absorbance file in the absorbance
      file's folder.

    Every row has ``include = no``.
    """
    inv = inventory.copy()
    inv["folder"] = inv["file"].map(_folder)
    eems = inv[(inv["kind"] == "eem") & ~inv["is_blank"]]
    absb = inv[(inv["kind"] == "absorbance") & ~inv["is_blank"]]
    eem_blanks = inv[(inv["kind"] == "eem") & inv["is_blank"]]
    abs_blanks = inv[(inv["kind"] == "absorbance") & inv["is_blank"]]
    abs_keys = absb["sample_name"].map(_key)

    rows, used = [], {}
    for _, e in eems.iterrows():
        notes = []
        sid = e["sample_name"] or Path(e["file"]).stem
        if sid in used:
            used[sid] += 1
            notes.append(f"sample name also used by another file; renamed to {sid}_{used[sid]}")
            sid = f"{sid}_{used[sid]}"
        else:
            used[sid] = 1

        cands = absb[abs_keys == _key(e["sample_name"])]
        same = cands[cands["folder"] == e["folder"]]
        pick = same if len(same) == 1 else cands
        if len(pick) == 1:
            abs_file = pick["file"].iloc[0]
            notes.append("absorbance matched by sample name")
        else:
            abs_file = ""
            notes.append("no absorbance with this sample name" if cands.empty
                         else f"{len(cands)} absorbance files with this sample name")

        eem_blank, why = _unique_in_folder(eem_blanks, e["folder"])
        notes.append(f"EEM blank: {'only blank in folder' if eem_blank else why}")
        abs_blank = ""
        if abs_file:
            abs_blank, why = _unique_in_folder(abs_blanks, _folder(abs_file))
            notes.append(f"absorbance blank: {'only blank in folder' if abs_blank else why}")

        rows.append({"sample_id": sid, "include": "no", "eem_file": e["file"],
                     "eem_blank_file": eem_blank, "abs_file": abs_file,
                     "abs_blank_file": abs_blank, "pairing_status": "suggested",
                     "pairing_notes": "; ".join(notes)})
    return pd.DataFrame(rows, columns=["sample_id", "include", "eem_file", "eem_blank_file",
                                       "abs_file", "abs_blank_file", "pairing_status",
                                       "pairing_notes"])
