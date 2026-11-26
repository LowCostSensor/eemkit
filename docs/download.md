# Download the application

Each [release](https://github.com/LowCostSensor/eemkit/releases/latest) has a
stand-alone build of the desktop application for Windows, macOS and Linux. It
needs no Python: download the file for your system from the *Assets* list of
the release, unpack it and start the application. (To use eemkit from Python
scripts as well, install it with pip instead: see the
[quick start](quickstart.md) and [installation](gui.md).)

| System | File | Start |
|---|---|---|
| Windows 10 or 11, 64-bit | `eemkit-vX.Y.Z-windows.zip` | Unzip, then double-click `eemkit.exe` in the `eemkit` folder |
| macOS on Apple silicon (M1 or later) | `eemkit-vX.Y.Z-macos-arm64.zip` | Unzip, move `eemkit.app` to *Applications*, open it as below |
| Linux, x86-64 | `eemkit-vX.Y.Z-linux-x86_64.tar.gz` | `tar -xzf eemkit-*.tar.gz`, then `eemkit/eemkit` |

Each build is about 150–200 MB unpacked. Keep the files together: on Windows
and Linux the program (`eemkit.exe`, `eemkit`) needs the `_internal` folder
next to it. The licence texts of eemkit and of every bundled library
(`LICENSE.txt`, `LGPL-3.0.txt`, `THIRD-PARTY-NOTICES.txt`) are in the same
folder, or in `eemkit.app/Contents/Resources/licenses` on macOS.

To update, download the build of the new release and replace the old folder
(or `eemkit.app`). Projects and settings are not stored in it.

## Windows

The application is not signed with a code-signing certificate, so the first
time Windows may show *Windows protected your PC* (SmartScreen). Click
*More info*, then *Run anyway*. To have it in the Start menu, right-click
`eemkit.exe` and choose *Pin to Start* (or create a shortcut).

## macOS

The application is not signed with an Apple Developer ID nor notarised, so
Gatekeeper blocks it the first time ("Apple could not verify that eemkit is
free of malware", or "the developer cannot be verified"):

* **macOS 14 (Sonoma) and earlier:** in *Applications*, right-click (or
  Control-click) `eemkit.app`, choose *Open*, then *Open* again in the dialog.
* **macOS 15 (Sequoia) and later:** double-click `eemkit.app` once and close the
  message; then go to *System Settings > Privacy & Security*, scroll to
  *Security*, click *Open Anyway* next to the message about eemkit, and confirm
  with your password.

macOS remembers the choice: later the application opens with a double-click.
Alternatively, in Terminal:

```bash
xattr -dr com.apple.quarantine /Applications/eemkit.app
```

The build is for Apple silicon Macs (M1 and later). On an Intel Mac install
eemkit with pip (`python -m pip install "eemkit[gui]"`, then
`python -m eemkit.gui`).

## Linux

The build is made on Ubuntu 22.04 and runs on distributions with glibc 2.35 or
newer (Ubuntu 22.04, Debian 12, Fedora 36, or later). Qt needs a few system
libraries that a desktop installation usually has; if the application does not
start, install them:

```bash
# Debian, Ubuntu and derivatives
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libegl1
# Fedora
sudo dnf install xcb-util-cursor libxkbcommon-x11 xcb-util-wm xcb-util-keysyms
```

`QT_DEBUG_PLUGINS=1 eemkit/eemkit` names the library that is missing. To add
eemkit to the applications menu (with its icon), run once, from the unpacked
folder:

```bash
eemkit/install-desktop-entry.sh
```

## If the application closes at start-up

The reason is written to `eemkit-crash.log` in the temporary folder
(`%TEMP%` on Windows, `$TMPDIR` on macOS, `/tmp` on Linux). Please attach it to
an [issue](https://github.com/LowCostSensor/eemkit/issues).
