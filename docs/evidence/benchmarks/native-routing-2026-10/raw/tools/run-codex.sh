#!/usr/bin/env bash
# usage: run-codex.sh <checkout-dir> <name> <prompt>   (from PH-04 tools/run-codex.sh)
# Runs with an isolated CODEX_HOME per run (<base>/codex-home/<run>, tools/codex-home.py): login and model
# settings only, no user AGENTS.md, skills, plugins, MCP servers or memories.
set -u
dir="$1"; name="$2"; prompt="$3"
base="<sandbox>"
out="$base/logs/transcripts/$name"; mkdir -p "$base/logs/transcripts"
for v in $(env | grep -o '^CLAUDE[A-Z_]*'); do unset "$v"; done
export PATH="<sandbox>/.tools/bin:$PATH"
home=$(python "$base/tools/codex-home.py" prepare "$dir" "$base/codex-home/$(basename "$dir")") || exit 8
cd "$dir" || exit 9
date -u +%FT%TZ > "$out.start"
CODEX_HOME="$home" codex exec --json --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust \
  -C "$dir" "$prompt" > "$out.jsonl" 2> "$out.stderr" < /dev/null
echo $? > "$out.exit"
date -u +%FT%TZ > "$out.end"
python "$base/tools/codex-home.py" sync "$home"
