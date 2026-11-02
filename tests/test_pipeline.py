"""Discovery of files, the pairing draft and the full pipeline on a synthetic project."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import cary60_text, eclipse_text

from eemkit import load_dataset, pipeline, read_pairing
from eemkit.errors import Cancelled, SettingsError
from eemkit.io.discover import classify, scan_folder, suggest_pairing

EX = np.arange(240.0, 451.0, 10.0)
EM = np.arange(250.0, 601.0, 2.0)
# (ex centre, ex width, em centre, em width): humic-like, protein-like
COMPONENTS = [(250, 40, 450, 50), (275, 15, 340, 25)]


def _gauss(x, c, w):
    return np.exp(-0.5 * ((x - c) / w) ** 2)


def _eem(scores) -> np.ndarray:
    out = np.zeros((EX.size, EM.size))
    for s, (ce, we, cm, wm) in zip(scores, COMPONENTS, strict=True):
        out += s * np.outer(_gauss(EX, ce, we), _gauss(EM, cm, wm))
    return out


def _blank() -> np.ndarray:
    raman = 1e7 / (1e7 / EX - 3400)
    return 2.0 * _gauss(EM[None, :], raman[:, None], 6.0) + 0.01


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # keep the instrument's CRLF line ends as they are


def make_project(root: Path, n: int = 8, seed: int = 0) -> Path:
    """Data folder: n samples (EEM + absorbance), one blank of each kind, two stray files."""
    rng = np.random.default_rng(seed)
    data = root / "data"
    for i in range(n):
        name = f"S{i + 1}"
        scores = rng.lognormal(0, 0.4, len(COMPONENTS)) * 50
        noise = 0.002 * rng.standard_normal((EX.size, EM.size))
        _write(data / "fluo" / f"{name}.csv",
               eclipse_text(name, EX, EM, _eem(scores) + _blank() + noise))
        _write(data / "abs" / f"{name}.csv", cary60_text(name))
    _write(data / "fluo" / "MilliQ.csv", eclipse_text("MilliQ", EX, EM, _blank()))
    wl = np.arange(900, 199, -1) + 0.0
    _write(data / "abs" / "Bianco.csv",
           cary60_text("Bianco", absorbance=np.full((3, wl.size), 0.001), wl=wl))
    _write(data / "fluo" / "notes.csv", "a,b\r\n1,2\r\n")
    (data / "fluo" / "S1.FDSW").write_bytes(b"\x00binary")
    return data


@pytest.fixture
def data_root(tmp_path) -> Path:
    return make_project(tmp_path)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

def test_scan_classifies_files_without_touching_them(data_root):
    before = {p: p.stat().st_mtime_ns for p in data_root.rglob("*")}
    inv = scan_folder(data_root)
    assert {p: p.stat().st_mtime_ns for p in data_root.rglob("*")} == before
    kinds = inv.set_index("file")["kind"]
    assert kinds["fluo/S1.csv"] == "eem" and kinds["abs/S1.csv"] == "absorbance"
    assert kinds["fluo/notes.csv"] == "unknown"
    assert "fluo/S1.FDSW" not in kinds.index  # only CSV files are considered
    blanks = set(inv.loc[inv["is_blank"], "file"])
    assert blanks == {"fluo/MilliQ.csv", "abs/Bianco.csv"}
    row = inv.set_index("file").loc["fluo/S1.csv"]
    assert (row["first_x"], row["last_x"], row["n_scans"]) == (240.0, 450.0, EX.size)


def test_classify_reports_why_a_file_is_not_used(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("only one line", encoding="utf-8")
    assert classify(p)["problem"] == "fewer than two lines"


def test_draft_pairing_is_excluded_and_explained(data_root):
    draft = suggest_pairing(scan_folder(data_root))
    assert len(draft) == 8
    assert (draft["include"] == "no").all() and (draft["pairing_status"] == "suggested").all()
    s1 = draft.set_index("sample_id").loc["S1"]
    assert s1["abs_file"] == "abs/S1.csv"
    assert s1["eem_blank_file"] == "fluo/MilliQ.csv"
    assert s1["abs_blank_file"] == "abs/Bianco.csv"
    assert "matched by sample name" in s1["pairing_notes"]


def test_draft_leaves_ambiguous_choices_empty(data_root):
    _write(data_root / "fluo" / "blank2.csv", eclipse_text("blank2", EX, EM, _blank()))
    draft = suggest_pairing(scan_folder(data_root))
    row = draft.set_index("sample_id").loc["S1"]
    assert row["eem_blank_file"] == ""
    assert "2 candidates" in row["pairing_notes"]


def test_unchecked_draft_cannot_be_loaded(data_root, tmp_path):
    path = tmp_path / "pairing.csv"
    suggest_pairing(scan_folder(data_root)).to_csv(path, index=False)
    with pytest.raises(ValueError, match="no included rows"):
        load_dataset(read_pairing(path, data_root=data_root), data_root=data_root)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #

def test_settings_round_trip_keeps_unset_values(tmp_path):
    s = pipeline.default_settings()
    s["parafac"]["final"]["openfluor"] = {"creator": "Ana Lópeé", "doi": ""}
    p = pipeline.save_settings(s, tmp_path / "s.toml")
    text = p.read_text(encoding="utf-8")
    assert "# absorbance_path_length_cm = (not set)" in text
    back = pipeline.load_settings(p)
    assert back == s


def test_path_length_has_no_default(data_root, tmp_path):
    s = _settings(data_root, tmp_path)
    s["inner_filter"]["absorbance_path_length_cm"] = None
    with pytest.raises(SettingsError, match="absorbance_path_length_cm"):
        pipeline.correct_until_raman(pipeline.load(s), s)


# --------------------------------------------------------------------------- #
# Full chain
# --------------------------------------------------------------------------- #

def _settings(data_root: Path, tmp_path: Path) -> dict:
    draft = suggest_pairing(scan_folder(data_root))
    draft["include"] = "yes"
    draft.to_csv(tmp_path / "pairing.csv", index=False)
    s = pipeline.default_settings()
    s["project"].update(data_root=str(data_root), pairing=str(tmp_path / "pairing.csv"),
                        output_dir=str(tmp_path / "out"))
    s["inner_filter"].update(absorbance_path_length_cm=1.0, fluorescence_path_length_cm=1.0)
    s["parafac"].update(ranks=[1, 2, 3], n_init=2, max_iter=500)
    s["parafac"]["split_half"].update(n_init=1)
    s["parafac"]["final"].update(rank=2, n_init=2, max_iter=1000)
    return s


def test_full_chain_recovers_components_and_exports(data_root, tmp_path):
    s = _settings(data_root, tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pipeline.load(s)
        after = pipeline.correct_until_raman(raw, s)
        cor = pipeline.finish_corrections(after, s)
        idx = pipeline.compute_indices(after, s)
        ds = pipeline.parafac_input(cor, s)
        seen = []
        ex = pipeline.explore(ds, s, progress=lambda m, i, n: seen.append((i, n)))
        model, split = pipeline.fit_final(ds, s)
    assert raw.sizes["sample"] == 8 and np.isnan(cor["intensity"]).any()
    assert list(idx.columns[:2]) == ["pairing_status", "pairing_notes"]
    assert set(idx.columns) >= {"FI", "HIX", "BIX"}
    assert seen[-1] == (6, 6) and list(ex.table.index) == [1, 2, 3]
    assert model.attrs["explained_variance_pct"] > 99

    paths = pipeline.export_results(s["project"]["output_dir"], s, corrected=cor, indices=idx,
                                    exploration=ex, model=model, split=split,
                                    openfluor={"creator": "Test"})
    names = {p.name for p in paths}
    assert {"settings.toml", "processing_record.json", "indices.csv",
            "parafac_2comp_openfluor.txt", "components.pdf"} <= names
    record = Path(s["project"]["output_dir"], "processing_record.json").read_text()
    assert '"inner_filter"' in record or "correct_inner_filter" in record
    fmax = pd.read_csv(Path(s["project"]["output_dir"], "parafac_2comp_fmax.csv"), index_col=0)
    assert fmax.shape == (8, 2)


def test_spectral_correction_from_settings(data_root, tmp_path):
    s = _settings(data_root, tmp_path)
    _write(tmp_path / "factors" / "ex.csv", "nm,factor\r\n200,2\r\n500,2\r\n")
    _write(tmp_path / "factors" / "em.csv", "nm,factor\r\n200,3\r\n700,3\r\n")
    s["spectral"].update(ex_factors="factors/ex.csv")  # relative to base
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pipeline.load(s)
        with pytest.raises(SettingsError, match="both"):
            pipeline.correct_until_raman(raw, s, base=tmp_path)
        plain = pipeline.correct_until_raman(raw, s | {"spectral": pipeline.DEFAULTS["spectral"]})
        s["spectral"].update(em_factors="factors/em.csv")
        corr = pipeline.correct_until_raman(raw, s, base=tmp_path)
    assert "applied" in corr.attrs["spectral_correction"]
    assert plain.attrs["spectral_correction"] == "none"
    # constant factors cancel in Raman units (sample and blank are both multiplied)
    np.testing.assert_allclose(corr["intensity"], plain["intensity"], rtol=1e-10)
    np.testing.assert_allclose(corr["spectral_correction_ex"], 2.0)


def test_explore_can_be_cancelled(data_root, tmp_path):
    s = _settings(data_root, tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ds = pipeline.finish_corrections(pipeline.correct_until_raman(pipeline.load(s), s), s)
    with pytest.raises(Cancelled):
        pipeline.explore(ds, s, cancelled=lambda: True)


def test_unknown_excluded_sample_is_an_error(data_root, tmp_path):
    s = _settings(data_root, tmp_path)
    s["parafac"]["exclude"] = ["nope"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cor = pipeline.finish_corrections(pipeline.correct_until_raman(pipeline.load(s), s), s)
    with pytest.raises(SettingsError, match="nope"):
        pipeline.parafac_input(cor, s)
