#!/usr/bin/env bash
# Package a Spec Kit extension into a release ZIP for catalog-based installs.
#
# The Spec Kit ZIP installer looks for extension.yml at the archive root or in a
# single top-level subdirectory. We zip the extension dir itself so the archive
# contains `<id>/extension.yml` (single top-level subdir → valid).
#
# Usage:
#   extensions/scripts/package.sh pr            # -> dist/pr.zip
#   extensions/scripts/package.sh pr 1.0.0      # version is informational only
#
# Then attach the ZIP to a GitHub release whose tag matches the catalog
# download_url, e.g.:
#   gh release create pr-v1.0.0 dist/pr.zip --title "pr extension v1.0.0" --notes "..."
set -euo pipefail

ID="${1:?usage: package.sh <extension-id> [version]}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/extensions/$ID"
OUT="$ROOT/dist"

[ -f "$SRC/extension.yml" ] || { echo "error: $SRC/extension.yml not found" >&2; exit 1; }

mkdir -p "$OUT"
rm -f "$OUT/$ID.zip"

# Zip from the extensions/ dir so the archive root is `<id>/...`
( cd "$ROOT/extensions" && zip -r -q "$OUT/$ID.zip" "$ID" \
    -x "$ID/.specify-dev*" -x "$ID/.specify*" )

echo "Built $OUT/$ID.zip"
unzip -l "$OUT/$ID.zip"
