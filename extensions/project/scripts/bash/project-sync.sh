#!/usr/bin/env bash
# Mirror a Spec Kit feature onto a GitHub Project (v2). Bash twin of project-sync.ps1.
# Idempotent, no-regress. Requires gh (with 'project' scope) and jq. Degrades gracefully
# (logs + exits 0) if gh/jq/remote/scope/config preconditions are not met.
#
# Usage: project-sync.sh --phase <open|analysis|engineer-review|ready|in-progress|in-review|done|auto>
#                        [--feature <slug>] [--dry-run] [--no-sub-issues] [--force] [--json]
set -euo pipefail

PHASE="auto"; FEATURE=""; DRYRUN=0; NOSUB=0; FORCE=0; JSON=0
while [ $# -gt 0 ]; do case "$1" in
  --phase) PHASE="$2"; shift 2;;
  --feature) FEATURE="$2"; shift 2;;
  --dry-run) DRYRUN=1; shift;;
  --no-sub-issues) NOSUB=1; shift;;
  --force) FORCE=1; shift;;
  --json) JSON=1; shift;;
  *) echo "[project][warn] unknown arg: $1"; shift;;
esac; done

log()  { echo "[project] $*"; }
warn() { echo "[project][warn] $*"; }
skip() { warn "skipped: $*"; [ "$JSON" = 1 ] && echo "{\"skipped\":true,\"reason\":\"$*\"}"; exit 0; }
gh_run() { if [ "$DRYRUN" = 1 ]; then log "DRYRUN gh $*"; return 0; fi; gh "$@"; }

command -v gh >/dev/null 2>&1 || skip "gh CLI not installed"
command -v jq >/dev/null 2>&1 || skip "jq not installed"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || skip "not a git repo"
cd "$ROOT"
CFG=".specify/extensions/project/config.json"
[ -f "$CFG" ] || skip "not configured - run project-init.sh (or /speckit-project-init) first"

gh auth status >/dev/null 2>&1 || skip "gh not authenticated"
gh auth status 2>&1 | grep -q "project" || skip "gh token lacks 'project' scope (gh auth refresh -h github.com -s project,read:project)"
REMOTE="$(git config --get remote.origin.url || true)"
echo "$REMOTE" | grep -q "github.com" || skip "remote is not GitHub ($REMOTE)"
REPO="$(echo "$REMOTE" | sed -E 's#.*github\.com[:/]+([^/]+)/([^/.]+)(\.git)?/?$#\1/\2#')"

if [ -z "$FEATURE" ] && [ -f .specify/feature.json ]; then
  FEATURE="$(jq -r '.feature_directory // empty' .specify/feature.json | sed 's#.*/##')"
fi
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
[ -z "$FEATURE" ] && FEATURE="$BRANCH"
[ -z "$FEATURE" ] && skip "could not resolve feature slug"
SLUG="$FEATURE"
FDIR="specs/$SLUG"; SPEC="$FDIR/spec.md"; PLAN="$FDIR/plan.md"; TASKS="$FDIR/tasks.md"
TITLE="$SLUG"
[ -f "$SPEC" ] && TITLE="$(grep -m1 -E '^# ' "$SPEC" | sed -E 's/^# +//; s/^(Feature Specification|Spec): *//' || echo "$SLUG")"

val() { jq -r "$1" "$CFG"; }
PROJ_NUM="$(val '.projectNumber')"; PROJ_ID="$(val '.projectId')"; OWNER="$(val '.owner')"
STATUS_FIELD="$(val '.statusFieldId')"; STATE_FILE="$(val '.stateFile')"
[ -n "$PROJ_ID" ] && [ "$PROJ_ID" != "null" ] || skip "config.json missing projectId - re-run project-init.sh"
status_opt()   { jq -r ".statusOptions[\"$1\"] // empty" "$CFG"; }
phase_status() { jq -r ".phaseToStatus[\"$1\"] // empty" "$CFG"; }
status_index() { jq -r --arg s "$1" '.statusOrder | index($s) // 0' "$CFG"; }

[ -f "$STATE_FILE" ] || echo '{}' > "$STATE_FILE"
ST="$(cat "$STATE_FILE")"
sget() { echo "$ST" | jq -r ".\"$SLUG\".$1 // empty"; }
ISSUE="$(sget issue)"; NODE="$(sget issueNodeId)"; ITEM="$(sget itemId)"; CURRENT="$(sget status)"
[ -z "$ISSUE" ] && ISSUE=0
save_state() { [ "$DRYRUN" = 1 ] && return 0; echo "$ST" > "$STATE_FILE"; }
st_set() { ST="$(echo "$ST" | jq --arg s "$SLUG" ".[\$s].$1 = $2")"; }
[ "$(echo "$ST" | jq -r --arg s "$SLUG" 'has($s)')" = "true" ] || ST="$(echo "$ST" | jq --arg s "$SLUG" '.[$s]={issue:0,issueNodeId:"",itemId:"",status:"",subIssues:{}}')"

ensure_parent() {
  if [ "${ISSUE:-0}" -gt 0 ] 2>/dev/null; then return; fi
  local found n
  found="$(gh issue list --repo "$REPO" --state all --label spec-feature --search "in:title $SLUG" --json number,title,id --limit 20 2>/dev/null || echo '[]')"
  n="$(echo "$found" | jq -r --arg s "$SLUG" 'map(select(.title|test($s;"i")))[0].number // empty')"
  if [ -n "$n" ]; then
    ISSUE="$n"; NODE="$(echo "$found" | jq -r --arg s "$SLUG" 'map(select(.title|test($s;"i")))[0].id')"
    log "found existing parent issue #$ISSUE"; st_set issue "$ISSUE"; st_set issueNodeId "\"$NODE\""; return
  fi
  if [ "$DRYRUN" = 1 ]; then log "DRYRUN create parent issue for $SLUG"; ISSUE=-1; return; fi
  gh label create spec-feature --repo "$REPO" --color BFD4F2 --force >/dev/null 2>&1 || true
  local url
  url="$(gh issue create --repo "$REPO" --title "[$SLUG] $TITLE" --body "Tracking issue for Spec Kit feature \`$SLUG\` (branch \`$BRANCH\`). Managed by the sanduq project extension." --label spec-feature)"
  ISSUE="$(echo "$url" | sed -E 's#.*/issues/([0-9]+).*#\1#')"
  NODE="$(gh issue view "$ISSUE" --repo "$REPO" --json id -q .id)"
  st_set issue "$ISSUE"; st_set issueNodeId "\"$NODE\""; log "created parent issue #$ISSUE"
}

ensure_in_project() {
  [ "${ISSUE:-0}" -gt 0 ] 2>/dev/null || return
  [ -n "$ITEM" ] && return
  local url res
  url="https://github.com/$REPO/issues/$ISSUE"
  res="$(gh_run project item-add "$PROJ_NUM" --owner "$OWNER" --url "$url" --format json 2>/dev/null || echo '')"
  [ -n "$res" ] && ITEM="$(echo "$res" | jq -r '.id // empty')"
  if [ -z "$ITEM" ] && [ "$DRYRUN" != 1 ]; then
    ITEM="$(gh project item-list "$PROJ_NUM" --owner "$OWNER" --format json --limit 200 2>/dev/null \
      | jq -r --argjson n "$ISSUE" '.items[] | select(.content.number==$n) | .id' | head -1)"
  fi
  [ -n "$ITEM" ] && { st_set itemId "\"$ITEM\""; log "issue #$ISSUE on Project #$PROJ_NUM"; }
}

set_status() {
  local s="$1" oi ci opt; oi="$(status_index "$s")"; ci="$(status_index "$CURRENT")"; opt="$(status_opt "$s")"
  [ -z "$opt" ] && { warn "column '$s' not on this board (phase unmapped); skipping"; return; }
  if [ -n "$CURRENT" ] && [ "$FORCE" != 1 ] && [ "$oi" -lt "$ci" ]; then log "no-regress: card '$CURRENT'; not moving to '$s'"; return; fi
  [ "$CURRENT" = "$s" ] && { log "status already '$s'"; return; }
  [ -z "$ITEM" ] && { warn "no project item id; cannot set status"; return; }
  gh_run project item-edit --id "$ITEM" --project-id "$PROJ_ID" --field-id "$STATUS_FIELD" --single-select-option-id "$opt" >/dev/null
  CURRENT="$s"; st_set status "\"$s\""; log "status -> $s"
}

parse_tasks() {
  [ -f "$TASKS" ] || return
  grep -E '^\s*-\s*\[[ xX]\]\s*' "$TASKS" | while IFS= read -r line; do
    local done id desc
    echo "$line" | grep -qE '^\s*-\s*\[[xX]\]' && done=1 || done=0
    id="$(echo "$line" | sed -nE 's/^\s*-\s*\[[ xX]\]\s*\**([Tt][0-9]+)\**.*/\1/p')"
    [ -z "$id" ] && continue
    desc="$(echo "$line" | sed -E 's/^\s*-\s*\[[ xX]\]\s*\**[Tt][0-9]+\**\s*//; s/\*\*//g; s/\[[Pp]\]//g' | cut -c1-90)"
    printf '%s\t%s\t%s\n' "$done" "$id" "$desc"
  done
}

sync_sub_issues() {
  [ "$(val '.subIssues.enabled')" = "true" ] || return
  [ "$NOSUB" = 1 ] && return
  [ -z "$NODE" ] && { warn "no parent node id; skipping sub-issues"; return; }
  gh label create spec-task --repo "$REPO" --color D4C5F9 --force >/dev/null 2>&1 || true
  local created=0
  while IFS=$'\t' read -r done id desc; do
    [ -z "$id" ] && continue
    echo "$ST" | jq -e --arg s "$SLUG" --arg i "$id" '.[$s].subIssues[$i]' >/dev/null 2>&1 && continue
    if [ "$DRYRUN" = 1 ]; then log "DRYRUN create sub-issue '$SLUG $id: $desc'"; created=$((created+1)); continue; fi
    local surl snum snode
    surl="$(gh issue create --repo "$REPO" --title "$SLUG $id: $desc" --body "Task \`$id\` of feature \`$SLUG\` (parent #$ISSUE)." --label spec-task)"
    snum="$(echo "$surl" | sed -E 's#.*/issues/([0-9]+).*#\1#')"
    snode="$(gh issue view "$snum" --repo "$REPO" --json id -q .id)"
    gh api graphql -H "GraphQL-Features: sub_issues" \
      -f query='mutation($p:ID!,$c:ID!){addSubIssue(input:{issueId:$p,subIssueId:$c}){subIssue{number}}}' \
      -f p="$NODE" -f c="$snode" >/dev/null 2>&1 || warn "sub-issue link failed for $id"
    ST="$(echo "$ST" | jq --arg s "$SLUG" --arg i "$id" --argjson n "$snum" --arg nd "$snode" '.[$s].subIssues[$i] = {number:$n,nodeId:$nd,closed:false}')"
    created=$((created+1))
  done < <(parse_tasks)
  [ "$created" -gt 0 ] && log "created $created sub-issue(s)"
}

sync_progress() {
  local total closed=0
  total="$(echo "$ST" | jq -r --arg s "$SLUG" '(.[$s].subIssues // {}) | length')"
  [ "$total" = 0 ] && return
  while IFS=$'\t' read -r done id desc; do
    [ "$done" = 1 ] || continue
    local isclosed num
    isclosed="$(echo "$ST" | jq -r --arg s "$SLUG" --arg i "$id" '.[$s].subIssues[$i].closed // empty')"
    num="$(echo "$ST" | jq -r --arg s "$SLUG" --arg i "$id" '.[$s].subIssues[$i].number // empty')"
    if [ -n "$num" ] && [ "$isclosed" != "true" ]; then
      gh_run issue close "$num" --repo "$REPO" --reason completed >/dev/null 2>&1 || true
      ST="$(echo "$ST" | jq --arg s "$SLUG" --arg i "$id" '.[$s].subIssues[$i].closed = true')"
      closed=$((closed+1))
    fi
  done < <(parse_tasks)
  local done_c; done_c="$(echo "$ST" | jq -r --arg s "$SLUG" '[.[$s].subIssues[] | select(.closed==true)] | length')"
  [ "$closed" -gt 0 ] && log "closed $closed completed sub-issue(s)"
  log "sub-issue progress: $done_c/$total"
}

has_open_pr() {
  local pr; pr="$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --json number --limit 1 2>/dev/null || echo '[]')"
  [ "$(echo "$pr" | jq 'length')" -gt 0 ] 2>/dev/null
}

resolve_auto() {
  local n done
  if [ -f "$TASKS" ]; then
    n="$(parse_tasks | wc -l | tr -d ' ')"; done="$(parse_tasks | awk -F'\t' '$1==1' | wc -l | tr -d ' ')"
    if [ "$n" -gt 0 ]; then
      [ "$done" = 0 ] && { phase_status ready; return; }
      [ "$done" -lt "$n" ] && { phase_status in-progress; return; }
      phase_status in-review; return
    fi
  fi
  [ -f "$PLAN" ] && { phase_status analysis; return; }
  phase_status open
}

log "feature '$SLUG' -> repo $REPO, Project #$PROJ_NUM, phase '$PHASE'"
ensure_parent
ensure_in_project

if [ "$PHASE" = "auto" ]; then TARGET="$(resolve_auto)"; else TARGET="$(phase_status "$PHASE")"; fi

if [ "$PHASE" = "ready" ] || { [ "$PHASE" = "auto" ] && [ "$TARGET" = "$(phase_status ready)" ]; }; then sync_sub_issues; fi
case "$PHASE" in in-progress|in-review|done|auto) sync_progress;; esac

# self-contained in-review when an open PR exists
case "$PHASE" in
  in-progress|auto|in-review)
    IR="$(phase_status in-review)"
    if [ -n "$IR" ] && [ "$(status_index "$TARGET")" -lt "$(status_index "$IR")" ] && has_open_pr; then
      log "open PR detected for '$BRANCH' -> advancing to in-review"; TARGET="$IR"
    fi;;
esac

set_status "$TARGET"
save_state
log "done: issue #$ISSUE, status '$CURRENT', phase '$PHASE'"
[ "$JSON" = 1 ] && echo "{\"feature\":\"$SLUG\",\"repo\":\"$REPO\",\"issue\":$ISSUE,\"status\":\"$CURRENT\",\"phase\":\"$PHASE\"}"
