#!/usr/bin/env bash
# usage: file-issues.sh [run ...]   (default: a1 a2 b1 b2 c1 c2 fx-claude fx-codex)
# Files one sandbox issue per run with the body from issue.md (variant A; fx-* runs get variant B, which
# asks for two separately testable tasks); appends "<run>\t<number>" to logs/issues.tsv.
set -eu
base="<sandbox>"; repo=samykabu/sanduq-sandbox-ph04
runs="${*:-a1 a2 b1 b2 c1 c2 fx-claude fx-codex}"
body=$(awk '/^````markdown$/{f=1;next} /^````$/{f=0} f' "$base/issue.md")
fixture_body=$(awk '/^````markdown fixture$/{f=1;next} /^````$/{f=0} f' "$base/issue.md")
[ -n "$body" ] && [ -n "$fixture_body" ] || { echo "no body (variant A and B) found in issue.md" >&2; exit 2; }
for r in $runs; do
  awk -F '\t' -v r="$r" '$1==r{f=1} END{exit !f}' "$base/logs/issues.tsv" 2>/dev/null && { echo "$r already filed"; continue; }
  url=$(gh issue create --repo "$repo" --title "Add initials and squeeze commands (T07 $r)" --body "$(case "$r" in fx-*) echo "$fixture_body" ;; *) echo "$body" ;; esac)")
  printf '%s\t%s\n' "$r" "${url##*/}" >> "$base/logs/issues.tsv"; echo "$r $url"
done
