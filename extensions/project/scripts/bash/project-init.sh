#!/usr/bin/env bash
# Deprecated stub, removed in the next release: Project init is scripts/project_init.py. Every argument
# (bash or PowerShell spelling) passes through unchanged.
echo "[project-init][warn] project-init.sh is deprecated; run: python .specify/extensions/project/scripts/project_init.py [flags]" >&2
PY="$(command -v python || command -v python3)" || { echo "[project-init][error] python not found"; exit 1; }
exec "$PY" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../project_init.py" "$@"
