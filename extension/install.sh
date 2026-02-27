#!/usr/bin/env bash
# install.sh — Install the Gnome Agent GNOME Shell extension.
#
# Usage: bash extension/install.sh
# After running: log out and back in (or run: gnome-extensions enable gnome-agent@localhost)

set -euo pipefail

EXTENSION_UUID="gnome-agent@localhost"
EXTENSION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.local/share/gnome-shell/extensions/${EXTENSION_UUID}"

echo "📦 Installing Gnome Agent extension..."

# Compile GSettings schema
echo "  → Compiling GSettings schema..."
glib-compile-schemas "${EXTENSION_DIR}/schemas/"

# Create install directory and symlink (or copy)
mkdir -p "${INSTALL_DIR}"
rsync -a --delete "${EXTENSION_DIR}/" "${INSTALL_DIR}/"

echo "  → Installed to: ${INSTALL_DIR}"

# Enable extension (requires gnome-shell running)
if command -v gnome-extensions &>/dev/null; then
    gnome-extensions enable "${EXTENSION_UUID}" 2>/dev/null && \
        echo "  → Extension enabled ✓" || \
        echo "  ℹ  Enable manually: gnome-extensions enable ${EXTENSION_UUID}"
fi

echo ""
echo "✅ Done! You may need to restart GNOME Shell:"
echo "   • On X11: Alt+F2 → type 'r' → Enter"
echo "   • On Wayland: Log out and log back in"
echo ""
echo "Then open the extension from the top bar."
