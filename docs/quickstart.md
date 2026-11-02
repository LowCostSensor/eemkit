# Quick start

This page runs the whole chain from Python: raw instrument files to a
validated PARAFAC model. The [desktop application](app-guide.md) does the same
without code, from the same settings file.

## 1. Pair the files

eemkit never guesses which blank or absorbance spectrum belongs to which
sample. A CSV table, checked by a person, lists one sample per row:

| column | required | content |
|---|---|---|
| `sample_id` | yes | unique identifier used throughout the analysis |
| `eem_file` | yes | fluorescence file, relative to the data folder |
| `include` | yes | `yes` / `no` |
| `eem_blank_file` | no | blank EEM (e.g. Milli-Q) measured with the sample |
| `abs_file` | no | absorbance spectrum of the same sample |
| `abs_blank_file` | no | absorbance blank |
| any other column | no | kept as sample metadata (river, site, date, …) |

A first draft can be made from a folder scan; every drafted row starts with
`include = no` and the reason for each choice in `pairing_notes`, so it is used
only after you check it:

```python
import eemkit

inventory = eemkit.scan_folder("raw_data/")        # classifies every CSV by its header
draft = eemkit.suggest_pairing(inventory)
draft.to_csv("pairing.csv", index=False)           # check it, then set include = yes
```

## 2. Write the settings

One TOML file holds the paths and every parameter; keys you leave out take the
defaults in `eemkit.pipeline.DEFAULTS`, except values that depend on your
measurement, which must be given.

```toml
[project]
data_root = "raw_data"          # read only: eemkit never writes there
pairing = "pairing.csv"
output_dir = "results"

[inner_filter]                  # cuvette path lengths: no default
absorbance_path_length_cm = 1.0
fluorescence_path_length_cm = 1.0

[scatter]
raman1 = [8, 8]                 # band widths below/above, nm
zero_below_rayleigh = 10

[crop]
ex_min = 240

[parafac]
ranks = [2, 3, 4, 5, 6, 7]
[parafac.split_half]
stratify = ["river", "campaign"]
```

## 3. Run the chain

```python
from eemkit import pipeline

s = pipeline.load_settings("project.toml")
raw = pipeline.load(s, base=".")                         # paths relative to base
after_raman = pipeline.correct_until_raman(raw, s, base=".")
corrected = pipeline.finish_corrections(after_raman, s)  # scatter removed, cropped
indices = pipeline.compute_indices(after_raman, s)

ds = pipeline.parafac_input(corrected, s)                # drops parafac.exclude
exploration = pipeline.explore(ds, s)
print(exploration.table)                                 # choose the number of components
```

Look at `exploration.table` (explained variance, core consistency, split-half
congruence) and at the components of each model, then set
`parafac.final.rank` and fit the final model:

```python
s["parafac"]["final"]["rank"] = 3
model, split = pipeline.fit_final(ds, s)
pipeline.export_results("results", s, corrected=corrected, indices=indices,
                        exploration=exploration, model=model, split=split)
```

`results/` then holds the corrected EEMs (netCDF), indices, PARAFAC tables,
an OpenFluor file, figures, the settings used and `processing_record.json`
with the software versions and every processing step.

## Step by step

Every step is also a function of its own, for analyses that need a different
order of work:

```python
from eemkit import corrections as C, indices as I, parafac as P

ds = eemkit.load_dataset("pairing.csv", data_root="raw_data/")
ds = C.subtract_absorbance_blank(ds)
ds = C.correct_inner_filter(ds, absorbance_path_length_cm=1, fluorescence_path_length_cm=1)
ds = C.subtract_blank(ds)
ds = C.normalize_raman(ds, ex=350, em_range=(381, 426))
table = I.compute_indices(ds, ex_method="linear")
ds = C.remove_scatter(ds, widths={"rayleigh1": (10, 10), "raman1": (8, 8)})
ds = C.crop(ds, ex=(240, None))

model = P.fit_parafac(ds, 3, n_init=20, normalization="norm", tol=1e-8)
check = P.split_half(ds, 3)
eemkit.get_history(model)       # every step with its parameters
```
