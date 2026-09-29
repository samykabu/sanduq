# Stage reference: scope

Loaded when `claim` returns `stage: scope`.

## Entry point

**scope**: require an explicit issue. Inspect its scope prerequisites and project policy;
never choose a feature from an editor tab. For a new issue-bound feature, run
`workflow.py prepare --issue <number>` and use its exact `feature` and `branch`
derived from the issue number and current title. If the Git extension owns
`before_specify`, pass its branch as `GIT_BRANCH_NAME` to that hook; otherwise
`prepare` creates the branch with Git argument arrays. For an existing bound feature,
reuse its saved feature path and branch even if the issue title has changed.
Resolve or reserve the matching feature identity,
then `start --feature specs/<feature> --issue owner/repo#number`. Pass this exact
path into Specify as SPECIFY_FEATURE_DIRECTORY. Run the stage loop in the core skill.

## Required work and evidence

Issue identity, prerequisite snapshot, project preferences, managed issue/labels and
complete spec-prompt. Policy-settled keep-together decisions skip decomposition
questions. Return actual publication evidence.
