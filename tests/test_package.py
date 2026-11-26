"""The package namespace: names load on first use, and import eemkit stays light."""

import subprocess
import sys

import eemkit


def test_public_names_resolve():
    for name in eemkit.__all__:
        assert getattr(eemkit, name) is not None
    assert eemkit.stack.__module__ == "eemkit.core.dataset"
    assert "pipeline" in dir(eemkit)


def test_unknown_name():
    try:
        eemkit.no_such_name  # noqa: B018
    except AttributeError as exc:
        assert "no_such_name" in str(exc)
    else:
        raise AssertionError("expected AttributeError")


def test_gui_package_import_is_light():
    """The application shows its start-up screen before the scientific libraries load."""
    code = ("import sys, eemkit, eemkit.gui; "
            "print(sorted(m for m in ('numpy', 'pandas', 'xarray', 'scipy') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
