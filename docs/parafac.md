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
| `core_consistency` | CORCONDIA (%) | Bro & Kiers 2003 |
| `leverage`, `sse_sample` | outlier detection | Murphy et al. 2013 |
| `split_half` | S4C6T3 validation, Tucker congruence ≥ 0.95 | Murphy et al. 2013; Lorenzo-Seva & ten Berge 2006 |
| `match_components` | pair components of two models | |
| `to_openfluor` | loadings in the OpenFluor text format | Murphy et al. 2014 |

Core consistency is computed on the data with missing values replaced by the
model.
