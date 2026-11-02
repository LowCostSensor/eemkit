# Changelog

All notable changes are listed here. Versions follow
[semantic versioning](https://semver.org/).

## 0.1.0 (2026-11-02)

First public release.

* Readers for Agilent Cary Eclipse 3-D EEMs and Cary 60 absorbance CSV files;
  folder scan, pairing table draft (always excluded until checked) and
  multi-sample `xarray` dataset on common wavelength grids.
* Corrections in an enforced order: instrument spectral correction,
  absorbance blank, inner filter, blank subtraction, Raman units, scatter
  removal with optional interpolation, crop. Every step is recorded in the
  processing history.
* Fluorescence indices (FI, HIX, BIX) and Coble peaks.
* Non-negative PARAFAC with missing values, random starts, core consistency,
  leverage, split-half validation and OpenFluor export.
* Publication figures (`eemkit.plot`), including a Cary Eclipse colour scale.
* `eemkit.pipeline`: the whole chain driven by one settings file.
* Desktop application (`eemkit-gui`, PySide6) and a PyInstaller recipe for a
  stand-alone Windows build.
* Benchmarked against staRdom 1.1.32 on 205 river-water samples.
