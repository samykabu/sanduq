#!/usr/bin/env bash
# usage: postmerge.sh <run>   (from PH-04 tools/postmerge.sh)
# Fresh LF clone, PR head merged with main locally, own suite + held-out tests; writes logs/rows/<run>.heldout.json
set -u
run="$1"; base=<sandbox>; repo=samykabu/sanduq-sandbox-ph04
issue=$(awk -v r="$run" '$1==r{print $2}' "$base/logs/issues.tsv")
branch=$(cd "$base/tools" && python -c "import policy; print(policy.feature_for($issue)[len('specs/'):])")
pr=$(gh pr list --repo "$repo" --state all --head "$branch" --json number --jq '.[0].number')
[ -n "$pr" ] || { echo "$run: no PR for $branch" >&2; exit 2; }
w="$base/pm/$run"; rm -rf "$w"
git -c core.autocrlf=false clone -q "https://github.com/$repo.git" "$w" && cd "$w" || exit 9
git fetch -q origin "pull/$pr/head:pr$pr" && git checkout -q "pr$pr"
git -c user.name=pm -c user.email=pm@local merge -q --no-edit origin/main >/dev/null 2>&1 || { echo "{\"run\":\"$run\",\"pr\":$pr,\"merge\":\"conflict\"}" > "$base/logs/rows/$run.heldout.json"; exit 1; }
own=$(python -m unittest discover -s tests 2>&1 | grep -E "^Ran|^OK|^FAILED" | tr '\n' ' ')
cp "$base/heldout/test_heldout_t07.py" .
hid=$(python -m unittest test_heldout_t07 2>&1 | grep -E "^Ran|^OK|^FAILED" | tr '\n' ' ')
mkdir -p "$base/logs/rows"
python - "$base/logs/rows/$run.heldout.json" "$run" "$pr" "$own" "$hid" <<'PY'
import json, re, sys
path, run, pr, own, hid = sys.argv[1:]
ran = int((re.search(r'Ran (\d+)', hid) or [0, 0])[1])
bad = sum(int(n) for n in re.findall(r'(?:failures|errors)=(\d+)', hid))
json.dump({'run': run, 'pr': int(pr), 'own': own.strip(), 'heldout': hid.strip(), 'heldout_failed': bad, 'heldout_ran': ran},
          open(path, 'w'), indent=1)
print(run, 'PR', pr, '| own:', own, '| held-out:', hid)
PY
