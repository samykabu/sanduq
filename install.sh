#!/usr/bin/env bash
# Manual (non-catalog) installer: copy a sanduq extension into a target Spec Kit repo.
#
# Full hook-wiring + rendering of the command into every assistant target is done by the
# Spec Kit CLI (`speckit extension install <id>`) — the supported path. This script is the
# fallback: it stages the extension files and prints the exact next steps.
#
# Usage (run from the TARGET repo root):
#   /path/to/sanduq/install.sh --extension project [--target .]
set -euo pipefail

EXT=""; TARGET="."
while [ $# -gt 0 ]; do case "$1" in
  --extension) EXT="$2"; shift 2;;
  --target) TARGET="$2"; shift 2;;
  *) echo "unknown arg: $1"; exit 1;;
esac; done
[ -z "$EXT" ] && { echo "usage: install.sh --extension <id> [--target <repo>]"; exit 1; }

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/extensions/$EXT"
[ -d "$SRC" ] || { echo "no such extension: $EXT (looked in $SRC)"; exit 1; }
[ -d "$TARGET/.specify" ] || { echo "target '$TARGET' is not a Spec Kit repo (.specify/ missing)"; exit 1; }

DEST="$TARGET/.specify/extensions/$EXT"
mkdir -p "$DEST"
cp -R "$SRC/." "$DEST/"
echo "[sanduq] copied extension '$EXT' -> $DEST"

echo
echo "Next steps:"
echo "  1. Finalise install (wire hooks + render the command into your assistant targets):"
echo "       speckit extension install $EXT      # if you use the Spec Kit CLI"
echo "     …or add sanduq to .specify/extension-catalogs.yml and install from the catalog."
echo "  2. One-time board setup:"
echo "       gh auth refresh -h github.com -s project,read:project"
echo "       pwsh $DEST/scripts/powershell/project-init.ps1   # or scripts/bash/project-init.sh"
echo "  3. Commit .specify/extensions/$EXT and .specify/extensions/$EXT/config.json."
echo
echo "Declared hooks to merge into .specify/extensions.yml (see $DEST/extension.yml 'hooks:'):"
echo "  after_specify/plan/analyze/tasks + before/after_implement -> speckit.project.sync"
