"""Licence notices for the stand-alone application.

The stand-alone build bundles Python, Qt (through PySide6) and the libraries
eemkit depends on. Their licences ask that the licence texts travel with the
copies, so this script writes into the application folder:

* ``LICENSE.txt``: the eemkit licence (GPL-3.0-or-later);
* ``LGPL-3.0.txt``: the licence under which Qt and PySide6 are used;
* ``THIRD-PARTY-NOTICES.txt``: every bundled package with its version, licence
  and the licence files shipped in its metadata.

The package list is the dependency closure of ``eemkit[gui]`` as installed in
the build environment. The spec file calls it after the build; it can also be
run alone::

    python packaging/notices.py dist/eemkit
"""

from __future__ import annotations

import re
import shutil
import sys
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LICENCE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)
QT_PACKAGES = {"pyside6", "pyside6-essentials", "pyside6-addons", "shiboken6"}

HEADER = """\
eemkit stand-alone application: third-party notices
=====================================================

eemkit is free software under the GNU General Public License v3.0 or later
(LICENSE.txt). Its source code is at https://github.com/LowCostSensor/eemkit.
This application folder also contains the software listed below, each under
its own licence.

Qt and PySide6
--------------
The application uses Qt and Qt for Python (PySide6, shiboken6) under the GNU
Lesser General Public License v3.0 (LGPL-3.0.txt; it builds on the GNU GPL
v3.0, in LICENSE.txt). They are not modified. Their source code is available
from https://code.qt.io and https://download.qt.io/official_releases/QtForPython/.
The Qt and PySide6 libraries are separate files in the _internal folder and
can be replaced with other compatible builds of the same version.

PyInstaller
-----------
The program that starts the application (eemkit.exe) is built with
PyInstaller (https://pyinstaller.org). Its bootloader is under the GNU GPL
v2.0 or later with an exception that allows its use in programs under any
licence.

Python
------
Python {python} is under the Python Software Foundation License; its licence
text follows at the end of this file.
"""


def root_requirements() -> list[Requirement]:
    """eemkit's own requirements, with the ``gui`` extra, from pyproject.toml."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    reqs = project["dependencies"] + project["optional-dependencies"]["gui"]
    return [Requirement(r) for r in reqs]


def closure() -> list[metadata.Distribution]:
    """Installed distributions needed by ``eemkit[gui]``, sorted by name."""
    found: dict[str, metadata.Distribution] = {}
    queue = [(r, set()) for r in root_requirements()]
    while queue:
        req, _ = queue.pop()
        name = canonicalize_name(req.name)
        if name in found:
            continue
        try:
            dist = metadata.distribution(req.name)
        except metadata.PackageNotFoundError:
            continue  # optional on this platform
        found[name] = dist
        extras = sorted(req.extras) or [""]
        for spec in dist.requires or []:
            sub = Requirement(spec)
            if sub.marker is None or any(sub.marker.evaluate({"extra": e}) for e in extras):
                queue.append((sub, sub.extras))
    return [found[k] for k in sorted(found)]


def licence_name(dist: metadata.Distribution) -> str:
    md = dist.metadata
    if canonicalize_name(md["Name"]) in QT_PACKAGES:
        return "LGPL-3.0 (see Qt and PySide6 above)"
    expr = md.get("License-Expression")
    if expr:
        return expr
    text = (md.get("License") or "").strip()
    if text and len(text) < 120 and "\n" not in text:
        return text
    classifiers = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or []
                   if c.startswith("License ::")]
    return "; ".join(classifiers) or "not stated in the package metadata"


def licence_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    texts = []
    for f in dist.files or []:
        parts = Path(str(f)).parts
        if not parts or not parts[0].endswith(".dist-info"):
            continue
        if LICENCE_FILE.search(parts[-1]):
            try:
                text = Path(f.locate()).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            texts.append(("/".join(parts[1:]), text))
    return texts


def homepage(dist: metadata.Distribution) -> str:
    md = dist.metadata
    if md.get("Home-page"):
        return md["Home-page"]
    for url in md.get_all("Project-URL") or []:
        label, _, link = url.partition(",")
        if label.strip().lower() in {"homepage", "home", "source", "source code", "repository"}:
            return link.strip()
    return ""


def notices() -> str:
    out = [HEADER.format(python=sys.version.split()[0])]
    dists = closure()
    out.append("\nBundled packages\n----------------\n")
    for d in dists:
        url = homepage(d)
        out.append(f"* {d.metadata['Name']} {d.version.strip()}: {licence_name(d)}"
                   + (f"\n  {url}" if url else ""))
    for d in dists:
        texts = licence_texts(d)
        title = f"{d.metadata['Name']} {d.version.strip()}"
        out.append("\n\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)
        if not texts:
            out.append(f"\nLicence: {licence_name(d)}. The package metadata ship no licence file;"
                       f" see {homepage(d) or 'the project page'}.")
        for name, text in texts:
            out.append(f"\n--- {name} ---\n\n{text.strip()}")
    python_licence = Path(sys.base_prefix) / "LICENSE.txt"
    out.append("\n\n" + "=" * 78 + f"\nPython {sys.version.split()[0]}\n" + "=" * 78)
    if python_licence.exists():
        out.append("\n" + python_licence.read_text(encoding="utf-8", errors="replace").strip())
    else:
        out.append("\nPython Software Foundation License: https://docs.python.org/3/license.html")
    return "\n".join(out) + "\n"


def write_notices(folder: str | Path) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "LICENSE", folder / "LICENSE.txt")
    shutil.copyfile(HERE / "licenses" / "LGPL-3.0.txt", folder / "LGPL-3.0.txt")
    (folder / "THIRD-PARTY-NOTICES.txt").write_text(notices(), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    write_notices(sys.argv[1])
    print(f"notices written to {sys.argv[1]}")
