"""The full processing chain, driven by one settings file.

The settings are a nested dictionary, stored as TOML, with the sections
``project``, ``spectral``, ``inner_filter``, ``raman``, ``scatter``, ``crop``,
``indices``, ``absorbance``, ``campaigns``, ``parafac`` (with ``split_half``
and ``final``), ``missing`` and ``display``. The same file drives scripts and
the desktop application, so every analysis can be rerun from the command line.

Steps, in the enforced order of the corrections:

1. :func:`load` - read the samples included in the pairing table;
2. :func:`correct_until_raman` - optional instrument spectral correction,
   absorbance blank, inner filter, EEM blank, Raman units;
   :func:`finish_corrections` - scatter, optional interpolation, crop;
3. :func:`compute_indices` - on the Raman-normalised EEMs, before scatter
   removal; :func:`compute_absorbance` - CDOM metrics;
4. :func:`explore` - PARAFAC for a range of ranks with split-half
   validation; :func:`fit_final` - the chosen rank with tighter convergence;
5. :func:`campaign_analysis` - differences between campaigns, along sites
   and with covariates, on any column of :func:`sample_table`;
6. :func:`export_results` - tables, OpenFluor file, figures, settings and
   processing history; :func:`export_campaigns` for campaign analyses.

Defaults that are scientific choices are listed in :data:`DEFAULTS` with
their source; values that depend on the measurement (cuvette path lengths)
have no default and must be set.
"""

from __future__ import annotations

import copy
import json
import platform
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from eemkit import absorbance as A
from eemkit import campaigns as K
from eemkit import corrections as C
from eemkit import indices as I
from eemkit import parafac as P
from eemkit.core.history import get_history
from eemkit.errors import Cancelled, SettingsError
from eemkit.io.loader import load_dataset
from eemkit.io.pairing import read_pairing

Progress = Callable[[str, int, int], None]

#: Default settings. ``None`` means "no default: must be provided".
DEFAULTS: dict = {
    "project": {"data_root": "", "pairing": "", "output_dir": ""},
    # Instrument-specific factor files (wavelength, factor); empty = not applied.
    # convention: "multiply" (correction factors) or "divide" (response spectra).
    "spectral": {"ex_factors": "", "em_factors": "", "convention": "multiply"},
    # Kothawala et al. (2013): absorbance-based inner-filter correction
    "inner_filter": {"absorbance_path_length_cm": None, "fluorescence_path_length_cm": None},
    # Lawaetz & Stedmon (2009): Raman area of the blank at ex 350, em 381-426 nm
    "raman": {"ex": 350.0, "em_range": [381.0, 426.0], "baseline": False},
    # Band widths (below, above) in nm. 10 nm is the eemR/staRdom default width;
    # check them against the blanks. Water Raman shift ~3400 cm-1 (Lakowicz 2006).
    "scatter": {"raman_shift_cm1": 3400.0, "rayleigh1": [10.0, 10.0], "raman1": [10.0, 10.0],
                "rayleigh2": [10.0, 10.0], "raman2": [10.0, 10.0],
                "zero_below_rayleigh": None, "interpolate": False},
    "crop": {"ex_min": None, "ex_max": None, "em_min": None, "em_max": None},
    "indices": {"ex_method": "linear", "bix_em_den": 430.0},
    # CDOM metrics. Baseline: mean absorbance 680-700 nm subtracted (Green & Blough 1994;
    # Helms et al. 2008). min_r2: eemkit quality threshold for the log-linear slope fits,
    # not a literature value. doc_column: sample column with DOC (mg/L), for SUVA254.
    "absorbance": {"baseline": [680.0, 700.0], "min_r2": 0.95, "doc_column": ""},
    # Comparison of campaigns, sites and rivers: names of sample columns, and optional
    # site table (by group and site) and covariate table (by group and time).
    "campaigns": {"group": "", "site": "", "time": "", "position": "", "sites_table": "",
                  "covariates_table": ""},
    # Murphy et al. (2013)
    "parafac": {
        "ranks": [2, 3, 4, 5, 6, 7], "n_init": 10, "normalization": "norm", "tol": 1e-6,
        "max_iter": 5000, "random_state": 0, "exclude": [],
        "split_half": {"n_init": 5, "stratify": [], "random_state": 0, "threshold": 0.95},
        "final": {"rank": None, "tol": 1e-8, "max_iter": 20000, "n_init": 20},
    },
    "missing": {"policy": "error"},
    # EEM colour map of the figures: "eclipse" (Cary Eclipse rainbow) or "blues"
    "display": {"eem_colours": "eclipse"},
}


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #

def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) \
            else copy.deepcopy(v)
    return out


def default_settings() -> dict:
    """A fresh copy of :data:`DEFAULTS`."""
    return copy.deepcopy(DEFAULTS)


def load_settings(path: str | Path) -> dict:
    """Read a settings TOML; keys it does not set take :data:`DEFAULTS`."""
    return _merge(DEFAULTS, tomllib.loads(Path(path).read_text(encoding="utf-8")))


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float | np.integer | np.floating):
        return repr(float(v)) if isinstance(v, float | np.floating) else str(int(v))
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list | tuple):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(f"cannot write {type(v).__name__} to TOML")


def dumps_settings(settings: dict) -> str:
    """Settings as TOML text. ``None`` values (unset) are written as comments."""
    lines: list[str] = ["# eemkit settings", ""]

    def table(name: str, d: dict) -> None:
        scalars = {k: v for k, v in d.items() if not isinstance(v, dict)}
        if name:
            lines.append(f"[{name}]")
        for k, v in scalars.items():
            lines.append(f"# {k} = (not set)" if v is None else f"{k} = {_toml_value(v)}")
        if name:
            lines.append("")
        for k, v in d.items():
            if isinstance(v, dict):
                table(f"{name}.{k}" if name else k, v)

    table("", settings)
    return "\n".join(lines).rstrip() + "\n"


def save_settings(settings: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_settings(settings), encoding="utf-8")
    return path


def _required(settings: dict, section: str, key: str) -> float:
    v = settings.get(section, {}).get(key)
    if v in (None, ""):
        raise SettingsError(f"{section}.{key} is not set; it depends on your measurement and "
                            "has no default")
    return float(v)


def _resolve(settings: dict, key: str, base: Path | None, section: str = "project") -> Path:
    v = settings[section].get(key, "")
    if not v:
        raise SettingsError(f"{section}.{key} is not set")
    p = Path(v)
    return p if p.is_absolute() or base is None else base / p


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #

def _check(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise Cancelled("cancelled")


def load(settings: dict, base: str | Path | None = None) -> xr.Dataset:
    """Read the included rows of ``project.pairing`` (paths relative to ``base``)."""
    base = Path(base) if base is not None else None
    root = _resolve(settings, "data_root", base)
    table = read_pairing(_resolve(settings, "pairing", base), data_root=root)
    return load_dataset(table, data_root=root)


def correct_until_raman(ds: xr.Dataset, settings: dict,
                        base: str | Path | None = None) -> xr.Dataset:
    """Spectral correction (if factor files are set), absorbance blank, inner
    filter, EEM blank and Raman units. Factor files are relative to ``base``."""
    l_abs = _required(settings, "inner_filter", "absorbance_path_length_cm")
    l_fl = _required(settings, "inner_filter", "fluorescence_path_length_cm")
    missing = settings["missing"]["policy"]
    sp = settings["spectral"]
    files = [bool(sp.get(k)) for k in ("ex_factors", "em_factors")]
    if any(files):
        if not all(files):
            raise SettingsError("spectral: set both ex_factors and em_factors, or neither")
        base = Path(base) if base is not None else None
        ds = C.apply_spectral_correction(
            ds, ex_factors=_resolve(settings, "ex_factors", base, "spectral"),
            em_factors=_resolve(settings, "em_factors", base, "spectral"),
            convention=sp.get("convention", "multiply"))
    ds = C.subtract_absorbance_blank(ds, missing=missing)
    ds = C.correct_inner_filter(ds, absorbance_path_length_cm=l_abs,
                                fluorescence_path_length_cm=l_fl, missing=missing)
    ds = C.subtract_blank(ds, missing=missing)
    r = settings["raman"]
    return C.normalize_raman(ds, ex=float(r["ex"]), em_range=tuple(r["em_range"]),
                             baseline=bool(r["baseline"]), missing=missing)


def finish_corrections(ds: xr.Dataset, settings: dict) -> xr.Dataset:
    """Scatter removal, optional interpolation of the gaps, crop."""
    s = settings["scatter"]
    widths = {b: tuple(s[b]) for b in C.scatter.BANDS if s.get(b)}
    ds = C.remove_scatter(ds, widths=widths, raman_shift_cm1=float(s["raman_shift_cm1"]),
                          zero_below_rayleigh=s.get("zero_below_rayleigh"))
    if s.get("interpolate"):
        ds = C.interpolate_missing(ds, method=s["interpolate"])
    c = settings["crop"]
    ex = (c.get("ex_min"), c.get("ex_max"))
    em = (c.get("em_min"), c.get("em_max"))
    if any(v is not None for v in ex + em):
        ds = C.crop(ds, ex=ex if any(v is not None for v in ex) else None,
                    em=em if any(v is not None for v in em) else None)
    return ds


def compute_indices(after_raman: xr.Dataset, settings: dict) -> pd.DataFrame:
    """FI, HIX, BIX and Coble peaks, with the sample metadata in front."""
    s = settings["indices"]
    df = I.compute_indices(after_raman, ex_method=s["ex_method"],
                           bix={"em_den": float(s["bix_em_den"])})
    meta = [c for c in after_raman.coords
            if after_raman[c].dims == ("sample",) and c != "sample"
            and after_raman[c].dtype == object and not c.startswith(("eem_", "abs_"))
            and not c.endswith("_file")]
    for c in reversed(meta):
        df.insert(0, c, after_raman[c].to_series().reindex(df.index).values)
    return df


def compute_absorbance(after_raman: xr.Dataset, settings: dict) -> pd.DataFrame:
    """CDOM metrics (a254, a350, spectral slopes, SR, E2:E3, SUVA254 with DOC)."""
    s = settings["absorbance"]
    baseline = tuple(s["baseline"]) if s.get("baseline") else None
    return A.compute_absorbance_metrics(
        after_raman,
        absorbance_path_length_cm=_required(settings, "inner_filter",
                                            "absorbance_path_length_cm"),
        baseline=baseline, min_r2=float(s["min_r2"]), doc=s.get("doc_column") or None)


def parafac_input(corrected: xr.Dataset, settings: dict) -> xr.Dataset:
    """Drop excluded samples; add the split-half stratum coordinate."""
    p = settings["parafac"]
    unknown = sorted(set(p["exclude"]) - set(corrected["sample"].values))
    if unknown:
        raise SettingsError(f"parafac.exclude lists unknown samples: {unknown}")
    ds = corrected.drop_sel(sample=p["exclude"]) if p["exclude"] else corrected
    strat = p["split_half"]["stratify"]
    if strat:
        bad = [c for c in strat if c not in ds.coords]
        if bad:
            raise SettingsError(f"parafac.split_half.stratify: no sample column {bad}")
        ds = ds.assign_coords(stratum=("sample", ["|".join(str(ds[c].values[i]) for c in strat)
                                                  for i in range(ds.sizes["sample"])]))
    return ds


def _fit_kwargs(p: dict, final: dict | None = None, n_jobs: int | None = None) -> dict:
    f = final or {}
    return dict(normalization=p["normalization"] or None, tol=float(f.get("tol", p["tol"])),
                max_iter=int(f.get("max_iter", p["max_iter"])),
                random_state=int(p["random_state"]), n_jobs=n_jobs)


def _split(ds: xr.Dataset, rank: int, p: dict, kw: dict) -> xr.Dataset:
    sh = p["split_half"]
    return P.split_half(ds, rank, stratify="stratum" if "stratum" in ds.coords else None,
                        split_random_state=int(sh["random_state"]),
                        threshold=float(sh["threshold"]), n_init=int(sh["n_init"]), **kw)


@dataclass
class Exploration:
    models: dict[int, xr.Dataset]
    splits: dict[int, xr.Dataset]
    table: pd.DataFrame


def explore(ds: xr.Dataset, settings: dict, *, progress: Progress | None = None,
            cancelled: Callable[[], bool] | None = None,
            n_jobs: int | None = None) -> Exploration:
    """PARAFAC and split-half validation for every rank in ``parafac.ranks``.

    ``cancelled`` is polled between fits; when it returns True,
    :class:`~eemkit.errors.Cancelled` is raised. ``n_jobs``: random starts
    run at the same time (see :func:`eemkit.parafac.fit_parafac`); it does
    not change the result.
    """
    p = settings["parafac"]
    kw = _fit_kwargs(p, n_jobs=n_jobs)
    ranks = [int(r) for r in p["ranks"]]
    models, splits = {}, {}
    for i, r in enumerate(ranks):
        _check(cancelled)
        if progress:
            progress(f"{r} components: fitting", 2 * i, 2 * len(ranks))
        models[r] = P.fit_parafac(ds, r, n_init=int(p["n_init"]), **kw)
        _check(cancelled)
        if progress:
            progress(f"{r} components: split-half", 2 * i + 1, 2 * len(ranks))
        splits[r] = _split(ds, r, p, kw)
    if progress:
        progress("done", 2 * len(ranks), 2 * len(ranks))
    table = P.summary_table(models)
    table["split_half_min_tcc"] = [splits[r].attrs["min_tcc"] for r in table.index]
    table["split_half_validated"] = [bool(splits[r].attrs["validated"]) for r in table.index]
    table["eemqual"] = [P.eemqual(models[r], splits[r])["eemqual"] for r in table.index]
    return Exploration(models, splits, table)


def fit_final(ds: xr.Dataset, settings: dict, *, progress: Progress | None = None,
              cancelled: Callable[[], bool] | None = None,
              n_jobs: int | None = None) -> tuple[xr.Dataset, xr.Dataset]:
    """The rank in ``parafac.final.rank`` with its own convergence settings."""
    p = settings["parafac"]
    final = p["final"]
    if not final.get("rank"):
        raise SettingsError("parafac.final.rank is not set: choose the number of components "
                            "after the exploratory models")
    r = int(final["rank"])
    kw = _fit_kwargs(p, final, n_jobs=n_jobs)
    if progress:
        progress(f"final {r}-component model", 0, 2)
    model = P.fit_parafac(ds, r, n_init=int(final["n_init"]), **kw)
    _check(cancelled)
    if progress:
        progress("split-half validation", 1, 2)
    split = _split(ds, r, p, kw)
    if progress:
        progress("done", 2, 2)
    return model, split


# --------------------------------------------------------------------------- #
# Campaigns, sites and rivers
# --------------------------------------------------------------------------- #

def sample_table(indices: pd.DataFrame | None, model: xr.Dataset | None = None) -> pd.DataFrame:
    """Indices and CDOM metrics, plus Fmax and the share of each component if a model is given.

    Samples left out of the model have no Fmax (empty cells).
    """
    if indices is None and model is None:
        raise SettingsError("compute the indices or fit a PARAFAC model first")
    df = indices.copy() if indices is not None else pd.DataFrame(index=pd.Index(
        model["sample"].values, name="sample"))
    if model is not None:
        fmax = model["fmax"].to_pandas()
        fmax.columns = [f"C{c}_Fmax" for c in fmax.columns]
        df = df.drop(columns=[c for c in fmax.columns if c in df]).join(fmax, how="left")
        if indices is None:
            for c in reversed([c for c in model.coords if model[c].dims == ("sample",)
                               and c != "sample" and model[c].dtype == object]):
                df.insert(0, c, model[c].to_series().reindex(df.index).values)
    fmax_cols = [c for c in df.columns if re.fullmatch(r"C\d+_Fmax", str(c))]
    if fmax_cols:
        comp = K.composition(df, fmax_cols)
        df = df.drop(columns=[c for c in comp.columns if c in df]).join(comp)
    return df


@dataclass
class CampaignAnalysis:
    value: str
    units: pd.DataFrame
    design: pd.DataFrame
    warnings: list[str]
    kruskal: pd.DataFrame
    pairwise: pd.DataFrame
    spatial: pd.DataFrame | None
    covariates: pd.DataFrame | None


def read_table(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")


def campaign_analysis(table: pd.DataFrame, value: str, settings: dict,
                      base: str | Path | None = None) -> CampaignAnalysis:
    """Differences of ``value`` between times, along sites and with covariates.

    Uses ``settings["campaigns"]``: ``group``, ``time`` and optionally
    ``site``, ``position`` (a column of the site table or of ``table``) and
    the two optional tables (paths relative to ``base``).
    """
    c = settings["campaigns"]
    group, time, site = c.get("group"), c.get("time"), c.get("site") or None
    if not group or not time:
        raise SettingsError("campaigns: choose the group column (e.g. river) and the time "
                            "column (e.g. campaign)")
    base = Path(base) if base is not None else None
    keys = {group, time} | ({site} if site else set())
    numeric = [k for k in table.columns if k not in keys
               and pd.api.types.is_numeric_dtype(table[k])]
    if value not in numeric:
        raise SettingsError(f"campaigns: {value!r} is not a numeric column of the table")
    units = K.site_means(table.reset_index(), numeric, group=group, time=time, site=site)
    notes: list[str] = []
    if c.get("sites_table"):
        if not site:
            raise SettingsError("campaigns: a site table needs the site column")
        units, n = K.join_sites(units, read_table(_resolve(settings, "sites_table", base,
                                                            "campaigns")), group=group, site=site)
        notes += n
    cov_cols: list[str] = []
    if c.get("covariates_table"):
        cov = read_table(_resolve(settings, "covariates_table", base, "campaigns"))
        cov_cols = [k for k in cov.columns if k not in (group, time)
                    and pd.api.types.is_numeric_dtype(cov[k])]
        units, n = K.join_covariates(units, cov, group=group, time=time)
        notes += n
    kw, pairs = K.compare_times(units, value, group=group, time=time)
    position = c.get("position")
    spatial = (K.spatial_trend(units, value, position, group=group, time=time)
               if position and position in units.columns else None)
    if position and position not in units.columns:
        notes.append(f"position column {position!r} not found; no spatial trend")
    covs = K.covariate_correlations(units, value, cov_cols, group=group) if cov_cols else None
    return CampaignAnalysis(value, units, K.design_table(units, group=group, time=time),
                            K.confounding(units, group=group, time=time) + notes, kw, pairs,
                            spatial, covs)


def export_campaigns(out_dir: str | Path, analysis: CampaignAnalysis, settings: dict,
                     figures: bool = True) -> list[Path]:
    """Tables (and figures) of one campaign analysis in ``out_dir``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    v = analysis.value
    written = []
    for name, df in (("site_means", analysis.units), ("design", analysis.design),
                     (f"{v}_kruskal", analysis.kruskal), (f"{v}_dunn", analysis.pairwise),
                     (f"{v}_spatial", analysis.spatial), (f"{v}_covariates", analysis.covariates)):
        if df is not None and not df.empty:
            written.append(out / f"{name}.csv")
            df.to_csv(written[-1], index=name == "design", float_format="%.6g")
    written.append(out / f"{v}_notes.txt")
    written[-1].write_text("\n".join([analysis.kruskal.attrs.get("method", "")]
                                     + analysis.warnings) + "\n", encoding="utf-8")
    if figures:
        import matplotlib.pyplot as plt

        from eemkit import plot
        c = settings["campaigns"]
        fig = plot.campaign_series(analysis.units, v, group=c["group"], time=c["time"])
        written += plot.save(fig, out / f"{v}_by_{c['time']}")
        plt.close(fig)
        if analysis.spatial is not None:
            fig = plot.along_sites(analysis.units, v, c["position"], group=c["group"])
            written += plot.save(fig, out / f"{v}_along_sites")
            plt.close(fig)
    return written


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

def versions() -> dict[str, str]:
    import scipy

    from eemkit import __version__
    return {"eemkit": __version__, "python": platform.python_version(),
            "numpy": np.__version__, "scipy": scipy.__version__, "pandas": pd.__version__,
            "xarray": xr.__version__}


def export_results(
    out_dir: str | Path,
    settings: dict,
    *,
    corrected: xr.Dataset | None = None,
    indices: pd.DataFrame | None = None,
    exploration: Exploration | None = None,
    model: xr.Dataset | None = None,
    split: xr.Dataset | None = None,
    openfluor: dict | None = None,
    figures: bool = True,
) -> list[Path]:
    """Write whatever results are given; returns the paths written.

    Always writes ``settings.toml`` and ``processing_record.json`` (versions,
    processing history, sample list) so the run can be repeated.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = [save_settings(settings, out / "settings.toml")]
    record: dict = {"versions": versions()}

    if corrected is not None:
        written.append(out / "corrected_eems.nc")
        corrected.to_netcdf(written[-1], engine="scipy")
        record["processing_history"] = get_history(corrected)
        record["samples"] = [str(s) for s in corrected["sample"].values]
        record["spectral_correction"] = C.spectral_correction_status(corrected)
    if indices is not None:
        written.append(out / "indices.csv")
        indices.to_csv(written[-1], float_format="%.6g")
    if exploration is not None:
        written.append(out / "parafac_exploration.csv")
        exploration.table.to_csv(written[-1])
    if model is not None:
        r = model.sizes["component"]
        fmax = model["fmax"].to_pandas()
        fmax.columns = [f"C{c}_Fmax" for c in fmax.columns]
        written.append(out / f"parafac_{r}comp_fmax.csv")
        fmax.to_csv(written[-1], float_format="%.6g")
        for mode in ("ex", "em"):
            written.append(out / f"parafac_{r}comp_{mode}_loadings.csv")
            pd.DataFrame(model[f"{mode}_loadings"].values, index=model[mode].values,
                         columns=[f"C{c}" for c in model["component"].values]
                         ).rename_axis(mode).to_csv(written[-1])
        written.append(P.to_openfluor(model, out / f"parafac_{r}comp_openfluor.txt",
                                      **(openfluor or {})))
        written.append(out / f"parafac_{r}comp_model.nc")
        model.to_netcdf(written[-1], engine="scipy")
        record["parafac"] = {k: model.attrs[k] for k in (
            "explained_variance_pct", "core_consistency_pct", "n_init_at_best_minimum")}
        if split is not None:
            record["parafac"]["split_half_min_tcc"] = split.attrs["min_tcc"]
            record["parafac"]["split_half_validated"] = bool(split.attrs["validated"])
    if figures:
        written += export_figures(out / "figures", settings, exploration, model, split)

    written.append(out / "processing_record.json")
    written[-1].write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return written


def export_figures(out: Path, settings: dict, exploration: Exploration | None,
                   model: xr.Dataset | None, split: xr.Dataset | None) -> list[Path]:
    """Rank diagnostics, components and leverage figures (needs matplotlib)."""
    import matplotlib.pyplot as plt

    from eemkit import plot

    written: list[Path] = []
    if exploration is not None:
        fig = plot.rank_diagnostics(exploration.table,
                                    threshold=settings["parafac"]["split_half"]["threshold"],
                                    chosen=settings["parafac"]["final"].get("rank"))
        written += plot.save(fig, out / "rank_diagnostics")
        plt.close(fig)
    if model is not None:
        cmap = settings.get("display", {}).get("eem_colours", "blues")
        for name, fig in (("components", plot.components(model, split, cmap=cmap)),
                          ("leverage", plot.leverage(model))):
            written += plot.save(fig, out / name)
            plt.close(fig)
    return written
