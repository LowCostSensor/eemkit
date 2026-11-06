"""The command line on a small synthetic project (the same as test_pipeline)."""

import warnings
from pathlib import Path

import pandas as pd
import pytest
from test_pipeline import make_project

from eemkit import pipeline
from eemkit.cli import main
from eemkit.io.discover import scan_folder, suggest_pairing


@pytest.fixture
def project(tmp_path) -> Path:
    """A project file with relative paths, next to its pairing table."""
    data = make_project(tmp_path)  # tmp_path / "data"
    work = tmp_path / "work"
    work.mkdir()
    draft = suggest_pairing(scan_folder(data))
    draft["include"] = "yes"
    draft.to_csv(work / "pairing.csv", index=False)
    s = pipeline.default_settings()
    s["project"].update(data_root="../data", pairing="pairing.csv", output_dir="out")
    s["inner_filter"].update(absorbance_path_length_cm=1.0, fluorescence_path_length_cm=1.0)
    s["parafac"].update(ranks=[1, 2], n_init=2, max_iter=300)
    s["parafac"]["split_half"].update(n_init=1)
    s["parafac"]["final"].update(rank=2, n_init=2, max_iter=500)
    return pipeline.save_settings(s, work / "project.toml")


def test_check_reports_a_ready_project(project, capsys):
    assert main(["check", str(project)]) == 0
    out = capsys.readouterr().out
    assert "8 included" in out and "2 components" in out and out.rstrip().endswith("OK")


def test_check_lists_missing_settings(project, capsys):
    s = pipeline.load_settings(project)
    s["inner_filter"]["absorbance_path_length_cm"] = None
    pipeline.save_settings(s, project)
    assert main(["check", str(project)]) == 1
    assert "inner_filter.absorbance_path_length_cm is not set" in capsys.readouterr().out


def test_run_writes_the_results_next_to_the_project(project, capsys):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert main(["run", str(project), "--jobs", "2", "--no-figures"]) == 0
    out = project.parent / "out"
    assert (out / "parafac_2comp_fmax.csv").is_file()
    assert (out / "parafac_exploration.csv").is_file()
    assert (out / "report.html").is_file()  # the report is written even without figures
    indices = pd.read_csv(out / "indices.csv", index_col=0)
    assert {"HIX", "a254", "SR"} <= set(indices.columns)
    assert "split-half" in capsys.readouterr().out


def test_run_refuses_an_output_folder_inside_the_data(project, capsys):
    data = project.parent.parent / "data"
    assert main(["run", str(project), "--output", str(data / "results")]) == 1
    assert "read-only" in capsys.readouterr().err
    assert not (data / "results").exists()


def test_bad_command_lines(project, capsys):
    assert main(["run", str(project), "--jobs", "0"]) == 2
    assert main(["check", str(project.parent / "missing.toml")]) == 1
    with pytest.raises(SystemExit):
        main(["nonsense"])
