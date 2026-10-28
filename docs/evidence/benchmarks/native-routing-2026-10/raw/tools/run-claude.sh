#!/usr/bin/env bash
# usage: run-claude.sh <checkout-dir> <name> <prompt>   (from PH-04 tools/run-claude.sh)
# Headless Claude Code run with project settings only; stream-json transcript kept.
# --setting-sources project,local keeps the user's ~/.claude/CLAUDE.md, settings, plugins and hooks out
# (checked 2026-10-28 by capturing the request body against a local stub; method.md, Isolation). The one
# user-level input left is auto-memory, keyed by the clone path: a run's first session refuses to start
# when that folder already holds files (an earlier batch at the same runs/<name> path).
set -u
dir="$1"; name="$2"; prompt="$3"
base="<sandbox>"
out="$base/logs/transcripts/$name"; mkdir -p "$base/logs/transcripts"
for v in $(env | grep -o '^CLAUDE[A-Z_]*'); do unset "$v"; done
unset ANTHROPIC_MODEL
export PATH="<sandbox>/.tools/bin:$PATH"
mem="$HOME/.claude/projects/$(printf '%s' "$dir" | sed 's#[^A-Za-z0-9]#-#g')/memory"
case "$name" in *-a-scope) [ -z "$(ls -A "$mem" 2>/dev/null)" ] ||
  { echo "refusing: $mem holds auto-memory from an earlier session at this path" >&2; exit 8; } ;; esac
cd "$dir" || exit 9
date -u +%FT%TZ > "$out.start"
claude -p "$prompt" --output-format stream-json --verbose \
  --permission-mode bypassPermissions --setting-sources project,local \
  > "$out.jsonl" 2> "$out.stderr"
echo $? > "$out.exit"
date -u +%FT%TZ > "$out.end"
