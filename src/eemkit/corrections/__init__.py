"""EEM corrections. Each is a separate, optional function recorded in the history.

Recommended order (each function refuses to run after a step that must follow it):

1. :func:`apply_spectral_correction` (instrument response; optional)
2. :func:`subtract_absorbance_blank`
3. :func:`correct_inner_filter`
4. :func:`subtract_blank`
5. :func:`normalize_raman`, then :func:`correct_dilution` (diluted samples) and
   :func:`zap` (regions removed by hand)
6. :func:`remove_scatter`, then optionally :func:`interpolate_missing`
7. :func:`crop`

With diluted samples, :func:`match_absorbance_dilution` goes between steps 2 and 3.
"""

from eemkit.corrections.blank import subtract_absorbance_blank, subtract_blank
from eemkit.corrections.crop import crop
from eemkit.corrections.dilution import correct_dilution, match_absorbance_dilution
from eemkit.corrections.inner_filter import correct_inner_filter
from eemkit.corrections.raman import normalize_raman, raman_area
from eemkit.corrections.scatter import (
    interpolate_missing,
    raman_emission,
    remove_scatter,
    scatter_mask,
)
from eemkit.corrections.spectral import (
    apply_spectral_correction,
    read_correction_file,
    spectral_correction_status,
)
from eemkit.corrections.zap import zap

__all__ = [
    "apply_spectral_correction",
    "correct_dilution",
    "correct_inner_filter",
    "crop",
    "interpolate_missing",
    "match_absorbance_dilution",
    "normalize_raman",
    "raman_area",
    "raman_emission",
    "read_correction_file",
    "remove_scatter",
    "scatter_mask",
    "spectral_correction_status",
    "subtract_absorbance_blank",
    "subtract_blank",
    "zap",
]
