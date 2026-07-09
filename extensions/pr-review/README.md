# PR Review Processor Extension

Process GitHub pull request review comments from Spec Kit with the same approval-gated workflow as
the `devtools:pr-review` Claude skill.

The Claude skill remains available outside Spec Kit projects. This extension adds the Spec Kit
command `/speckit-pr-review-process`.

## Command

| Command | Invocation | Description |
|---|---|---|
| `speckit.pr-review.process` | `/speckit-pr-review-process` | Process unresolved PR review feedback through a classify, approve, fix/reply, push, and resolve workflow |

## Usage

```text
/speckit-pr-review-process 123
/speckit-pr-review-process https://github.com/owner/repo/pull/123
/speckit-pr-review-process owner/repo#123
```

If no PR is supplied, the command tries to detect the PR for the current branch using `gh pr view`.
If detection is ambiguous, it asks for the PR identifier.

## Lifecycle

This command is intentionally manual. It should run after reviewers or bots have left comments on an
open pull request. That normally happens outside the core Spec Kit implementation lifecycle, so the
extension does not register an automatic hook by default.

## Safety Gates

- Reviewer content is treated as untrusted input.
- No code edits, PR replies, commits, pushes, or thread resolutions happen before the user approves
  the proposed plan.
- Every unresolved substantive comment is classified as valid, invalid, or needs user input.
- Threads are resolved only after approved fixes/replies are pushed or posted.

## Requirements

- `gh` authenticated with access to the repository.
- `git` available in the local checkout.
