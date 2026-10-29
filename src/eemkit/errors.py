"""Exceptions and warnings raised by eemkit."""


class EEMKitError(Exception):
    """Base class for eemkit errors."""


class FileFormatError(EEMKitError, ValueError):
    """An instrument file does not have the expected layout."""


class PairingError(EEMKitError, ValueError):
    """The pairing table is malformed or points to missing files."""


class GridError(EEMKitError, ValueError):
    """Spectra cannot be placed on, or combined into, a common wavelength grid."""


class CorrectionError(EEMKitError, ValueError):
    """A correction cannot be applied: missing input, wrong order or applied twice."""


class EEMKitWarning(UserWarning):
    """Something unusual that does not prevent processing but should be reviewed."""
