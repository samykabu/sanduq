# Round 3: implementation contract

Decision (user, 2026-10-19): **no renaming**. Every extension id, display name, command name and preset
stays as it is. Implement the "Fix first" and "Do" groups of `round-3-final-plan.md`; "Defer" and "Drop"
stay out. Work runs in the worktree `D:\Projects\Personal\sanduq-round3` (branch `feat/round-3`) and in
`D:\Projects\Personal\sanduq-skills` (branch `feat/round-3`). Notes: `round-3-notes.md`, one shell append
per stream under its heading.

Rules for every stream: no git commands that change the tree or the index; stay inside the owned files;
every defect fix gets a regression test that fails before the fix; keep every existing test green or
change it with a one-line reason in the notes; no version bumps and no CHANGELOG edits (the orchestrator
does those); receipts, evidence gates, GitHub decisions and observability stay intact; no new policy keys.
Savings are measured after implementation, never added together. Worker prohibitions stay in instruction
text whatever the guard hook does (Codex may not have approved it). Memory tests run with
`uv run --no-project --python 3.11 --with pyyaml python -m unittest ...` on this machine.

## Shared contracts

- **Illustrate hook ownership (IP5).** `extensions/illustrate/extension.yml` drops its `events:` block, so
  Spec Kit no longer registers the hook for everyone. `extensions/illustrate/hooks/self_check_hook.py`
  gains a management CLI:
  `python .specify/extensions/illustrate/hooks/self_check_hook.py install|uninstall|status --host claude|codex --root <project> [--json]`.
  `install` writes one native PostToolUse entry (Claude: `.claude/settings.json`, matcher
  `Write|Edit|MultiEdit`; Codex: `.codex/hooks.json`, matcher covering `apply_patch` and edit tools) that runs
  the script directly; `uninstall` removes it; both also remove any old Spec Kit dispatcher entry that
  runs `speckit.illustrate.hook` from `.claude/settings.json` and `.codex/config.toml`; both preserve every
  unrelated hook, are idempotent, and print `{host, file, added, removed, needs_approval}`. The hook body
  still exits 0 at once unless `illustrate.hooks.self_check` is true, and now understands Codex
  `apply_patch` payloads (every added, updated or moved `.html` path in the patch text). Removal never
  leaves a command pointing at a missing script. Owner of the script and manifest: S-IL. Owner of the
  Workflow side (S-INST): `install.py` and `upgrade.py` call `install` when the policy key is true and
  `uninstall` otherwise, on every apply and upgrade (this is also the cleanup for consumers upgrading
  from 2.5.0), record the result per host in `install-lock.json`, print the Codex `/hooks` approval step
  when `needs_approval`, and include both host files in the rollback set. Standalone users run the
  command themselves (README). Tests on both sides, including a failure mid-apply that rolls back.
- **Descriptions.** Catalog budget for all 47 commands: under 7,000 characters in total (today 8,604).
  Workflow at most 2,000, scope at most 1,000, others as they are or shorter. Every description passes
  `benchmark_instructions.py` checks; frontmatter and `extension.yml` stay identical (check_docs).
- **Benchmark (S-REL).** `benchmark_instructions.py` counts alternative references once per command
  (the import command's three `import-*.md`) and reports conditional references separately
  (`conditional_bytes`), so AFTER numbers are honest; the round-3 BEFORE numbers are re-run with the
  fixed harness before any stream lands and committed as `round-3-before-v2*`.
- **Spec Kit pin.** Compatibility runs against the commit CI pins (`tested_spec_kit` in
  `extensions/workflow/dependencies.json`, 8147943). S-REL fetches it into `D:\Projects\Personal\spec-kit`
  (`git fetch origin 8147943`, read-only otherwise) and records what the `specify_cli.events` dispatcher
  does there in the notes; S-IL and S-INST read that note.

## Streams

| Stream | Items | Owns |
| --- | --- | --- |
| U-IL illustration-tools (sanduq-skills) | IP1 icon lookup script, IP2 examples and templates pass the checks the procedure requires plus a strict baseline test, IP3 technical-color check profile and one shared toolbar section, IP4 upstream part (export reads `export.md` only on failure; split `output-spec.md`) | `skills/illustration-tools/**` |
| U-AT agent-tools and dev-tools (sanduq-skills) | IP10 browser tests out of the default Progress run (opt-in flag or env), `live_ab.py` moved next to its `tests/` dependency or made importable | `skills/agent-tools/**`, `skills/dev-tools/**` |
| S-WF workflow runtime | W1 one git and fingerprint pass per command (operation-scoped caches, invalidation tests), W2/W3 Execute claim carries only the protocol that applies, W4 receipt skeleton in the claim, W5 Codex guard-approval check in `doctor` and `status`, W8 cleanup, PM6 investigation (code-level: whether memory's hooks and Workflow's memory handoff both run in a managed project; report, change nothing unless shown), workflow descriptions | `extensions/workflow/scripts/workflow.py` and every workflow script except `install.py`, `upgrade.py`, `hosts.py`; `extensions/workflow/skills/workflow/**` except the three Scope-owned references below; `extensions/workflow/commands/**`; `extensions/workflow/extension.yml`; the workflow tests for those |
| S-INST installer | IP5 Workflow side, IP9 installer reports the Progress hook cost class and hints at native wiring, presets re-added only when changed (X7 half), W7 runtime-only delegate-task install | `extensions/workflow/scripts/install.py`, `upgrade.py`, `hosts.py`, `extensions/workflow/tests/test_install.py`, `test_upgrade*.py`, `test_hosts*.py` (and new install tests) |
| S-SC scope and presets | SC1, SC3 (behind dependency-completeness tests and a fallback), SC4, SC5, SC6, SC7, SC9, scope descriptions | `extensions/scope/**`, `presets/**`, and in workflow only `skills/workflow/references/stage-scope.md`, `stage-specify.md`, `stage-clarify.md`, `scope-binding.md` |
| S-AU assure and user-manual | AU1 diagram stages follow Illustrate's procedure, AU2 audit placeholders and links, AU3 skip unchanged reruns, AU4 one freshness CLI, AU5 authoritative gate parsing, stable scan output, one exclude list, AU7 host-neutral names and lighter init | `extensions/assure/**`, `extensions/user-manual/**` except vendored files, `extensions/scripts/shared/sanduq_freshness.py` |
| S-PM pr, project and memory | PM1 images resolved to verified remote URLs before lint, PM3 publication hardening (failed lookup is not "no PR", malformed markers refused, guard covers inline `--body`), PM4 remote normalisation like Workflow plus scope checks and timeouts, PM5-small (init passes the existing non-interactive flags, no forced interactive auth, actionable missing-choice report), PM7, PM8 | `extensions/pr/**`, `extensions/project/**`, `extensions/memory/**`, `extensions/workflow/hooks/guard.py`, `extensions/workflow/tests/test_guard_hook.py` |
| S-IL illustrate and progress, sanduq side | IP5 extension side (contract above), IP4 command side, IP7 sanduq tests stop duplicating upstream (keep only sanduq-specific tests; vendored verifiers run in CI from the vendored copy), Progress commands untouched unless IP9 needs a README line | `extensions/illustrate/**` except `skill/**`, `extensions/progress/**` except vendored files |
| S-CI | X3 path selection (release metadata and docs lint-only; project changes keep their coverage through a `project` suite that runs `test_project_sync_summary`), smoke jobs gated on `changes`, Windows memory on the same event rule, X5 pip, Playwright and Spec Kit wheel caches (fresh runners still install Chromium's OS deps), X6 vendored verifiers only on vendor bumps and nightly, IP7 and IP10 CI side, X4 Windows workflow suite in four shards | `.github/**`, `extensions/scripts/tests/test_ci_matrix.py` |
| S-REL release tooling, packaging, docs | Measurement first (harness fixes, BEFORE v2, Spec Kit pin note), X1 `release.py bump` and pending-marker clearing in `promote`, X2 factual `check_docs` rules (pins, changelog headings, pending markers, extension counts) and the stale facts (README extension count and install block, root CHANGELOG "(pending release)" headings), X8 one packaging exclusion list (IP6, IP8: Progress docs, delegate-task images, unrunnable files), AU6 vendored user-manual test mapping | `extensions/scripts/**` except `shared/sanduq_freshness.py` and `tests/test_ci_matrix.py`, `vendor.lock.json` (AU6 entry only), `README.md`, `CHANGELOG.md`, `docs/**` except per-extension pages, `extensions/README.md` |

Per-extension doc pages (`docs/extensions/<id>.md`) and READMEs belong to that extension's stream.
Ordering: S-REL's harness fix and BEFORE v2 land first (orchestrator commits it before the others merge);
U-IL and U-AT release before the sanduq vendor sync; S-CI's X4 shard sizes are checked against a CI run of
this branch before release.
