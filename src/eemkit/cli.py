"""Command line: check a project and run the whole chain without the application.

::

    eemkit check project.toml
    eemkit run project.toml [--output DIR] [--jobs N] [--no-explore] [--no-figures]

``run`` does what the desktop application does, in the same order and with
the same settings file: corrections, indices and CDOM metrics, exploratory
PARAFAC models (unless ``--no-explore``), the final model when
``parafac.final.rank`` is set, and the export to the output folder
(``project.output_dir``, or ``--output``). Paths in the project file are
relative to the folder that contains it. Exit status: 0 on success, 1 when the
project has a problem, 2 for a wrong command line.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from pathlib import Path

from eemkit import __version__
from eemkit.errors import EEMKitError, EEMKitWarning

#: lines of a long problem list that ``check`` prints
MAX_LINES = 10


def _say(msg: str) -> None:
    print(msg, flush=True)


def _show_warning(message, category, filename, lineno, file=None, line=None):
    prefix = "warning" if issubclass(category, EEMKitWarning) else category.__name__
    print(f"  {prefix}: {message}", file=sys.stderr, flush=True)


def _project(path: str):
    from eemkit import pipeline

    p = Path(path)
    if not p.is_file():
        raise EEMKitError(f"{p}: no such project file")
    # absolute(), not resolve(): keep a mapped drive letter (Windows) as given
    return pipeline.load_settings(p), p.absolute().parent


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    return True


def _output_dir(settings: dict, base: Path, override: str | None) -> Path:
    v = override or settings["project"].get("output_dir", "")
    if not v:
        raise EEMKitError("no output folder: set project.output_dir or pass --output")
    out = Path(v)
    out = Path(os.path.normpath(out if out.is_absolute()
                                else (Path.cwd() if override else base) / out))
    root = settings["project"].get("data_root", "")
    if root:
        root_path = Path(os.path.normpath(root if Path(root).is_absolute() else base / root))
        if _inside(out, root_path):
            raise EEMKitError(f"the output folder {out} is inside the data folder "
                              f"{root_path}, which is read-only; choose another one")
    return out


def check(args: argparse.Namespace) -> int:
    """Report what ``run`` would read and which settings are missing."""
    from eemkit import pipeline
    from eemkit.io.pairing import read_pairing

    settings, base = _project(args.project)
    problems: list[str] = []
    notes: list[str] = []
    proj = settings["project"]
    for key in ("data_root", "pairing"):
        if not proj.get(key):
            problems.append(f"project.{key} is not set")
    if not problems:
        root = Path(proj["data_root"])
        root = root if root.is_absolute() else base / root
        if not root.is_dir():
            problems.append(f"data folder not found: {root}")
        else:
            pairing = Path(proj["pairing"])
            pairing = pairing if pairing.is_absolute() else base / pairing
            try:
                table = read_pairing(pairing, data_root=root)
            except EEMKitError as e:
                lines = str(e).splitlines()
                if len(lines) > MAX_LINES + 1:
                    lines = lines[:MAX_LINES + 1] + [f"  ... and {len(lines) - MAX_LINES - 1} "
                                                     "more"]
                problems.append("\n    ".join(lines))
            else:
                n_in = int(table["include"].sum())
                notes.append(f"pairing table: {len(table)} rows, {n_in} included")
                if n_in == 0:
                    problems.append("no row of the pairing table is included")
    for key in ("absorbance_path_length_cm", "fluorescence_path_length_cm"):
        if settings["inner_filter"].get(key) in (None, ""):
            problems.append(f"inner_filter.{key} is not set (it depends on your cuvettes)")
    try:
        notes.append(f"output folder: {_output_dir(settings, base, None)}")
    except EEMKitError as e:
        problems.append(str(e))
    rank = settings["parafac"]["final"].get("rank")
    notes.append(f"final PARAFAC model: {rank} components" if rank else
                 "final PARAFAC model: not chosen yet (parafac.final.rank); "
                 "run will fit only the exploratory models")
    unknown = sorted(set(settings) - set(pipeline.DEFAULTS))
    if unknown:
        notes.append(f"sections not used by eemkit {__version__}: {unknown}")

    for n in notes:
        _say(f"  {n}")
    for p in problems:
        _say(f"  problem: {p}")
    _say("OK" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def run(args: argparse.Namespace) -> int:
    """The whole chain, as in the application."""
    from eemkit import pipeline

    settings, base = _project(args.project)
    out = _output_dir(settings, base, args.output)
    t0 = time.perf_counter()

    def step(msg: str) -> None:
        _say(f"[{time.perf_counter() - t0:6.1f} s] {msg}")

    def progress(msg: str, i: int, n: int) -> None:
        step(f"  {msg} ({i + 1}/{n})" if n and i < n else f"  {msg}")

    step("reading the samples of the pairing table")
    raw = pipeline.load(settings, base=base)
    step(f"  {raw.sizes['sample']} samples")
    step("corrections up to Raman units")
    after_raman = pipeline.correct_until_raman(raw, settings, base=base)
    step("scatter removal and crop")
    corrected = pipeline.finish_corrections(after_raman, settings)
    step("fluorescence indices")
    indices = pipeline.compute_indices(after_raman, settings)
    if "absorbance" in after_raman:
        step("CDOM metrics")
        indices = indices.join(pipeline.compute_absorbance(after_raman, settings))

    ds = pipeline.parafac_input(corrected, settings)
    exploration = model = split = None
    if not args.no_explore:
        step("exploratory PARAFAC models")
        exploration = pipeline.explore(ds, settings, progress=progress, n_jobs=args.jobs)
        for line in exploration.table.round(3).to_string().splitlines():
            _say(f"    {line}")
    if settings["parafac"]["final"].get("rank"):
        model, split = pipeline.fit_final(ds, settings, progress=progress, n_jobs=args.jobs)
        a = model.attrs
        step(f"  explained {a['explained_variance_pct']:.3f} %, core consistency "
             f"{a['core_consistency_pct']:.1f} %, {a['n_init_at_best_minimum']}/{a['n_init']} "
             f"starts at the best minimum, split-half min TCC {split.attrs['min_tcc']:.4f} "
             f"({'validated' if split.attrs['validated'] else 'NOT validated'})")
    else:
        step("no final model: set parafac.final.rank after looking at the exploration")

    figures, report = not args.no_figures, not args.no_report
    if figures or report:
        try:
            import matplotlib

            matplotlib.use("Agg")
        except ImportError:
            step("matplotlib is not installed: figures and report skipped "
                 "(pip install \"eemkit[plot]\")")
            figures = report = False
    meta = settings["parafac"]["final"].get("openfluor", {}) or {}
    step(f"writing results to {out}")
    paths = pipeline.export_results(out, settings, corrected=corrected, indices=indices,
                                    exploration=exploration, model=model, split=split,
                                    openfluor={k: v for k, v in meta.items() if v},
                                    figures=figures, report=report)
    step(f"done: {len(paths)} files")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eemkit", description="EEM processing and PARAFAC modelling from a project file.")
    parser.add_argument("--version", action="version", version=f"eemkit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="check a project file, its data folder and pairing table")
    c.add_argument("project", help="project settings file (.toml)")
    c.set_defaults(func=check)

    r = sub.add_parser("run", help="run the whole chain and export the results")
    r.add_argument("project", help="project settings file (.toml)")
    r.add_argument("-o", "--output", help="output folder (default: project.output_dir)")
    r.add_argument("-j", "--jobs", type=int, default=None,
                   help="PARAFAC random starts run at the same time (default: all processors; "
                        "the result does not depend on it)")
    r.add_argument("--no-explore", action="store_true",
                   help="skip the exploratory models; fit only parafac.final.rank")
    r.add_argument("--no-figures", action="store_true", help="do not write figures")
    r.add_argument("--no-report", action="store_true", help="do not write report.html")
    r.set_defaults(func=run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "jobs", None) is not None and args.jobs < 1:
        print("eemkit: --jobs must be at least 1", file=sys.stderr)
        return 2
    warnings.showwarning = _show_warning
    try:
        return args.func(args)
    except EEMKitError as e:
        print(f"eemkit: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
