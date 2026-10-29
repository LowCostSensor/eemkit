# eemkit

Python tools for excitation-emission matrices (EEMs) of dissolved organic
matter: instrument import, corrections, fluorescence indices and validated
PARAFAC modelling.

**Status:** early development (phase 1: readers and data model).

## Install (development)

In any Python >= 3.11 environment:

```bash
pip install -e ".[dev]"
pytest
```

Tests that need the real dataset are skipped unless `EEMKIT_TEST_DATA` points
to its root folder.

## Quick look

```python
import eemkit

eem = eemkit.read_cary_eclipse("Sample 21.csv")      # xarray.Dataset (ex, em)
ab = eemkit.read_cary60("Sample 21 abs.csv")         # xarray.Dataset (cycle, wavelength)

ds = eemkit.load_dataset("pairing.csv", data_root="raw_data/")
ds["intensity"]          # (sample, ex, em) on a common emission grid
ds["blank_intensity"]    # matching Milli-Q blank per sample
ds["absorbance"]         # (sample, wavelength), mean of the instrument cycles
eemkit.get_history(ds)   # every processing step with its parameters
```

## Data model

See `docs/data_model.md`.
