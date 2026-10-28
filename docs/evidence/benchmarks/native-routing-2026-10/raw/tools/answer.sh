#!/usr/bin/env bash
# usage: answer.sh <issue>   (from PH-04 tools/answer.sh)
# Posts "<id>: <recommended option>" for each Clarify question on the issue not answered before.
set -u
iss="$1"; base="<sandbox>"; repo=samykabu/sanduq-sandbox-ph04
gh issue view "$iss" --repo "$repo" --json comments --jq '.comments[].body' > "$base/logs/ans-$iss.txt" || exit 0
ans=$(python - "$base/logs/ans-$iss.txt" <<'PY'
import json, re, sys
txt = open(sys.argv[1], encoding='utf-8').read()
asked = {}
for m in re.finditer(r'<!-- speckit-clarification:question (\{.*?\}) -->', txt):
    q = json.loads(m.group(1)); asked[q['id']] = 'ABCDEFG'[q.get('recommended_option', 1) - 1]
answered = set(re.findall(r'(?m)^(C\d+Q\d+|SD\d+):\s*[A-G]\b', txt))
print('\n'.join(f'{i}: {o}' for i, o in asked.items() if i not in answered))
PY
)
[ -z "$ans" ] && exit 0
echo "answering #$iss:"; echo "$ans"
gh issue comment "$iss" --repo "$repo" --body "$ans" > /dev/null
