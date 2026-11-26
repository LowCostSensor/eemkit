# PyInstaller recipe for a stand-alone eemkit desktop application (one folder).
#
#   pip install eemkit[gui] pyinstaller
#   pyinstaller packaging/eemkit-gui.spec --noconfirm
#
# The result is dist/eemkit/eemkit(.exe) on Windows and Linux (zip or tar the
# dist/eemkit folder to share it) and dist/eemkit.app on macOS.
# Build on each target platform (Windows, macOS, Linux) separately.
# With conda, run from an *activated* environment: conda-forge keeps the Qt and
# shiboken DLLs in <env>/Library/bin, which PyInstaller finds only on PATH.
# On Windows keep the output path short (--distpath C:\tmp\dist): Qt plugin paths
# exceed the 260-character limit inside deep folders.

import os
import shutil
import subprocess
import sys
from importlib.metadata import version

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

sys.path.insert(0, SPECPATH)
from notices import write_notices  # noqa: E402

block_cipher = None
VERSION = version("eemkit")
ICONS = os.path.join(SPECPATH, "icons")
ICON = {"win32": os.path.join(ICONS, "eemkit.ico"),
        "darwin": os.path.join(ICONS, "eemkit.icns")}.get(sys.platform)

a = Analysis(
    ["launch.py"],
    pathex=[],
    datas=collect_data_files("eemkit"),  # the window icons in eemkit/gui/icons
    hiddenimports=collect_submodules("eemkit") + ["scipy.special._cdflib"],
    excludes=["tkinter", "IPython", "jupyter", "tensorly", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="eemkit",
    console=False,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name="eemkit")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="eemkit.app",
        icon=ICON,
        bundle_identifier="io.github.lowcostsensor.eemkit",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "eemkit",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,  # follow the system dark mode
        },
    )
    # Licence texts inside the bundle, then sign it again (ad hoc, no identity):
    # files added after signing would break the signature, and Apple-silicon Macs
    # refuse to start an application whose signature is broken.
    bundle = os.path.join(DISTPATH, "eemkit.app")
    write_notices(os.path.join(bundle, "Contents", "Resources", "licenses"))
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", bundle], check=True)
else:
    # Licence texts of eemkit, Qt and every bundled package, next to eemkit(.exe).
    folder = os.path.join(DISTPATH, "eemkit")
    write_notices(folder)
    if sys.platform.startswith("linux"):
        # Icon and a script that adds eemkit to the applications menu.
        shutil.copyfile(os.path.join(ICONS, "eemkit-256.png"), os.path.join(folder, "eemkit.png"))
        target = os.path.join(folder, "install-desktop-entry.sh")
        shutil.copyfile(os.path.join(SPECPATH, "linux", "install-desktop-entry.sh"), target)
        os.chmod(target, 0o755)
