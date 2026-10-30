# PyInstaller recipe for a stand-alone eemkit desktop application (one folder).
#
#   pip install eemkit[gui] pyinstaller
#   pyinstaller packaging/eemkit-gui.spec --noconfirm
#
# The result is dist/eemkit/eemkit(.exe); zip the dist/eemkit folder to share it.
# Build on each target platform (Windows, macOS, Linux) separately.
# With conda, run from an *activated* environment: conda-forge keeps the Qt and
# shiboken DLLs in <env>/Library/bin, which PyInstaller finds only on PATH.
# On Windows keep the output path short (--distpath C:\tmp\dist): Qt plugin paths
# exceed the 260-character limit inside deep folders.

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["launch.py"],
    pathex=[],
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
)
coll = COLLECT(exe, a.binaries, a.datas, name="eemkit")
