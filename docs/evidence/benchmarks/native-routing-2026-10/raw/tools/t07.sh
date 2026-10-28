#!/usr/bin/env bash
# usage: t07.sh <workflow-version> <run> [<run> ...]      e.g. t07.sh 2.0.2 fx-codex
#   For each run in the order given: setup-run.sh (fresh clone + arm policy) and checkroute.py (the route
#   predicted at setup, logs/route-<run>.json) -> run-feature.sh (paid sessions) -> collect.py ->
#   validate.py (validity line in logs/rows/<run>.json) -> postmerge.sh. Runs strictly one after another.
#   Stops on the first failed or INVALID run, or when spend reaches STOP_USD (default 140).
#   Issues must be filed first (file-issues.sh).
#   run names: a1 a2 (in-session), b1 b2 (native), c1 c2 (external), fx-claude, fx-codex (fixtures)
set -u
version="$1"; shift
t="<sandbox>/tools"
export PATH="<sandbox>/.tools/bin:$PATH"
for run in "$@"; do
  case "$run" in
    a*) arm=insession; host=claude ;;  b*) arm=native; host=claude ;;  c*) arm=external; host=claude ;;
    fx-claude) arm=fixture; host=claude ;;  fx-codex) arm=fixture; host=codex ;;
    *) echo "unknown run $run" >&2; exit 2 ;;
  esac
  issue=$(awk -v r="$run" '$1==r{print $2}' "$t/../logs/issues.tsv")
  [ -n "$issue" ] || { echo "no issue filed for $run" >&2; exit 2; }
  extra=(); [ "$arm" = fixture ] && extra=(--issue "$issue")
  echo "=== $run ($arm, $host, issue #$issue) $(date -u +%FT%TZ)"
  dir="$t/../runs/$run"
  if [ ! -d "$dir" ]; then
    bash "$t/setup-run.sh" "$run" "$arm" "$version" "$host" "${extra[@]}" || exit 3
    python "$t/checkroute.py" "$dir" --feature "$(cd "$t" && python -c "import policy; print(policy.feature_for($issue))")" \
      > "$t/../logs/route-$run.json" || exit 3
  fi
  have=$(python -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1],encoding='utf-8'))['extension']['version'])" \
    "$dir/.specify/extensions/workflow/extension.yml")
  [ "$have" = "$version" ] || { echo "refusing: $dir has Workflow $have, expected $version" >&2; exit 3; }
  bash "$t/run-feature.sh" "$run" "$host"; rc=$?
  python "$t/collect.py" "$run"
  python "$t/validate.py" "$run"; vrc=$?
  bash "$t/postmerge.sh" "$run" || { echo "stopping: $run post-merge check failed" >&2; exit 8; }
  python "$t/spend.py" | tail -1
  [ $rc -eq 0 ] || { echo "stopping: $run exit $rc" >&2; exit $rc; }
  [ $vrc -eq 0 ] || { echo "stopping: $run is INVALID (validate.py exit $vrc); see logs/rows/$run.json" >&2; exit 7; }
done
