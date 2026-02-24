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
chmod +x "$SRC_DIR/installer/MayaUSD_${PKG_VERSION}_Maya${MAYA_VERSION}.3_Linux.run"
printf 'yes\n2\n' | PATH="$FAKELESS:$PATH" "$SRC_DIR/installer/MayaUSD_${PKG_VERSION}_Maya${MAYA_VERSION}.3_Linux.run" --nox11 --target "$EXTRACT_DIR"
rm -rf "$FAKELESS"

# The archive contains an RPM. Extract it without root using rpm --root.
RPM_FILE=$(find "$EXTRACT_DIR" -name '*.rpm' | head -1)
RPM_ROOT=$(mktemp -d)
rpm -ivh --nodeps --noscripts --root "$RPM_ROOT" "$RPM_FILE"
rm -rf "$EXTRACT_DIR"

# Move the installed files into the conda prefix, preserving the directory structure
# RPM installs to /usr/autodesk/mayausd/maya2026/<build_version>/ and /usr/autodesk/modules/
cp -r "$RPM_ROOT/usr" "$PREFIX/usr"
rm -rf "$RPM_ROOT"
