"""Comparison of campaigns, sites and rivers on a small synthetic survey."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from eemkit import campaigns as K
from eemkit import pipeline
from eemkit.errors import SettingsError


def survey() -> pd.DataFrame:
    """River A at three times, river B at two other times; 4 sites, 3 replicates."""
    rng = np.random.default_rng(1)
    rows = []
    for river, times in (("A", ["2024-04", "2024-05", "2024-06"]), ("B", ["2024-09", "2024-10"])):
        for k, t in enumerate(times):
            for site in range(1, 5):
                for rep in range(1, 4):
                    rows.append({"sample": f"{river}_{t}_S{site}_R{rep}", "river": river,
                                 "campaign": t, "site": str(site), "replicate": str(rep),
                                 "HIX": 0.5 + 0.1 * k + 0.02 * site + 0.005 * rng.standard_normal(),
                                 "C1_Fmax": 1.0 + k, "C2_Fmax": 1.0})
    return pd.DataFrame(rows).set_index("sample")


def test_site_means_average_replicates():
    u = K.site_means(survey(), ["HIX"], group="river", time="campaign", site="site")
    assert len(u) == 4 * 5 and (u["n"] == 3).all()
    assert {"HIX", "HIX_sd", "HIX_cv_pct"} <= set(u.columns)


def test_composition_adds_to_100():
    c = K.composition(survey(), ["C1_Fmax", "C2_Fmax"])
    assert list(c.columns) == ["C1_pct", "C2_pct"]
    assert np.allclose(c.sum(axis=1), 100)


def test_confounding_is_reported():
    u = K.site_means(survey(), ["HIX"], group="river", time="campaign", site="site")
    msgs = K.confounding(u, group="river", time="campaign")
    assert any("A and B were never sampled at the same campaign" in m for m in msgs)
    assert "completely confounded" in msgs[0]
    assert K.design_table(u, group="river", time="campaign").loc["2024-05", "A"] == 4


def test_kruskal_matches_scipy_and_dunn_has_all_pairs():
    u = K.site_means(survey(), ["HIX"], group="river", time="campaign", site="site")
    kw, pairs = K.compare_times(u, "HIX", group="river", time="campaign")
    a = u[u["river"] == "A"]
    h, p = stats.kruskal(*[g["HIX"].to_numpy() for _, g in a.groupby("campaign")])
    row = kw.set_index("river").loc["A"]
    assert row["H"] == pytest.approx(h) and row["p"] == pytest.approx(p)
    assert len(pairs[pairs["river"] == "A"]) == 3 and len(pairs[pairs["river"] == "B"]) == 1
    assert (pairs["p_holm"] >= pairs["p"]).all()


def test_dunn_z_by_hand():
    d = K.dunn([1, 2, 3, 4, 5, 6], ["x", "x", "x", "y", "y", "y"])
    se = np.sqrt(6 * 7 / 12 * (1 / 3 + 1 / 3))
    assert d.loc[0, "z"] == pytest.approx((2 - 5) / se)


def test_holm():
    assert np.allclose(K._holm(np.array([0.01, 0.04, 0.03])), [0.03, 0.06, 0.06])


def test_spatial_trend_and_joins():
    u = K.site_means(survey(), ["HIX"], group="river", time="campaign", site="site")
    sites = pd.DataFrame({"river": ["A"] * 4 + ["B"] * 3,
                          "site": ["1", "2", "3", "4", "1", "2", "3"],
                          "distance_km": [0, 5, 10, 15, 0, 4, 8]})
    j, notes = K.join_sites(u, sites, group="river", site="site")
    assert notes == ["site table: no row for river=B, site=4"]
    sp = K.spatial_trend(j, "HIX", "distance_km", group="river", time="campaign")
    # within one campaign HIX rises along the river; pooled, the time effect dilutes it
    assert sp.set_index(["river", "campaign"]).loc[("A", "2024-04"), "rho"] == pytest.approx(1)
    assert sp.set_index(["river", "campaign"]).loc[("A", "all"), "n"] == 12
    with pytest.raises(SettingsError, match="duplicate"):
        K.join_sites(u, pd.concat([sites, sites]), group="river", site="site")


def test_pipeline_campaign_analysis(tmp_path):
    table = survey()
    pd.DataFrame({"river": ["A", "A", "A", "B", "B"],
                  "campaign": ["2024-04", "2024-05", "2024-06", "2024-09", "2024-10"],
                  "discharge": [10, 5, 2, 8, 12]}).to_csv(tmp_path / "hydro.csv", index=False)
    s = pipeline.default_settings()
    s["campaigns"].update(group="river", time="campaign", site="site",
                          covariates_table="hydro.csv")
    res = pipeline.campaign_analysis(table, "HIX", s, base=tmp_path)
    assert res.covariates is not None and "discharge" in set(res.covariates["covariate"])
    assert any("confounded" in w for w in res.warnings)
    written = pipeline.export_campaigns(tmp_path / "out", res, s)
    names = {p.name for p in written}
    assert {"site_means.csv", "HIX_kruskal.csv", "HIX_notes.txt", "HIX_by_campaign.png"} <= names
    with pytest.raises(SettingsError, match="numeric"):
        pipeline.campaign_analysis(table, "river", s, base=tmp_path)
