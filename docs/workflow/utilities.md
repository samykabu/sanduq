# Workflow utilities

This page is the reference for the five utility entry points that are not claimed stages, for switching the default host between Codex and Claude Code, and for the skill inventory that `doctor --project` reports. Each utility is a thin command backed by a script in [`extensions/workflow/scripts/`](../../extensions/workflow/scripts/workflow.py).

Back to the [Workflow guide](../../extensions/workflow/README.md).

## Utility entry points (B13)

Five entry points are not claimed stages; each is a thin command plus a
runtime script, listed alongside `init`/`continue`/`status`/`doctor`/
`reconcile` in the skill's Entry points section and documented in its own
`skills/workflow/references/<name>.md`:

- **`verify-affected`** (`scripts/verify_affected.py`) runs a feature's
  affected lanes locally instead of a full merge-tier run. It classifies the
  diff against `--base-ref` -- the actual working tree, including staged,
  unstaged and untracked paths, never only `base_ref..HEAD` -- through the
  existing `ci.gate.affected_command` hook, unions the result with any
  `--lane` names the feature always needs, and -- only when at least one
  lane is affected -- runs the project's new, optional `ci.gate.verify_command`
  (an argv list or command string, read `{"lanes": [...], "results_path":
  "<path>"}` on stdin, its whole process tree killed on timeout) into the
  same results.json shape CI itself would produce. No diff, or a diff every
  drifted path maps to no lane, reports `no_affected_lanes` and runs
  nothing, matching the gate's own lane-free-drift rule; a hook or a
  results file that fails is a clear, distinct error
  (`AFFECTED_COMMAND_UNSET`, `VERIFY_COMMAND_UNSET`, `VERIFY_COMMAND_FAILED`,
  `VERIFY_RESULTS_MISSING`/`_INVALID`), never a silent pass. This is never CI
  evidence: both the summary and results.json are stamped `"source":
  "local"`/`"ci_grade": false` and must never be recorded as a Verify
  receipt's `ci_evidence`.
- **`ci-report`** (`scripts/ci_report.py`) summarizes the last N runs of a
  workflow into a leg/lane/wall-clock-span table (`wall_clock_span_seconds`:
  earliest job start to latest job completion -- a span, not a computed
  dependency-aware critical path), fixed vs test time (fixed is the
  duration of jobs named by `--fixed-job`, repeatable; everything else
  counts as test time, and is zero without it, never guessed) and cancelled
  runs. Runs and jobs are both paginated past GitHub's 100-per-page cap and
  `--branch` is URL-encoded. It reads only through `ci_evidence.GhClient`
  (`gh api`), the same client Verify evidence already uses.
- **`gate-explain`** (`scripts/gate_explain.py`) runs the same check
  `ci_gate.py` runs and turns a `STALE_RECEIPT` failure into the failing
  stage, the gate's own `recovery_recipe`, and `evidence_only_eligible`:
  true only when every drifted path of that stage is already listed as
  that receipt's own `evidence` *and* is not also a declared input or a
  required core artifact (a path can be both, and amending it under
  `unchanged` would launder a real change). `--auto-fix --reason "<why>"
  --assessment unchanged|changed` (both required, no default) re-validates
  every eligible path against one loaded state snapshot before amending any
  of them (all-or-nothing), then runs `Run.amend` for exactly those paths
  and refuses (`GATE_EXPLAIN_NOT_EVIDENCE_ONLY`) for anything else; `amend`
  itself re-hashes the real file, so a path that is eligible by
  classification but missing on disk still refuses (`EVIDENCE_MISSING`)
  rather than being silently accepted. `--reason` is never invented by the
  script, and `--auto-fix` refuses outright inside a delegated worker or
  orchestrator process, matching `Run.amend`'s own guard.
- **`worker-brief`** (`scripts/worker_brief.py`) generates one task's brief
  (default `specs/<feature>/workflow/briefs/T###.md`, targeted at 3-5 KB --
  the contract excerpt is dropped first if that would push it over, and the
  result carries `oversized: true` if it is still over without one): the
  task's exact `tasks.md` line, owned paths (backtick-quoted file paths in
  its description), verbatim lines from `spec.md`/`plan.md`/
  `data-model.md`/`research.md` naming a requirement id
  (`[A-Z]{2,10}-\d+`, e.g. `EXEC-06`) the task references, a best-effort
  contract excerpt, and sections read live (never copied) from
  `execution-assign.md`/`execution-report.md`: the T0 turn-budget row for
  the task's class, the F1/F2 spawn-and-wait rules, the F3
  report-on-state-change rule, the T8 read-summary-first rule, the S6
  forbidden-commands rule (reusing `delegate_dispatch.py`'s own
  `NO_DISPATCHER_COMMANDS`/`QA_COLLECT_ADDENDUM`), and the T7 ten-line
  result template. The work type, when `--class` is omitted, is classified
  the same way delegation routing already does (`delegation.task_type`), so
  the brief and the delegated route agree; `--class` never accepts
  `qa_collect`, which is light-tier eligible only behind an explicit
  `[Collect]` task marker.
- **`apply-pending`** (`scripts/apply_pending.py`) applies
  `workflow/pending-artifact-updates.md` (F15): workers append a proposed
  wording change for a contract/data-model/research heading instead of
  editing it mid-Execute; a dry run (default) reports what would apply,
  `--apply` locates the named heading in the target file, replaces its body
  up to the next same-or-shallower heading, and marks the entry `applied`
  or `rejected` (`ANCHOR_NOT_FOUND`, `TARGET_FILE_MISSING`,
  `PENDING_TARGET_ABSOLUTE_REFUSED`, `PENDING_TARGET_NOT_ALLOWED`) so
  re-running is safe. Every target is confined and resolved (contained;
  absolute paths, `..` and symlink escapes refused) to
  `<feature>/contracts/**`, `data-model.md` or `research.md`, and the
  pending file itself is contained the same way. Judging whether the
  proposed wording still matches shipped code is the calling agent's job,
  never the script's. `--apply` refuses inside a delegated worker or
  orchestrator process and while a claim is active. When an applied change
  touches a path an already-passed receipt fingerprinted, the result's
  `stale` list names the stage and its `recovery_recipe` (or, if the check
  itself fails, `stale: null` with a `stale_error`, never a bare `[]`);
  this script never re-validates a stage itself.

## Switching hosts

A project can have several Spec Kit integrations installed (for example `codex` and
`claude`, listed in `.specify/integration.json` `installed_integrations`), but Spec Kit
registers extension commands and skills only for the default one. Two things follow:

- `specify extension add --force`, which every install and upgrade runs, removes the
  reinstalled extension's skills from every other host folder.
- `specify integration use <host>` regenerates the new default's skills from upstream
  sources, which replaces Sanduq's managed aliases (`speckit-superpowers-bridge`,
  `speckit-scope`) with the upstream content, including the unguarded Bridge executor.

`install.py --apply` (and so `upgrade.py --apply`) therefore re-registers every
installed Codex or Claude host after the packages change: it runs
`specify integration use <other>` for each other host, then
`specify integration use <default>`, and puts `.specify/integration.json` and
`.specify/init-options.json` back byte for byte. It then writes the managed aliases into
every host folder and checks that each host has every command of the installed Sanduq
extensions, the same Sanduq preset overlays and the packaged aliases. Any gap
(`HOST_SKILLS_MISSING`, `HOST_OVERLAY_MISSING`, `ALIAS_NOT_RESTORED`) rolls the install
back. A single-host project runs no extra commands.

An existing alias file is judged by its whole content (CRLF normalised to LF), never by
its frontmatter alone, and by what it held before the transaction, so content Spec Kit
wrote during the transaction is replaced whenever the earlier content is. It is replaced
without asking only when its SHA-256 is one of:

- the packaged alias;
- an accepted legacy alias hash (`assets/legacy-*-alias-hashes.json`);
- the hash `.specify/workflow/install-lock.json` `aliases` recorded for that path;
- exactly the file Spec Kit generates for that command now. Sanduq copies `.specify`
  into an empty temporary project, runs `specify integration use <host>` there and
  compares the full hash of the alias it renders, so the upstream Bridge a bare
  `specify integration use` left behind is replaced. The project is not touched, and
  the render runs only when an alias matches none of the hashes above.

Anything else, such as local instructions added under unchanged upstream frontmatter, is
a local edit: `install.py`, `upgrade.py` and `workflow.py host --use` refuse with
`ALIAS_HAS_LOCAL_EDITS: <path>` before anything changes, and the previews list it. Move
the customization into Sanduq, or pass `--replace-unrecognized-aliases` to replace it
anyway: the file is first copied to `unrecognized-aliases/<path>` in that run's backup
folder (`.specify/workflow/backups/installs/<id>` or `.../hosts/<id>`), and the result
lists each path with its backup under `replaced_unrecognized_aliases`.

Change the default host with the supported command, never with a bare
`specify integration use`:

```text
python .specify/extensions/workflow/scripts/workflow.py host                       # status
python .specify/extensions/workflow/scripts/workflow.py host --use claude --preview
python .specify/extensions/workflow/scripts/workflow.py host --use claude
```

`host` with no option reports the default, the installed hosts, any missing skills or
aliases and the current dependency digest. `--use codex|claude` then:

1. refuses, without changing anything, when the host is not installed
   (`HOST_NOT_INSTALLED`), a stage claim is active, a legacy Bridge handoff is
   executing, an alias has local edits, an upgrade is running, or the delegation policy
   cannot route to the new host (below);
2. under the install and dispatch locks, snapshots the managed files and runs
   `specify integration use <host>`;
3. re-registers any other installed host that is missing managed skills (the repair
   for a project an earlier upgrade left incomplete; `--use <current default>` is
   therefore also the repair command doctor names);
4. restores the managed aliases in every host folder, reconciles the managed hooks and,
   when delegation is enabled, installs the delegate-task skill for the new host at
   `delegation.install_scope`;
5. verifies every host as the installer does, runs doctor and rolls everything back
   (`HOST_SWITCH_ROLLED_BACK`) when a check fails or doctor reports an error it did not
   report before the switch;
6. records the new host, aliases and digest in `.specify/workflow/install-lock.json`.

The result reports `dependency_digest.before`, `.after` and `.changed`. The digest
fingerprints `.specify/integration.json` and `.specify/init-options.json`, so a real
switch always changes it, and `checkpoints_to_migrate` lists every feature checkpoint
whose recorded digest no longer matches, with its branch and the exact commands
(`git switch <branch>`, `workflow.py migrate --feature <feature> --preview`, then
`migrate --feature <feature> --reason "Host switched from <old> to <new>"`);
`already_stale: true` marks one that did not match the digest before the switch either
and so needed `migrate` regardless. Until a
checkpoint is migrated, `claim` refuses it with `DEPENDENCY_CHANGED`.

The delegation check reads `.specify/workflow.yml` and never rewrites it. With
delegation enabled, `delegation.required_changes` lists what must change before the
switch can apply: a missing `delegation.models.<host>` tier, a tier model that names
the other host's model family (for example a `gpt-*` model under `models.claude`), a
route that follows the selected host but pins the other host's model, or an unknown
tier. `delegation.notes` lists routes that pin a harness explicitly and so keep
delegating to it after the switch. With delegation disabled the same findings are
`advisories` and do not block.

`--preview` changes nothing, runs no command and returns the same plan: the commands it
would run, the skills each host lacks now, the aliases it would restore, the delegation
findings, whether the digest will change and the checkpoints that will need `migrate`,
plus `blockers` and `can_apply`. The switch does not restore templates or scripts that
`specify integration use` refreshes outside the managed files; without `--force` Spec
Kit keeps customized ones. Doctor warns (`HOST_SKILLS_MISSING: <other host>`) when a
host other than the default has lost managed skills, with the repair command.

## Skill inventory (doctor)

`doctor --project` reports a `skill_inventory` block (never on a plain `doctor`,
including a `migrate`/`upgrade`-triggered one, so those never pay its cost; a scan
failure is caught and turned into a `SKILL_INVENTORY_UNAVAILABLE` warning, never a
doctor failure). It is reported **per host session load**, not one cross-host sum:
a Claude session and a Codex session read different, overlapping directories, and
summing them double-counts every skill Sanduq installs into both.

- `claude` loads `roots.claude_home` (`~/.claude/skills`), `roots.claude_project`
  (`.claude/skills`), and `roots.claude_plugins` — every installed, enabled
  plugin's skills, read only from `~/.claude/plugins/installed_plugins.json`'s
  recorded `installPath` per plugin (the one place Claude Code itself records
  which installed copy is live; the wider `plugins/cache` and
  `plugins/marketplaces` trees hold every version ever fetched, including a
  `.trash` of superseded ones, and are never scanned directly). A missing or
  unparseable manifest is reported as `"counted": false` with a `reason`, rather
  than guessed at from the cache. Three checks apply per manifest entry before it
  is scanned: a `project`- or `local`-scoped entry only counts when its
  `projectPath` resolves to this project (a `user`-scoped or unmarked entry
  always counts); a plugin turned off in `enabledPlugins` is skipped (checked in
  `~/.claude/settings.json`, then the project's own `.claude/settings.json`,
  then its `.claude/settings.local.json` — each later file's explicit
  true/false wins over the one before it); and its `installPath` must resolve,
  following symlinks, to somewhere inside `~/.claude/plugins` itself, or it is
  rejected and listed under `claude_plugins.skipped_install_paths` (a UNC path,
  `\\host\share` or `//host/share`, is rejected by its literal text before any
  filesystem access at all, since resolving or stat-ing an unreachable network
  path can hang or error slowly).
- `codex` loads `roots.codex_home` (`$CODEX_HOME/skills`, or `~/.codex/skills`
  when that real Codex CLI environment variable — never renamed — is unset),
  `roots.agents_home` (`~/.agents/skills`), and `roots.agents_project`
  (`.agents/skills`). `$CODEX_HOME/skills` is confirmed live, not legacy:
  checked 2026-09-29 against the installed Codex CLI (codex-cli 0.159.0), whose
  compiled binary (`@openai/codex-win32-x64` vendor `codex.exe`) embeds the
  literal default-expansion `"${CODEX_HOME:-$HOME/.codex}/skills"` next to its
  `SkillsList` client request, and the directory on this machine holds real
  per-skill folders a session actually reads (plus a `.system` subfolder of
  bundled skills this flat, one-level scan does not descend into, same as
  every other root here).

`roots` always gives the full per-root numbers (`skill_count`, total and max
frontmatter `description:` bytes, total `SKILL.md` bytes; `claude_plugins` adds
`counted`/`reason`/`skipped_install_paths`). `hosts.claude` and `hosts.codex`
each give `combined` (summed over exactly that host's own roots) and
`duplicates` — a skill name repeated *within* that host's own roots (home vs.
project vs., for claude, a plugin). `mirrors` lists a name shared between a
claude root and a codex root separately: Sanduq itself installs the same
command skill into both `.claude/skills` and `.agents/skills` at every level it
manages, so that overlap is an expected mirror, not a duplicate, and never
inflates either host's `combined`.

Every root tolerates being missing, an unreadable or malformed `SKILL.md` (no
frontmatter, or a `description` that is not a string, counts as 0 bytes, never an
error), and a symlink or junction skill folder (resolved and counted once, never
followed recursively, so a cycle cannot loop). The home root resolves through
`Path.home()`, overridable with `SANDUQ_SKILLS_HOME` (tests must set it rather
than touch the real machine's home).

Doctor warns `SKILL_INVENTORY_LARGE` (non-blocking) per host whose own combined
skill count exceeds 200, or combined description bytes exceed 40 KiB (40960); a
project heavy on one host and light on the other gets exactly one warning, not
zero or two by averaging. Frontmatter `description:` text is what a host loads
into every session only to list what is available, before any skill is invoked,
so its combined size approximates a fixed per-session token cost. Measured source
for the defaults (`workflow.py doctor --project`, read-only, against a large pilot
project, 2026-09-29): one project's own skill root is 86 skills / 10578 bytes on both
hosts (`roots.claude_project` and `roots.agents_project`); 200 skills / 40 KiB is
roughly double that count and four times the bytes, giving headroom for home and
plugin skills before flagging. On that same measurement the pilot project's actual per-host
session load was already far past both — claude 379 skills / 144351 bytes, codex
385 skills / 149763 bytes, driven by an unpruned `~/.claude/skills` and
`~/.agents/skills` (273 and 272 skills) — which is exactly the kind of
accumulation across marketplaces, plugins and a project's own skills/ that C4
(skill pruning) exists to catch; a claim of "a few dozen skills" for a project's
own root does not hold once a project of that size is measured. Override
either key under `policy['skills']['inventory_thresholds']` (`skill_count`,
`description_bytes`; positive integers only) in `.specify/workflow.yml` — applied
independently to each host's own combined total, not to a cross-host sum.
Deciding what to prune, including any "never invoked" signal, needs a telemetry
source and a window neither doctor nor this inventory has; that judgement (and
the pruning pass itself) is owner-only and out of this package's scope.
