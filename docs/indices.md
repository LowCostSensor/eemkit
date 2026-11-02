# Indices

`eemkit.indices.compute_indices` returns one row per sample with the
fluorescence index, the humification and biological indices and the Coble
peaks; the settings used, the spectral-correction status and the processing
history are in `df.attrs`.

| index | definition (defaults) | reference |
|---|---|---|
| `FI` | I(ex 370, em 470) / I(ex 370, em 520) | Cory & McKnight 2005 |
| `HIX` | H / (H + L) at ex 254; H = area em 435–480, L = area em 300–345 | Ohno 2002 |
| `BIX` | I(ex 310, em 380) / I(ex 310, em 430) | Huguet et al. 2009 |
| peaks B, T, A, M, C | B 275/310, T 275/340, A 260/380–460, M 312/380–420, C 350/420–480 (ex/em, nm); maximum over the emission range | Coble 1996 |

Every wavelength can be changed, for example `fi={"em": (450, 500)}` for the
emission pair used by eemR, or `peak_definitions=` for other peaks.

* **Excitations off the grid** (254, 275 or 312 nm on a 10 nm grid) follow
  `ex_method`: `"linear"` interpolates between the two neighbouring scans,
  `"nearest"` takes the closest one, `"exact"` refuses.
* Emission values off the grid are linearly interpolated; emission areas are
  trapezoidal integrals of the piecewise-linear spectrum between the exact
  limits.
* A value that would need a missing point (removed scatter) is NaN and raises
  a warning, so compute indices **before** scatter removal: peak B at ex 275 /
  em 310 lies inside the first-order Raman band.
* Ratios depend on the instrument's spectral response (Cory et al. 2010).
  Without [spectral correction](corrections.md#spectral-correction), compare
  them only with values from the same instrument.
