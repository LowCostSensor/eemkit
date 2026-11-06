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
| 2b | `match_absorbance_dilution` | diluted samples only: absorbance rescaled to the EEM's dilution | Beer–Lambert |
| 3 | `correct_inner_filter` | `F * 10**((A_ex + A_em) / 2)`, path lengths required | Kothawala et al. 2013; Lakowicz 2006 |
| 4 | `subtract_blank` | `intensity - blank_intensity` | |
| 5 | `normalize_raman` | divides by the blank's water Raman area | Lawaetz & Stedmon 2009 |
| 5b | `correct_dilution` | diluted samples only: `intensity * dilution_factor` | staRdom `eem_dilution` |
| 5c | `zap` | regions listed by hand set to NaN | drEEM `zapnoise`; staRdom `eem_setNA` |
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

## Diluted samples

Optically dense samples are diluted before measurement (Kothawala et al. 2013
recommend it above A254 = 1.5 in a 1 cm cuvette). Two optional columns of the
pairing table give the dilution of each sample:

| column | dilution of the solution measured in |
|---|---|
| `dilution_factor` | the fluorometer (EEM) |
| `abs_dilution_factor` | the spectrophotometer (absorbance) |

A factor is final volume / sample volume (1 = undiluted, 2 = one part sample
plus one part water); an empty cell means 1. Text that is not a number, or a
number below 1, stops the processing with the samples named.

When either column is present, the pipeline:

1. rescales each absorbance spectrum to the dilution of its EEM
   (`absorbance × abs_dilution_factor / dilution_factor`; absorbance is
   proportional to concentration), so the inner-filter correction uses the
   absorbance of the solution that was in the fluorescence cuvette;
2. after Raman units, multiplies each EEM by `dilution_factor`, so the EEMs,
   the peaks and the PARAFAC scores describe the undiluted sample (as
   staRdom's `eem_dilution`); the blank is not multiplied;
3. reports the CDOM metrics for the undiluted sample: a254, a350 and SUVA254
   are multiplied by the dilution; slopes, SR and E2:E3 do not change.

FI, HIX and BIX are ratios and do not change with dilution.

## Removing bad data by hand (zap)

A spike, a lamp flicker or a bad excitation scan can be removed from one
sample without discarding the whole sample. List the regions in the
`[zap]` section of the project file:

```toml
[zap]
regions = [
  {sample = "Merse_2024-07_S3_R3", ex = [240, 250], em = [330, 360], reason = "spike"},
  {sample = "Farma_2024-11_S1_R1", ex = [300, 300], reason = "bad scan"},  # whole scan
]
interpolate = false   # or "em", "ex", "both"
```

* Each region is a sample with an excitation and an emission range in nm,
  inclusive; leaving a range out takes the whole range.
* The values become missing (NaN) right after Raman units, so the indices and
  PARAFAC both use the cleaned data. The regions, with their reasons, are
  recorded in the processing history; the removed cells are kept as the
  variable `zapped`.
* An index that needs a removed value is left empty, never computed on
  filled data.
* `interpolate` fills the zapped cells for PARAFAC with the same linear
  interpolation as the scatter bands; it is off by default. With
  `scatter.interpolate` on and `zap.interpolate` off, the scatter bands are
  filled and the zapped cells stay missing.
* An unknown sample, a range with no measured wavelength or a range written
  high-to-low is an error, so a typo never passes silently.
* eemkit never decides what to remove: look at the data, for example at the
  residual EEMs of the [report](parafac.md#outlier-diagnostics), and list
  the regions yourself.
