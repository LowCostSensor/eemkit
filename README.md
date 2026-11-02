# eemkit

[![tests](https://github.com/LowCostSensor/eemkit/actions/workflows/tests.yml/badge.svg)](https://github.com/LowCostSensor/eemkit/actions/workflows/tests.yml)
[![docs](https://github.com/LowCostSensor/eemkit/actions/workflows/docs.yml/badge.svg)](https://lowcostsensor.github.io/eemkit/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

Python tools and a desktop application for fluorescence excitation-emission
matrices (EEMs) of dissolved organic matter: instrument import, corrections,
fluorescence indices and validated PARAFAC modelling, with every processing
step recorded so that an analysis can be repeated exactly.

![The eemkit desktop application: corrections of a river-water EEM](https://raw.githubusercontent.com/LowCostSensor/eemkit/main/docs/img/app/2_corrections.png)

## What it does

* **Import** Agilent Cary Eclipse 3-D EEMs and Cary 60 absorbance spectra
  (CSV "ASCII with log"), with the instrument settings from the file log.
  Samples, blanks and absorbance spectra are paired through an explicit,
  hand-editable table: nothing is matched silently.
* **Correct** in a fixed, enforced order: instrument spectral correction
  (optional), absorbance blank, inner-filter effect (Kothawala et al. 2013),
  blank subtraction, Raman units (Lawaetz & Stedmon 2009), Rayleigh and Raman
  scatter removal, crop. Values that depend on the measurement, such as cuvette
  path lengths, have no defaults.
* **Indices**: fluorescence index, humification and biological indices, Coble
  peaks.
* **PARAFAC** with non-negativity and missing values, random starts, core
  consistency, leverage and residuals, split-half validation (Murphy et al.
  2013) and export to OpenFluor.
* **Figures** for publication, and a **desktop application** (PySide6) that
  drives the whole chain without code.
* **Provenance**: data are `xarray` datasets that carry their metadata and the
  full processing history; one settings file drives both scripts and the
  application.

## Install

```bash
pip install eemkit            # library
pip install "eemkit[plot]"    # + figures (matplotlib)
pip install "eemkit[gui]"     # + desktop application
```

Python 3.11 or later. A stand-alone Windows build of the application is
attached to each [release](https://github.com/LowCostSensor/eemkit/releases).

## Quick start

```python
from eemkit import pipeline

s = pipeline.load_settings("project.toml")    # data folder, pairing table, parameters
raw = pipeline.load(s, base=".")
after_raman = pipeline.correct_until_raman(raw, s, base=".")
corrected = pipeline.finish_corrections(after_raman, s)
indices = pipeline.compute_indices(after_raman, s)

ds = pipeline.parafac_input(corrected, s)
exploration = pipeline.explore(ds, s)          # 2..7 components, split-half validation
model, split = pipeline.fit_final(ds, s)       # the number of components you chose
pipeline.export_results("results", s, corrected=corrected, indices=indices,
                        exploration=exploration, model=model, split=split)
```

Or start the application and open the same `project.toml`:

```bash
eemkit-gui
```

Every function can also be used on its own; see the
[documentation](https://lowcostsensor.github.io/eemkit/).

## Validation

On 205 river-water samples (Ombrone basin, Italy; Polvani et al. 2026) eemkit
was compared with the R package staRdom 1.1.32 (Pucher et al. 2019):

* corrected EEMs agree to a median relative difference of 2.2 × 10⁻⁴ (the
  remainder is the numerical integration of the Raman area);
* FI, BIX and Coble peaks agree to machine precision, HIX to 3 × 10⁻⁴;
* the 3-component PARAFAC models have Tucker congruence ≥ 0.999 for every
  excitation and emission loading.

The scripts and the full report are in
[ombrone-fdom](https://github.com/LowCostSensor/ombrone-fdom).

## Development

```bash
git clone https://github.com/LowCostSensor/eemkit
cd eemkit
pip install -e ".[dev]"
pytest
```

Tests that need the real dataset are skipped unless `EEMKIT_TEST_DATA` points
to its root folder. Contributions and bug reports are welcome: see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Citation

If you use eemkit, please cite it (see [CITATION.cff](CITATION.cff); a DOI is
issued on Zenodo for every release) and the methods it implements, listed in
the documentation of each step.

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE).

## References

Kothawala et al. (2013) *Limnol. Oceanogr. Methods* 11, 616–630 ·
Lawaetz & Stedmon (2009) *Appl. Spectrosc.* 63, 936–940 ·
Murphy et al. (2013) *Anal. Methods* 5, 6557–6566 ·
Polvani et al. (2026) *Environ. Pollut.* 396, 127858 ·
Pucher et al. (2019) *Water* 11, 2366.
