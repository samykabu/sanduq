# Security

Sanduq is a set of Spec Kit extensions that run on your machine, in your checkout, with your
accounts. This page says what that means, what runs without asking, and how to report a problem.

## Trust assumptions

- **The repository is trusted.** Running Sanduq in a repository runs that repository's code: hook
  scripts under `.specify/`, the policy in `.specify/workflow.yml`, commands it names, and the
  installed skills. Do not run Sanduq in a repository you would not run `make` or `npm install` in.
- **Issue authors are trusted, or named.** Workflow reads GitHub issues and their comments as
  work and as decisions. Restrict who can answer with `decisions.authorized_users` in
  `.specify/workflow.yml` ([schemas](docs/workflow/schemas.md)); without it, every commenter is one.
- **The machine and the accounts are yours.** `gh` runs with your login; agents run with your file
  permissions. Nothing in Sanduq separates two users on one machine or one checkout.

## What runs automatically

- **Hooks.** The Workflow installer merges a PreToolUse guard into `.claude/settings.json` and
  `.codex/hooks.json`; the extensions' lifecycle hooks run around Spec Kit commands
  ([hooks reference](docs/reference/hooks.md)). The guard is advisory: it sees only the host's shell
  tools (`Bash`, `PowerShell`, Codex's shell tool), so a script, an alias or another tool bypasses
  it, and a hook error allows the call ([guard hook](extensions/workflow/README.md#guard-hook)).
- **Policy commands.** `ci.gate.verify_command` and the affected-check commands in
  `.specify/workflow.yml` run as written ([operations](docs/workflow/operations.md)).
- **The Progress statusline.** When installed, it runs the status line command that was configured
  before it, and only while `.specify/progress/config.json` is untracked and still names the
  command the install recorded; a tracked file or a changed command is ignored with a line in
  `diagnostics.log`.
- **Install backups.** Each apply writes `.specify/workflow/backups/*/before.zip` with the exact
  bytes of every file it may change, including `.claude/settings.json`, `.codex/config.toml` and
  `.codex/hooks.json`, which can carry MCP server keys. They are excluded from git in that clone
  only and travel with any copy of the folder.

## Delegation

Delegated work runs another agent CLI through the `delegate-task` driver
([delegation](docs/workflow/delegation.md#security)). Two modes exist:

- **Bypass** (`permission: bypass`, the driver's default): the worker runs any command without
  asking, in your checkout. Every external launch Sanduq makes passes `--clean-env` with an explicit
  `--keep-env` allowlist, so the worker sees runtime basics, its own harness credentials and the
  `SANDUQ_*` variables, not the rest of your environment. The ledger records the kept names, never
  values.
- **Sandbox** (`--sandbox`): review and analysis routes start read-only.

A task worker never receives the workflow claim token. `accept`, `adopt`, `reassign` and
`trust-reset` need a nonce kept under your home folder, outside every worker's checkout, and refuse a
process that descends from a live delegated run even with its `SANDUQ_*` variables removed. Both
stop a worker that uses only what it was given; neither stops a worker running as your OS user
that reads the nonce file or escapes its process tree
([residual risk](docs/workflow/delegation.md#security)).

Workers and the dispatcher share one checkout and one set of permissions. Receipts and the
delegation ledger are self-asserted, and the ledger's tamper markers detect accidental edits only
(review decision DEC-11); a worker that wants to lie can. The CI gate checks that receipts are
present, passing and current, and in its default `advisory` mode it warns without blocking
([limits](docs/scenarios/managed-workflow.md#limits)). The control is the pull request review.

## Tokens and logs

- GitHub access goes through the `gh` CLI with your login. `GH_TOKEN` and `GITHUB_TOKEN` reach a
  delegated worker only on routes that need the GitHub adapter.
- Driver run folders under `.delegate/runs/` hold the task text and the harness's raw output. On
  finalisation the driver masks token shapes and credential-looking assignments in `stdout.log` and
  `stderr.log`, and `collect` deletes finished runs older than 30 days (`DELEGATE_PRUNE_DAYS`, `0`
  disables). A nested `.gitignore` keeps `.delegate/` out of git. The result block a harness writes
  is kept as it was written.
- On Windows, the shared `gh` transport and Workflow's git runner resolve the tool from `PATH`
  only, and the dispatcher calls `taskkill` by its `System32` path, so an executable committed in
  a checkout cannot shadow them. Other extensions' direct `git` calls still use the bare name.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository (Security tab, "Report a
vulnerability"). If it is unavailable, open an issue that says only that you have a security
report and the maintainer will contact you. Do not post details in a public issue or pull request.
