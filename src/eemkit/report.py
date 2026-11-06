"""One self-contained HTML page that documents a whole analysis.

The report gathers what a reviewer or a co-author needs to judge the analysis
without running it: the samples, every processing step with its parameters,
the indices, the exploratory PARAFAC models, the final model with its
validation and its outlier diagnostics, and how to repeat it. Figures are
embedded as images, so the page can be sent by e-mail or archived as it is.
Needs matplotlib (``pip install "eemkit[plot]"``); call it from the thread
that owns matplotlib (in the application, the GUI thread).
"""

from __future__ import annotations

import base64
import html
import io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

#: steps whose parameters are only counts of samples (shown, but not as method)
_COUNT_PREFIX = "n_"

_CSS = """
:root { --bg:#ffffff; --fg:#1b1b1a; --muted:#6b6a65; --line:#e1e0d9; --card:#f7f6f2;
        --accent:#2a78d6; --warn:#b4540a; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#161615; --fg:#ecebe6; --muted:#a4a39c; --line:#34332f; --card:#1f1e1c;
          --accent:#6da7ec; --warn:#f0a35e; }
  img { background:#ffffff; border-radius:4px; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { max-width:1100px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:1.7rem; margin:0 0 4px; }
h2 { font-size:1.25rem; margin:40px 0 8px; padding-top:8px; border-top:1px solid var(--line); }
h3 { font-size:1.02rem; margin:22px 0 6px; }
p, li { max-width:75ch; }
.muted { color:var(--muted); }
.warn { color:var(--warn); }
nav { margin:12px 0 0; display:flex; flex-wrap:wrap; gap:6px 14px; font-size:.9rem; }
a { color:var(--accent); }
.stats { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px;
         margin:12px 0; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:10px 12px; }
.stat b { display:block; font-size:1.25rem; font-variant-numeric:tabular-nums; }
.stat span { color:var(--muted); font-size:.82rem; }
.table { overflow-x:auto; margin:8px 0 4px; }
table { border-collapse:collapse; font-size:.85rem; font-variant-numeric:tabular-nums; }
th, td { border-bottom:1px solid var(--line); padding:4px 10px; text-align:right;
         white-space:nowrap; }
th { color:var(--muted); font-weight:600; }
td:first-child, th:first-child { text-align:left; }
table.wrap td, table.wrap th { text-align:left; white-space:normal; vertical-align:top; }
table.wrap td:nth-child(3) { min-width:22rem; }
figure { margin:14px 0; }
figure img { max-width:100%; height:auto; display:block; }
figcaption { color:var(--muted); font-size:.85rem; margin-top:4px; max-width:75ch; }
details { margin:8px 0; }
pre { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:10px;
      overflow-x:auto; font-size:.8rem; }
"""


def _esc(x) -> str:
    return html.escape(str(x))


def _table(df: pd.DataFrame, *, digits: int = 4, index: bool = True, wrap: bool = False) -> str:
    fmt = (lambda v: f"{v:.{digits}g}") if digits else None
    classes = "wrap" if wrap else None
    return ('<div class="table">' + df.to_html(index=index, border=0, escape=True,
                                               float_format=fmt, na_rep="–", classes=classes)
            + "</div>")


def _params(params: dict) -> str:
    def value(v) -> str:
        if isinstance(v, dict) and {"start", "stop", "n"} <= set(v):
            step = f", step {v['step']:g}" if v.get("step") else ""
            return f"{v['start']:g}–{v['stop']:g} nm ({v['n']} points{step})"
        if isinstance(v, dict):
            return "{" + ", ".join(f"{k}: {value(x)}" for k, x in v.items()) + "}"
        if isinstance(v, list):
            return "[" + ", ".join(value(x) for x in v) + "]"
        if isinstance(v, float):
            return f"{v:.6g}"
        return str(v)

    return "; ".join(f"{k} = {value(v)}" for k, v in params.items())


def _figure(fig, caption: str) -> str:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return (f'<figure><img alt="{_esc(caption)}" src="data:image/png;base64,{data}">'
            f"<figcaption>{_esc(caption)}</figcaption></figure>")


def _stat(value: str, label: str) -> str:
    return f'<div class="stat"><b>{_esc(value)}</b><span>{_esc(label)}</span></div>'


def _history_table(history: list[dict]) -> pd.DataFrame:
    rows = []
    for i, e in enumerate(history, 1):
        params = e.get("params", {})
        method = {k: v for k, v in params.items() if not k.startswith(_COUNT_PREFIX)}
        counts = {k: v for k, v in params.items() if k.startswith(_COUNT_PREFIX)}
        rows.append({"#": i, "step": e["step"], "parameters": _params(method),
                     "samples": ", ".join(f"{k[2:]}={v}" for k, v in counts.items()),
                     "eemkit": e.get("eemkit_version", "")})
    return pd.DataFrame(rows).set_index("#")


def _samples_section(ds: xr.Dataset) -> str:
    from eemkit.parafac.outliers import sample_labels

    out = [f"<p>{ds.sizes['sample']} samples, {ds.sizes['ex']} excitation × "
           f"{ds.sizes['em']} emission wavelengths "
           f"({float(ds.ex.min()):g}–{float(ds.ex.max()):g} nm × "
           f"{float(ds.em.min()):g}–{float(ds.em.max()):g} nm).</p>"]
    for c in sample_labels(ds):
        counts = pd.Series(ds[c].values.astype(str)).value_counts().sort_index()
        if 1 < counts.size <= 24 and c not in ("stratum", "notes", "info", "flags", "status"):
            out.append(f"<h3>Samples by {_esc(c)}</h3>"
                       + _table(counts.rename("samples").to_frame().T, index=False))
    return "".join(out)


def write_report(
    path: str | Path,
    settings: dict,
    *,
    corrected: xr.Dataset | None = None,
    indices: pd.DataFrame | None = None,
    exploration=None,
    model: xr.Dataset | None = None,
    split: xr.Dataset | None = None,
    title: str | None = None,
    n_residual_samples: int = 3,
) -> Path:
    """Write the HTML report of an analysis; returns its path.

    Every argument except ``path`` and ``settings`` is optional: the report
    contains the sections for the results given. ``corrected`` is the dataset
    after all corrections (the model's samples are taken from it for the
    residual figures); ``exploration`` is the result of
    :func:`eemkit.pipeline.explore`.
    """
    import matplotlib

    from eemkit import parafac as P
    from eemkit import plot
    from eemkit.core.history import get_history
    from eemkit.pipeline import dumps_settings, versions

    del matplotlib  # imported only to fail early when it is missing
    path = Path(path)
    cmap = settings.get("display", {}).get("eem_colours", "blues")
    title = title or "eemkit analysis report"
    ver = versions()
    parts: list[str] = []
    toc: list[tuple[str, str]] = []

    def section(anchor: str, heading: str, body: str) -> None:
        toc.append((anchor, heading))
        parts.append(f'<h2 id="{anchor}">{_esc(heading)}</h2>{body}')

    # --- data and processing ------------------------------------------------
    if corrected is not None:
        section("samples", "Samples", _samples_section(corrected))
        hist = get_history(corrected)
        body = ("<p>Every step applied to the EEMs, in order, with its parameters "
                "(from the processing history stored in the data).</p>"
                + _table(_history_table(hist), digits=0, wrap=True) if hist else
                '<p class="warn">The data carry no processing history: they were not '
                "processed with eemkit, so the steps cannot be listed.</p>")
        section("processing", "Processing", body)

    # --- indices --------------------------------------------------------------
    if indices is not None:
        labels = {"replicate", "site", "pair_id", "variant"}
        num = indices.select_dtypes("number").dropna(axis=1, how="all")
        num = num[[c for c in num.columns if c not in labels]]
        desc = num.describe().T[["count", "mean", "std", "min", "max"]]
        body = ("<p>Summary over all samples; the full table is in <code>indices.csv</code>."
                "</p>" + _table(desc))
        if "cdom_notes" in indices:
            n_notes = int((indices["cdom_notes"].fillna("").astype(str) != "").sum())
            if n_notes:
                body += (f'<p class="warn">{n_notes} sample(s) have CDOM values left empty '
                         "because the signal was too low; the reason is in the "
                         "<code>cdom_notes</code> column.</p>")
        section("indices", "Indices and CDOM metrics", body)

    # --- exploration ----------------------------------------------------------
    if exploration is not None:
        t = exploration.table.copy()
        body = ("<p>One model per number of components, each with split-half validation "
                "(Murphy et al. 2013). EEMqual = fit × core consistency × split-half "
                "(Bro & Vidal 2011).</p>" + _table(t))
        thr = settings["parafac"]["split_half"]["threshold"]
        body += _figure(plot.rank_diagnostics(t, threshold=thr,
                                              chosen=settings["parafac"]["final"].get("rank")),
                        "Explained variance, core consistency and split-half congruence "
                        "against the number of components.")
        if len(exploration.models) > 1:
            cr = P.compare_ranks(exploration.models)
            body += ("<h3>How components change when one is added</h3>"
                     "<p>Components of each rank paired with those of the next; TCC and SSC "
                     "near 1 mean the component stays the same.</p>" + _table(cr, index=False))
        section("exploration", "Exploratory PARAFAC models", body)

    # --- final model ----------------------------------------------------------
    if model is not None:
        a = model.attrs
        stats = [_stat(f"{model.sizes['component']}", "components"),
                 _stat(f"{a['explained_variance_pct']:.3f} %", "explained variance"),
                 _stat(f"{a['core_consistency_pct']:.1f} %", "core consistency"),
                 _stat(f"{a['n_init_at_best_minimum']}/{a['n_init']}",
                       "random starts at the best minimum"),
                 _stat(f"{model.sizes['sample']}", "samples in the model")]
        if split is not None:
            q = P.eemqual(model, split)
            stats += [_stat(f"{split.attrs['min_tcc']:.4f}", "split-half min. TCC"),
                      _stat("validated" if split.attrs["validated"] else "NOT validated",
                            f"split-half, threshold {split.attrs['threshold']}"),
                      _stat(f"{q['eemqual']:.3f}", "EEMqual")]
        body = '<div class="stats">' + "".join(stats) + "</div>"
        body += _figure(plot.components(model, split, cmap=cmap),
                        "Components: EEM (top) and excitation and emission loadings "
                        "(bottom); grey lines are the split-half models.")
        if split is not None:
            rows = []
            for i, test in enumerate(split["test"].values):
                for j, c in enumerate(split["component"].values):
                    rows.append({"test": test, "component": f"C{c}",
                                 "TCC ex": split.tcc_ex.values[i, j],
                                 "TCC em": split.tcc_em.values[i, j],
                                 "SSC ex": split.ssc_ex.values[i, j]
                                 if "ssc_ex" in split else np.nan,
                                 "SSC em": split.ssc_em.values[i, j]
                                 if "ssc_em" in split else np.nan})
            body += ("<h3>Split-half validation</h3><p>Design S4C6T3; the decision uses Tucker "
                     "congruence (TCC); SSC (Wünsch et al. 2019) is shown for reference.</p>"
                     + _table(pd.DataFrame(rows), index=False))
        body += ("<h3>Correlation of the components across samples</h3>"
                 "<p>Spearman correlation of Fmax. Components that always vary together may "
                 "be one source split in two, or sources this dataset cannot separate.</p>"
                 + _table(P.component_correlations(model), digits=3))
        fmax = model["fmax"].to_pandas()
        fmax.columns = [f"C{c} Fmax" for c in fmax.columns]
        body += ("<h3>Fmax</h3><p>Summary over samples; the full table is in "
                 "<code>parafac_*comp_fmax.csv</code>.</p>"
                 + _table(fmax.describe().T[["mean", "std", "min", "max"]]))
        section("model", "Final PARAFAC model", body)

        # --- outliers ---------------------------------------------------------
        diag = P.sample_diagnostics(model)
        diag = diag.drop(columns=[c for c in diag.columns if c == "stratum" or (
            diag[c].dtype == object and diag[c].astype(str).str.strip().eq("").all())])
        body = ("<p>Samples with high leverage pull the model towards themselves; samples "
                "with a high relative residual are not described by it. No threshold is "
                "applied: look at the samples at the top of the list and at their residual "
                "EEMs.</p>" + _table(diag.head(10)))
        body += _figure(plot.leverage(model), "Sample leverage against normalised residual; "
                        "the samples furthest out are labelled.")
        if corrected is not None:
            body += _figure(
                plot.residual_eems(model, corrected, n=n_residual_samples, cmap=cmap),
                f"Measured, modelled and residual EEM of the {n_residual_samples} samples "
                "with the highest relative residual; structure in the residual shows what "
                "the model misses.")
            body += _figure(plot.spectral_residuals(P.spectral_residuals(model, corrected)),
                            "Residual by wavelength, over all samples: relative sum of squares "
                            "(top) and mean residual (bottom). High values at the edges of "
                            "the range or along scatter bands are common.")
        section("outliers", "Outlier diagnostics", body)

    # --- reproducibility ------------------------------------------------------
    vt = pd.DataFrame([ver]).T.rename(columns={0: "version"})
    body = ("<p>The settings below, with the same data and eemkit version, repeat this "
            "analysis: <code>eemkit run settings.toml</code> or, in the application, "
            "<i>File → Open project</i>.</p>" + _table(vt, digits=0)
            + "<details><summary>Settings (TOML)</summary><pre>"
            + _esc(dumps_settings(settings)) + "</pre></details>")
    section("reproduce", "Software and settings", body)

    nav = "".join(f'<a href="#{a}">{_esc(h)}</a>' for a, h in toc)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head><body><main>"
        f"<h1>{_esc(title)}</h1><p class=\"muted\">Written {now} by eemkit "
        f"{_esc(ver['eemkit'])}.</p><nav>{nav}</nav>" + "".join(parts)
        + '<p class="muted" style="margin-top:40px">References: Bro & Vidal 2011, '
        "Chemom. Intell. Lab. Syst. 106:86–92; Murphy et al. 2013, Anal. Methods "
        "5:6557–6566; Wünsch et al. 2019, Anal. Methods 11:888–893.</p>"
        "</main></body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
