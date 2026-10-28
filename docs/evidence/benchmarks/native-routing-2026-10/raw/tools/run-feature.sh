#!/usr/bin/env bash
# usage: run-feature.sh <run> [claude|codex]
#   Scope, then continue through the PR stage, for the run's issue (logs/issues.tsv) in runs/<run>.
#   When a session stops on Clarify questions, posts the recommended option for each new question as a
#   comment on the issue (as PH-04's owner did by hand) and continues, at most 4 continue sessions.
#   Refuses to start a session once measured spend reaches the stop line (spend.py --check).
set -u
run="$1"; host="${2:-claude}"
base="<sandbox>"; t="$base/tools"; repo=samykabu/sanduq-sandbox-ph04
STOP_USD="${STOP_USD:-140}"   # 160 USD cap minus a 20 USD reserve for one in-flight session
issue=$(awk -v r="$run" '$1==r{print $2}' "$base/logs/issues.tsv")
[ -n "$issue" ] || { echo "no issue for $run in logs/issues.tsv" >&2; exit 2; }
dir="$base/runs/$run"; [ -d "$dir" ] || { echo "no clone $dir (setup-run.sh first)" >&2; exit 2; }
if [ "$host" = codex ]; then runner="$t/run-codex.sh"; p='$'; else runner="$t/run-claude.sh"; p='/'; fi
continue_prompt="${p}speckit-workflow-continue #$issue Owner approval: yes, publish #$issue as one issue with 0 sub-issues at the proposed effort score; if the proposed score is above 3, the owner sets it to 3. Then continue the managed lifecycle through the PR stage: open the pull request but do not merge it. If Clarify posts questions on the issue, stop and list them. Do not edit .specify/workflow.yml; run each task on the route its claim records."
guard() { python "$t/spend.py" --check "$STOP_USD" || { echo "STOP: spend reached $STOP_USD USD; not starting $1" >&2; exit 5; }; }
branch=$(cd "$t" && python -c "import policy; print(policy.feature_for($issue)[len('specs/'):])")
has_pr() { [ -n "$(gh pr list --repo "$repo" --state all --head "$branch" --json number --jq '.[].number' | head -1)" ]; }
guard "$run-a-scope"
bash "$runner" "$dir" "$run-a-scope" "${p}speckit-workflow-scope $issue"
for step in b c d e; do
  has_pr && { echo "$run: PR open"; exit 0; }
  bash "$t/answer.sh" "$issue"   # posts recommended answers to unanswered Clarify questions, if any
  guard "$run-$step-continue"
  bash "$runner" "$dir" "$run-$step-continue" "$continue_prompt"
done
has_pr && echo "$run: PR open" || { echo "$run: no PR after 4 continue sessions; inspect logs/transcripts/$run-*" >&2; exit 6; }
