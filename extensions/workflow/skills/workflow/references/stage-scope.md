# Stage reference: scope

## Entry point

**scope**: require an explicit issue; never choose a feature from an editor tab. Inspect its
scope prerequisites and project policy. For a new issue-bound feature run `workflow.py prepare
--issue <number>` and use its exact `feature` and `branch`. If the Git extension owns
`before_specify`, pass that branch as `GIT_BRANCH_NAME` to the hook; otherwise `prepare`
creates it. For an existing bound feature reuse its saved path and branch even if the title
changed. Then `start --feature specs/<feature> --issue owner/repo#number`, pass the same path to
Specify as `SPECIFY_FEATURE_DIRECTORY`, and run the stage loop.

## Required work and evidence

Run the Scope analyst for the issue: identity, prerequisite snapshot, project preferences,
managed issue and labels, and a complete Specify prompt. Policy-settled keep-together decisions
skip decomposition questions. Gate and bind flags inside this claim:
[scope-binding.md](scope-binding.md).

When the issue is a single executable leaf whose published receipt approves this exact
analysis, render the spec from it: `scope.py render-spec <issue> --analysis <file> --feature
specs/<feature>` prints the text; review it, then add `--apply` (it refuses any other case). The spec starts with `<!-- sanduq-scope:rendered
<sha256> -->`, and the Specify claim then returns `mode: bind-only`.

Receipt: actual publication evidence, the analysis in `inputs`, and `effort_score` (one of 1 2
3 5 8 13 21, the approved score). With `profiles.enabled`, `complete` refuses a Scope receipt
without it; the score fixes the tier when Plan is first claimed.
