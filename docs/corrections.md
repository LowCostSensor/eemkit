# Corrections

All corrections live in `eemkit.corrections`. Each is a separate function
that returns a new dataset, records its parameters in the history, and
refuses to run twice or in an order that would give a wrong result.
No correction has default scientific parameters that depend on the
instrument or the sample: path lengths, Raman settings and scatter widths are
always passed explicitly.

| order | function | what it does | reference |
|---|---|---|---|
| 1 | `apply_spectral_correction` | multiplies by excitation/emission correction factors read from files | instrument-specific |
| 2 | `subtract_absorbance_blank` | `absorbance - blank_absorbance` | |
| 3 | `correct_inner_filter` | `F * 10**((A_ex + A_em) / 2)`, path lengths required | Kothawala et al. 2013; Lakowicz 2006 |
| 4 | `subtract_blank` | `intensity - blank_intensity` | |
| 5 | `normalize_raman` | divides by the blank's water Raman area | Lawaetz & Stedmon 2009 |
| 6 | `remove_scatter` | Rayleigh/Raman bands, 1st and 2nd order, to NaN; optional zeros below Rayleigh | Thygesen et al. 2004 (zeros) |
| 6b | `interpolate_missing` | linear fill of the removed bands along em, ex or both | |
| 7 | `crop` | restrict the ex/em window | |

Why this order:

* The inner-filter effect also attenuates the water Raman signal inside the
  sample, so it is corrected before the blank is subtracted.
* The Raman area is taken from the blank before scatter removal, which would
  delete the Raman band itself.

Samples lacking an input (blank, absorbance) make a correction fail unless
`missing="keep"` (leave them uncorrected, flagged in a coordinate) or
`missing="drop"` is passed.

## Spectral correction

`ds.attrs["spectral_correction"]` is `"none"` until
`apply_spectral_correction` is used. Without it, Raman-normalised intensities
are consistent within one instrument but not comparable with other studies;
reports should say so.

```python
ds = C.apply_spectral_correction(ds, ex_factors="ex_corr.csv", em_factors="em_corr.csv")
```

Factor files have two columns, wavelength (nm) and factor; header lines and
`,` `;` tab or space separators are accepted. They must cover the whole
excitation and emission range of the EEMs (no extrapolation) and be positive.
With `convention="multiply"` (default) the files hold correction factors;
with `convention="divide"` they hold an instrument response (e.g. a reference
spectrum) and the EEMs are divided by it. The multipliers actually applied are
stored as `spectral_correction_ex` and `spectral_correction_em`. Data recorded
with the Cary Eclipse's own "Corrected spectra" ON are refused, so a
correction is never applied twice. eemkit ships no factors: they belong to
one instrument and must be measured.

In `eemkit.pipeline` the `[spectral]` section (`ex_factors`, `em_factors`,
`convention`) switches the step on; paths are relative to the settings file.
