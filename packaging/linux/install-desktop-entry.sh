#!/bin/sh
# Adds eemkit to the applications menu of the current user (no root needed).
# Run it from the unpacked eemkit folder; run it again if the folder is moved.
# To remove the entry: rm ~/.local/share/applications/eemkit.desktop
set -e
here=$(cd "$(dirname "$0")" && pwd)
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$apps"
cat > "$apps/eemkit.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=eemkit
Comment=EEM processing and PARAFAC modelling of DOM fluorescence
Exec="$here/eemkit" %f
Icon=$here/eemkit.png
Terminal=false
Categories=Science;Education;
StartupWMClass=eemkit
EOF
echo "Added $apps/eemkit.desktop"
