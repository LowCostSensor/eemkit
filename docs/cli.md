# Command line

The `eemkit` command runs a project without the application: the same
settings file, the same steps, the same results. It is the way to rerun an
analysis on a server, in a batch script, or months later.

```bash
eemkit check project.toml
eemkit run project.toml
```

If the `eemkit` command is not found (Python's `Scripts` folder is not on the
PATH), use `python -m eemkit` instead: `python -m eemkit run project.toml`.

## `eemkit check`

Reads the project file and reports, without processing anything:

* how many rows the pairing table has and how many are included;
* every file of an included row that is missing (the first ten, then a count);
* settings that have no default and are not set, such as the cuvette path
  lengths;
* the output folder, and whether the final PARAFAC model has been chosen.

It ends with `OK` (exit status 0) or the number of problems (exit status 1).

## `eemkit run`

Runs the whole chain in the order of the application:

1. reads the included samples;
2. corrections up to Raman units, then scatter removal and crop;
3. fluorescence indices and, when absorbance spectra are paired, CDOM metrics;
4. the exploratory PARAFAC models for every rank in `parafac.ranks`, with
   split-half validation (the table is printed);
5. the final model, if `parafac.final.rank` is set;
6. the export: corrected EEMs, indices, models, OpenFluor file, figures,
   `report.html` (the whole analysis on one page), settings and processing
   record.

| Option | Meaning |
| --- | --- |
| `-o`, `--output DIR` | Output folder; default `project.output_dir`. It may not be inside the data folder, which is read-only. |
| `-j`, `--jobs N` | PARAFAC random starts run at the same time; default every processor. The result does not depend on it. |
| `--no-explore` | Skip the exploratory models and fit only `parafac.final.rank`. |
| `--no-figures` | Do not write figures (they need matplotlib: `pip install "eemkit[plot]"`). |
| `--no-report` | Do not write `report.html` (it also needs matplotlib). |

Paths in the project file are relative to the folder that contains it.
Warnings are printed as they occur; an error stops the run with exit status 1
and a message that names the setting or the file.

Example on the Ombrone dataset (205 samples; abridged):

```text
$ eemkit run config/ombrone_project.toml -o results
[   0.0 s] reading the samples of the pairing table
[   9.8 s]   205 samples
[   9.8 s] corrections up to Raman units
[   9.9 s] scatter removal and crop
[  10.0 s] fluorescence indices
[  10.1 s] CDOM metrics
  warning: CDOM metrics: 40 sample(s) with values left empty (low signal); see the cdom_notes column
[  10.1 s] exploratory PARAFAC models
[  10.1 s]   2 components: fitting (1/12)
...
          explained_pct  core_consistency_pct  ...  split_half_min_tcc  split_half_validated
    rank
    2            97.933                99.444  ...               0.989                  True
    3            99.016                85.136  ...               0.992                  True
    4            99.209              -124.439  ...               0.175                 False
...
[1214.2 s]   final 3-component model (1/2)
[1485.1 s]   split-half validation (2/2)
[1705.4 s]   explained 99.017 %, core consistency 85.5 %, 20/20 starts at the best minimum, split-half min TCC 0.9915 (validated)
[1705.6 s] writing results to results
[1708.0 s] done: 16 files
```

The exploration of six ranks with split-half validation is the slow part
(about 20 minutes here); once the rank is chosen, `--no-explore` reruns only
the final model.
