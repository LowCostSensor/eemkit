# Instruments and file formats

eemkit reads EEMs and absorbance spectra exactly as the instruments export
them. The format is set in the project file, never guessed:

```toml
[project]
instrument = "aqualog"            # EEM format, see the table
absorbance_format = "two_column"  # "cary60" (default) or "two_column"
already_done = ["blank", "raman"] # steps the instrument software already did
```

| `instrument` | files | notes |
|---|---|---|
| `cary_eclipse` (default) | Agilent Cary Eclipse CSV "ASCII with log" | instrument settings from the log; "Corrected spectra" read from it |
| `aqualog` | Horiba Aqualog `.dat` | the first cell and text lines (e.g. "Sample - Blank", "Normalized by 75.335") are kept as `instrument_processing` |
| `fluoromax` | Horiba Fluoromax `.dat` matrix | the file says nothing about its processing |
| `hitachi_f7000` | Hitachi F-7000 `.TXT` 3-D scan | header kept (slits, detector voltage, "Corrected spectra"); the over-range value 9999.9 becomes missing, with a warning |
| `shimadzu` | Shimadzu `.TXT` | the file has no excitation wavelengths: set `[shimadzu] ex_start` and `ex_step` (nm) |
| `matrix_csv` | any text matrix | first row and first column hold the wavelengths; `[matrix_csv] orientation = "em_rows"` (first row = excitation) or `"ex_rows"`; comma, semicolon or tab |

| `absorbance_format` | files |
|---|---|
| `cary60` (default) | Agilent Cary 60 CSV with log, one or more cycles |
| `two_column` | two columns, wavelength (nm) and decadic absorbance; title lines are skipped; comma, semicolon, tab or space |

Values are never changed when read: no smoothing, no correction. A file that
does not have the structure of the chosen format is refused with the reason.
The Aqualog and Fluoromax matrices have the same layout, so for them only the
structure can be checked: choose the instrument that produced the files.

The folder scan of the application (`Scan folder`) uses the same setting: it
reads the files with the instrument's suffixes (`.dat`, `.TXT`, `.csv`) and
classifies them as EEM or absorbance.

## Processing already done by the instrument software

Some exports are already processed. An Aqualog file headed "Sample - Blank"
has had its blank subtracted; correcting it again would be wrong, and so would
skipping a correction without saying so. eemkit therefore:

1. reads what each file says about its processing (blank, inner filter,
   Raman units);
2. stops with an error if a file says a step was done that is not listed in
   `project.already_done`, quoting the file header;
3. for each step in `already_done` writes a processing-history entry with
   `done_by = "instrument software"` and the file header, instead of running
   the step, so the record is complete and the step cannot run twice.

Further rules:

* `blank` in `already_done` with blank files in the pairing table is an error.
* Raman units are computed from the water blank: if the instrument subtracted
  the blank, also list `raman` (when the instrument normalised to Raman units),
  otherwise there is nothing to normalise with.
* If the instrument subtracted the blank but eemkit corrects the inner filter,
  the two happen in the opposite of eemkit's own order; a warning says so.
* The meaning of a normalisation factor written by the instrument (e.g.
  "Normalized by 75.335") is not interpreted: only you can say whether it is
  Raman units.

## Instrument spectral correction

Cary Eclipse and Hitachi files say whether the instrument corrected the
spectra ("Corrected spectra On"); if so, eemkit refuses to correct them a
second time. Aqualog, Fluoromax, Shimadzu and matrix files do not say: their
status is recorded as *unknown (not stated in the files)*, which is what the
processing record and the report show. You can still apply your own factor
files (see [Corrections](corrections.md#spectral-correction)).

## Test files

The readers are tested on the example files of the R package eemR
(Massicotte, GPL ≥ 2; kept in `tests/data/eemR` with their licence note).
eemR has no blanks or absorbance spectra for these instruments, so the tests
check the reading and the rules above, not a full analysis on each
instrument. Files from your own instrument are welcome as a GitHub issue.
