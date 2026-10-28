#!/usr/bin/env bash
# usage: setup-run.sh <run-name> <arm> <expected-workflow-version> [claude|codex] [--issue N]
#   Fresh clone of sandbox main (or of $BASE_SRC, a local base clone, for dry runs), default host,
#   arm policy (tools/policy.py), role files re-rendered (reconcile.py --apply), delegate-task driver
#   installed when delegation is on, doctor, one local commit "T07 arm policy". No model call, no push.
# Example: setup-run.sh b1 native 2.0.2
#          setup-run.sh fx-codex fixture 2.0.2 codex --issue 123
set -eu
name="$1"; arm="$2"; version="$3"; host="${4:-claude}"; shift 4 2>/dev/null || shift $#
base="<sandbox>"
src="${BASE_SRC:-https://github.com/samykabu/sanduq-sandbox-ph04.git}"
dir="$base/runs/$name"; log="$base/logs/setup-$name.log"
export PATH="<sandbox>/.tools/bin:$PATH"
export MSYS_NO_PATHCONV=1
W="python .specify/extensions/workflow/scripts"
[ -e "$dir" ] && { echo "refusing: $dir exists" >&2; exit 2; }
git clone -q "$src" "$dir"
cd "$dir"
echo ".specify/workflow/runtime/" >> .git/info/exclude
git remote set-url origin https://github.com/samykabu/sanduq-sandbox-ph04.git
git config user.name "Sanduq sandbox"; git config user.email "sandbox@local"
have=$(python -c "import yaml;print(yaml.safe_load(open('.specify/extensions/workflow/extension.yml',encoding='utf-8'))['extension']['version'])")
[ "$have" = "$version" ] || { echo "refusing: clone has Workflow $have, expected $version (run prepare-base.sh first)" >&2; exit 3; }
{
  if [ "$host" = codex ]; then $W/workflow.py host --use codex; fi
  python "$base/tools/policy.py" "$dir" "$arm" "$@"
  if [ "$arm" != insession ]; then $W/reconcile.py --apply; fi
  if [ "$arm" != insession ]; then $W/delegation.py install; fi
} > "$log" 2>&1 || { tail -20 "$log"; exit 4; }
$W/workflow.py doctor --project > "$base/logs/doctor-$name.json" 2>&1 || true
python - "$base/logs/doctor-$name.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
codes = [w.split(':')[0] for w in d.get('warnings', [])]
print('doctor ok:', d.get('ok'), '| errors:', d.get('errors'), '| warnings:', sorted(set(codes)))
PY
git add -A && git commit -q --allow-empty -m "T07 arm policy: $arm (host $host)"   # empty for in-session: validate.py needs it && git log --oneline -1
grep -h "^model" .claude/agents/sanduq-worker.md .codex/agents/sanduq-worker.toml 2>/dev/null || true
