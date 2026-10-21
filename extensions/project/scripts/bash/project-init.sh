#!/usr/bin/env bash
# One-time setup for the 'project' extension (bash twin of project-init.ps1): discover a
# GitHub Project (v2), map lifecycle phases to the board's Status columns (exact -> fuzzy ->
# prompt -> optional auto-create), and write .specify/extensions/project/config.json. A rerun keeps
# the existing parentIssue, subIssues and stateFile settings.
#
# Usage: project-init.sh [--owner <login>] [--number <n>] [--owner-type user|org]
#                        [--hooks-mode optional|required] [--auto-create-columns]
#                        [--non-interactive] [--allow-status-reset] [--dry-run] [--json]
# --allow-status-reset: change columns even when the board's item statuses cannot be read; they are then cleared.
set -euo pipefail

OWNER=""; NUMBER=0; OWNER_TYPE=""; HOOKS_MODE=""; AUTOCREATE=0; NONINT=0; DRYRUN=0; JSON=0; ALLOW_RESET=0; RESTORE_FAILED=0
while [ $# -gt 0 ]; do case "$1" in
  --owner) OWNER="$2"; shift 2;;
  --number) NUMBER="$2"; shift 2;;
  --owner-type) OWNER_TYPE="$2"; shift 2;;
  --hooks-mode) HOOKS_MODE="$2"; shift 2;;
  --auto-create-columns) AUTOCREATE=1; shift;;
  --non-interactive) NONINT=1; shift;;
  --allow-status-reset) ALLOW_RESET=1; shift;;
  --dry-run) DRYRUN=1; shift;;
  --json) JSON=1; shift;;
  *) echo "[project-init][warn] unknown arg: $1"; shift;;
esac; done

info(){ echo "[project-init] $*"; }
warn(){ echo "[project-init][warn] $*"; }
die(){ echo "[project-init][error] $*"; exit 1; }

set_project_hook_mode(){
  local mode="$1" optional_value count tmp
  local extensions_yml=".specify/extensions.yml"
  [ -f "$extensions_yml" ] || die ".specify/extensions.yml not found - install with 'specify extension add project' before init"
  [ "$mode" = "optional" ] && optional_value=true || optional_value=false
  count="$(awk '
    /^[[:space:]]*-[[:space:]]+extension:[[:space:]]+project[[:space:]]*$/ { in_project=1; next }
    /^[[:space:]]*-[[:space:]]+extension:[[:space:]]+/ { in_project=0 }
    in_project && /^[[:space:]]*optional:[[:space:]]*(true|false)[[:space:]]*$/ { count++; in_project=0 }
    END { print count+0 }
  ' "$extensions_yml")"
  [ "$count" -gt 0 ] || die "no project sync hooks found in .specify/extensions.yml - reinstall the project extension and retry"
  if [ "$DRYRUN" = 1 ]; then
    info "DRYRUN would set $count project sync hook(s) to $mode"
    return
  fi
  tmp="$(mktemp "${extensions_yml}.tmp.XXXXXX")"
  awk -v value="$optional_value" '
    /^[[:space:]]*-[[:space:]]+extension:[[:space:]]+project[[:space:]]*$/ { in_project=1 }
    /^[[:space:]]*-[[:space:]]+extension:[[:space:]]+/ && $0 !~ /extension:[[:space:]]+project[[:space:]]*$/ { in_project=0 }
    in_project && /^[[:space:]]*optional:[[:space:]]*(true|false)[[:space:]]*$/ {
      sub(/optional:[[:space:]]*(true|false)[[:space:]]*$/, "optional: " value)
      in_project=0
    }
    { print }
  ' "$extensions_yml" > "$tmp"
  mv "$tmp" "$extensions_yml"
  info "set $count project sync hook(s) to $mode"
}

command -v gh >/dev/null 2>&1 || die "gh CLI not installed"
command -v jq >/dev/null 2>&1 || die "jq not installed"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not inside a git repository"
cd "$ROOT"
EXT_DIR=".specify/extensions/project"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEF="$SCRIPT_DIR/../../config.default.json"; [ -f "$DEF" ] || DEF="$EXT_DIR/config.default.json"
[ -f "$DEF" ] || die "config.default.json not found"
OUT="$EXT_DIR/config.json"
# A rerun keeps the existing sub-issue, parent and state settings; defaults apply on the first run only.
[ -f "$OUT" ] && { jq -e . "$OUT" >/dev/null 2>&1 || die "$OUT is not valid JSON - fix or delete it, then rerun"; }
keep(){ if [ -f "$OUT" ] && jq -e --arg k "$1" 'has($k)' "$OUT" >/dev/null; then jq --arg k "$1" '.[$k]' "$OUT"; else jq --arg k "$1" '.[$k]' "$DEF"; fi; }
MANAGED_WORKFLOW=0
MANAGED_DEFAULTS='{}'
REQUIRED=""  # managed: the exact column names Workflow's doctor requires, one per line
if [ -f "$ROOT/.specify/workflow.yml" ]; then
  MANAGED_WORKFLOW=1; HOOKS_MODE=required
  MANAGED_DEFAULTS="$(python "$ROOT/.specify/extensions/workflow/scripts/workflow.py" project-defaults)" || die 'cannot read managed workflow phase defaults; run workflow doctor'
  REQUIRED="$(printf '%s' "$MANAGED_DEFAULTS" | jq -r '.statuses[]?' | tr -d '\r')"
fi

gh auth status >/dev/null 2>&1 || die "gh not authenticated - run: gh auth login"
# 'project' as a whole scope: 'read:project' alone cannot write the board
gh auth status 2>&1 | grep -Eq "(^|[^:[:alnum:]_-])project([^:[:alnum:]_-]|$)" || die "gh token lacks 'project' scope - run: gh auth refresh -h github.com -s project,read:project"

[ -z "$OWNER" ] && OWNER="$(gh api user --jq .login)"
[ -z "$OWNER" ] && die "could not resolve owner - pass --owner"
if [ -z "$OWNER_TYPE" ]; then
  # 'gh project list' accepts org logins too, so only the account type tells the two apart
  KIND="$(gh api "users/$OWNER" --jq .type 2>/dev/null | tr -d '\r')" || die "cannot tell whether $OWNER is a user or an organization - pass --owner-type user|org"
  if [ "$KIND" = "Organization" ]; then OWNER_TYPE="org"; else OWNER_TYPE="user"; fi
fi
info "owner: $OWNER ($OWNER_TYPE)"

if [ "$NUMBER" -le 0 ] 2>/dev/null; then
  LIST="$(gh project list --owner "$OWNER" --format json)" || die "could not list projects for $OWNER"
  COUNT="$(echo "$LIST" | jq '.projects | length')"
  [ "$COUNT" -eq 0 ] && die "no projects for $OWNER - create one or pass --number"
  if [ "$COUNT" -eq 1 ]; then NUMBER="$(echo "$LIST" | jq -r '.projects[0].number')"
  elif [ "$NONINT" = 1 ]; then die "multiple projects for $OWNER: $(echo "$LIST" | jq -r '[.projects[] | "#\(.number) \(.title)"] | join(", ")') - ask which one and rerun with --number <n>"
  else
    info "Select a project:"
    echo "$LIST" | jq -r '.projects | to_entries[] | "  [\(.key)] #\(.value.number)  \(.value.title)"'
    read -r -p "index: " IDX
    NUMBER="$(echo "$LIST" | jq -r --argjson i "$IDX" '.projects[$i].number')"
  fi
fi
info "project #$NUMBER"

VIEW="$(gh project view "$NUMBER" --owner "$OWNER" --format json)" || die "cannot view project #$NUMBER"
PROJ_ID="$(echo "$VIEW" | jq -r '.id')"
PROJ_URL="$(echo "$VIEW" | jq -r '.url')"
FIELDS="$(gh project field-list "$NUMBER" --owner "$OWNER" --format json)"
STATUS_FIELD_ID="$(echo "$FIELDS" | jq -r '.fields[] | select(.name=="Status" and .options) | .id' | head -1)"
[ -z "$STATUS_FIELD_ID" ] && die "no single-select 'Status' field on project #$NUMBER"
# board columns: name<TAB>id
BOARD="$(echo "$FIELDS" | jq -r '.fields[] | select(.id=="'"$STATUS_FIELD_ID"'") | .options[] | "\(.name)\t\(.id)"')"
info "board Status columns: $(echo "$BOARD" | cut -f1 | paste -sd, -)"

norm(){ echo "$1" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]'; }
board_fuzzy(){ local nw; nw="$(norm "$1")"; echo "$BOARD" | cut -f1 | while read -r c; do nc="$(norm "$c")"; if [ "$nc" = "$nw" ] || echo "$nc" | grep -q "$nw" || echo "$nw" | grep -q "$nc"; then echo "$c"; break; fi; done; }

PHASES="open analysis engineer-review ready in-progress in-review done"
PALETTE=(GRAY BLUE PURPLE GREEN YELLOW ORANGE PINK)
declare -A PHASE2STATUS; declare -A STATUSOPT
while IFS=$'\t' read -r name option_id; do
  [ -n "$name" ] && STATUSOPT["$name"]="$option_id"
done <<< "$BOARD"
CREATE_NAMES=(); CREATE_COLORS=(); CREATE_FROM=()  # one entry per name; FROM: a board column renamed to it

map_column(){
  local phase="$1" wanted="$2" color="$3" label match variant idx do_create ans
  if [ -n "$phase" ]; then label="phase '$phase'"; else label="status '$wanted'"; fi
  # managed: doctor and Scope compare exact names, so only an exact (case-sensitive) column matches
  match="$(echo "$BOARD" | awk -F'\t' -v n="$wanted" '$1==n{print $1; exit}')"
  if [ -z "$match" ] && [ "$MANAGED_WORKFLOW" = 0 ]; then
    match="$(echo "$BOARD" | awk -F'\t' -v n="$wanted" 'tolower($1)==tolower(n){print $1; exit}')"
    [ -n "$match" ] || match="$(board_fuzzy "$wanted")"
  fi
  if [ -n "$match" ]; then
    if [ -n "$phase" ]; then PHASE2STATUS[$phase]="$match"; fi
    printf '[project-init]   %-16s -> %s\n' "${phase:-status}" "$match"
    return 0
  fi
  for idx in "${!CREATE_NAMES[@]}"; do
    if [ "${CREATE_NAMES[$idx]}" = "$wanted" ]; then
      if [ -n "$phase" ]; then PHASE2STATUS[$phase]="$wanted"; fi
      return 0
    fi
  done
  # managed: a column that differs only in case or spacing is renamed rather than duplicated
  variant=""
  if [ "$MANAGED_WORKFLOW" = 1 ]; then
    variant="$(echo "$BOARD" | cut -f1 | while read -r c; do if [ -n "$c" ] && [ "$(norm "$c")" = "$(norm "$wanted")" ]; then echo "$c"; break; fi; done)"
  fi
  do_create=$AUTOCREATE
  if [ "$do_create" = 0 ] && [ "$NONINT" = 0 ]; then
    if [ -n "$variant" ]; then ans="Rename '$variant' to '$wanted'"; else ans="Create '$wanted'"; fi
    read -r -p "[project-init]   no column for $label (wanted '$wanted'). $ans? [y/N] " ans
    if [[ "$ans" =~ ^[yY] ]]; then do_create=1; fi
  fi
  if [ "$do_create" = 1 ]; then
    CREATE_NAMES+=("$wanted"); CREATE_COLORS+=("$color"); CREATE_FROM+=("$variant")
    if [ -n "$phase" ]; then PHASE2STATUS[$phase]="$wanted"; fi
  else warn "$label has no column (wanted '$wanted') - that transition is a no-op until mapped; rerun with --auto-create-columns to create it, or add the column on the board and rerun"; fi
}

i=0
for phase in $PHASES; do
  wanted="$(jq -r --arg p "$phase" '.phaseToStatus[$p]' "$DEF")"
  if [ "$MANAGED_WORKFLOW" = 1 ]; then wanted="$(printf '%s' "$MANAGED_DEFAULTS" | jq -r --arg p "$phase" '.phaseToStatus[$p]' | tr -d '\r')"; fi
  map_column "$phase" "$wanted" "${PALETTE[$((i % 7))]}"
  i=$((i+1))
done
while IFS= read -r name; do
  if [ -n "$name" ]; then map_column "" "$name" GRAY; fi
done <<< "$REQUIRED"

if [ "${#CREATE_NAMES[@]}" -gt 0 ]; then
  if [ "$DRYRUN" = 1 ]; then
    for idx in "${!CREATE_NAMES[@]}"; do
      if [ -n "${CREATE_FROM[$idx]}" ]; then info "DRYRUN rename column '${CREATE_FROM[$idx]}' to '${CREATE_NAMES[$idx]}'"
      else info "DRYRUN create column '${CREATE_NAMES[$idx]}'"; fi
    done
  else
    # full option set = existing (renamed where asked) + new (updateProjectV2Field replaces all options)
    OPTS=""
    while IFS=$'\t' read -r name _; do
      [ -n "$name" ] || continue
      label="$name"
      for idx in "${!CREATE_FROM[@]}"; do if [ "${CREATE_FROM[$idx]}" = "$name" ]; then label="${CREATE_NAMES[$idx]}"; fi; done
      color="$(echo "$FIELDS" | jq -r '.fields[] | select(.id=="'"$STATUS_FIELD_ID"'") | .options[] | select(.name=="'"$name"'") | .color // "GRAY"' | tr '[:lower:]' '[:upper:]')"
      [ -z "$color" ] && color="GRAY"
      OPTS="$OPTS{name:$(printf '%s' "$label" | jq -Rr @json),color:$color,description:\"\"},"
    done <<< "$BOARD"
    for idx in "${!CREATE_NAMES[@]}"; do
      [ -z "${CREATE_FROM[$idx]}" ] || continue
      OPTS="$OPTS{name:$(printf '%s' "${CREATE_NAMES[$idx]}" | jq -Rr @json),color:${CREATE_COLORS[$idx]},description:\"\"},"
    done
    OPTS="${OPTS%,}"
    # The update replaces every option id, which clears every item's Status: save each by name first.
    # GraphQL, not `gh project item-list`, which leaves archived items out.
    SAVED=""; CURSOR=""; READ_ERROR=""
    while :; do
      AFTER=""; [ -z "$CURSOR" ] || AFTER=",after:\"$CURSOR\""
      IQ="query{node(id:\"$PROJ_ID\"){... on ProjectV2{items(first:100$AFTER,archivedStates:[ARCHIVED,NOT_ARCHIVED]){pageInfo{hasNextPage endCursor} nodes{id isArchived fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}"
      if ! PAGE="$(gh api graphql -f query="$IQ" 2>&1)" || ! printf '%s' "$PAGE" | jq -e '.data.node.items' >/dev/null 2>&1; then
        READ_ERROR="${PAGE:-no answer}"; break
      fi
      SAVED="$SAVED$(printf '%s' "$PAGE" | jq -r '.data.node.items.nodes[] | select((.fieldValueByName.name // "") != "") | "\(.id)\t\(.isArchived)\t\(.fieldValueByName.name)"' | tr -d '\r')"$'\n'
      CURSOR="$(printf '%s' "$PAGE" | jq -r 'if .data.node.items.pageInfo.hasNextPage then .data.node.items.pageInfo.endCursor else "" end' | tr -d '\r')"
      [ -n "$CURSOR" ] || break
    done
    if [ -n "$READ_ERROR" ] && [ "$ALLOW_RESET" = 1 ]; then SAVED=""; warn "cannot read the board's items ($READ_ERROR); --allow-status-reset: their Status will be cleared"
    elif [ -n "$READ_ERROR" ]; then die "cannot read the board's items, so their Status could not be restored after the column change: $READ_ERROR - fix access and rerun, or pass --allow-status-reset to accept that every item loses its Status"; fi
    Q="mutation{updateProjectV2Field(input:{fieldId:\"$STATUS_FIELD_ID\",singleSelectOptions:[$OPTS]}){projectV2Field{... on ProjectV2SingleSelectField{options{id name}}}}}"
    RES="$(gh api graphql -f query="$Q" 2>&1)" || { warn "column creation failed: $RES"; RES=""; }
    if [ -n "$RES" ]; then
      NEW="$(echo "$RES" | jq -r '.data.updateProjectV2Field.projectV2Field.options[] | "\(.name)\t\(.id)"' | tr -d '\r')"
      # The update replaces every option, so every option id is new: rebuild the whole map.
      unset STATUSOPT; declare -A STATUSOPT
      while IFS=$'\t' read -r name option_id; do
        if [ -n "$name" ]; then STATUSOPT["$name"]="$option_id"; fi
      done <<< "$NEW"
      saved_count=0; restored=0
      while IFS=$'\t' read -r item_id item_archived item_status; do
        [ -n "$item_id" ] || continue
        saved_count=$((saved_count+1)); target="$item_status"; label="$item_id"
        for idx in "${!CREATE_FROM[@]}"; do if [ "${CREATE_FROM[$idx]}" = "$item_status" ]; then target="${CREATE_NAMES[$idx]}"; fi; done
        option_id="${STATUSOPT[$target]:-}"
        # GitHub refuses to update an archived item: unarchive it, set the Status, archive it again.
        pair="projectId:\"$PROJ_ID\",itemId:\"$item_id\""
        if [ "$item_archived" = true ]; then label="$item_id (archived)"; fi
        if [ -z "$option_id" ]; then out="no such column after the update"
        elif [ "$item_archived" = true ] && ! out="$(gh api graphql -f query="mutation{unarchiveProjectV2Item(input:{$pair}){item{id}}}" 2>&1)"; then :
        elif out="$(gh project item-edit --id "$item_id" --project-id "$PROJ_ID" --field-id "$STATUS_FIELD_ID" --single-select-option-id "$option_id" 2>&1)"; then
          if [ "$item_archived" != true ] || again="$(gh api graphql -f query="mutation{archiveProjectV2Item(input:{$pair}){item{id}}}" 2>&1)"; then
            restored=$((restored+1)); continue
          fi
          out="left unarchived: $again"
        elif [ "$item_archived" = true ]; then
          gh api graphql -f query="mutation{archiveProjectV2Item(input:{$pair}){item{id}}}" >/dev/null 2>&1 || out="$out; left unarchived"
        fi
        RESTORE_FAILED=1; warn "item Status not restored, set it by hand: $label was '$item_status': $out"
      done <<< "$SAVED"
      info "restored Status on $restored of $saved_count item(s)"
      for name in "${CREATE_NAMES[@]}"; do
        if [ -n "${STATUSOPT[$name]:-}" ]; then info "created & mapped -> $name"; fi
      done
    fi
  fi
fi

if [ -z "$HOOKS_MODE" ]; then
  if [ "$NONINT" = 1 ]; then
    [ -f "$OUT" ] && HOOKS_MODE="$(jq -r '.hookMode // empty' "$OUT" | tr -d '\r')"
    [ "$HOOKS_MODE" = "optional" ] || [ "$HOOKS_MODE" = "required" ] || HOOKS_MODE="optional"
    info "hook mode not supplied in non-interactive mode; using $HOOKS_MODE (rerun with --hooks-mode optional|required to choose)"
  else
    while :; do
      read -r -p "[project-init] Project sync hooks: 'required' runs sync automatically; 'optional' offers manual execution [optional]: " HOOKS_MODE
      HOOKS_MODE="${HOOKS_MODE:-optional}"
      HOOKS_MODE="$(printf '%s' "$HOOKS_MODE" | tr '[:upper:]' '[:lower:]')"
      if [ "$HOOKS_MODE" = "optional" ] || [ "$HOOKS_MODE" = "required" ]; then break; fi
      warn "enter 'optional' or 'required'"
    done
  fi
fi
[ "$HOOKS_MODE" = "optional" ] || [ "$HOOKS_MODE" = "required" ] || die "--hooks-mode must be optional or required"
if [ "$MANAGED_WORKFLOW" = 1 ]; then
  info 'Sanduq workflow owns lifecycle dispatch; preserving reconciled hook entries'
else
  set_project_hook_mode "$HOOKS_MODE"
fi

# statusOrder in phase order
ORDER_JSON="[]"
for phase in $PHASES; do s="${PHASE2STATUS[$phase]:-}"; [ -n "$s" ] && ORDER_JSON="$(echo "$ORDER_JSON" | jq --arg s "$s" 'if index($s) then . else . + [$s] end')"; done
# phaseToStatus + statusOptions objects
P2S="{}"; for phase in $PHASES; do s="${PHASE2STATUS[$phase]:-}"; [ -n "$s" ] && P2S="$(echo "$P2S" | jq --arg k "$phase" --arg v "$s" '.[$k]=$v')"; done
SOPT="{}"; for k in "${!STATUSOPT[@]}"; do SOPT="$(echo "$SOPT" | jq --arg k "$k" --arg v "${STATUSOPT[$k]}" '.[$k]=$v')"; done

CONFIG="$(jq -n \
  --arg owner "$OWNER" --arg ot "$OWNER_TYPE" --arg hook "$HOOKS_MODE" --argjson num "$NUMBER" \
  --arg pid "$PROJ_ID" --arg purl "$PROJ_URL" --arg sfid "$STATUS_FIELD_ID" \
  --argjson sopt "$SOPT" --argjson p2s "$P2S" --argjson order "$ORDER_JSON" \
  --argjson parent "$(keep parentIssue)" --argjson sub "$(keep subIssues)" --argjson state "$(keep stateFile)" \
  '{owner:$owner,ownerType:$ot,hookMode:$hook,projectNumber:$num,projectId:$pid,projectUrl:$purl,statusFieldId:$sfid,statusOptions:$sopt,phaseToStatus:$p2s,statusOrder:$order,parentIssue:$parent,subIssues:$sub,stateFile:$state}')"

if [ "$DRYRUN" = 1 ]; then info "DRYRUN would write $OUT:"; echo "$CONFIG";
else mkdir -p "$EXT_DIR"; echo "$CONFIG" > "$OUT"; info "wrote $OUT"; fi
info "done. Next: commit config.json, then dry-run: python $EXT_DIR/scripts/project_sync.py --phase open --dry-run"
if [ "$JSON" = 1 ]; then echo "$CONFIG" | jq -c .; fi
[ "$RESTORE_FAILED" = 0 ] || exit 1
