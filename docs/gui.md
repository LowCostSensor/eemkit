# Desktop application

```bash
python -m pip install "eemkit[gui] @ https://github.com/LowCostSensor/eemkit/archive/refs/heads/main.zip"
python -m eemkit.gui       # optionally followed by a project.toml
```

(Until eemkit is on PyPI; then `pip install "eemkit[gui]"`.) The
`eemkit-gui` command does the same as `python -m eemkit.gui` when Python's
`Scripts` folder is on the PATH.

The application is a front end to `eemkit.pipeline`: it does no processing
of its own. Its project file is the pipeline's settings TOML, so an analysis
made in the application can be rerun from a script:

```python
from eemkit import pipeline
s = pipeline.load_settings("project.toml")
raw = pipeline.load(s, base="folder/of/project.toml")
after = pipeline.correct_until_raman(raw, s)
corrected = pipeline.finish_corrections(after, s)
```

Long computations run in the background with a progress bar and a Cancel
button (cancellation takes effect after the current model fit). Warnings
raised during a computation (for example a model that did not converge) are
collected and shown with a "⚠ warnings" button in the status bar.

## Steps

The steps are listed in a sidebar; a ✓ marks the steps whose results are
ready (• when they are partly done), and a summary of the project sits below
the list. The main action of each page is the coloured button.

1. **Project and pairing.** Choose the data folder (only read, never
   written), the pairing table and an output folder. *Scan data folder*
   classifies every CSV from its header (Cary Eclipse 3-D EEM, Cary 60
   absorbance, or not recognised). *Draft pairing from scan* proposes one row
   per sample: absorbance file with the same sample name, and the only blank
   in the folder. Every drafted row starts **excluded** and yellow, with
   the reason for each choice in `pairing_notes`; rows are used only after you
   check and include them. Cells are edited by double-click; file columns
   offer the files found by the scan.
2. **Corrections.** Optional instrument spectral correction (excitation and
   emission factor files; each file is read when chosen and its range shown),
   cuvette path lengths (required, no default), Raman normalisation, scatter
   bands, crop. *Apply corrections* runs the chain in the enforced order; the
   preview shows any sample at any step, and the factors that were applied.
3. **Indices and CDOM.** FI, HIX, BIX and Coble peaks, and the
   [CDOM metrics](absorbance.md) (a254, a350, spectral slopes, SR, E2:E3,
   SUVA254 with a DOC column), as one table plotted against any sample column
   (e.g. campaign) grouped by another (e.g. river).
4. **PARAFAC.** Exploratory models for a range of components with split-half
   validation; the number-of-components diagnostics, the components of each
   model with the split-half models behind, and an outlier view (leverage vs
   residuals) from which samples can be left out. Then the final model.
5. **Rivers and dates.** [Comparison of campaigns, sites and rivers](campaigns.md)
   for any variable of the indices table or of the final model (Fmax, share of
   each component): replicate means per site and time, a warning when rivers
   and dates cannot be separated, Kruskal–Wallis and Dunn tests between
   campaigns within each river, correlations with the position along the
   river and with covariates from optional tables. *Save to output folder*
   writes the tables and figures in `campaigns/<variable>/`.
6. **Export.** Corrected EEMs, indices, PARAFAC tables, OpenFluor file and
   figures, always with `settings.toml` and `processing_record.json`
   (software versions and every processing step with its parameters).

When a setting changes, results that depended on it are discarded, so no tab
shows results that are out of date.

**View → Theme** switches between a light and a dark theme, or follows the
operating system; the choice is a preference of the computer, not of the
project. **View → EEM colours** switches every EEM plot (previews, components, exported
figures) between the Cary Eclipse rainbow (default) and a single-hue blue
scale for print. The choice is saved in the project file.

## Stand-alone build

`packaging/eemkit-gui.spec` builds a folder with an executable that runs
without a Python installation:

```
git clone https://github.com/LowCostSensor/eemkit && cd eemkit
pip install ".[gui]" pyinstaller
pyinstaller packaging/eemkit-gui.spec --noconfirm
```

With conda, build from an activated environment (`conda activate ...`):
conda-forge keeps the Qt DLLs in `Library/bin`, which PyInstaller finds only
on the PATH. On Windows use a short `--distpath` (Qt plugin paths exceed the
260-character limit in deep folders). The Windows build is about 160 MB. If the
application closes at start-up, the reason is written to `eemkit-crash.log`
in the temporary folder.
