# Example files from eemR

These instrument files come unchanged from the example data
(`inst/extdata`) of the R package **eemR** 1.0.2 by Philippe Massicotte
(<https://github.com/PMassicotte/eemR>, CRAN: `eemR_1.0.2.tar.gz`),
distributed under the GNU General Public License, version 2 or later; its
`DESCRIPTION` file is kept here as `eemR_DESCRIPTION.txt`. eemkit is
distributed under the GPL version 3 or later, which is compatible.

They are used only to test eemkit's readers:

| folder | instrument | eemR reader |
|---|---|---|
| `aqualog/` | Horiba Aqualog, exported already blank-subtracted and normalised | `eem_read_aqualog` |
| `fluoromax4/` | Horiba Fluoromax-4 | `eem_read_fluoromax4` |
| `hitachi-f7000-fl/` | Hitachi F-7000 | (staRdom `eem_hitachi`) |
| `shimadzu/` | Shimadzu (excitation wavelengths not stored in the file) | `eem_read_shimadzu` |

No blank or absorbance files exist for these instruments in eemR, so they
test reading, not a full analysis.
