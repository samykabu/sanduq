# Round 3: stream notes

Append under your heading with one shell append. Contract: `round-3-implementation.md`.

## U-IL

### U-IL notes (2026-10-20)

All under `skills/illustration-tools/**` in sanduq-skills (branch feat/round-3); nothing committed, no version or CHANGELOG.

- **IP2 (strict assets).** Before: 51 of 296 shipped HTML pass `self_check.py --strict` (178 default). After: 274 of 296
  pass `--strict` (every editorial template and example), the 18 technical-color files pass
  `--profile technical-color` (0 of 18 passed the default before), and the only failures left are the four gallery
  pages (`icons.html`, `index*.html`), now the whole content of `scripts/self-check-baseline.txt`. Fixes are in the
  assets: svg `min-width` set to the viewBox width (222 files), the accessible-SVG contract added to the 92 legacy
  examples and 18 technical-color files (titles and one-sentence descs written per type), nodes moved or resized onto
  the 4px grid (data-flow, state-lifecycle, high-level-vertical, quadrant, medallion header band 50 -> 48 with the
  formula in type-medallion.md, template-full rebuilt on the grid with a legend strip below the region,
  paved-road and queue animated), paper masks of data-bound bars marked `data-mask` and bars `data-value` (bar,
  marimekko, waterfall: the documented data-bound exception), diagonal connectors rerouted as r=8 elbows (state,
  swimlane, paved-road, queue), architecture labels moved off the node (its verify-geometry baseline entries and the
  swimlane ones are gone; that baseline is now empty), heatmap and fishbone frames hold their min-width. Hand
  variants regenerated with `generate-hand-variants.cjs` (scratch npm install, deterministic; output equals the
  committed files apart from the edits).
- **Checks taught, not loosened.** `verify-geometry.orthogonal_findings` accepts exactly the shapes the type
  references already document as rule-1 exceptions: Loop `class="ring"` (one clockwise `A R R 0 0 1` arc) and
  `class="spoke"` (one `M L` radius), Medallion `class="promotion"` (the symmetric over-the-top cubic between two
  vertical leads). type-loop.md and type-medallion.md now say to keep those classes. `verify-polar.py` canonical
  svg rule pinned `min-width: 900px`; now `1000px` (the polar viewBox width), or strict and verify-polar contradicted.
- **IP3.** `self_check.py --profile technical-color` (refuses `--strict` with it): default checks, plus exactly the two
  pinned CDN scripts (URL, integrity, crossorigin, nothing else, once each), the four toolbar `onclick` values on
  `<button>`, and one inline script equal to the template's apart from `backgroundColor` hex and download file names.
  Toolbar section now lives once in `references/technical-color-common.md`; both family references link to it.
  SKILL.md step 7 names the profile. Not done: the Claude.ai "Preview & Fix" prose in technical-color-process-flow.md
  (not in this stream's row).
- **IP1.** `scripts/icon_lookup.py <name or keyword>...` prints snippets from the new generated `scripts/icons.json`;
  unknown term exits 2 with nearest names. `build-icons.py` emits the index, the JSON and the gallery (LF on every
  OS) and gained `--check` (offline, from the vendored SVGs; icons.html unchanged). `primitive-icons.md` 81,851 ->
  4,603 B. Stale "41 icons" in type-it-state.md fixed.
- **IP4 upstream.** SKILL.md §12 carries the exporter flags and reads export.md only when the exporter exits non-zero
  or for animation options (export.md Trigger says the same; the three import references too). `output-spec.md`
  15,724 -> 11,078 B; the size-class half (narrow screens, `fit`, type ramp, safe areas) is `size-classes.md`
  (5,127 B), preset table stays (lint-render and the import verifiers read it). Anchored links retargeted.
- **Existing tests changed:** test_self_check ShippedAssets now runs the procedure's check over every asset (rglob)
  instead of the default check over top-level files; test_verify_heatmap N8 anchor follows the heatmap svg rule
  (min-width added); verify-drawio-import reads size-classes.md with output-spec.md. New: TechnicalColorProfile tests,
  documented-arc pass/fail cases, tests/test_icons.py.
- **For S-IL:** the opt-in hook calls self_check without a profile, so a technical-color write still fails it; pass
  `--profile technical-color` for files that carry the toolbar if that matters. The vendored copy of
  test_self_check.py changes with the sync.

## U-AT

## S-WF

## S-INST

## S-SC

## S-AU

## S-PM

## S-IL

## S-CI

## S-REL

## Orchestrator

- User decision 2026-10-19: no renaming; ids and display names unchanged (report db selection/current version 13).

### S-REL: Spec Kit pin note (8147943, specify-cli 1.0.11)

Read with `git -C D:\Projects\Personal\spec-kit show 8147943:src/specify_cli/events/__init__.py` (2,641 lines;
`events/command_run.py` is only the `specify event run` CLI adapter).

- **`specify_cli.events` exists** at the pin: a package with `collect_extension_events`, `resolve_events`,
  `install_integration_events`, `remove_integration_events`, `refresh_integration_events`,
  `resolve_and_run_event_command` and the flag `EVENT_SCRIPT_PATH_CONFINEMENT = True`.
- **Rendering.** `collect_extension_events` reads `events:` from every installed, enabled extension (validated
  manifest first, raw `extension.yml` as fallback; disabled extensions skipped). Layering: CLI `--events` flag,
  then `.specify/integration-events.yml`, then extension-declared, then built-in. `install_integration_events`
  writes the shared dispatcher `.specify/events.py` (generated, recorded in the integration manifest) and merges one
  native entry per handler:
  - Claude (`json-nested`, `.claude/settings.json`): `hooks.<PostToolUse>[{matcher, hooks:[{type:"command",
    command:"<python> \"${CLAUDE_PROJECT_DIR}/.specify/events.py\" <command> <event> <timeout>", timeout:<t+5>,
    "__speckit_event__": true}]}]`, grouped by matcher (default `*`).
  - Codex (`toml`, `.codex/config.toml`): one `[[hooks.PostToolUse]]` block per handler with `matcher` (default
    `*`), `[[hooks.PostToolUse.hooks]]` `type="command"`, the same dispatcher command, and `speckit_marker = true`.
    Nothing is written to `.codex/hooks.json`.
  - The interpreter is `IntegrationBase.resolve_python_interpreter` (project venv aware), resolved at render time.
- **Running.** The native host runs `events.py <command> <event> <timeout>` with the payload on stdin (1 MiB cap).
  It first tries `from specify_cli.events import EVENT_SCRIPT_PATH_CONFINEMENT, resolve_and_run_event_command`
  (this import is the 1.4 s case IP9 measured); on ImportError it uses an inline stdlib resolver. Both look up the
  command in the extension's `provides.commands` (`name` -> `file`), read that command file's frontmatter
  `scripts:` entry for the project's script type (`sh`/`ps`/`py` from init options, platform default otherwise),
  confine the script path to the project, and run it with `cwd=<project>`, stdout passed through (plain envelope
  for Claude and Codex). A missing command or script logs a warning and exits 0 (not an error); timeout exits 2.
  So a hook runs the command file's `scripts:` entry, never a script path named in `extension.yml`.
- **Removal.** `specify extension remove`, `enable`, `disable`, `add` and a successful `update` all end in
  `_refresh_events_and_warn` -> `refresh_integration_events`, which re-resolves events for every installed
  event-capable integration and calls `install_integration_events` again. Before merging, it drops every entry
  carrying the marker (`__speckit_event__` in JSON, `speckit_marker = true` in TOML) and keeps user entries; an
  empty map strips all marked entries and deletes `.specify/events.py` unless another integration's manifest still
  claims it. A refresh failure prints a warning ("a stale native hook may still be active") and does not fail the
  command. So: dropping `events:` from Illustrate's manifest and running `extension update` removes the old
  dispatcher entry on its own on this pin; entries written without the marker (Sanduq's own native hooks) are never
  touched by Spec Kit.

### S-IL (illustrate and progress, sanduq side)

- **IP5 extension side.** `extensions/illustrate/extension.yml` has no `events:` block; `commands/speckit.illustrate.hook.md`
  is deleted (it existed only for the dispatcher; it was never in `provides.commands`, and S-REL's note shows nothing else
  looks it up). `hooks/self_check_hook.py` keeps its hook mode (no argv, or only the tag) and gains
  `install|uninstall|status --host claude|codex --root <project> [--json]`.
  - Entry: `{"matcher": M, "hooks": [{"type": "command", "command": "<python> \"<path>\" --managed-by=sanduq-illustrate", "timeout": 60}]}`
    in `hooks.PostToolUse`; Claude M `Write|Edit|MultiEdit`, path `${CLAUDE_PROJECT_DIR}/.specify/extensions/illustrate/hooks/self_check_hook.py`;
    Codex (`.codex/hooks.json`) M `apply_patch|Write|Edit|MultiEdit|write_file|edit_file`, project-relative path. `<python>` is
    `python` on Windows, `python3` elsewhere (as Progress). Own entries are found by the tag.
  - Output, one JSON object with `--json`: `{"host": "codex", "file": ".codex/hooks.json", "added": 1, "removed": 1, "needs_approval": true}`.
    Without `--json`: `host="codex" file=".codex/hooks.json" added=1 removed=1 needs_approval=true` plus a `/hooks` line.
    `status` adds `installed` (bool) and `dispatcher_entries` (int); its `needs_approval` is "installed on Codex" since approval
    is not visible. `install` `needs_approval` is true only when it added the Codex entry (a rerun is false).
  - `removed` counts own stale entries replaced plus old dispatcher entries (`speckit.illustrate.hook`): handlers in
    `.claude/settings.json` (host claude) and `[[hooks.*]]` blocks with `speckit_marker = true` in `.codex/config.toml` (host codex).
  - Exit 0 on success; exit 2 with `illustrate hook <action>: <reason>` on stderr and nothing written when the JSON is invalid or
    oddly shaped, or when the running copy is outside `--root` (a command must point at the project's own script).
    S-INST: call the copy under `.specify/extensions/illustrate/hooks/`, not the source tree.
  - Limit: the command cannot end in `; exit 0` (exit 2 is how a failure reaches the agent), so a native entry left behind after
    `specify extension remove illustrate` would fail each write. README and docs say to run `uninstall` first; Workflow does it.
  - Hook body: Codex `apply_patch` targets (`*** Add File:`, `*** Update File:`, `*** Move to:`) from any string in `tool_input`
    (dict, bare string or argv list); every `.html` with `<svg` is checked; the PyYAML import is skipped when `workflow.yml`
    lacks the text `self_check`.
- **IP4 command side.** `commands/speckit.illustrate.export.md` reads `export.md` only when the exporter exits non-zero or the
  user asks about animation (now step 6); frontmatter unchanged.
- **IP7.** `extensions/illustrate/tests` keeps `test_self_check_hook.py` (sanduq hook and CLI) and `test_illustration_theme.py`
  cut to the one sanduq-specific test (`.github/illustration-theme.yml` and `docs/examples/booking-illustration-theme.yml`
  validate; `ci_matrix.py`'s DOC_SUITES comment still holds). Removed, each a path-rewritten copy of the same-named upstream file
  in `sanduq-skills/skills/illustration-tools/tests/` at f260c7b (ROOT/path-only diff unless noted): `_helpers.py`,
  `_retheme_fixture.py`, `fixtures/` (6 files), `test_import_extractors.py`, `test_lint_render.py`, `test_lint_skin.py`,
  `test_self_check.py` (subset: upstream adds StrictContract), `test_skill_frontmatter.py` (subset: upstream adds SkillEntry),
  `test_theme_matrix.py`, `test_verifier_cross_scope.py`, `test_verifier_hand_scope.py`, `test_verify_geometry.py` (subset:
  upstream adds Orthogonality), `test_verify_{architecture_delta,axonometric_plan,beeswarm,block_registry,bubble,bump,dumbbell,
  exploded,heatmap,marimekko,motion,polar,ridgeline,sankey,semantic_motion,sequence_oauth,slopegraph,streamgraph,treemap,
  waterfall}.py`, `verify-{drawio,excalidraw,mermaid}-import.py`; plus the rest of `test_illustration_theme.py` (identical to
  upstream). The vendored verifiers in `skill/scripts` do not need `tests/` and run as before (`ci.yml` steps). Stale but
  harmless: `.gitattributes:16` (`extensions/illustrate/tests/fixtures/**`), not S-IL's file.
- Illustrate suite: 9 tests, 4.4 s (was 142 tests, 210 s). Progress untouched (14 tests, 7 skipped). Regression check: the
  `apply_patch` test fails against the HEAD hook (0 != 2).

## U-AT

- IP10: `tests/test_ui_browser.py` and `tests/test_ui_v3_browser.py` raise `unittest.SkipTest` in `setUpModule` unless
  `PROGRESS_UI_TESTS=1` (documented in the progress-report README "Tests" section). Default run: 507 tests, 13 skipped
  (the 11 before plus the two modules), 138.4 s; with the flag: 581 tests, 11 skipped, 219.4 s (this machine, Python 3.13).
  The poll-interval cut from the IP10 card was not done (out of this brief); the default run still covers every
  non-browser test. User Manual: 29 tests OK, 8.1 s default, 5.5 s with the flag (unaffected).
- IP8 upstream: `scripts/live_ab.py` moved to `tests/live_ab.py` next to `tests/bench` (dropped its `sys.path` insert of
  `tests/`; `test_live_ab.py` dropped its `scripts/` path insert). Refs updated in README, `docs/commands.md`,
  `docs/token-benchmark.md` and `tests/bench/report.py`. Nothing outside `tests/` imports from `tests/` any more, so the
  sanduq `EXCLUDE_PATHS['progress']` entry for `scripts/live_ab.py` becomes unnecessary after the vendor sync.
- ci.yml change for sanduq-skills (owner of `.github`): today ci.yml runs no Progress tests at all. Add to job `tests`,
  after "User Manual tests":

      - name: Progress Report tests
        run: python -m unittest discover -s skills/agent-tools/skills/progress-report/tests -q

  and a new job (Playwright already installed by the same steps as `tests`):

  progress-ui:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch' || contains(github.event.pull_request.labels.*.name, 'progress-ui')
    runs-on: ubuntu-latest
    env:
      PROGRESS_UI_TESTS: '1'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.13'}
      - run: python -m pip install -r requirements-test.txt playwright==1.63.0
      - run: python -m playwright install --with-deps chromium
      - run: python -m unittest discover -s skills/agent-tools/skills/progress-report/tests -q

  with `on:` gaining `schedule: [{cron: '17 3 * * *'}]` and `workflow_dispatch:`. (Pin actions to the SHAs the rest of
  ci.yml uses once dev-tools-v1.1.3's pinning lands there.)
- **S-IL follow-up (coordinator).** The installed command is now
  `<python> -c "import os,runpy,sys;p=os.path.join(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd(),'.specify/extensions/illustrate/hooks/self_check_hook.py');sys.exit(0) if not os.path.isfile(p) else runpy.run_path(p,run_name='__main__')" --managed-by=sanduq-illustrate`
  for both hosts (Codex: process cwd, since reading the payload's cwd would consume stdin). A missing script exits 0 silently;
  a present one keeps its exit code (2 on a failed check). Detection is still the tag. The earlier "leftover entry fails
  every write" limit is gone. Test: `test_installed_command_runs_the_script_and_is_inert_once_it_is_gone`; smoke-run in sh
  and pwsh. Illustrate suite: 10 tests, 7.5 s.

## S-CI

Files: `.github/scripts/ci_matrix.py`, `.github/workflows/ci.yml`, `.github/workflows/release-extensions.yml`, `extensions/scripts/tests/test_ci_matrix.py`.

- X3: root `CHANGELOG.md`, `README.md`, `CONTRIBUTING.md`, `extensions/README.md`, `extensions/pending-releases.json` and `docs/**` (except `docs/examples/`) select lint only. Per-extension READMEs and CHANGELOGs stay with their suite (progress tests read `extensions/progress/README.md`). New `project` suite: `extensions/project/**` runs `test_project_sync_summary` from the workflow tests on both OS (plus `extensions/project/tests` if it appears); dropped whenever the workflow suite runs, since that suite already contains the module. New `install_smoke` output gates installation, upgrade, project-init and dryrun (`needs: changes`): true for `extensions/workflow/`, `extensions/project/`, `extensions/*/extension.yml`, `extensions/scripts/package.*`, `smoke_*`, `shared/`, `presets/`, `prototypes/` (installation runs the native probe), `vendor.lock.json`, `ci.yml`, `.github/scripts/`, unknown diffs, schedule and dispatch. Windows memory now skips pushes like Windows workflow (`WINDOWS_SLOW_SUITES`).
- Existing tests changed: `test_shared_paths_run_everything` drops `README.md` and `extensions/pending-releases.json` (now lint-only by X3) and adds `vendor.lock.json`; the run-everything assertions compare against all suites minus `project` (its module runs inside workflow).
- X6 and IP7: new `illustrate_vendored` output (vendor.lock.json or `extensions/illustrate/skill/**` changed, schedule, dispatch, unknown diff). The builders, verifiers and `lint-render.py` steps run only then, from the vendored copy, with the commands ci.yml already used (upstream tests are not vendored). The illustrate unittest step and Playwright stay on every illustrate change. Shortcut: any vendor.lock.json change counts, including other inputs.
- IP10: nothing to change in sanduq. The vendored Progress map covers `scripts` and `assets/ui` only; the sanduq progress suite (`test_extension.py`, `test_token_budget.py`) has no browser tests, so the regression already runs the non-browser set. The nightly browser run belongs to the sanduq-skills CI.
- X5: `cache: pip` on every setup-python (regression keyed on the requirement files; Spec Kit jobs also on ci.yml, which holds the pin, so they get their own cache entry; release keyed on workflow requirements). Spec Kit now installs as `specify-cli @ git+...@8147943...`: pip only consults its wheel cache for a named VCS requirement at a full sha. Checked locally: the second install printed `Using cached specify_cli-1.0.11-py3-none-any.whl` with no clone. Playwright browser cached per OS, arch and 1.63.0; `playwright install --with-deps chromium` still runs every time, so fresh runners get the OS libraries. vendor-update has no requirements file and installs only pyyaml, so it gets no pip cache.
- X4: Windows workflow runs as 4 shards (`workflow_shards()`, rule-based: largest module first onto the lightest shard, by file size, over discover-pattern `test*.py`, so new modules join automatically). Today: 8/16/15/15 modules, 278/278/278/277 KB, test counts 239/302/331/337 = 1209, same as discover. Shard jobs run `PYTHONPATH=<tests> python -m unittest -q <modules>` (site makes the path absolute; cwd stays the repo root as with discover). Linux workflow stays one job. Job names keep the old form `regression (<os>, <suite>)` plus `, n/4` for shards; branch protection that required `regression (windows-latest, workflow)` would need the four new names. Size is a proxy for time: check the shard times on the first CI run of this branch (contract) and switch to measured seconds if one shard dominates.
- Validation: `test_ci_matrix.py` 31 tests OK; `extensions/scripts/tests` 120 tests OK; all four workflows parse with PyYAML; `git diff --check` clean on the owned files.
- Samples (`--event pull_request --files`): docs plus CHANGELOG plus pending-releases: 0 jobs, every flag false. `extensions/project/scripts/project_sync.py`: project x2, install_smoke true. `extensions/illustrate/commands/speckit.illustrate.export.md`: illustrate x2, install_smoke false, illustrate_vendored false. `vendor.lock.json` plus `extensions/illustrate/skill/SKILL.md`: 19 jobs (all suites on both OS, Windows workflow as 4 shards), all flags true.

## S-PM (notes)

- PM3: `pr_publish.py` treats any `gh pr view` failure other than "no pull requests found" as exit 3 (no push, no create); refuses unpaired, repeated or reversed markers in the PR body and a marker inside the document (exit 2). `workflow/hooks/guard.py` refuses inline `gh pr create|edit --body/-b/--body=` in a managed project and names `pr_publish.py`. Guard hash changes, so Codex users re-approve it in `/hooks`.
- PM1: `pr_publish.py` rewrites relative image paths (Markdown and `<img src>`, outside code) to `https://github.com/<repo>/blob/<HEAD sha>/<path>?raw=true` before the lint, after `git cat-file -e` (exit 2) and `gh api repos/<repo>/contents/<path>?ref=<sha>` (exit 3); a new PR's branch is pushed first only when images need it. `pr-image-embedding.md` and `speckit.pr.generate.md` say so; the `body_html` check after publication stays with the model.
- PM4: `project_sync.py` uses Workflow's `normalize_remote_url` when `.specify/extensions/workflow/scripts/workflow.py` imports, else an identical copy (test asserts equality on 9 remotes); case-insensitive binding; `project` must be a whole token scope; 120 s timeouts (`error exit=1 reason=timeout: ...`); missing git is a skip; the unconditional rate-limit probe is gone. Existing test changed: FakeGh with budget 0 now fails GraphQL-backed subcommands, because without the probe REST is reached through a failed call, as on GitHub. `test_project_sync_summary.py` (workflow tests dir) carries the project tests, as the CI contract keeps it.
- PM5-small: init command runs both scripts with `--non-interactive`/`-NonInteractive`, no `gh auth refresh` step; scripts list the projects when several exist, name `--auto-create-columns` for a missing column and `--hooks-mode` for the default; scope check refuses `read:project` alone. New `ProjectInitTests` run both real scripts with a fake gh (skip without bash+jq and pwsh). `smoke_project_init.py` passes on bash and pwsh.
- PM7/PM8: `run.md` step 3 (preflight, `data.ok`) removed, steps renumbered, the journal's `references` named as the repair list. Memory descriptions 983 to 724 characters, identical in frontmatter and `extension.yml`, each passes `benchmark_instructions.describe`; `install.py` unchanged (already reads frontmatter).
- Not done: `gh pr create --fill` in a managed project (unlinted body) is still allowed; `pr_changelog.py` default branch; `workflow.py` printing the sync command when project is absent (S-WF); `docs/reference/commands.md` needs no regeneration (check_docs clean for memory).

## S-AU (notes)

- AU5 gate: `assure_state.gate_on` returns the PyYAML value when the file parses (`false  # set to true` is off). Only on a parse failure or missing PyYAML does the comment-aware `assure_scan.read_config` run; a file that names the key where neither reader finds it fails closed (gate on) with one stderr line `<config>: cannot be parsed; treating the documentation gate as on`. The substring scan is gone.
- AU2: `audit_qa.py` skips SECRET values containing `redacted`, `example`, `placeholder`, `<`, `&lt;` or `${` (user-manual's allowlist plus `&lt;`); the value now stops at `<` so `hunter2</pre>` is still caught. Links are percent-decoded; `/x` resolves against the nearest `public`/`static` ancestor, else `--repo-root`. Document step 7 says fix real findings and report suspected false ones instead of deleting correct content.
- Stable scan: `assure_scan.py` re-renders with the stored `Last scanned` date and keeps the file when that equals it; a new date is written only when the inventory changes. The one literal exclude list is `assure-config.template.yml`: `DEFAULT_EXCLUDE` is read from it, and `assure_init.config_text` is the template with the mode substituted (postcondition check, clear exit if the template drifts). `SCAN_EXCLUDE` removed.
- AU1: Document 5.3 and Update step 6 follow `.specify/extensions/illustrate/skill/SKILL.md` §0 theme gate and §10 (type index and `type-*.md`, theme apply/validate, step 7 checks), scripts under `.specify/extensions/illustrate/skill/scripts/`; export names `export_diagram.py` by its installed path and "Illustrate §12" (no `export.md` mention, so IP4's on-failure wording upstream stays consistent). Both Analyze commands keep the type-index route and say the drawing stage follows the full procedure. Section tags checked against sanduq-skills feat/round-3 SKILL.md (§0, §10, §12 unchanged).
- AU3: Assure Analyze starts with `assure_state.py status --kind analyze --summary` and stops on `ok` unless `--report-only` or a requested refresh. Update step 2 is one `manual_impact.py` call whose output now carries `current` and `changed_outputs` (status computed once; `manual_state.py status` no longer run separately) and names `current`, stale and full branches. User Manual Analyze keeps its evidence-scope-only impact call (it would otherwise need PyYAML at analyze time).
- AU4: `sanduq_freshness.cli(description, record, state_path, kind, default_outputs, gate)` holds the shared argparse, gate, summary and exit code; both scripts keep their entry points and flags and pass their own `record_or_status` (existing mock-based tests still patch it). Assure `--summary` now prints `changed_inputs=N changed_outputs=M` (D7).
- AU7: `Assure.Init/Analyze/Document` and `UserManual.Init` replaced by `speckit.*` names in commands, manifest hook prompt, README, both SKILL.ext.md descriptions and ADAPTER.md; init no longer loads the skill; the duplicated gate sentence in `references/analysis.md` removed.
- Tests: new `assure/tests/test_commands.py`, `user-manual/tests/test_commands.py`; new cases in `test_assure_state_gate.py`, `test_audit_qa.py`, `test_assure_scan.py`, `test_manual_impact.py`; all failed against HEAD (checked in a `git archive` copy). No existing expectation changed.
- Not done: `--check` still prints the memory block (`--show-block` not added); the four dependency blocks were not shortened; CHANGELOGs and versions left to the orchestrator (assure, user-manual, and every package that bundles `sanduq_freshness.py`).

### S-INST

- **IP5 (Workflow side).** `install.py` `wire_illustrate` runs after the last Spec Kit call (after reconcile and
  `wire_progress`) on every apply, so also inside every upgrade (upgrade.py runs the new installer). It calls
  `self_check_hook.py install|uninstall --host <h> --root <project> --json` for each installed claude/codex host,
  `install` only when `illustrate.hooks.self_check` is true. A non-zero exit or no JSON (an Illustrate older than the
  CLI) fails the apply and rolls back; a missing script is skipped when off and refused when on. The three host files
  were already in `FILES` (rollback set). `install-lock.json` and the receipt get `illustrate: {self_check, action,
  hosts: {<h>: {file, added, removed, needs_approval}}}`; `needs_approval` adds `illustrate_hook_approval` (printed on
  stderr by install.py and upgrade.py). Verified against S-IL's real CLI and in the smoke project with real Spec Kit
  (key on: one entry per host, Codex approval line; key off: both removed).
- **IP9.** `wire_progress` (speckit wiring) records per host `dispatcher: {path, interpreter, imports_specify_cli}` and
  `cost_class` (`dispatcher`, `dispatcher-specify-cli`, `native`); the interpreter is read from the rendered entry
  (shlex, Spec Kit POSIX-quotes it) and probed once with `-c "import specify_cli.events"` (5 s timeout). The slow class
  adds `progress.hint` (stderr line pointing at `progress.hook_wiring: native`). Default unchanged. `progress_bridge`
  copying the flag into `workflow status` is S-WF's file and was not done.
- **Presets (X7 half).** Lock presets gain `source_sha256` (bundled files, LF-normalised). A preset is skipped when no
  extension operation runs in this apply, its `preset.yml` is installed, and digest and priority match the lock;
  result/receipt list `skipped_presets`. Any extension update still re-adds all presets: Spec Kit 8147943 reconciles
  the priority stack only on preset install, and extension add re-renders `speckit.scope.run`, which a preset replaces.
- **W7.** The copy lives in `delegation.py` (S-WF's file): one line widened `ignore_patterns` with `assets`, `README*`.
  `contracts/` and `references/` stay (SKILL.md reads them). Flagged to S-WF; test in `test_install_hooks.py`.
- Tests: new `tests/test_install_hooks.py` (14). No existing test changed. hosts.py unchanged (a host added later with
  `specify integration install` gets the Illustrate hook on the next apply).

## S-SC

Scope and presets (SC1, SC3, SC4, SC5, SC6, SC7, SC9, scope descriptions). Call counts: test-suite fake client, each command from a fresh process (no board cache); before = `git archive HEAD`.

| Operation | Before | After |
| --- | ---: | ---: |
| `publish --apply`, 3-child split, 200 unrelated issues, 2 dependents | 290 | 62 (same count with 0 unrelated issues; item-list 4 to 1, field-list 7 to 1, label listings 8 to 1, `blocked_by` 210 to 10) |
| `gate` without `--snapshot` | 6 | 3 (2 when the analyst's snapshot is current) |
| `bind --apply` | 10 | 4 |
| `clarification.py publish --apply`, 6 questions | 27 | 23 |

- SC3: `rewire` takes candidates from `GET issues/{parent}/dependencies/blocking` plus every issue whose body, receipt, board Blocked by or catalogue entry names the parent (local, no calls), and falls back to the full per-issue scan when that read fails or is malformed (stderr line). Not verified: the live `dependencies/blocking` endpoint (the fallback covers its absence). New items and field edits update the in-memory board row; `board-cache.json` is still removed after every write. The split now sets Backlog on new children (real GitHub items start with no status; the old fake hid this).
- SC4: `execution_tools.py` is S-WF's file, so nothing there changed: `gate` and `bind` pick up `.specify/scope/issue-<n>-snapshot.json` themselves when no `--snapshot` is given; their fallback inspect stops after prerequisites (the fresh-claim path keeps full evidence because it validates images). `main` reports `snapshot_reused` via `getattr` so workflow's `Recorder` stand-in keeps working.
- SC6: in-session spec log lines are unchanged (they already carry the answer; `test_clarification` pins them).
- SC7: the `__SPECKIT_COMMAND_*__` host tokens were not done (not in this stream's brief, unverified on the pinned Spec Kit). Seven scope descriptions total 969 characters; all pass `benchmark_instructions.py`.
- SC1: clarification diagram text moved to `extensions/scope/references/clarification-diagrams.md`, not under the skill's `references/` (workflow's `test_skill_split` pins that folder to four files). Pinned rules-inventory sentences were kept. No CHANGELOG edit: the orchestrator should note the moved 1.5.x/1.6.0 migration text, the `inspect --skeleton` flag, the spec log `Q: ... → A: ...` line, and `implementation-plan.mapping.json` written by `export-plan`.
- Tests: no existing test changed except `FakeGitHub` (adds `dependencies/blocking` and `blocking_unavailable`). New: `test_github_calls.py`, `test_instructions.py`, `test_plan.WaveTests`, skeleton tests in `test_scope.py`, and suggestion and log tests in `test_clarification.py`.

### S-REL: release tooling, packaging, docs

- **Harness (measurement first).** `benchmark_instructions.py` classifies links per file: a routing list
  (`case → file` sibling items) or an "otherwise" sentence is one alternative group, counted once as its
  largest member (`alternatives`); a link in a clause with if/when/whenever/unless/otherwise goes to
  `conditional`/`conditional_bytes`, not `instruction_bytes`; a plain mention wins. Extension totals now sum
  only files some entry reads unconditionally (`conditional_bytes`, `conditional_files`, `command_bytes` added).
  Rules and known limits in `docs/internal/benchmarks/README.md`; test `tests/test_benchmark_instructions.py`.
- **BEFORE v2** (`round-3-before-v2-instructions.*`, base worktree 7ad9135). instruction / conditional /
  per-invocation command bytes: workflow 35,558 / 7,342 / 42,743; scope 43,593 / 2,341 / 25,776; assure
  22,082 / 6,530 / 22,772; user-manual 26,820 / 7,121 / 24,266; pr 23,957 / 5,201 / 23,957; project 3,602 / 0 /
  3,602; illustrate 249,775 / 52,088 / 65,890; memory 29,717 / 2,008 / 31,862; progress 9,195 / 0 / 4,192; all
  444,299 / 82,631 / 245,060 (old harness: 526,930). `speckit.illustrate.import` is 31,824 (was 61,141), one of 3.
- **X1.** `release.py bump <id> <version>` writes extension.yml (version line only), the extensions/README.md
  row, every dependencies.json pin of that id, pending-releases.json (status ready/released becomes
  implementation-in-progress); refuses a lower version, writes nothing on error, second run is a no-op.
  `promote` drops " (pending release)" from root CHANGELOG headings naming a promoted version. `write()` now
  writes LF on Windows. Tests `tests/test_release_bump.py`. CONTRIBUTING.md "Prepare a release" should name
  `bump` (not my file).
- **X2.** `check_docs.py` rules: Workflow pins equal manifest versions; "N extensions" counts (words, digits,
  the shields badge) equal the manifest count; the install-by-host add-all block lists every id; root
  CHANGELOG preamble first, every `##` heading dated, no "(unreleased)", no "(pending release)" naming a
  version catalog.json lists. Fixed: README badge and alt text, glossary, install-by-host (nine, Progress in
  the block, anchor `#all-nine-extensions`), product map (Progress box, Workflow uses Progress; svg,
  animated svg, html), root CHANGELOG (preamble moved up, three pending markers, two undated headings dated
  from the workflow-v1.5.0 and v1.0.0 tags). Fixtures appended to `test_check_docs.py`.
  Not touched: `extensions/workflow/CHANGELOG.md` still has "## 1.0.0 (unreleased)" (S-WF/orchestrator).
- **X8.** `package.py` has one `EXCLUDE_PATHS` tuple of `<ext>/<path>` files or folders: progress `docs`
  and `scripts/live_ab.py`; illustrate preview images, `index-variation-1/2.html`, `scripts/vendor`,
  `build-icons.py`, `fix-mojibake.py`; workflow delegate-task `README.md`, `README.ar.md`, `assets/`. Kept
  (named by references): `build-exploded-examples.py`, `build-axonometric-plan-examples.py`,
  `generate-hand-variants.cjs` and the `package.json` it needs. The packaged README rewrites links to
  excluded paths to GitHub URLs and `SKILL.ext.md` links to `SKILL.md`. Test `tests/test_package_exclusions.py`
  (absent, required assets present, no agent route names an exclusion, packaged README links resolve).
  Sizes zip (raw): workflow 762,747 to 555,008 (1,785,404 to 1,474,473); illustrate 3,620,014 to 2,768,461
  (10,709,940 to 9,690,996); progress 215,818 to 157,616 (607,852 to 453,055); others unchanged.
  Root CHANGELOG.md per package is not excluded (Spec Kit use unverified).
  **Needs S-IL:** `extensions/progress/tests/test_extension.py:57` asserts `progress/docs/commands.md` ships;
  flip it to `assertNotIn` (IP8). `test_delegation.py` (181) and `test_eol_fingerprints.py` stay green.
- **AU6.** vendor.py already vendors an explicit file map (its tests/ skip applies only inside folder maps),
  so no code change: `vendor.lock.json` maps `skills/dev-tools/skills/user-manual/tests/test_build_manual.py`
  at dev-tools-v1.2.0; the synced copy adds the asset-leak test and `AllEditionsTests`; user-manual suite 44
  OK; `vendor.py check` passes. **Needs S-AU:** drop the `extensions/user-manual/ADAPTER.md:44` row (now vendored).

## S-WF

- W1 (`workflow.py`, `sanduq_hash.py`): `operation()` memo per CLI command (`main`, `claim`, `complete`); outside it nothing is cached. Memoised: origin URL (one read for `github_repository` and `normalized_remote`), shallowness, root commit, resolved root, git text attributes per path (`portable_files(..., attributes=)`), the source inventory. `_wrote()` drops what a runtime write can change: any `replace_file`/`write`, a write outside the operational folders drops the inventory, a `.gitattributes` or `.git/info` write drops attributes, a mutating `git()` call or the exclude-file write drops everything. `verify_checkpoint_identity` uses `merge-base --is-ancestor` on the recorded root first; `rev-list` runs only when that cannot answer. `next_stage` prefetches attributes for every receipt in one `check-attr`. Tests: `test_front_half_runtime.OperationCacheTests` (memo and invalidation, no `rev-list` on load, claim after Ready: one `ls-files`, three `check-attr`). `test_workflow` setUp copies one template `.git` per process instead of 5 git calls per test.
- Measured (benchmark_front_half, BEFORE from a `git archive HEAD` copy, both on this loaded machine): full git_subprocess 744 -> 316, claim avg 983 -> 436 ms (git 16.8 -> 7.5), complete avg 2000 -> 1238 ms (git 20.1 -> 8.4), command_ms 56.8 -> 30.2 s; lite 459 -> 226, claim 784 -> 357 ms, complete 1572 -> 736 ms. `test_workflow` 116.2 -> 55.8 s, `test_delegation` 168.8 -> 114.9 s. `source_fingerprints` counter stays 26/18: the benchmark counts calls, not the memoised computations (11 of 26 computed in full).
- W2/W3: Execute `reference_text` = `stage-execute.md` + `execution-assign.md` + `execution-report.md` (mode-neutral core) + `execute/lean.md` or `execute/orchestrator.md` + `execute/delegated-workers.md` (delegation on) + `reporting.md` (projection/refresh) or `execute/reporting-legacy.md`. The claim prints `reporting {mode, reason}` (progress_bridge.mode with detected or default host) and `execute_protocol`. Worker prohibitions stay in the core in every mode (plus one sentence on the Codex guard). Delegation and lean text moved from `delegation-and-decisions.md` (6,687 -> 2,280 B, still read per session) to `delegation.md` (read when a claim carries `delegation` or `environment`). Execute text: 34,819 B before (stage file + three files it told the model to read); after 20,154 (lean, no delegation, projection) to 29,559 (orchestrator, delegation, legacy). Review ids gone from the four headings; `worker_brief.py` parses the new headings.
- For S-REL: `benchmark_front_half.py` `STAGE_EXTRAS['execute']` and `POINTER_SET` still name the old static set, so its instruction_bytes no longer match what Execute loads, and `claim_stdout_bytes` (36,883 -> 81,316 full) now includes the composed Execute protocol (twice: claim and recovery claim) and `receipt_template`; count the protocol once, from the claim.
- W4: `claim` prints `receipt_template` (`Run.receipt_template`, next to `_check_stage_rules`); receipt-rules.md no longer asks for the decision ledger or required artifacts in inputs. Test: every stage completes from its template, and dropping any stage field is refused.
- W5: `progress_bridge.codex_hook_state(root, markers)` (shared trust and approval reading); doctor and `status` add `GUARD_HOOK_UNAPPROVED: <CODEX_HOOK_APPROVAL>` (the `/hooks` step) when Codex is installed and the guard is registered but not trusted and approved. Warning only. Tests: unapproved, untrusted, approved, Claude-only.
- W8: removed `delegation.ledger_state_trusted` and `progress_bridge.progress_at_least`.
- Descriptions: 13 workflow descriptions 3,241 -> 1,995 characters, all pass the benchmark checks (third person, what, "Use when", quoted trigger), frontmatter == extension.yml (single-quoted YAML).
- Tests changed, with reasons: `test_execution_protocol_b11` reads the core plus `execute/*.md` and `reporting.md` (rules moved between files, none dropped); `test_reporting_instructions` globs `references/**` and points at the moved legacy section; `rules-inventory.json` retargets two delegation rules to `delegation.md` and drops "and include it in the stage inputs" (W4); `test_worker_brief` oversize test sets the budget just below the brief (the protocol text it inlines got shorter).
- PM6 finding: both run, by code. `memory/extension.yml:47-53` registers `after_implement: speckit.memory.prepare` and `before_specify: speckit.memory.session`, both `optional: false`. Workflow never disables them: `reconcile.py:11` `OWNED` and doctor's owned list (`workflow.py` DUPLICATE_STAGE_OWNER check) have no `memory`. The managed overlays continue into the upstream command (`presets/workflow/commands/speckit.implement.md:7`, `speckit.specify.md:7`), and the pinned Spec Kit 8147943 `templates/commands/implement.md:179-185` ("Mandatory Post-Execution Hooks") and `specify.md:21-25` dispatch enabled mandatory hooks. Then `complete` runs `memory_handoff.handoff('execute')` (`workflow.py` `_accept_completion`), which calls `archive.py pending` and `policy` again and returns `MEMORY_ALREADY_QUEUED` when the hook queued first (`memory_handoff.py:113` "A hook or an earlier handoff already queued it"; `memory-lifecycle.md:12-13`; `test_memory_handoff.py:108-124`). memory-lifecycle.md:30 also runs `memory-handoff --transition session` before creating a feature, so a non-bind-only Specify runs `pending` twice. The effect is idempotent by design (no double queue); the cost is a duplicate prepare body read and model step plus 2-3 helper processes per transition. Not changed: the plan asked for one managed run to confirm, and the Workflow-side fix (add the two memory entries to `reconcile.py`'s managed rule and doctor's list) also changes the generated hooks page that `check_docs.py` derives from `reconcile.py`'s `OWNED`/`managed` AST, and makes doctor fail `DUPLICATE_STAGE_OWNER` on projects that install Memory after Workflow until `reconcile --apply`. Recommend it for the next round with that run.
