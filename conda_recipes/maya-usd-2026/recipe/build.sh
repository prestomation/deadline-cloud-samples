#!/bin/sh
set -xeuo pipefail

MAYA_VERSION=${PKG_VERSION%.*}
MAYA_VERSION="2026"

# This is where to install Maya USD within the installation prefix
MAYAUSD_ROOT="usr/autodesk/maya-usd-$MAYA_VERSION"

mkdir -p "$PREFIX/$MAYAUSD_ROOT"
cd "$PREFIX"

# The .run installer is a self-extracting archive. Extract it without running the installer.
chmod +x "$SRC_DIR/installer/MayaUSD_${PKG_VERSION}_Maya${MAYA_VERSION}.3_Linux.run"
"$SRC_DIR/installer/MayaUSD_${PKG_VERSION}_Maya${MAYA_VERSION}.3_Linux.run" --noexec --target "$PREFIX/$MAYAUSD_ROOT/extracted"

# Move the plugin files into place
if [ -d "$PREFIX/$MAYAUSD_ROOT/extracted/MayaUSD" ]; then
    cp -r "$PREFIX/$MAYAUSD_ROOT/extracted/MayaUSD/"* "$PREFIX/$MAYAUSD_ROOT/"
fi
rm -rf "$PREFIX/$MAYAUSD_ROOT/extracted"

# Create the maya-usd.mod file so Maya loads the plugin.
mkdir -p "$PREFIX/usr/autodesk/modules/maya/$MAYA_VERSION"
cat <<EOF > "$PREFIX/usr/autodesk/modules/maya/$MAYA_VERSION/maya-usd.mod"
+ MayaUSD any $PREFIX/$MAYAUSD_ROOT
EOF
