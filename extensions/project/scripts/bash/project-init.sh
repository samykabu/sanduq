#!/usr/bin/env bash
# One-time setup for the 'project' extension (bash twin of project-init.ps1): discover a
# GitHub Project (v2), map lifecycle phases to the board's Status columns (exact -> fuzzy ->
# prompt -> optional auto-create), and write .specify/extensions/project/config.json.
#
# Usage: project-init.sh [--owner <login>] [--number <n>] [--owner-type user|org]
#                        [--auto-create-columns] [--non-interactive] [--dry-run] [--json]
set -euo pipefail

OWNER=""; NUMBER=0; OWNER_TYPE=""; AUTOCREATE=0; NONINT=0; DRYRUN=0; JSON=0
while [ $# -gt 0 ]; do case "$1" in
  --owner) OWNER="$2"; shift 2;;
  --number) NUMBER="$2"; shift 2;;
  --owner-type) OWNER_TYPE="$2"; shift 2;;
  --auto-create-columns) AUTOCREATE=1; shift;;
  --non-interactive) NONINT=1; shift;;
  --dry-run) DRYRUN=1; shift;;
  --json) JSON=1; shift;;
  *) echo "[project-init][warn] unknown arg: $1"; shift;;
esac; done

info(){ echo "[project-init] $*"; }
warn(){ echo "[project-init][warn] $*"; }
die(){ echo "[project-init][error] $*"; exit 1; }

command -v gh >/dev/null 2>&1 || die "gh CLI not installed"
command -v jq >/dev/null 2>&1 || die "jq not installed"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not inside a git repository"
cd "$ROOT"
EXT_DIR=".specify/extensions/project"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEF="$SCRIPT_DIR/../../config.default.json"; [ -f "$DEF" ] || DEF="$EXT_DIR/config.default.json"
[ -f "$DEF" ] || die "config.default.json not found"

gh auth status >/dev/null 2>&1 || die "gh not authenticated - run: gh auth login"
gh auth status 2>&1 | grep -q "project" || die "gh token lacks 'project' scope - run: gh auth refresh -h github.com -s project,read:project"

[ -z "$OWNER" ] && OWNER="$(gh api user --jq .login)"
[ -z "$OWNER" ] && die "could not resolve owner - pass --owner"
if [ -z "$OWNER_TYPE" ]; then
  if gh project list --owner "$OWNER" --limit 1 --format json >/dev/null 2>&1; then OWNER_TYPE="user"; else OWNER_TYPE="org"; fi
fi
info "owner: $OWNER ($OWNER_TYPE)"

if [ "$NUMBER" -le 0 ] 2>/dev/null; then
  LIST="$(gh project list --owner "$OWNER" --format json)" || die "could not list projects for $OWNER"
  COUNT="$(echo "$LIST" | jq '.projects | length')"
  [ "$COUNT" -eq 0 ] && die "no projects for $OWNER - create one or pass --number"
  if [ "$COUNT" -eq 1 ]; then NUMBER="$(echo "$LIST" | jq -r '.projects[0].number')"
  elif [ "$NONINT" = 1 ]; then die "multiple projects; pass --number in non-interactive mode"
  else
    info "Select a project:"
    echo "$LIST" | jq -r '.projects | to_entries[] | "  [\(.key)] #\(.value.number)  \(.value.title)"'
    read -r -p "index: " IDX
    NUMBER="$(echo "$LIST" | jq -r --argjson i "$IDX" '.projects[$i].number')"
  fi
fi
info "project #$NUMBER"

PROJ_ID="$(gh project view "$NUMBER" --owner "$OWNER" --format json | jq -r '.id')"
PROJ_URL="$(gh project view "$NUMBER" --owner "$OWNER" --format json | jq -r '.url')"
FIELDS="$(gh project field-list "$NUMBER" --owner "$OWNER" --format json)"
STATUS_FIELD_ID="$(echo "$FIELDS" | jq -r '.fields[] | select(.name=="Status" and .options) | .id' | head -1)"
[ -z "$STATUS_FIELD_ID" ] && die "no single-select 'Status' field on project #$NUMBER"
# board columns: name<TAB>id
BOARD="$(echo "$FIELDS" | jq -r '.fields[] | select(.id=="'"$STATUS_FIELD_ID"'") | .options[] | "\(.name)\t\(.id)"')"
info "board Status columns: $(echo "$BOARD" | cut -f1 | paste -sd, -)"

norm(){ echo "$1" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]'; }
board_id_for(){ echo "$BOARD" | awk -F'\t' -v n="$1" 'tolower($1)==tolower(n){print $2; exit}'; }
board_fuzzy(){ local nw; nw="$(norm "$1")"; echo "$BOARD" | cut -f1 | while read -r c; do nc="$(norm "$c")"; if [ "$nc" = "$nw" ] || echo "$nc" | grep -q "$nw" || echo "$nw" | grep -q "$nc"; then echo "$c"; break; fi; done; }

PHASES="open analysis engineer-review ready in-progress in-review done"
PALETTE=(GRAY BLUE PURPLE GREEN YELLOW ORANGE PINK)
declare -A PHASE2STATUS; declare -A STATUSOPT
CREATE_NAMES=(); CREATE_COLORS=()
i=0
for phase in $PHASES; do
  wanted="$(jq -r --arg p "$phase" '.phaseToStatus[$p]' "$DEF")"
  match="$(echo "$BOARD" | awk -F'\t' -v n="$wanted" 'tolower($1)==tolower(n){print $1; exit}')"
  [ -z "$match" ] && match="$(board_fuzzy "$wanted")"
  if [ -n "$match" ]; then
    PHASE2STATUS[$phase]="$match"; STATUSOPT[$match]="$(board_id_for "$match")"
    printf '[project-init]   %-16s -> %s\n' "$phase" "$match"
  else
    do_create=$AUTOCREATE
    if [ "$do_create" = 0 ] && [ "$NONINT" = 0 ]; then
      read -r -p "[project-init]   no column for phase '$phase' (wanted '$wanted'). Create '$wanted'? [y/N] " ans
      [[ "$ans" =~ ^[yY] ]] && do_create=1
    fi
    if [ "$do_create" = 1 ]; then CREATE_NAMES+=("$wanted"); CREATE_COLORS+=("${PALETTE[$((i % 7))]}"); PHASE2STATUS[$phase]="$wanted"
    else warn "phase '$phase' has no column - that transition will be a no-op until mapped"; fi
  fi
  i=$((i+1))
done

if [ "${#CREATE_NAMES[@]}" -gt 0 ]; then
  if [ "$DRYRUN" = 1 ]; then for n in "${CREATE_NAMES[@]}"; do info "DRYRUN create column '$n'"; done
  else
    # full option set = existing + new (updateProjectV2Field replaces all options)
    OPTS=""
    while IFS=$'\t' read -r name id; do
      color="$(echo "$FIELDS" | jq -r '.fields[] | select(.id=="'"$STATUS_FIELD_ID"'") | .options[] | select(.name=="'"$name"'") | .color // "GRAY"' | tr '[:lower:]' '[:upper:]')"
      [ -z "$color" ] && color="GRAY"
      OPTS="$OPTS{name:$(printf '%s' "$name" | jq -Rr @json),color:$color,description:\"\"},"
    done <<< "$BOARD"
    for idx in "${!CREATE_NAMES[@]}"; do
      OPTS="$OPTS{name:$(printf '%s' "${CREATE_NAMES[$idx]}" | jq -Rr @json),color:${CREATE_COLORS[$idx]},description:\"\"},"
    done
    OPTS="${OPTS%,}"
    Q="mutation{updateProjectV2Field(input:{fieldId:\"$STATUS_FIELD_ID\",singleSelectOptions:[$OPTS]}){projectV2Field{... on ProjectV2SingleSelectField{options{id name}}}}}"
    RES="$(gh api graphql -f query="$Q" 2>&1)" || { warn "column creation failed: $RES"; RES=""; }
    if [ -n "$RES" ]; then
      NEW="$(echo "$RES" | jq -r '.data.updateProjectV2Field.projectV2Field.options[] | "\(.name)\t\(.id)"')"
      for name in "${CREATE_NAMES[@]}"; do
        nid="$(echo "$NEW" | awk -F'\t' -v n="$name" 'tolower($1)==tolower(n){print $2; exit}')"
        [ -n "$nid" ] && { STATUSOPT[$name]="$nid"; info "created & mapped -> $name"; }
      done
    fi
  fi
fi

# statusOrder in phase order
ORDER_JSON="[]"
for phase in $PHASES; do s="${PHASE2STATUS[$phase]:-}"; [ -n "$s" ] && ORDER_JSON="$(echo "$ORDER_JSON" | jq --arg s "$s" 'if index($s) then . else . + [$s] end')"; done
# phaseToStatus + statusOptions objects
P2S="{}"; for phase in $PHASES; do s="${PHASE2STATUS[$phase]:-}"; [ -n "$s" ] && P2S="$(echo "$P2S" | jq --arg k "$phase" --arg v "$s" '.[$k]=$v')"; done
SOPT="{}"; for k in "${!STATUSOPT[@]}"; do SOPT="$(echo "$SOPT" | jq --arg k "$k" --arg v "${STATUSOPT[$k]}" '.[$k]=$v')"; done

CONFIG="$(jq -n \
  --arg owner "$OWNER" --arg ot "$OWNER_TYPE" --argjson num "$NUMBER" \
  --arg pid "$PROJ_ID" --arg purl "$PROJ_URL" --arg sfid "$STATUS_FIELD_ID" \
  --argjson sopt "$SOPT" --argjson p2s "$P2S" --argjson order "$ORDER_JSON" \
  --argjson parent "$(jq '.parentIssue' "$DEF")" --argjson sub "$(jq '.subIssues' "$DEF")" \
  --arg state "$(jq -r '.stateFile' "$DEF")" \
  '{owner:$owner,ownerType:$ot,projectNumber:$num,projectId:$pid,projectUrl:$purl,statusFieldId:$sfid,statusOptions:$sopt,phaseToStatus:$p2s,statusOrder:$order,parentIssue:$parent,subIssues:$sub,stateFile:$state}')"

OUT="$EXT_DIR/config.json"
if [ "$DRYRUN" = 1 ]; then info "DRYRUN would write $OUT:"; echo "$CONFIG";
else mkdir -p "$EXT_DIR"; echo "$CONFIG" > "$OUT"; info "wrote $OUT"; fi
info "done. Next: commit config.json, then dry-run: bash $EXT_DIR/scripts/bash/project-sync.sh --phase open --dry-run"
[ "$JSON" = 1 ] && echo "$CONFIG" | jq -c .
