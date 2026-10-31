# Changelog

## [2.7.3] - 2026-10-31

- The packaged `sanduq_freshness.py` leaves another feature's untracked files under `specs/<other>/` out of the QA document inputs, so an untracked note in a sibling feature no longer stales this feature's QA record (#113). Committed files still count through the branch diff.

## [2.7.2] - 2026-10-29

- The packaged shared helpers (`sanduq_freshness.py`, `sanduq_hash.py`, `sanduq_ci.py`, `deps.py`) start with an `SPDX-License-Identifier: MIT` line. No behaviour change.

## [2.7.1] - 2026-10-28

- The packaged `sanduq_ci.py` helper's docstrings state the rule they protect instead of citing review findings. No behaviour change.

## [2.7.0] - 2026-10-28

- `documentation-gates.yml` checks out the PR base into `.sanduq-base` and runs the base's `assure_state.py` and User Manual script against the head; `SANDUQ_POLICY_ROOT` makes the base's `assure-config.yml` decide whether the gate is on (SEC-03). A first-install PR runs the released Assure the head names, after `sanduq_ci.py verify-release` checks the head copy. `assure init` replaces an unedited render of the previous template.
- `requires.tools` declares Python `>=3.11`, the floor every Sanduq extension now states (SAMY-11).

## [2.6.2] - 2026-10-26

- License: this package is MIT; versions before this one were PolyForm Noncommercial 1.0.0. The archive now ships its LICENSE.

## [2.6.1] - 2026-10-21

- The injected `sanduq_ci.load_ci` also reads a policy file passed directly, so the vendored User Manual init honours `--ci-policy FILE`.

## [2.6.0] - 2026-10-21

Optimization round 4. No renames.

Optimization round 4.

- The rendered `documentation-gates.yml` checks out the PR head, not GitHub's merge commit, so a base branch that moved after `record` no longer fails the gate.
- `assure init` keeps an existing `assure-config.yml` and changes only its three lifecycle values. It rewrites `extensions.yml` only when a hook changes. A config without those keys stops init with a message instead of being replaced.
- The scanner skips folders git ignores (such as `.venv`) inside a git work tree and reads each folder once. The default exclude list adds `.venv`, `venv`, `__pycache__`, `target`, `vendor`, `Pods` and `.gradle` for scans outside git.
- `assure_scan.py --check` prints the inventory and the `would write` line; `--show-block` also prints the memory block.
- The analyze state ignores the User Manual task block in `tasks.md`, as input and as output, so the User Manual `after_tasks` hook no longer forces a full Analyze rerun.
- `status` no longer collects default outputs it does not use. `deps.py` names the next step in its one line; the commands say one sentence about it.
- Document's Illustrate step names full script paths (Spec Kit rewrote the bare `scripts/` token). The skill drops its routing section; its paths point at `.specify/extensions/assure/scripts/`.
- The config template drops `freshness.policy`, `freshness.state_directory` and `output.directory_name`, which nothing read.

### Migration

- An unedited earlier `documentation-gates.yml` is replaced by `assure init` (and the Workflow upgrade). An edited one is kept; init prints the `ref:` line to add.
- The first scan after the upgrade can drop rows that came from ignored folders. That rewrites `.github/memory/project-memory.md` once and stales recorded document and manual states once.
- An analyze state recorded over a `tasks.md` that already held the User Manual block goes stale once. Every other earlier state compares as before.
- An existing `assure-config.yml` keeps the removed keys; they do nothing.

## [2.5.1] - 2026-10-20

- Document freshness hashes each declared `--output` as an output only, not also as an implicit input, so a regenerated output no longer reports as a changed input; a missing or changed output still stales the state. States recorded by 2.5.0 compare as before until the next `record`. Analyze is unchanged.
- Analyze and Document name `.specify/extensions/assure/state/<feature-name>/reports/` for freshness logs and status reports, written before the final `record`. Part of samykabu/sanduq#99.

## [2.5.0] - 2026-10-20

Optimization round 3 (fixes to 2.4.0).

- The documentation gate: a parsed config value is final, so `false  # set to true` is off; a config neither reader understands turns the gate on with one message. The rendered `documentation-gates.yml` passes the feature path through `env`.
- `audit_qa.py` shares the User Manual placeholder allowlist and resolves encoded and root-relative links.
- The scanner keeps its date unless the inventory changed (a rerun on another day no longer stales the manual) and reads its exclude list from the packaged template only.
- Diagram steps follow Illustrate's theme gate and checks again. Analyze stops early on an unchanged state. One freshness CLI shared with User Manual.

## [2.4.0] - 2026-10-19

Optimization round 2, measured with `extensions/scripts/benchmark_instructions.py`.

- `scripts/assure_scan.py` writes the project inventory block in `.github/memory/project-memory.md` (Analyze runs it with `--check`, Document writes). The excluded folders are `scan.exclude` in `assure-config.yml`; the default is the list the commands used before.
- `scripts/audit_qa.py` checks the generated QA manual: image alt text and captions, relative links, the development-only marker and secret-looking values.
- `assure_state.py status --gate` decides the documentation gate from the parsed config (PyYAML when available, a narrow reader otherwise, failing closed on a layout neither understands). The rendered `documentation-gates.yml` changes on upgrade: one line per freshness step, with the feature path passed through `env`.
- The two commands moved their shared contract into the skill references: Analyze is 6,050 bytes instead of 14,031, Document 9,609 instead of 14,620. Diagrams use Illustrate's type index instead of the whole skill. `--phase` is gone; the hook configuration sets the phase.
- On a rerun, Document reads the `changed_inputs` and `changed_outputs` that freshness now reports.
- One description per command, the same in the command file and `extension.yml`. The unused `agents/openai.yaml` is removed.

## [2.3.4] - 2026-10-19

- `documentation-gates.yml` skips fork pull requests when the project's linux runner is self-hosted
  (rendered by Workflow's `self_hosted` template flag) and pins `actions/checkout` to v4.3.0 by
  commit. Part of samykabu/sanduq#94.

## [2.3.3] - 2026-10-18

- Ship the reviewed shared freshness helper in the Assure package. Generated Progress reports
  under `specs/*/progress/` and `.specify/progress/` no longer stale QA analysis or documentation
  state. Changes to true source inputs, including product directories such as `src/progress`,
  still invalidate that state.

## [2.3.2] - 2026-10-10

- README links point to the new extension page, install-by-host page and command reference.

## [2.3.1] - 2026-10-06

- Link setup and complete usage examples from the package README; links work in installed copies.

## 2.3.0

- **B7 — quiet output.** `assure_state.py` gains `--summary` (one line:
  `ok`/`error`, e.g. `ok action=record kind=document outputs=1
  recorded=1`) as an alternative to the previous full JSON output, which is
  unchanged and now also selectable explicitly with `--json`. `--summary`
  and `--json` together is rejected; default (no flag) behaviour and the
  exit code are unchanged. A `reason` with embedded whitespace or newlines
  is collapsed to a single line so `--summary` always prints exactly one
  line.
- **B9 — shared dependency script.** `speckit.assure.analyze` and
  `speckit.assure.document` now ensure the `illustrate` dependency with the
  shared `scripts/deps.py ensure illustrate` (also shipped to `pr` and
  `user-manual`) instead of duplicated prose: it checks the Spec Kit
  registry, follows the project's `update_policy`, and prints one line,
  failing closed with `deps.py ensure illustrate --approve` as the
  recovery when illustrate cannot be brought into range; an exit-0 "newer
  compatible release" note is surfaced to the user. Illustrate's
  `SKILL.md` now loads only when a diagram task or asset is actually being
  added, not unconditionally at step 0a.

  `deps.py` itself parses `specify extension info`'s real plain-text
  `Name (vX.Y.Z)` header (it has no `--json` output); answers `specify
  extension update`'s unavoidable `typer.confirm` prompt with an explicit
  `y` only on an authorised update, closing stdin otherwise so an
  unexpected prompt fails fast; every subprocess call has a timeout; the
  version comparator follows SemVer precedence for pre-release/build-
  metadata suffixes, a leading `v`, space-separated clauses, `^`/`~=`, and
  npm-semver's pre-release range rule (a plain `>=2.0.0,<3.0.0` never
  admits a pre-release version). `.dependency-checks.json` records a check
  only when the catalog probe actually ran and succeeded. It ships no
  third-party dependency: `dependencies.yml` and
  `.specify/extension-dependencies.yml` are read by a small built-in
  parser (nothing installs a package's `requirements.txt` before its
  commands run) that rejects a tab in leading whitespace, a duplicate or
  quoted key, a flow-style value, and an unbalanced quote, and reports a
  malformed list item's own line number.

## 2.2.2

- `assure_state.py` defaults `--base-ref` to the feature's bound target
  branch recorded in its Workflow checkpoint instead of always assuming the
  origin HEAD default branch, when the checkpoint recorded one. An explicit
  `--base-ref` still wins, and a feature with no checkpoint, or none recorded,
  keeps today's origin-HEAD default (F16).

## 2.2.1

- The bundled freshness helper shares Workflow's checkout-independent
  fingerprints: an unchanged tracked `.sql` or `-text` file that a Windows
  `core.autocrlf` checkout wrote with different line endings hashes as its
  committed blob, so QA state recorded on Windows stays current in Linux CI.

## 2.1.0

- Use YAML parsing for hook initialization and shared source/output freshness with deletion detection.
- Managed initialization preserves dispatcher-owned hooks and uses the workflow's
  selected-process CI instead of creating an unconditional documentation gate.

All notable changes to the Assure extension.

## [2.0.0] - 2026-07-19

### Breaking

- Renamed the extension from `qa` to `assure` because the `qa` id conflicts with an existing
  extension in the Spec Kit community catalog. Commands are now `/speckit-assure-*`, the install
  directory is `.specify/extensions/assure/`, and the config file is `assure-config.yml`.
  No compatibility alias is retained.

### Migration

- Remove `qa`, install `assure`, and rerun `/speckit-assure-init` to regenerate hooks and config.
  QA output directories (for example `docs/<feature>/qa/`) and task markers are unchanged, so
  generated documentation is preserved. Prior `qa-v*` release tags remain available in Git history.

## [1.0.0] - 2026-07-18

### Breaking

- Replaced the `how-to-test` extension and commands immediately with the `qa` extension and
  `/speckit-qa-*` commands. No compatibility alias is retained.

### Added

- Added `QA.Init` with integrated and manual project lifecycle policies.
- Added a mandatory `before_implement` analysis gate in integrated mode.
- Added feature-scoped analyze/document freshness evidence for PR preflight enforcement.
- Added a reusable QA skill with progressively loaded analysis and documentation contracts.

### Migration

- Remove `how-to-test`, install `qa`, and run `/speckit-qa-init`. The former extension's release
  history remains available in Git history and its published release tags.
