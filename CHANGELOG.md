# Changelog

All notable changes are listed here. Versions follow
[semantic versioning](https://semver.org/).

## 0.4.2 (2026-11-25)

One fix in the application. Results do not change.

* **Sensor channels view readable on small or scaled screens.** On a laptop
  screen at 150 % scaling the channel table and the share table took all the
  height and the figure was squeezed into a strip a few pixels high. The
  figure now keeps a readable height (the view scrolls when the window is
  too small), the two tables sit side by side, each only as tall as its rows,
  and the message line takes no space when it is empty. With many components
  or a narrow window the tables scroll sideways instead of cutting the numbers
  (checked with 7 components and 4 channels).

## 0.4.1 (2026-11-23)

Documentation only: the README figure now shows the PARAFAC model and the
weight of each component in the application (the PyPI page takes its text
and image from the README of the released version). No code changes.

## 0.4.0 (2026-11-23)

Sensor channels (LED and filter) in the application, the figures and the
report. Nothing that existed before changes.

* **Sensor channels in the application, the figures and the report.** The
  PARAFAC page has a new view, `Sensor channels`: type the LED wavelength and
  the filter band of each channel and see, for the final or any exploratory
  model, which components it follows (the channels on the mean modelled EEM,
  the share of each component per channel with its range between samples).
  The channels are saved in the project (`[channels.NAME]`), and with them
  the export writes `parafac_*comp_channels.csv`,
  `parafac_*comp_channel_sensitivity.csv` and `figures/channel_signals`; the
  HTML report gets a `Sensor channels` section. New figure
  `plot.channel_signals`; `pipeline.channel_signals`, `channel_specs` and
  `channel_tables` do the same from scripts and the command line
  (`eemkit run`). `component_signals` now also returns where each channel
  sits (`ex_min`, `ex_max`, `em_min`, `em_max`).

## 0.3.0 (2026-11-23)

A new function to check what a filter-based optical channel sees, and a fix
to the indices table. The values of everything that could be computed in 0.2.0
are unchanged.

* New: `parafac.component_signals(model, channels)`: the signal each PARAFAC
  component gives in an LED and filter channel, for every sample (score x
  excitation loading weighted by the LED x emission loading integrated over the
  filter), with the share of each component and the channel's sensitivity.
  Meant to check whether a channel (e.g. a tryptophan-like one) follows the
  component it is meant to follow.
* **Fixed: one index that cannot be computed no longer stops the whole
  index table.** In 0.2.0, `compute_indices` (and so the application, the
  command line and `pipeline.compute_indices`) raised as soon as one index or
  peak needed a wavelength outside the measured range: for example, on data
  whose emission starts at 300.3 nm (the drEEM tutorial data), HIX needs
  300 nm and no index at all was returned. Now that index is left empty
  (NaN) with an `EEMKitWarning` giving the reason, every other index and peak
  is computed, and the reasons are kept in
  `df.attrs["settings"]["not_computed"]` (also in the JSON file of
  `export_indices`). Each peak is computed on its own, so one peak outside
  the data does not empty the others. `on_error="raise"` keeps the old,
  strict behaviour. Values of the indices that can be computed do not
  change.
* HTML report: index columns that are empty for every sample are listed with
  their reason, instead of being left out of the summary without a word.

## 0.2.0 (2026-11-06)

Other fluorometers, diluted samples, zap, PARAFAC model comparison and
diagnostics, new samples on a fitted model, an HTML report and a command
line; benchmarked against drEEM as well as staRdom. One result changes: core
consistency is now computed as in drEEM (first item).

* **Changed: core consistency is now computed as the N-way toolbox's
  `corcond` (the copy used by drEEM)**: loading vectors of each component
  scaled to the same norm, core fitted to the observed cells only (missing
  values left out, not filled with the model), denominator the sum of squares
  of the core. eemkit 0.1 gave values that depended on how each component's
  size was split between the modes; values now match drEEM 2.26.03 to 10⁻⁶ %
  (tested). They are usually lower than before for good models (Ombrone,
  3 components: 75.0 % instead of 85.5 %) and no longer strongly negative for
  overfactored ones; EEMqual changes with them. The models themselves do not
  change. Rank-1 models are now computed too, instead of set to 100.
* Application: the window no longer grows wider than the screen once a final
  PARAFAC model is shown (its summary line now wraps); it fits a 1366-pixel
  wide laptop screen.
* Benchmark of the PARAFAC fit against drEEM 2.26.03 (N-way and parafac3w
  engines) on the Ombrone data: same model, Tucker congruence ≥ 0.9999.
* Command line: `eemkit check project.toml` reports missing files and
  settings; `eemkit run project.toml` runs the whole chain and exports the
  results, as the application does (also `python -m eemkit`).
* PARAFAC random starts run in parallel threads (`n_jobs`, default every
  processor); the model does not depend on it.
* README and documentation: install from PyPI, Zenodo DOI.
* Shift- and shape-sensitive congruence (`shift_shape_congruence`; Wünsch et
  al. 2019), also reported in split-half validation (`ssc_ex`, `ssc_em`).
* `eemqual` (Bro & Vidal 2011) and an `eemqual` column in the exploration
  table.
* `compare_models`, `compare_ranks` and `component_correlations` to compare
  PARAFAC models and their components.
* `project_samples`: scores of new samples on a fitted model with its spectra
  fixed, with a flag for samples the model describes worse than any of its
  own.
* PARAFAC models store each sample's data sum of squares (`data_sumsq`).
* Outlier diagnostics: `sample_diagnostics` (leverage, relative residual and
  ranks per sample), `spectral_residuals` (residual by wavelength), and the
  figures `plot.residual_eems` and `plot.spectral_residuals`.
* Other fluorometers: readers for Horiba Aqualog and Fluoromax, Hitachi
  F-7000 (over-range values to missing), Shimadzu (excitation wavelengths from
  the settings) and any text matrix; two-column absorbance files. The format
  is set in `project.instrument` / `project.absorbance_format`, and the folder
  scan follows it. Processing already done by the instrument software (e.g.
  Aqualog "Sample - Blank") must be declared in `project.already_done`: it is
  recorded, never repeated nor skipped silently. Files that do not state the
  instrument's spectral correction are marked "unknown". Tested on the
  example files of the R package eemR. In the application, an `Instrument`
  box on the Project page sets the formats and the steps already done.
* Diluted samples: optional pairing-table columns `dilution_factor` and
  `abs_dilution_factor`; absorbance rescaled to the EEM's dilution before the
  inner-filter correction (`match_absorbance_dilution`), EEMs multiplied by
  their dilution after Raman units (`correct_dilution`), CDOM metrics
  reported for the undiluted sample.
* `zap`: regions listed in the project file (`[zap]`) set to NaN after Raman
  units and recorded in the history; optional interpolation separate from the
  scatter bands (`interpolate_missing(only=...)`).
* `report.html`: the whole analysis on one self-contained page (samples,
  processing history, indices, exploration, final model, validation, outlier
  diagnostics, settings), from `eemkit.report.write_report`, the export
  (`report=True`), the command line and the application's Export page.

## 0.1.0 (2026-11-05)

First public release.

* Readers for Agilent Cary Eclipse 3-D EEMs and Cary 60 absorbance CSV files;
  folder scan, pairing table draft (always excluded until checked) and
  multi-sample `xarray` dataset on common wavelength grids.
* Corrections in an enforced order: instrument spectral correction,
  absorbance blank, inner filter, blank subtraction, Raman units, scatter
  removal with optional interpolation, crop. Every step is recorded in the
  processing history.
* Fluorescence indices (FI, HIX, BIX) and Coble peaks.
* CDOM metrics from the absorbance spectra (`eemkit.absorbance`): a254, a350,
  S275–295, S350–400, SR, E2:E3 and SUVA254 (with a DOC column), after a
  680–700 nm baseline correction; low-signal values are left empty with the
  reason.
* Non-negative PARAFAC with missing values, random starts, core consistency,
  leverage, split-half validation and OpenFluor export.
* Comparison of campaigns, sites and rivers (`eemkit.campaigns`): replicate
  means per site and time, design and confounding warnings, Kruskal–Wallis
  and Dunn–Holm tests within each group, Spearman correlations with site
  position and with covariates, PARAFAC composition; optional site and
  covariate tables.
* Publication figures (`eemkit.plot`), including a Cary Eclipse colour scale.
* `eemkit.pipeline`: the whole chain driven by one settings file.
* Desktop application (`eemkit-gui`, PySide6): a sidebar of steps with their
  status, light and dark themes, and a "Rivers and dates" page; a
  PyInstaller recipe for a stand-alone Windows build, which ships the
  licence texts of eemkit, Qt and every bundled package.
* Benchmarked against staRdom 1.1.32 on 205 river-water samples.
