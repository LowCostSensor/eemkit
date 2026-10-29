"""Non-negative PARAFAC with the diagnostics of Murphy et al. (2013)."""

from eemkit.parafac._cp import nn_parafac
from eemkit.parafac.diagnostics import (
    core_consistency,
    leverage,
    match_components,
    tucker_congruence,
)
from eemkit.parafac.export import to_openfluor
from eemkit.parafac.model import fit_parafac, fit_ranks, model_eem, residuals, summary_table
from eemkit.parafac.validation import split_groups, split_half

__all__ = [
    "core_consistency",
    "fit_parafac",
    "fit_ranks",
    "leverage",
    "match_components",
    "model_eem",
    "nn_parafac",
    "residuals",
    "split_groups",
    "split_half",
    "summary_table",
    "to_openfluor",
    "tucker_congruence",
]
