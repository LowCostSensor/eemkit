# Figures

`eemkit.plot` draws publication figures with matplotlib (`pip install eemkit[plot]`).
Each function returns a matplotlib figure; `plot.save(fig, "fig1")` writes
`fig1.pdf` (vector, embedded fonts) and `fig1.png` (300 dpi).

| function | figure |
|---|---|
| `eem(ax, da)` | filled contours of one EEM; missing cells (removed scatter) in grey |
| `eems({title: da, ...})` | small multiples; `vmax` per panel or `shared_scale=True` |
| `components(model, split_half)` | each component's EEM and loadings, with the split-half models behind |
| `rank_diagnostics(table, chosen=3)` | explained variance, core consistency and split-half congruence vs rank, one panel each |
| `leverage(model, by="river")` | leverage vs residuals, the most extreme samples labelled |
| `scores_over(df, cols, x="campaign", by="river")` | mean ± SD per group over time, samples as faint points |

Widths default to two journal columns (180 mm); `plot.SINGLE_COLUMN` is 85 mm.

## Colour

* Intensities use one sequential hue, white (0) to dark blue. A `vmax` below
  the scatter peaks keeps fluorescence readable in uncorrected EEMs; values
  above it share the darkest colour.
* Groups and components follow a fixed categorical order
  (`plot.CATEGORICAL`): blue, orange, aqua, ... The first three are
  distinguishable in any combination under the common colour-vision
  deficiencies; groups also differ in marker shape, so colour is never the
  only cue. More than eight groups are refused.
* Different quantities never share a y-axis: `rank_diagnostics` uses three
  panels rather than a twin axis.
