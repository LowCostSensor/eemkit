# API reference

## Reading data

::: eemkit.io.cary_eclipse.read_cary_eclipse

::: eemkit.io.cary60.read_cary60

::: eemkit.io.cary60.mean_cycles

::: eemkit.io.discover.scan_folder

::: eemkit.io.discover.suggest_pairing

::: eemkit.io.pairing.read_pairing

::: eemkit.io.loader.load_dataset

::: eemkit.core.history.get_history

## Corrections

::: eemkit.corrections
    options:
      members:
        - apply_spectral_correction
        - read_correction_file
        - subtract_absorbance_blank
        - match_absorbance_dilution
        - correct_inner_filter
        - subtract_blank
        - normalize_raman
        - correct_dilution
        - zap
        - raman_area
        - remove_scatter
        - interpolate_missing
        - crop

## Indices

::: eemkit.indices
    options:
      show_root_toc_entry: false
      members:
        - compute_indices
        - fluorescence_index
        - humification_index
        - biological_index
        - peaks
        - export_indices

## CDOM metrics

::: eemkit.absorbance
    options:
      show_root_toc_entry: false
      members:
        - compute_absorbance_metrics
        - baseline_corrected
        - spectral_slope

## PARAFAC

::: eemkit.parafac.model
    options:
      show_root_toc_entry: false
      members:
        - fit_parafac
        - fit_ranks
        - summary_table
        - model_eem
        - residuals
        - project_samples

::: eemkit.parafac.validation.split_half

::: eemkit.parafac.compare
    options:
      show_root_toc_entry: false

::: eemkit.parafac.outliers
    options:
      show_root_toc_entry: false

::: eemkit.parafac.diagnostics
    options:
      show_root_toc_entry: false

::: eemkit.parafac.export.to_openfluor

## Rivers, sites and dates

::: eemkit.campaigns
    options:
      show_root_toc_entry: false

## Pipeline

::: eemkit.pipeline
    options:
      show_root_toc_entry: false

## Figures

::: eemkit.plot
    options:
      show_root_toc_entry: false

## Report

::: eemkit.report.write_report

## Command line

::: eemkit.cli.main
