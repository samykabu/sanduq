# Changelog

## [1.1.2] - 2026-10-16

- The five hook commands (`speckit.progress.hook-session-start` and the others) are replaced by one internal command, `speckit.progress.hook`, that is no longer listed under `provides.commands`. Spec Kit registers every listed command as an agent skill, which cost the host ten skills for Progress and tripped Codex's skills budget. The command file `commands/speckit.progress.hook.md` is still found by the event dispatcher through its on-disk file-name lookup, so only the five user commands remain as skills. The hook script `hooks/dispatch.py` takes the event from the payload's `hook_event_name` and hands it to the unchanged `scripts/hook.py`. Reinstall to drop the old hook entries and skills.
- The vendored `docs/` still describe the five `speckit.progress.hook-*` commands until the next vendor update from sanduq-skills.

## [1.1.1] - 2026-10-16

- Vendors `progress-report` from `agent-tools-v1.2.1`. `progress hooks status --host codex` now reports how many Progress hooks Codex has approved and whether the project is trusted, including the hooks Spec Kit writes into `.codex/config.toml`; Codex skips unapproved project hooks silently, so the session never binds until you approve them in Codex. `progress status` hints at this when no session is bound. The host docs list the five hooks to approve.

## [1.1.0] - 2026-10-16

- The Progress code, report page and reference docs are now vendored from the portable `progress-report` skill in
  [sanduq-skills](https://github.com/samykabu/sanduq-skills) (`agent-tools-v1.2.0`, pinned in `vendor.lock.json`). Paths under
  `.specify/extensions/progress/` are unchanged. Edit them in sanduq-skills, not here. The extension keeps its manifest,
  commands, hook commands, `SKILL.ext.md` and README, and a reference copy of the skill's `SKILL.md` in `assets/skill/`.
- Plan mode: `progress init --plan PATH` reports on any Markdown checklist outside Spec Kit, stored in `.progress/<name>/`.
  Verbs target a report with `--plan NAME` or `--feature DIR`.
- `progress hooks install|uninstall|status --host claude|codex [--scope project|user]` writes the host's native hook entries
  without touching other settings.
- Nested `.gitignore` files protect the disposable report folders, in addition to `.git/info/exclude`.
- Review-cycle fixes from the skill: see the skill's changelog for the full list.
- License: the vendored code is MIT in sanduq-skills. The extension wrapper keeps PolyForm Noncommercial 1.0.0, as
  Illustrate does. The MIT notice is in `THIRD_PARTY_NOTICES.md`.

## [1.0.1] - 2026-10-15

- Hooks run `scripts/hook.py`, a standard-library entry that exits before importing Progress for an unbound session
  (about 30 ms instead of about 105 ms; a bound debounced event about 60 ms instead of about 120 ms).
- Hooks write nothing in a project where Progress was never initialised; an unbound session is logged once per id.
  `diagnostics.log*` and `*.lock` under `.specify/progress/` join the git exclude list.
- A debounce window publishes the clean-to-dirty transition once instead of rewriting `report.json` and `data.js` on every event.
- Codex `spawn_agent` and other asynchronous launches no longer finish on the launch response. A finished child that runs
  again starts a new generation. Child lane ids (`C<n>`) live in the host snapshots and never renumber. Host snapshots moved from `.view/host` to the git-ignored `.host/`. The first hook moves them under the feature lock (one rename; a conflicting file is kept as `.host/legacy-<name>`, a linked or unconfined `.view/host` is left alone, and a failed move is retried on the next event without writing a fresh snapshot) and adds `.host/` to the git exclude list, so deleting
  `.view/` keeps every child id; blockers follow a child into the lane it merges into; linking and splitting a child keeps its newest lifecycle.
- Writes refuse a symlink or junction at `facts.jsonl`, the view files and copied assets (`PROGRESS_UNSAFE_TARGET`).
- The UI poller abandons a data.js load that never settles after 10 s and tries again (Chromium under heavy load sometimes
  fires neither load nor error, which froze the page).
- `os.replace` retries a Windows sharing violation. The projection reads only the runs the ledger names.
- `init --theme BAD` fails before creating anything (`PROGRESS_THEME_INVALID`, exit 2) and a valid theme prints only the `ready` line. `theme` supports `--help` and works without an initialised feature, refreshing only existing views. `live_ab.py` finds `delegate.mjs` through `DELEGATE_SCRIPT` or the project's skills folders instead of an author path. The unused `feature_dir_mode` config key is no longer written.
- Flaky test fixes on Windows and under load; regression tests and docs for the review fixes.

## [1.0.0] - 2026-10-15

- First release. A live report for one Spec Kit feature, built as a deterministic projection of `tasks.md`,
  the Workflow ledger, a small tracked fact file and the host's native hook payloads.
- Verbs: `init`, `bind`, `refresh`, `status`, `lane`, `block`, `unblock`, `decide`, `note`, `theme`, `export`.
- Native hooks for session start, tool use, stop and session end. A successful automatic refresh prints nothing.
- Integration verbs for Workflow: `attempt record` stores a legacy attempt fact (origin `legacy`, never overriding producer state) and `runs --json` returns the `progress.runs.v1` run projection.
- Four themes, light and dark, importable from the Illustrate theme.
- Token benchmark against a hand-maintained Markdown report and the legacy Workflow report protocol.
