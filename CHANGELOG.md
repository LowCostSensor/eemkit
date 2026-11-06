# Changelog

All notable changes are listed here. Versions follow
[semantic versioning](https://semver.org/).

## Unreleased

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
