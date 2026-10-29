import numpy as np
import pytest
import xarray as xr

from eemkit import GridError, get_history, infer_common_grid, regular_grid, resample
from eemkit.core.grid import interp_on_grid


def test_regular_grid():
    np.testing.assert_allclose(regular_grid(250, 600, 2), np.arange(250, 601, 2))
    with pytest.raises(GridError):
        regular_grid(250, 601, 2)
    with pytest.raises(GridError):
        regular_grid(600, 250, 2)


def test_interp_handles_order_nan_and_edges():
    x = np.array([4.0, 0.0, 2.0, np.nan])
    y = np.array([40.0, 0.0, 20.0, 99.0])
    out = interp_on_grid(x, y, np.array([-0.05, 1.0, 3.0, 4.05, 5.0]), tolerance=0.1)
    np.testing.assert_allclose(out[:4], [0, 10, 30, 40])
    assert np.isnan(out[4])


def test_interp_rejects_duplicate_x():
    with pytest.raises(GridError):
        interp_on_grid(np.array([1.0, 1.0, 2.0]), np.array([1.0, 2.0, 3.0]), np.array([1.5]))


def test_infer_common_grid_takes_coarsest_step_and_overlap():
    a = np.array([250.0, 252.03, 254.06, 255.93, 598.0, 600.0])  # median step ~2
    b = np.arange(249.0, 599.01, 1.03)  # 1 nm data ending at ~598.8
    g = infer_common_grid([a, b])
    assert g[0] == 250 and g[1] - g[0] == 2
    assert g[-1] == 598


def test_infer_common_grid_tolerates_jitter():
    wl = np.arange(200, 901) + 0.0048 * np.sin(np.arange(701))
    g = infer_common_grid([wl])
    assert (g[0], g[-1], g.size) == (200, 900, 701)


def test_resample_keeps_other_dims_and_records_history():
    ds = xr.Dataset(
        {"intensity": (("ex", "em"), np.array([[0.0, 1.0, 2.0], [10.0, 11.0, 12.0]])),
         "other": (("ex",), np.array([1.0, 2.0]))},
        coords={"ex": [200.0, 210.0], "em": [250.0, 251.0, 252.0]},
        attrs={"sample_name": "S"},
    )
    out = resample(ds, "em", np.array([250.5, 251.5]))
    np.testing.assert_allclose(out["intensity"], [[0.5, 1.5], [10.5, 11.5]])
    np.testing.assert_allclose(out["other"], [1, 2])
    assert out.attrs["sample_name"] == "S"
    h = get_history(out)[-1]
    assert h["step"] == "resample" and h["params"]["grid"]["n"] == 2
