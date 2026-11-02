"""The desktop application, driven end to end on a synthetic project (no window shown)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QMessageBox  # noqa: E402
from test_pipeline import make_project  # noqa: E402

from eemkit import pipeline  # noqa: E402
from eemkit.gui.main_window import MainWindow  # noqa: E402

TIMEOUT = 120_000


@pytest.fixture
def dialogs(monkeypatch):
    """Record message boxes instead of showing them; 'question' answers Yes."""
    seen = []

    def record(kind):
        def f(*args, **kwargs):
            seen.append((kind, args[2] if len(args) > 2 else ""))
            return QMessageBox.Yes
        return staticmethod(f)

    for kind in ("information", "warning", "question", "about"):
        monkeypatch.setattr(QMessageBox, kind, record(kind))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: seen.append(("exec", self.text())))
    return seen


@pytest.fixture
def window(qtbot, dialogs):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


def _idle(qtbot, w):
    qtbot.waitUntil(lambda: not w.tasks.busy, timeout=TIMEOUT)


def test_full_workflow(qtbot, window, dialogs, tmp_path):
    w, p = window, window.project
    data = make_project(tmp_path)
    p.set_path_setting("data_root", data)
    p.set_path_setting("pairing", tmp_path / "pairing.csv")
    p.set_path_setting("output_dir", tmp_path / "results")
    p.changed.emit("settings")

    # 1 project: scan, draft (all excluded), include after checking, load
    w.project_tab.scan()
    _idle(qtbot, w)
    assert len(p.inventory) == 19  # 8 EEM + 8 absorbance + 2 blanks + 1 unrelated CSV
    w.project_tab.suggest()
    assert len(p.pairing) == 8 and (p.pairing["include"] == "no").all()
    w.project_tab.pairing_view.selectAll()
    w.project_tab.set_include(True)
    assert (p.pairing["include"] == "yes").all()
    assert (p.pairing["pairing_status"] == "checked").all()
    w.project_tab.load_data()
    _idle(qtbot, w)
    assert p.raw is not None and p.raw.sizes["sample"] == 8
    assert (tmp_path / "pairing.csv").is_file()

    # 2 corrections: refused without path lengths, then applied
    w.corrections_tab.apply()
    assert dialogs[-1][0] == "information" and "path length" in dialogs[-1][1]
    w.corrections_tab.l_abs.setText("1")
    w.corrections_tab.l_fl.setText("1")
    w.corrections_tab.apply()
    _idle(qtbot, w)
    assert p.corrected is not None
    assert p.settings["inner_filter"]["absorbance_path_length_cm"] == 1.0
    assert w.corrections_tab.plot.figure is not None

    # 3 indices
    w.indices_tab.compute()
    _idle(qtbot, w)
    assert {"FI", "HIX", "BIX"} <= set(p.indices.columns)

    # 4 PARAFAC
    t = w.parafac_tab
    t.r_from.setValue(1)
    t.r_to.setValue(2)
    t.n_init.setValue(1)
    t.sh_init.setValue(1)
    t.max_iter.setValue(300)
    t.explore()
    _idle(qtbot, w)
    assert list(p.exploration.table.index) == [1, 2]
    # 300 iterations are too few on purpose: the warning reaches the user, it does not abort
    assert any("did not converge" in m for m in w.tasks.warnings)
    assert not w.tasks.warnings_button.isHidden()
    assert t.out_model.rowCount() == 8
    t.f_rank.setValue(2)
    t.f_init.setValue(1)
    t.f_iter.setValue(500)
    t.fit_final()
    _idle(qtbot, w)
    assert p.model.sizes["component"] == 2 and "Split-half" in t.final_text.text()

    # 5 export
    w.export_tab.meta["creator"].setText("Test Person")
    w.export_tab.export()
    _idle(qtbot, w)
    out = tmp_path / "results"
    for name in ("settings.toml", "processing_record.json", "indices.csv",
                 "parafac_2comp_openfluor.txt", "figures/components.pdf"):
        assert (out / name).is_file(), name
    assert "creator\tTest Person" in (out / "parafac_2comp_openfluor.txt").read_text("utf-8")
    assert not [d for d in dialogs if d[0] in ("warning", "exec")]

    # the saved project reopens with the same settings and pairing
    p.save(tmp_path / "project.toml")
    other = MainWindow(tmp_path / "project.toml")
    qtbot.addWidget(other)
    assert other.project.settings == pipeline.load_settings(tmp_path / "project.toml")
    assert other.project.settings["parafac"]["final"]["rank"] == 2
    assert len(other.project.pairing) == 8


def test_spectral_correction_and_eem_colours(qtbot, window, dialogs, tmp_path):
    w, p, t = window, window.project, window.corrections_tab
    data = make_project(tmp_path)
    p.set_path_setting("data_root", data)
    p.set_path_setting("pairing", tmp_path / "pairing.csv")
    p.changed.emit("settings")
    w.project_tab.scan()
    _idle(qtbot, w)
    w.project_tab.suggest()
    w.project_tab.pairing_view.selectAll()
    w.project_tab.set_include(True)
    w.project_tab.load_data()
    _idle(qtbot, w)

    # default colours are the Cary Eclipse ones; the View menu switches them
    assert p.eem_colours == "eclipse" and w.colour_actions["eclipse"].isChecked()
    w.colour_actions["blues"].trigger()
    assert p.eem_colours == "blues" and p.dirty

    ex, em = tmp_path / "ex.txt", tmp_path / "em.txt"
    ex.write_text("200 2\n500 2\n", encoding="utf-8")
    em.write_text("200 1\n700 3\n", encoding="utf-8")
    t.l_abs.setText("1")
    t.l_fl.setText("1")
    t.set_factor_file("ex_factors", str(ex))
    t.apply()  # only one file: refused
    assert dialogs[-1][0] == "information" and "both" in dialogs[-1][1]
    t.set_factor_file("em_factors", str(em))
    assert "2 values, 200-700 nm" in t.factor_info["em_factors"].text()
    t.apply()
    _idle(qtbot, w)
    assert "applied" in p.after_raman.attrs["spectral_correction"]
    assert "applied" in t.summary.text()
    t.stage.setCurrentText("Spectral correction factors")
    assert t.plot.figure is not None

    # factor files are stored relative to the project file and survive reopening
    p.save(tmp_path / "project.toml")
    back = pipeline.load_settings(tmp_path / "project.toml")
    assert back["spectral"]["ex_factors"] == "ex.txt"
    assert back["display"]["eem_colours"] == "blues"


def test_changing_settings_drops_dependent_results(qtbot, window, tmp_path):
    p = window.project
    p.exploration, p.model = object(), object()
    p.set_settings("raman", {"ex": 351.0}, "corrected")
    assert p.exploration is None and p.model is None


def test_output_inside_data_folder_is_refused(window, tmp_path):
    p = window.project
    p.set_path_setting("data_root", tmp_path / "data")
    assert p.in_data_root(tmp_path / "data" / "out")
    assert not p.in_data_root(tmp_path / "out")
