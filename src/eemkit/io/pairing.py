"""The pairing table: which EEM, absorbance and blank files belong together.

Pairing is never guessed by eemkit. A CSV table, written or checked by a
person, lists one sample per row:

=================  ========  ==================================================
column             required  content
=================  ========  ==================================================
``sample_id``      yes       unique identifier used throughout the analysis
``eem_file``       yes       fluorescence file, relative to ``data_root``
``include``        yes       yes/no (also true/false, 1/0, si/sì)
``eem_blank_file`` no        blank EEM (e.g. Milli-Q) measured with the sample
``abs_file``       no        absorbance file of the same sample
``abs_blank_file`` no        absorbance blank
any other column   no        kept as sample metadata (river, site, date, ...)
=================  ========  ==================================================

Comma or semicolon separators are accepted, so the table can be edited in a
spreadsheet with an Italian or other comma-decimal locale.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from eemkit.errors import PairingError

REQUIRED_COLUMNS = ("sample_id", "eem_file", "include")
FILE_COLUMNS = ("eem_file", "eem_blank_file", "abs_file", "abs_blank_file")
_TRUE = {"yes", "y", "true", "1", "si", "sì"}
_FALSE = {"no", "n", "false", "0", ""}


def read_pairing(
    path: str | Path,
    data_root: str | Path | None = None,
    check_files: bool = True,
) -> pd.DataFrame:
    """Read and validate a pairing table.

    Parameters
    ----------
    path
        CSV file.
    data_root
        Folder the file paths are relative to; defaults to the table's folder.
    check_files
        Verify that every file referenced by an included row exists.

    Returns
    -------
    pandas.DataFrame
        All rows (included or not), every column as text except ``include``
        (bool). ``df.attrs`` holds ``source`` and ``data_root``.

    Raises
    ------
    PairingError
        Listing every problem found, not only the first.
    """
    path = Path(path)
    root = Path(data_root) if data_root is not None else path.parent
    df = _read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise PairingError(f"{path}: missing required column(s) {missing}")
    for col in FILE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df.apply(lambda s: s.str.strip())

    problems = []
    flags = df["include"].str.lower()
    bad = ~flags.isin(_TRUE | _FALSE)
    for i in df.index[bad]:
        problems.append(f"row {i + 2}: include={df.at[i, 'include']!r} is not yes/no")
    df["include"] = flags.isin(_TRUE)

    inc = df[df["include"]]
    for i in inc.index[inc["sample_id"] == ""]:
        problems.append(f"row {i + 2}: empty sample_id")
    for i in inc.index[inc["eem_file"] == ""]:
        problems.append(f"row {i + 2}: included but eem_file is empty")
    dup = inc["sample_id"][inc["sample_id"].duplicated(keep=False) & (inc["sample_id"] != "")]
    for sid in sorted(set(dup)):
        rows = [str(i + 2) for i in dup.index[dup == sid]]
        problems.append(f"sample_id {sid!r} used by rows {', '.join(rows)}")

    if check_files:
        for i, row in inc.iterrows():
            for col in FILE_COLUMNS:
                if row[col] and not (root / row[col]).is_file():
                    problems.append(f"row {i + 2}: {col} not found: {row[col]}")

    if problems:
        raise PairingError(f"{path}: {len(problems)} problem(s)\n  " + "\n  ".join(problems))
    df.attrs["source"] = str(path)
    df.attrs["data_root"] = str(root)
    return df


def _read_csv(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, encoding=enc) as fh:
                header = fh.readline()
            sep = ";" if header.count(";") > header.count(",") else ","
            return pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise PairingError(f"{path}: cannot decode as UTF-8 or Windows-1252")
