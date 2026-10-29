# Data model

eemkit keeps data in `xarray.Dataset` objects, so every array carries its
wavelength axes and every dataset carries its metadata and processing history.
Datasets can be saved with `ds.to_netcdf()` without losing either.

## Single measurements

| reader | variable | dims | coordinates |
|---|---|---|---|
| `read_cary_eclipse` | `intensity` (a.u.) | `ex`, `em` | `scan_time(ex)` |
| `read_cary60` | `absorbance` (decadic) | `cycle`, `wavelength` | `scan_time(cycle)` |
| `mean_cycles` | `absorbance`, `absorbance_sd` | `wavelength` | |

Readers return values exactly as exported; they never correct, subtract or
normalise. Axes are sorted ascending. Attributes hold the file path
(`source_file`), the sample name written inside the file (`sample_name`, which
may differ from the file name), collection times and the instrument settings
from the log (slits, PMT voltage, `corrected_spectra`, data interval, …).

## Multi-sample dataset

`load_dataset(pairing.csv, data_root=...)` returns:

| variable | dims | content |
|---|---|---|
| `intensity` | `sample, ex, em` | sample EEMs on the common emission grid |
| `blank_intensity` | `sample, ex, em` | blank paired with each sample (NaN if none) |
| `absorbance`, `absorbance_sd` | `sample, wavelength` | mean and SD of the cycles (NaN if none) |
| `blank_absorbance` | `sample, wavelength` | absorbance blank |

* Every pairing-table column becomes a `sample` coordinate (`river`, `site`, …).
* File and instrument metadata are prefixed `eem_`, `eem_blank_`, `abs_`,
  `abs_blank_`. A value shared by all samples is a dataset attribute;
  a value that differs between samples is a `sample` coordinate.

## Grids

Emission scans of the Cary Eclipse are not exactly evenly spaced, and Cary 60
wavelengths are a few hundredths of a nm off integers. `load_dataset` resamples
every spectrum by linear interpolation onto one regular grid per axis:

* given explicitly (`em_grid=`, `wavelength_grid=`), or
* inferred by `infer_common_grid`: the coarsest native step, over the range
  covered by every file. Grid points more than `tolerance` (0.1 nm) outside a
  file's range are NaN; nothing is extrapolated.

## Processing history

`get_history(ds)` returns the list of steps applied, each with its parameters,
eemkit version and UTC time. It is stored as JSON in
`ds.attrs["eemkit_history"]`.
