# Changelog

All notable changes are listed here. Versions follow
[semantic versioning](https://semver.org/).

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
