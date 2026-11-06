# PARAFAC

`eemkit.parafac` fits non-negative PARAFAC models and provides the diagnostics
recommended by Murphy et al. (2013, Anal. Methods 5:6557-6566).

## Algorithm

Alternating least squares with HALS column updates (Cichocki & Phan 2009),
which give exact non-negativity. Missing values (removed scatter) are imputed
from the current model before every sweep (expectation-maximisation, as in
the N-way toolbox; Tomasi & Bro 2005). The implementation is plain numpy and
is checked against TensorLy's `non_negative_parafac_hals` on complete data in
the test suite.

Why not TensorLy directly: its non-negative solver that accepts a missing-data
mask uses multiplicative updates, which converge slowly and never reach exact
zeros; its HALS solver does not accept missing data.

## Fitting

```python
m = eemkit.parafac.fit_parafac(ds, rank=5, n_init=10, normalization="norm", tol=1e-8)
```

* `normalization="norm"` scales every sample to unit Frobenius norm before
  fitting, so a few intense samples do not dominate; scores are scaled back.
* `n_init` random starts; the best is kept, and `init_sse` /
  `attrs["n_init_at_best_minimum"]` show whether starts agree.
* `n_jobs` random starts run at the same time, in threads (default: every
  processor; `n_jobs=1` runs them one after the other). Each start keeps its
  own seed, so the model is identical whatever `n_jobs` is; on an 8-core
  laptop the starts take about half the time.
* Output: `scores`, `fmax`, `ex_loadings`, `em_loadings` (unit norm),
  leverages, per-sample residual sums of squares, explained variance and
  core consistency.

## Diagnostics

| function | purpose | reference |
|---|---|---|
| `core_consistency` | CORCONDIA (%), as the N-way toolbox computes it | Bro & Kiers 2003; Andersson & Bro 2000 |
| `leverage`, `sse_sample` | outlier detection | Murphy et al. 2013 |
| `split_half` | S4C6T3 validation, Tucker congruence ≥ 0.95; SSC also reported | Murphy et al. 2013; Lorenzo-Seva & ten Berge 2006 |
| `eemqual` | fit × core consistency × split-half, to rank models | Bro & Vidal 2011 |
| `shift_shape_congruence` | SSC: congruence sensitive to peak shift and width | Wünsch et al. 2019 |
| `compare_models`, `compare_ranks` | pair the components of two models, with TCC and SSC | |
| `component_correlations` | correlation of component Fmax across samples | |
| `match_components` | pair components of two models | |
| `to_openfluor` | loadings in the OpenFluor text format | Murphy et al. 2014 |

### Core consistency

Core consistency (CORCONDIA, Bro & Kiers 2003) asks how far the best Tucker
core for the model's loadings is from the superdiagonal core of a perfect
trilinear model; 100 % means perfect. eemkit computes it exactly as `corcond`
of the N-way toolbox (Andersson & Bro 2000), the copy drEEM uses, so values
can be compared with drEEM's and with the literature:

1. each component's three loading vectors are given the same norm, so the
   result does not depend on how the component's size is split between them;
2. the core is fitted by least squares to the observed cells only: missing
   values (scatter) are left out, not filled with the model;
3. CC = 100 (1 − Σ(G − T)² / ΣG²), with G the fitted core and T the
   superdiagonal core.

On the same arrays eemkit and N-way (drEEM 2.26.03) agree to 10⁻⁶ %; a test
checks it. eemkit 0.1 used another convention (all of a component's size in
the scores, missing cells filled with the model, denominator F), which gave
higher values: 85.5 % instead of 74.9 % on the Ombrone model. If a loading
matrix is rank-deficient (two components with the same profile in one mode),
the value is NaN with a warning.

### Shift- and shape-sensitive congruence (SSC)

Tucker's congruence (TCC) rates two spectra whose maxima are 10–15 nm apart
as almost identical. SSC (Wünsch et al. 2019) subtracts two penalties from it:

* α = |wavelength of maximum₁ − wavelength of maximum₂| / wavelength range;
* β = |area₁ − area₂| / wavelength range, where each spectrum is first divided
  by its own maximum, so β grows when one peak is wider.

SSC = TCC − α − β. Wünsch et al. compare emission spectra with SSC and
excitation spectra with TCC. eemkit integrates the areas with the trapezoid
rule, so SSC does not depend on the wavelength step; staRdom's `ssc` sums the
points, which on a 1 nm grid differs by at most 1 / range. In split-half
validation SSC is reported (`ssc_ex`, `ssc_em`, `attrs["min_ssc_em"]`) but
the decision still uses TCC ≥ 0.95, as in Murphy et al. (2013).

### EEMqual

`eemqual(model, split)` multiplies three numbers between 0 and 1 (Bro & Vidal
2011): explained variance / 100, core consistency / 100 (negative values set
to 0) and the lowest split-half Tucker congruence (`split.attrs["min_tcc"]`).
The last term is an eemkit choice: staRdom uses the product of the best
congruence of each component, which is never lower. The exploration table
(`pipeline.explore`) has an `eemqual` column. EEMqual ranks models fitted to
the same data; it does not replace looking at the components.

### Comparing models

`compare_models(m1, m2)` pairs the components of two models fitted on the same
wavelengths (they may have different ranks) and gives TCC and SSC for
excitation and emission. `compare_ranks(models)` does it between each rank
and the next, which shows which components stay stable when one more is added
and which split. `component_correlations(model)` gives the Spearman (or
Pearson) correlation of the components' Fmax: two components that always vary
together may be one source split in two.

## Outlier diagnostics

```python
eemkit.parafac.sample_diagnostics(model)          # leverage, residual, ranks per sample
sr = eemkit.parafac.spectral_residuals(model, ds) # residual by excitation and emission
eemkit.plot.residual_eems(model, ds)              # measured, model, residual EEMs
eemkit.plot.spectral_residuals(sr)
```

Murphy et al. (2013) inspect every model for samples with high leverage
(they pull the model towards themselves) and for samples or wavelengths with
large residuals (the model does not describe them). `sample_diagnostics`
lists the samples with their leverage, residual sum of squares and relative
residual (residual / data sum of squares, comparable between samples of
different intensity), with the samples to inspect first at the top.
`residual_eems` shows, for the worst-fitted samples, the measured EEM, the
model and the residual: a peak left in the residual is fluorescence the model
does not have; a band along the scatter lines is scatter not fully removed.
`spectral_residuals` sums the residuals over samples for each wavelength, so a
wavelength fitted badly in every sample stands out. No threshold is applied:
which samples to remove is a decision to make looking at them, and to report.

## Applying a model to new samples

```python
new = eemkit.parafac.project_samples(model, new_corrected_eems)
new["fmax"]                    # scores in the units of the data
new["outside_model_range"]     # True: fitted worse than any sample of the model
```

The model's excitation and emission spectra are kept fixed; for each new
sample the scores are the non-negative least-squares fit of its observed
values, as drEEM's `projectmodel` and staRdom's `A_missing` do. Scaling a
sample scales its scores by the same factor, so the per-sample normalisation
used to fit the model does not change the projected scores.

The new samples must be on the model's wavelengths and should be processed in
the same way; a warning says when their processing history differs.
`relative_sse` is the residual over the data sum of squares of each sample;
`outside_model_range` marks the samples for which it is higher than for any
sample used to build the model: the model does not describe them well, and
they may contain a component the model does not have.

## References

Andersson, C.A., Bro, R. (2000) *Chemometrics and Intelligent Laboratory Systems* 52, 1–4 ·
Bro, R., Kiers, H.A.L. (2003) *Journal of Chemometrics* 17, 274–286 ·
Bro, R., Vidal, M. (2011) *Chemometrics and Intelligent Laboratory Systems* 106, 86–92 ·
Lorenzo-Seva, U., ten Berge, J.M.F. (2006) *Methodology* 2, 57–64 ·
Murphy, K.R. et al. (2013) *Analytical Methods* 5, 6557–6566 ·
Murphy, K.R. et al. (2014) *Analytical Methods* 6, 658–661 ·
Wünsch, U.J., Bro, R., Stedmon, C.A., Wenig, P., Murphy, K.R. (2019) *Analytical Methods* 11, 888–893.
