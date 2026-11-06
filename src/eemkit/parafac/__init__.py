"""Non-negative PARAFAC with the diagnostics of Murphy et al. (2013)."""

from eemkit.parafac._cp import nn_parafac
from eemkit.parafac.compare import compare_models, compare_ranks, component_correlations
from eemkit.parafac.diagnostics import (
    core_consistency,
    eemqual,
    leverage,
    match_components,
    shift_shape_congruence,
    tucker_congruence,
)
from eemkit.parafac.export import to_openfluor
from eemkit.parafac.model import (
    fit_parafac,
    fit_ranks,
    model_eem,
    project_samples,
    residuals,
    summary_table,
)
from eemkit.parafac.validation import split_groups, split_half

__all__ = [
    "compare_models",
    "compare_ranks",
    "component_correlations",
    "core_consistency",
    "eemqual",
    "fit_parafac",
    "fit_ranks",
    "leverage",
    "match_components",
    "model_eem",
    "nn_parafac",
    "project_samples",
    "residuals",
    "shift_shape_congruence",
    "split_groups",
    "split_half",
    "summary_table",
    "to_openfluor",
    "tucker_congruence",
]
