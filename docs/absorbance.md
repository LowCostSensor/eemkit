# CDOM metrics

`eemkit.absorbance.compute_absorbance_metrics` returns one row per sample
with the absorption coefficients, spectral slopes and ratios of chromophoric
dissolved organic matter (CDOM), computed from the blank-corrected Cary 60
spectra already in the dataset. In the pipeline and the application they are
computed together with the fluorescence indices and written in the same
table.

| metric | definition | reference |
|---|---|---|
| `a254`, `a350` | Napierian absorption coefficient a = ln(10) A / l, in m⁻¹ (l in m) | Green & Blough 1994 |
| `S275_295` | slope of ln a(λ) against λ, 275–295 nm, nm⁻¹ (reported positive) | Helms et al. 2008 |
| `S350_400` | the same over 350–400 nm | Helms et al. 2008 |
| `SR` | S275_295 / S350_400 | Helms et al. 2008 |
| `E2_E3` | A(250) / A(365) | De Haan & De Boer 1987 |
| `SUVA254` | A(254) / l (decadic, m⁻¹) / DOC (mg L⁻¹), in L mg⁻¹ m⁻¹ | Weishaar et al. 2003 |

```python
from eemkit.absorbance import compute_absorbance_metrics
df = compute_absorbance_metrics(ds, absorbance_path_length_cm=1.0)       # baseline 680-700 nm
df = compute_absorbance_metrics(ds, absorbance_path_length_cm=1.0, doc="DOC_mg_L")  # + SUVA254
```

## Baseline offset

Each spectrum is first corrected for its baseline offset by subtracting its
mean absorbance over 680–700 nm, where CDOM does not absorb (Green & Blough
1994; Helms et al. 2008). In river water measured in a 1 cm cuvette the CDOM
signal above 350 nm is of the same order as such offsets (for the Ombrone
data, A(400) has a median of 0.004 and the offsets are within ±0.006), so
without this step the long-wavelength slope and E2:E3 are dominated by the
offset. The range is a setting (`absorbance.baseline`); an empty list turns
the correction off.

## Low signal is never a number

A metric that would need a non-positive absorbance, or a slope whose
log-linear fit has R² below `min_r2` (default 0.95), is left empty (NaN) and
the reason is written in the `cdom_notes` column, for example
`S350_400: a <= 0 in 350-400 nm`. The R² of every fit is kept
(`S275_295_R2`, `S350_400_R2`). The 0.95 threshold is an eemkit quality
setting, not a value from the literature: report the value you used.

For the Ombrone samples (1 cm cuvette), 165 of 205 samples have both slopes
and SR; the others have too little absorbance above 350 nm. A longer cuvette
(5 or 10 cm) is the usual remedy for clear waters.

## DOC and SUVA254

SUVA254 needs dissolved organic carbon. Add a column with DOC in mg L⁻¹ to the
pairing table (for example `DOC_mg_L`) and choose it as the DOC column; empty
or non-numeric cells give an empty SUVA254 with a note. SUVA254 uses the
decadic absorbance per metre, as defined by Weishaar et al. (2003).

## References

De Haan, H., De Boer, T. (1987) *Water Research* 21, 731–734 ·
Green, S.A., Blough, N.V. (1994) *Limnology and Oceanography* 39, 1903–1916 ·
Helms, J.R. et al. (2008) *Limnology and Oceanography* 53, 955–969 ·
Weishaar, J.L. et al. (2003) *Environmental Science & Technology* 37, 4702–4708.
