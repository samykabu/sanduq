#!/usr/bin/env bash
# usage: prepare-base.sh <workflow-version> <release|path-to-sanduq-checkout> [--push]
#   One-time: fresh clone of sandbox main, Workflow upgraded to <version> from the GitHub release
#   (release) or from packages built out of a local Sanduq checkout (e.g. the PR branch worktree),
#   doctor, commit. With --push the upgrade becomes the new sandbox main (as PH-04 did for 1.24.0),
#   so every run clone starts from it. No model call.
# Example: prepare-base.sh 1.25.0 release --push
#          prepare-base.sh 1.25.0 <work>/sanduq/.worktrees/ph05      (dry run, no push)
set -eu
version="$1"; source="$2"; push="${3:-}"
base="<sandbox>"
repo="https://github.com/samykabu/sanduq-sandbox-ph04.git"
dir="$base/runs/base-$version"; log="$base/logs/prepare-base-$version.log"
export PATH="<sandbox>/.tools/bin:$PATH"   # Spec Kit 1.1.3 first, as in PH-04
export MSYS_NO_PATHCONV=1
mkdir -p "$base/logs"
[ -e "$dir" ] && { echo "refusing: $dir exists (remove it to rebuild)" >&2; exit 2; }
git -c core.autocrlf=false clone -q "$repo" "$dir"
cd "$dir"
git config user.name "Sanduq sandbox"; git config user.email "sandbox@local"
up=(python .specify/extensions/workflow/scripts/upgrade.py --version "$version")
if [ "$source" != release ]; then
  pk="$base/packages/$version"
  if [ ! -d "$pk/workflow" ]; then
    mkdir -p "$pk"
    python - "$source" "$pk" <<'PY'
import sys, zipfile
from pathlib import Path
src, out = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(src / 'extensions/scripts'))
import package
for ext in sorted(p.parent.name for p in (src / 'extensions').glob('*/extension.yml')):
    z = package.package(ext, output=out / (ext + '.zip'), root=src)
    zipfile.ZipFile(z['archive']).extractall(out)
    print(ext, z['sha256'][:12])
PY
  fi
  up+=(--packages "$pk")
fi
{ echo "== preview"; "${up[@]}"; echo "== apply"; "${up[@]}" --apply; } > "$log" 2>&1 || { tail -30 "$log"; exit 3; }
python .specify/extensions/workflow/scripts/workflow.py doctor --project > "$base/logs/doctor-base-$version.json" 2>&1 || true
python - "$base/logs/doctor-base-$version.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
print('doctor ok:', d.get('ok'), '| errors:', [e.get('code', e) if isinstance(e, dict) else e for e in d.get('errors', [])][:8])
PY
git add -A
git commit -qm "Upgrade Sanduq to Workflow $version for PH-05-T07 ($( [ "$source" = release ] && echo release || echo local packages))"
git log --oneline -1
if [ "$push" = --push ]; then git push -q origin HEAD:main && echo "pushed to sandbox main"; fi
