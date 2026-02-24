#!/bin/sh
set -xeuo pipefail

MAYA_VERSION="2026"

# The .run installer is a Makeself archive whose license prompt pipes through 'less -e',
# hijacking the terminal. Bypass with a fake 'less' that discards output, then pipe
# 'yes\n2' to accept license and choose Extract.
FAKELESS=$(mktemp -d)
printf '#!/bin/sh\ncat > /dev/null\n' > "$FAKELESS/less"
chmod +x "$FAKELESS/less"

EXTRACT_DIR=$(mktemp -d)
chmod +x "$SRC_DIR/installer/MayaUSD_${PKG_VERSION}_Maya${MAYA_VERSION}.1_Linux.run"
printf 'yes\n2\n' | PATH="$FAKELESS:$PATH" "$SRC_DIR/installer/MayaUSD_${PKG_VERSION}_Maya${MAYA_VERSION}.1_Linux.run" --nox11 --target "$EXTRACT_DIR"
rm -rf "$FAKELESS"

# The archive contains an RPM. Extract it without root using rpm --root.
RPM_FILE=$(find "$EXTRACT_DIR" -name '*.rpm' -print -quit)
RPM_ROOT=$(mktemp -d)
rpm -ivh --nodeps --noscripts --root "$RPM_ROOT" "$RPM_FILE"
rm -rf "$EXTRACT_DIR"

# Move the installed files into the conda prefix, preserving the directory structure
# RPM installs to /usr/autodesk/mayausd/maya2026/<build_version>/ and /usr/autodesk/modules/
# Remove .build-id symlinks that conflict with the maya base package
find "$RPM_ROOT" -path "*/.build-id" -type d -exec rm -rf {} + 2>/dev/null || true
cp -r "$RPM_ROOT/usr" "$PREFIX/usr"
rm -rf "$RPM_ROOT"

# Copy .mod files to a location on Maya's default MAYA_MODULE_PATH
# The maya conda package sets MAYA_MODULE_PATH to include modules/maya/<version>
mkdir -p "$PREFIX/usr/autodesk/modules/maya/$MAYA_VERSION"
find "$PREFIX/usr/autodesk/modules" -maxdepth 1 -name '*.mod' -exec cp {} "$PREFIX/usr/autodesk/modules/maya/$MAYA_VERSION/" \;

# Add activation script to set LD_LIBRARY_PATH for the MayaUSD shared libraries
MAYAUSD_LIB_DIR=$(find "$PREFIX/usr/autodesk/mayausd" -type d -name lib -path "*/MayaUSD*/lib" ! -path "*/genglsl/*" -print -quit)
if [ -n "$MAYAUSD_LIB_DIR" ]; then
    RELATIVE_LIB=${MAYAUSD_LIB_DIR#$PREFIX/}
    mkdir -p "$PREFIX/etc/conda/activate.d"
    cat <<EOF > "$PREFIX/etc/conda/activate.d/maya-usd-${PKG_VERSION}-vars.sh"
export LD_LIBRARY_PATH="\$CONDA_PREFIX/$RELATIVE_LIB:\${LD_LIBRARY_PATH:-}"
EOF
    mkdir -p "$PREFIX/etc/conda/deactivate.d"
    cat <<EOF > "$PREFIX/etc/conda/deactivate.d/maya-usd-${PKG_VERSION}-vars.sh"
# Remove the maya-usd lib from LD_LIBRARY_PATH
export LD_LIBRARY_PATH="\$(echo "\$LD_LIBRARY_PATH" | sed "s|\$CONDA_PREFIX/$RELATIVE_LIB:||")"
EOF
fi
