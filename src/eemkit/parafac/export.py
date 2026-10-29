"""Export of PARAFAC loadings in the OpenFluor text format.

OpenFluor (openfluor.org; Murphy et al. 2014, Anal. Methods 6:658-661)
accepts a tab-separated file: '#' comment lines, a block of ``key<TAB>value``
metadata, then one line per wavelength, ``Ex`` or ``Em`` followed by the
wavelength and the loading of each component. This follows the layout written
by drEEM's ``openfluor`` function; check the file against the current
OpenFluor upload template before submitting.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import xarray as xr

METADATA_KEYS = ("name", "creator", "email", "doi", "reference", "unit", "toolbox", "date",
                 "fluorometer", "nSample", "constraints", "validation", "methods",
                 "preprocess", "sources", "ecozones", "description")


def to_openfluor(model: xr.Dataset, path: str | Path, **metadata: str) -> Path:
    """Write ``model``'s excitation and emission loadings for OpenFluor.

    Loadings are scaled to a maximum of 1 per component (OpenFluor compares
    shapes). Unknown metadata are written as '?'; pass e.g. ``name=``,
    ``creator=``, ``doi=``, ``description=``. Fields derived from the model
    (unit, toolbox, date, nSample, constraints) are filled in unless given.
    """
    from eemkit import __version__

    unknown = set(metadata) - set(METADATA_KEYS)
    if unknown:
        raise ValueError(f"unknown OpenFluor metadata {sorted(unknown)}; use {METADATA_KEYS}")
    meta = {k: "?" for k in METADATA_KEYS}
    meta.update(unit=str(model["scores"].attrs.get("units", "?")) or "?",
                toolbox=f"eemkit {__version__}", date=date.today().isoformat(),
                nSample=str(model.sizes["sample"]), constraints="non-negativity")
    meta.update({k: str(v) for k, v in metadata.items()})

    ex = model["ex_loadings"] / model["ex_loadings"].max("ex")
    em = model["em_loadings"] / model["em_loadings"].max("em")
    lines = ["#", "# Fluorescence Model", "#"]
    lines += [f"{k}\t{meta[k]}" for k in METADATA_KEYS]
    lines += ["#", "# Excitation/Emission (Ex, Em), wavelength [nm], component[n] [intensity]",
              "#"]
    for label, da, dim in (("Ex", ex, "ex"), ("Em", em, "em")):
        for w in da[dim].values:
            vals = da.sel({dim: w}).values
            lines.append("\t".join([label, f"{w:g}"] + [f"{v:.6g}" for v in vals]))
    path = Path(path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
