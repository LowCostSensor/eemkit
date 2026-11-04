# Rivers, sites and dates

`eemkit.campaigns` compares sampling campaigns, sites and rivers on any
per-sample variable: fluorescence indices, CDOM metrics, PARAFAC Fmax or the
share of each component in total Fmax (`C1_pct`, ...). It is generic: you
name the columns of your pairing table that hold the *group* (e.g. river),
the *time* (e.g. campaign) and the *site*.

## The statistical unit

Replicates of one site at one time are not independent samples; treating
them as such inflates the significance of every test (pseudoreplication,
Hurlbert 1984). `site_means` therefore averages them first, keeping their
standard deviation, coefficient of variation and number; every test below
uses these site means.

## What it reports

* **Design and confounding.** `design_table` shows how many sites were
  sampled for every group and time; `confounding` says in plain language when
  two groups were never sampled at the same time, in which case differences
  between them cannot be separated from differences between times. In the
  application the warning stays visible above the results.
* **Differences between times, within each group.** Kruskal–Wallis test
  (Kruskal & Wallis 1952) and Dunn's pairwise comparisons (Dunn 1964) with
  Holm's correction (Holm 1979). Groups are never pooled, because of the
  confounding above.
* **Along the river.** With a site table that gives a position for each site
  (e.g. distance from the source in km), Spearman's correlation between the
  variable and the position, per group, overall and per time.
* **Covariates.** With a covariate table (e.g. discharge, rainfall per river
  and campaign), Spearman's correlation per group and overall.
* **Composition.** The share of each PARAFAC component in total Fmax, as
  stacked bars per group and time.

Non-parametric tests are used because the number of sites per time is small
and normality cannot be checked reliably.

## Optional tables

Both are CSV files (comma, semicolon or tab separated):

```text
sites.csv                          covariates.csv
river,site,latitude,longitude,distance_km      river,campaign,discharge_m3s,rain_7d_mm
Merse,1,43.21,11.23,4.5                        Merse,2024-04,3.2,18
Merse,2,43.18,11.25,9.0                        Merse,2024-05,2.1,5
```

The key columns must have the same names and values as in the samples: time
values are matched exactly as written (`2024-05`), never by guessing dates.
Rows that do not match are reported, and duplicate rows are refused.

```python
from eemkit import pipeline
s = pipeline.load_settings("project.toml")
s["campaigns"].update(group="river", time="campaign", site="site",
                      sites_table="sites.csv", position="distance_km")
table = pipeline.sample_table(indices, model)       # indices + Fmax + composition
res = pipeline.campaign_analysis(table, "HIX", s, base=".")
res.warnings, res.kruskal, res.pairwise, res.spatial
pipeline.export_campaigns("results/campaigns/HIX", res, s)
```

## References

Dunn, O.J. (1964) *Technometrics* 6, 241–252 ·
Holm, S. (1979) *Scandinavian Journal of Statistics* 6, 65–70 ·
Hurlbert, S.H. (1984) *Ecological Monographs* 54, 187–211 ·
Kruskal, W.H., Wallis, W.A. (1952) *Journal of the American Statistical Association* 47, 583–621.
