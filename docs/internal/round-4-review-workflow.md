# Round 4 review: Workflow (stream R1)

Read-only review of `extensions/workflow` 1.16.0 and `presets/workflow` on `feat/round-4` (worktree
`sanduq-round4`). Line numbers are for the files named. Nothing in the tree was changed. Scratch scripts and
outputs are in the R1 scratchpad, not committed.

Sources:

- `benchmark_front_half.py --tier full` and `--tier lite` on this worktree.
- A cProfile run of the lite benchmark.
- Targeted `python -m unittest <module>` timings.
- Two reproduction scripts (W10, W11).
- Node probe timings.

**Measurement caveat.** This machine was about twice as slow as in round 3. `test_workflow` took 117 s (round
3 after: 55.8 s), and benchmark `command_ms` was 59.5 s (round 3 after: 24.2 s). The work counts did not
change: 316 git subprocesses, 459 `fingerprint_files` calls and 26 `source_fingerprints` calls. So compare
counts across rounds, not milliseconds. The fixture lives in `%TEMP%`, where the first read of each new file
costs about 2 ms (antivirus scanning). That inflates the fixture's source-inventory time: 2.5 s per inventory,
against 0.16 s to read and hash the repo's own 1,004 files warm.

Round 3 used W1 to W9. The new ids start at W10. W6 and W9 keep their round-3 ids.

## Summary

- **Three defects, all verified.**
  - W10: `reconcile` fails for good after any extension re-registers a hook it owns. Both `--apply` and the
    restore step that Workflow's installer runs first (`install.py:829-830`) fail. A reproduction is below.
  - W11: `sync-amend` and `migrate` refuse a legitimate legacy receipt when the committed state file has CRLF
    line endings.
  - W12: Scope's remote regex rejects three remote forms that Workflow accepts.
- **D3 depends on W10.** Memory's installer re-adds its hooks with `enabled: true`
  (`memory/scripts/install.py:96-114`). Spec Kit does the same on update (`register_hooks`). So once Workflow
  owns Memory's hooks, every Memory re-init would trigger W10.
- **The largest runtime lever left is W6.** A delegated claim spends 4.2 to 4.4 s on 4 node processes, measured
  here (`node delegate.mjs doctor` alone takes 3.1 s). With about 15 delegated claims, that is about 60 s per
  full feature.
- **Every claim hashes the installed packages again.** `package_digest` reads about 417 files (4.3 MB) per claim
  in a real install: 320 to 347 ms, against 14 to 29 ms to stat them (W18).
- **The prose asks for a Memory session handoff "before claiming a stage"** (`dispatcher-operations.md:126`).
  Taken literally, that is one extra model tool call per claim, 17 per full feature, even without Memory. W14
  moves it into the runtime, and that is also how Workflow "owns" `session` under D3.
- **Slow tests.** `test_sync_binding` (22 tests) takes 163 s and `test_memory_handoff` (17 tests) takes 114 s.
  `test_progress_shim` (68 tests, 114 s) goes away with D5.

## 1. Decided items: design input

### D1. `workflow.finalize` and `workflow.status` descriptions

Current text (`extension.yml:38-43`, mirrored in `commands/finalize.md:2` and `commands/status.md:2`):
finalize says `"open the PR"`, which is also `pr.generate`'s trigger (`pr/extension.yml:37`); status says
"checking progress", which overlaps `progress.status`.

Proposed (both pass `benchmark_instructions.describe()`: third person, what, when, quoted trigger, under 1,024):

- finalize (237 chars, was 152): `Runs the managed Ready and PR stages of an issue-bound feature: readiness
  checks, its one pull request, then the merge check. Use when every earlier stage has passed in a project
  with .specify/workflow.yml, or for "finalize the feature".`
- status (281 chars, was 160): `Prints the workflow record of one issue-bound feature: stage, active claim,
  receipts, blockers and evidence freshness; read-only. Use when asked which stage a feature is in or what
  blocks it, or for "where is this feature". For the live progress report use speckit.progress.status.`

Workflow's catalog grows from 1,995 to about 2,201 characters. R6 checks the 8,000-character budget.

Edit both copies: `extension.yml` and the command frontmatter. No test checks that they agree. Add one to
`test_skill_split.py`: for every `provides.commands` entry, the frontmatter `description` equals the manifest
text. The PR side belongs to R4: `pr.generate` should say it is the standalone route, and that a managed
project uses `speckit.workflow.finalize`. W21 below makes the status output carry Progress's line, so the two
commands stay distinct.

### D3. Workflow owns `speckit.memory.session` and `speckit.memory.prepare` in managed projects

What happens today, from the code:

- Both hooks are mandatory and enabled. The managed overlays continue into upstream Implement and Specify,
  which dispatch enabled mandatory hooks. `complete` for Execute then runs `memory_handoff.handoff('execute')`
  (`workflow.py:3806-3812`). That call reruns `archive.py pending` and `policy`, and returns
  `MEMORY_ALREADY_QUEUED` when the hook queued first (`memory_handoff.py:111-113`).
- Neither hook is in `OWNED` (`reconcile.py:11`) or in doctor's list (`workflow.py:1466`).

Changes:

1. **`reconcile.py`.** Move the predicate at line 35 into `def managed_hook(event, hook):`. Keep the local
   assignment `managed = (...)`, because `check_docs.workflow_rules` finds it with `ast.walk`
   (`check_docs.py:88-92`). Add `or (hook.get('extension') == 'memory' and hook.get('command') in
   ('speckit.memory.session', 'speckit.memory.prepare'))` with an inline literal tuple: `check_docs` evaluates
   the expression with only `OWNED` in globals, so a new constant would raise a NameError. Drop the redundant
   `project and after_tasks` clause, since `project` is already in `OWNED`. `impact` stays a hook. Land W10 in
   the same change.
2. **Doctor's owned list.** `workflow.py:1466` duplicates the rule inline. Replace it with a lazy
   `from reconcile import managed_hook` inside `doctor`. It must be lazy because reconcile imports workflow at
   module level. Make the message `DUPLICATE_STAGE_OWNER: <event:command>; run "python
   .specify/extensions/workflow/scripts/reconcile.py --apply"`. That also removes the second copy of the rule
   (W13).
3. **Hooks page.** Run `check_docs.py --write`. The two Memory rows become "disabled; the dispatcher owns this
   step". Also edit the hand-written sentence at `docs/reference/hooks.md:17` ("Memory's hooks ... stay as they
   are") to "Memory's impact hook".
4. **Memory handoff.** Change `memory-lifecycle.md:12-13`: replace "An upstream hook may already have
   queued..." with "In a managed project the prepare hook is disabled; this handoff queues". The `execute`
   transition stays as it is.
   - Behaviour change: in managed projects the queue uses `policy.default_checks` (`memory_handoff.py:114`)
     instead of the checks the model picked in the hook. `queue` still checks coverage
     (`archive.py:169,174`). When none fit, the existing `speckit.memory.prepare` action comes back.
   - The hook's early `archive.py preflight` (`memory/commands/prepare.md:15-17`) no longer runs at Implement.
     Preflight still runs at verify and archive (`archive.py:465,687`).
5. **Session ownership.** Do W14, so the runtime, not prose, replaces the `before_specify` session hook.
6. **Tests.**
   - `test_reconcile`: the two Memory hooks are disabled, `impact` is kept, and restore brings both back.
   - Doctor: an enabled `speckit.memory.session` reports `DUPLICATE_STAGE_OWNER`, and an enabled `impact` does
     not.
   - W10's tests.
   - `test_check_docs` stays green after `--write`.
7. **Consumer impact.** Two `enabled: false` flags in `.specify/extensions.yml`, journaled in
   `integration-backup.json`. `upgrade.py` runs install, which runs `reconcile --apply`. A project that installs
   Memory after Workflow already needs `migrate`, because `package_digest` changes and `DEPENDENCY_CHANGED`
   follows. Now it also needs `reconcile --apply`, and doctor names that command. No policy key, state path or
   lock change.

**The required confirmation run.** Two parts. Both use real Spec Kit at the CI pin (8147943).

1. **Deterministic check, about 10 minutes, no model.** In a `smoke_install.py` fixture (managed, Claude), run
   `specify extension add --dev <memory package>` and Memory's `install.py`. Show: doctor is green and
   `reconcile.py` (dry run) reports no Memory change; `.specify/extensions.yml` holds `session` and `prepare`
   with `enabled: true, optional: false`; the rendered `speckit-implement` and `speckit-specify` skills carry
   the upstream mandatory-hook dispatch sections. Then, with automatic mode enabled (as
   `test_memory_handoff.enable` does), run `archive.py queue --spec specs/<f> --check <c>` as the hook would,
   then `workflow.py memory-handoff --transition execute --feature specs/<f>`: expect `MEMORY_ALREADY_QUEUED`.
2. **One live managed run** (lite tier, Claude Code, Memory in its default disabled mode), from
   `speckit.workflow.scope` to Execute `complete`. Count in the transcript (`~/.claude/projects/<slug>/*.jsonl`)
   the Skill calls to `speckit-memory-session` and `speckit-memory-prepare`, and the Bash calls with
   `archive.py pending` and `memory-handoff`. A hook-driven `pending` plus a handoff for the same transition
   shows the duplication; the handoff file under `.specify/workflow/runtime/memory-handoffs/` records its own
   `pending`. Disabled mode is enough: the hook still reads the prepare body (1,680 B). Repeat after D3.

### D4. One shared remote normaliser (Workflow side)

- **Where.** Put it in `extensions/scripts/shared/sanduq_remote.py`, injected by `package.py` into `workflow`
  and `project`. This is the same mechanism as `check_inputs.py` and `deps.py` (`package.py:65-84`). Its
  contents:
  - `strip_dotgit`, `normalize_path_remote`, `normalize_remote_url`. This is the body of `workflow.py:360-441`,
    with the rationale docstring.
  - `github_slug(url) -> 'owner/repo' | None`. This is the regex at `workflow.py:329` and
    `project_sync.py:117`.
  - `same_github_repository`.
- **Workflow imports.** `workflow.py` imports these names with the fallback pattern from `execution_tools.py:32-36`
  (`try: import sanduq_remote; except ModuleNotFoundError:` add `parents[2]/'scripts'/'shared'`). It keeps
  `normalize_remote_url` and `same_github_repository` as module names. Scope's `workflow_policy`, the tests and
  `memory_handoff` (via `SimpleNamespace(**globals())`) use them through `workflow`. `github_repository` becomes
  `require(github_slug(origin_url(root)) ...)` with the same error codes. Delete `_strip_dotgit` and
  `_normalize_path_remote` from `workflow.py`. Only these lines use them.
- **Project side (R4).** `project_sync.py:65-119` imports the module with the same fallback and drops `WORKFLOW`,
  the `exec_module` and the `sys.path` insert. That saves 275 to 297 ms per sync (measured exec of
  `workflow.py`), about 1.7 s for 6 syncs per feature. It also removes a behaviour that depended on whichever
  Workflow version is installed.
- **Scope (R2, W12).** `scope.py:525-528` should use `github_slug` too. The module would need injecting into
  `scope` as well.
- **Tests.**
  - `test_checkpoint_identity` keeps its 30-odd remote-form cases through `w.normalize_remote_url`.
  - Replace the 9-remote equality test in `test_project_sync_summary.py` with one package test: the archives
    for `workflow` and `project` (and `scope`, if adopted) carry a byte-identical `sanduq_remote.py`.
  - Add a source-tree import test for each consumer.
- **Risk.** Low. Installed copies can skew between releases, as with `deps.py`.

### D5. Retire `scripts/progress_shim.py`

- **Callers.** The only one is `progress.py:467-473`. No package, CI, rules-inventory or other script names it
  (grep over `extensions/`, `presets/`, `.github/`).
- **New behaviour.** When `progress_bridge.script(root)` finds an enabled Progress (`progress_bridge.py:62-71`),
  `progress.py` writes nothing and exits 2 (today's `COMPAT_EXIT`). It prints one line in the `--summary` form
  (`error PROGRESS_INSTALLED: ...`), naming the replacement:

  | Legacy call | Replacement |
  | --- | --- |
  | `init` | `progress init` |
  | `task` | check the box in `tasks.md` |
  | `usage` | none (hooks and delegate results record it) |
  | `sync` | `progress refresh` |
  | `phase` | none |
  | `pr` | `progress note "PR open: <url>"` |
  | `event` | `progress note "<text>"` |

  Without Progress, the legacy reporter runs unchanged. `usage.py` stays, because the legacy reporter uses it.
- **Text changes.**
  - `reporting.md:38`: "it exits 2 and names the Progress verb; do not retry".
  - `reporting.md:30`: drop "the `progress.py` forwarder adds it to the lanes it creates".
  - `execute/reporting-legacy.md:9`, `README.md:187`, `docs/extensions/progress.md:61` (it says existing prompts
    keep working; they no longer do).
  - A CHANGELOG Migration block.
- **Tests.**
  - Delete `test_progress_shim.py`: 874 lines, 68 tests, 114 s on this machine.
  - Add to `test_progress.py`, with `SANDUQ_PROGRESS_SCRIPT` set and the registry enabled: each legacy
    subcommand exits 2, names its replacement, and writes no `state.json` or `index.html`; `--summary` prints
    exactly one line.
  - The existing no-Progress tests stay.
- **Who notices.** Only a session that runs a legacy call after Progress was installed. The Execute claim
  reprints the protocol when the mode changes (`workflow.py:3478-3486`).
- **Cross-stream (R5).** Progress's `attempt record` verb and the "legacy supplemental attempts" path
  (`progress/scripts/progress.py:657`, `sanduq_progress/model.py:466`) lose their only caller. Keep them for one
  window, because older Workflow releases still call them.

## 2. Defects (fix first)

### W10. Reconcile fails after a hook re-registration

- **What.** `_reconcile` refuses any owned hook that differs from its journaled `managed` copy
  (`reconcile.py:45-48`). Spec Kit's `register_hooks` re-adds an extension's entries with `enabled: True` on
  `extension add` and `update` (spec-kit `extensions/__init__.py:3089-3189`), and Memory's installer does the
  same (`memory/scripts/install.py:96-114`). After that, `reconcile --apply` raises
  `HOOK_CHANGED_SINCE_RECONCILE`, and so does the restore step Workflow's installer runs first
  (`install.py:829-830`), so install, upgrade and `host --use` (`hosts.py:562`) are blocked. Doctor keeps
  reporting `DUPLICATE_STAGE_OWNER` and points to reconcile. No doc gives a way out; no test covers the error.
- **Reproduction.** Scratchpad `repro_reconcile.py`, built on the `test_reconcile` fixture. It writes the
  Project hook enabled, runs `reconcile(apply=True)`, writes the same enabled hook again as Spec Kit would, and
  reconciles again. Output: `apply: HOOK_CHANGED_SINCE_RECONCILE: after_tasks:speckit.project.sync` and
  `restore: HOOK_CHANGED_SINCE_RECONCILE: ...`.
- **Fix (S).** If the current entry is enabled, treat it as a fresh registration: store it as the new
  `original` and disable it again. On restore, an enabled entry is the extension's own current registration,
  so leave it and drop its journal record. Keep refusing an entry that is still disabled but was edited (the
  user-edit case `test_reconcile_refuses_to_overwrite_later_user_hook_edit` pins).
- **Tests.** Re-registration then apply succeeds and disables. Restore after a re-registration keeps the
  extension's entry. A disabled, edited entry is still refused.
- **Risk.** Low. A user who re-enabled an owned hook on purpose gets it disabled again, which is what doctor
  already asks for.

### W11. `sync-amend` and `migrate` refuse CRLF state-file history

- **What.** `recorded_sync_fields` (`workflow.py:1093-1111`) compares the recorded hash with the portable hash
  of the working tree (CRLF folded to LF, `sanduq_hash.py:45-49`), but hashes raw `git show` bytes for history
  (`:1103`). Project writes its state file with `write_text` (`project_sync.py:422`), which writes CRLF on
  Windows; with `core.autocrlf=false` and no text attribute the blob keeps CRLF. So the usual sync-amend case,
  a status change after the receipt, cannot find the recorded bytes and refuses.
- **Reproduction.** Scratchpad `repro_sync_crlf.py`. With LF: `fields: ['status']`. With CRLF:
  `SYNC_BINDING_MISMATCH: no version of .specify/project-sync-state.json matches the recorded hash`.
- **Fix (S).** Hash `portable_content(label, blob, attribute)`, the same normalisation the receipt used. While
  there, replace the up to 51 `git show` processes with one `git log -n 50 --format=%H -- <label>` and one
  `git cat-file --batch`. Project could also write with `newline='\n'` (R4).
- **Test.** The CRLF case in `test_sync_binding`.
- **Consumer impact.** None. It affects only pre-1.16.0 receipts on Windows checkouts.

### W12. Scope rejects remotes that Workflow accepts (R2's file)

- **What.** `scope.py:526` uses `github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$`. Checked against
  `workflow.normalize_remote_url`:

  | Remote | Scope | Workflow |
  | --- | --- | --- |
  | `ssh://git@github.com:22/acme/app.git` | rejected | `acme/app` |
  | `https://GitHub.com/acme/app` | rejected | `acme/app` |
  | `https://github.com/acme/app/` | rejected | `acme/app` |

  `workflow start` accepts these remotes, and Scope then fails with "A GitHub origin remote is required".
- **Fix.** Use D4's `github_slug`. S, low risk.

## 3. Options

Bases: one full-tier feature has 17 claims and 22 completes (benchmark). It has about 15 non-coordinator
claims when delegation is on (round 3). "Tool call" means one model round-trip of about 200 to 400 tokens.

| Id | What | Evidence | Saving (base) | Effort | Risk | Mark |
| --- | --- | --- | --- | --- | --- | --- |
| W10 | Reconcile accepts re-registered hooks | §2 | unblocks install and upgrade | S | low | fix-first |
| W11 | Portable hash for sync-amend history; one git process | §2 | removes a false refusal | S | low | fix-first |
| W12 | Scope uses the shared slug | §2 | 3 remote forms work | S | low | fix-first (R2) |
| W13 | One `managed_hook` predicate for reconcile and doctor (D3 step 1-2) | `reconcile.py:35` vs `workflow.py:1466` | one rule, not two | S | low | do |
| W14 | Runtime runs the Memory session handoff | below | up to 17 tool calls per feature | S-M | low-med | do |
| W15 | D4 shared `sanduq_remote.py` | §1 | 40 duplicate lines; about 0.28 s per sync | S | low | do |
| W16 | D5 retire the forwarder | §1 | 16 KB code, 874 test lines, 114 s of tests | S | low | do |
| W17 | D1 descriptions and frontmatter test | §1 | routing; +206 catalog chars | S | low | do |
| W6 | Cache the delegation health probe | below | about 4.2 s per delegated claim, about 60 s per feature | S | low | do |
| W18 | Stat-keyed hash cache for `package_digest` | below | about 0.3 s per claim, about 5 s per feature | M | low | do |
| W19 | Resolve each directory once in `canonical_path` | below | 0.1-0.2 s per 1k paths per command | S | med | do |
| W20 | `recovery_recipe` prints `sync-amend`; move the 1.16.0 text out of the session set | below | 1.6 KB per session | S | low | do |
| W21 | `status` includes Progress's one line | below | 1 tool call per status | S | low | do |
| W22 | Lifecycle snapshot per class in slow tests | below | 50-70% of 277 s here | M | low | do |
| W9 | Split `workflow.py` (phases 1-2) | below | maintainer reads; no runtime gain | L | med | do last; phase 3 defer |
| W23 | Cleanup leftovers | below | small | S | low | do (S parts) |
| W24 | Hash cache for the source inventory | below | 0.16-2.5 s per post-Verify command | M | med | defer |
| W25 | Index the foreign active claim | `workflow.py:3387-3388` | about 50 ms per claim at 100 features | S | med | drop |
| W26 | Merge git and sha256 helpers | round 3 W8 list | small | S | low | drop |
| W27 | Drop `repo_path` from the checkpoint | `workflow.py:3272-3275` | 1 field | S | med | defer |

### W13. One hook-ownership rule

- **What.** Two copies of the predicate exist: `reconcile.py:35` and `workflow.py:1466`, which also writes
  `OWNED` out by hand. Use `reconcile.managed_hook` in both, as in D3 steps 1-2.
- **Tests.** A table test: for each `(event, hook)` in the manifests, reconcile's decision equals doctor's.
- **Migration.** None.

### W14. The runtime owns the Memory session handoff

- **What.** `dispatcher-operations.md:126-129` says "Before creating a feature or claiming a stage, run
  `workflow.py memory-handoff --transition session`": one model tool call per claim, even without Memory
  (then it returns `MEMORY_DEPENDENCY_MISSING_OR_DISABLED`, `memory_handoff.py:67-69`). Instead, call
  `memory_handoff.handoff(w, root, 'session')` in `Run.start`, in `claim` at `scope` and `specify`, and when
  `usage.session_id` differs from the last claim's (Memory's "session start", `memory/commands/session.md:7`).
  Refuse the claim on `MEMORY_ACTIVE_RECOVERY_REQUIRED` and `MEMORY_WRITER_OR_NUMBER_GUARD_BLOCKED`, where the
  hook's `pending --gate` stops (`session.md:20-23`). Print `memory_handoff` in the claim only for `dispatch` or
  `blocked`. The handoff takes `dispatch.lock` (`memory_handoff.py:65`), which `claim` already holds
  (`workflow.py:3383`), and `locked` is not re-entrant (`:2460-2471`): add a `lock=False` parameter. Shorten the
  prose to "honor the claim's `memory_handoff`".
- **Saving.** Up to 17 tool calls per full feature (with or without Memory). With Memory enabled, 2 helper
  processes on 2 or 3 claims.
- **Risk.** The claim can now refuse on a Memory blocker. The mandatory hook does the same today.
- **Tests.**
  - The Specify claim with an active run refuses.
  - A claim without Memory starts no helper.
  - A new `session_id` triggers one handoff, and the same `session_id` does not.

### W6. Cache the delegation health probe (round 3's deferred item, now measured)

- **What.** `claim` runs `delegation.doctor(install=True)` on every non-coordinator stage
  (`workflow.py:3419-3426`): `node --version`, `node --check`, `delegate.mjs contract` and `delegate.mjs doctor`,
  4 processes and 4.22-4.38 s measured (`doctor` alone 3.1 s; it probes 5 CLIs). Store a green result in
  `.specify/workflow/runtime/delegation-health.json`, keyed by the driver path and the sha256 of `SKILL_FILES`,
  the `shutil.which` path and stat of `node`, `codex` and `claude`, the host and `install_scope`. Reuse it for
  3,600 s (doctor's 600 s is shorter than one model stage). A miss, a red result or a `delegate_dispatch` driver
  error (which deletes the file) probes again; `annotate_tasks` still runs; the explicit `doctor` always probes.
- **Saving.** About 4 s per delegated claim, about 60 s per full feature (base: 15 claims).
- **Risk.** A CLI that loses its login within the hour is found at `delegate_dispatch.start`, not at claim.
- **Tests.**
  - A second claim makes no node call.
  - A changed driver hash or a changed `node` stat probes again.
  - A red result is not cached.

### W18. Stat-keyed hash cache for `package_digest`

- **What.** `claim` recomputes `package_digest` every time (`workflow.py:3389`): about 417 `.py`, `.md` and
  `.yml` files (4.3 MB) in a nine-extension install, 320-347 ms through `fingerprint_files` against 14-29 ms to
  stat them (measured). Keep `{label: [size, mtime_ns, sha256]}` in `.specify/workflow/runtime/hash-cache.json`
  (git-excluded) and reuse a hash only when size and mtime match and the mtime is over 2 s old ("racy git"
  rule). Only `package_digest` uses it; receipts are unchanged; CI has no cache and gets the same digest.
- **Saving.** About 0.3 s per claim, about 5 s per feature.
- **Risk.** A local edit that keeps both size and mtime evades detection. Such an edit needs a deliberate
  `touch -d`, and the same local user can edit the checkpoint anyway.
- **Tests.**
  - A hit makes no read.
  - A size or mtime change reads.
  - A file with a fresh mtime is not cached.
  - The digest equals the uncached digest.

### W19. Resolve each directory once

- **What.** `canonical_path` calls `inside`, which runs `Path.resolve()` per label (`workflow.py:215-239`):
  7,511 resolves and 5.0 s of 38 s CLI time in the lite profile; warm, 1,004 repo paths take 0.18-0.2 s, more
  than reading and hashing them (0.16 s). Memoise the resolved parent directory per operation and `lstat` the
  leaf; resolve fully only when the leaf is a link. Same result: a path escapes only through a link in the leaf
  or an ancestor.
- **Tests.**
  - A symlinked leaf outside the root is refused.
  - A symlinked directory is refused.
  - A Windows junction is refused (`delegation.is_junction` exists).
- **Risk.** Medium, because this is a security check. Hence the tests.

### W20. Move the 1.16.0 sync text out of the per-session reading

- **What.** `dispatcher-operations.md`, read once per session (`SKILL.ext.md:8-9`), grew from 5,455 B (round 3
  after) to 8,152 B. Two blocks are migration and recovery text: "Receipts fingerprint..." (779 B) and the
  "receipt recorded before 1.16.0" bullet (816 B). `recovery_recipe` (`workflow.py:2185-2228`) never offers
  `sync-amend`, so the model must remember it from prose. When a drifted path is `sync_state_label(root)` and
  the receipt holds a raw hash, make the recipe's first step `workflow.py sync-amend --feature <f> --reason
  "<why>"`; move both blocks to `recovery.md` (read on drift) and leave one sentence.
- **Saving.** About 1.6 KB per session, about 400 tokens.
- **Tests.**
  - The recipe for a raw-hash drift names `sync-amend`.
  - `test_skill_split` and the `check_docs` links stay green.

### W21. `status` includes Progress's line

- **What.** `dispatcher-operations.md:17-19` asks the model to run `progress.py status` after `status`. Instead,
  `native_run_status` appends `progress: <line>` when `progress_bridge.script(root)` finds Progress: one
  subprocess with a 10 s timeout, and errors are reported as text. Drop the sentence from the prose. Together
  with D1, `workflow.status` is the workflow record that carries the progress line.
- **Saving.** One tool call per status request.

### W22. Faster slow test modules

- **What.**
  - Measured here: `test_sync_binding` takes 163 s for 22 tests, and `test_memory_handoff` takes 114 s for 17.
  - Each test drives a fresh lifecycle (`Harness.complete_through`, `test_receipt_contract.py:59-64`). The
    Memory tests spawn real `archive.py` helpers.
  - Change: build the advanced fixture once in `setUpClass` and copy the tree per test. This is the round-3
    `.git` template idea applied to the whole lifecycle.
  - Note: `test_sync_binding` needs `jsonschema` (`test-requirements.txt`). Without it, the module fails at
    import.
- **Saving.** Estimated 50-70% of those two modules. Not measured.
- **Risk.** Tests must not share mutable state. Copy the tree; never reuse it.

### W9. Split `workflow.py` (4,137 lines, 151 functions plus `Run`)

Module map. Each moved name is re-exported from `workflow.py`, so `from workflow import ...` keeps working.
That covers 14 internal importers, `smoke_project_init.py`, `smoke_upgrade.py`, Scope's `workflow_policy`
loading by path, and `memory_handoff`'s `SimpleNamespace(**globals())`.

| New module | Moves | Lines |
| --- | --- | ---: |
| `wf_core.py` | `WorkflowError` through `canonical_path`, `git`, the operation memo (`_OPERATION`, `operation`, `_memo`, `_wrote`), `locked`, `ensure_local_excludes`, `default_actor`, `require_not_delegated_context` (`145-311`, `2407-2473`) | about 260 |
| `identity.py` | `github_repository` through `prepare_issue` (`312-770`), minus the normaliser that D4 moves | about 380 |
| `policy.py` | `default_policy` through `policy_cutoff` (`771-1185`), minus the sync helpers | about 325 |
| `fingerprints.py` | `fingerprint_files`, attributes, `sync_state_label`, `sync_entry`, `sync_projection`, `required_inputs`, `source_fingerprints`, inventories (`1023-1050`, `1667-1830`) | about 230 |
| `health.py` | `registry` through `pr_lint_binding` (`1186-1560`) | about 375 |
| `receipts.py` | context gates, input roles, drift, CI evidence, `receipt_status`, `recovery_recipe`, `ready_checks`, sync binding verification (`1053-1114`, `1560-1666`, `1830-2406`) | about 700 |
| `workflow.py` | constants (`41-144`, because `check_docs.py:77-83` parses `BASE_STAGES`, `COMMANDS` and `stages()`, so `stages` stays too), `Run`, CLI | about 1,900 |

Order: phase 1 is `wf_core` and `identity`, done together with D4. Phase 2 is `policy`, `fingerprints`,
`health` and `receipts`. Phase 3, splitting `Run` (1,370 lines), is deferred.

Impact:

- **Test patches.** About 70 `patch.object(w, ...)` sites (`doctor` 20, `load_policy` 9, `required_inputs` 7,
  `github_repository` 5, `fingerprint_files` 5, others 24). A patch on `w.X` works only while every caller of
  `X` stays in `workflow.py`: `cached_doctor` calls `doctor`, so the 15 `test_delegation` sites must patch
  `health.doctor`. Rule: move a patched name with all its callers, or retarget the patch in the same commit.
- **Benchmark.** It wraps `w.fingerprint_files`, `w.git`, `w.doctor` and `w.source_fingerprints`; wrap the
  defining modules, or the counters undercount.
- **Memo.** `_OPERATION` must live only in `wf_core`; a re-export would be a stale copy. `w.operation()` stays
  valid as a function re-export.
- **Imports.** Bare sibling names, as `sanduq_hash` already is. A process that loads two runtimes
  (`smoke_install.py:63`) reuses the first submodules; that hazard exists today. Packaging is unchanged.

Value: maintainer and agent reads drop from one 228 KB file to modules of 30 to 90 KB. There is no consumer or
runtime gain, and the full suite must pass.

### W23. Cleanup leftovers

- **Dead code.**
  - `clear_caches` (`workflow.py:273-276`) has no caller at all, although its docstring and round-3 notes say
    the tests call it. Delete it.
  - `scope_decision` (`:1140`) and `worker_brief.project_result` are still referenced only by tests. Move them
    into the tests or delete them.
- **Docs.** Document the policy values that do nothing (round 3 W8, not done): `updates.policy`,
  `execution.checkpoints: every-phase`, `context.mode: measured-with-estimated-fallback` (behaves as
  `measured-only`), and `clarification.transport`.
- **Drop.** Leave the 120 "round N, finding X" citations in code (`delegate_dispatch.py` 47, `workflow.py` 35):
  they cost nothing at runtime.

### W24 (defer) and W25-W27

- **W24.** Apply W18's cache to `source_fingerprints`. It is evidence-critical. Measure on a large consumer
  repository first; the fixture's 2.5 s per inventory is mostly first-open scanning in `%TEMP%`.
- **W25 (drop).** The foreign-claim scan parses every checkpoint (`workflow.py:3387-3388`). It costs about 50 ms
  at 100 features, and an index would add a second source of truth.
- **W26 (drop).** The same reasons as in round 3.
- **W27 (defer).** Drop `repo_path` in a schema release.

## 4. Instruction load (full tier)

Instruction bytes went from 171,472 (round 3 after) to 177,971; claim stdout from 60,694 to 61,534. The growth:
`dispatcher-operations.md` +2,697 B (W20 takes back 1.6 KB), `stage-pr.md` +832 B, `receipt-rules.md` +198 B
(counted in all 16 stages by the benchmark, read once per session). The largest stages (Scope 18,143 B, Clarify
14,839 B, Specify 13,760 B) are mostly Scope's files (R2). The preset overlays are 778-810 B each (the two
`replace` overlays 2.7-2.9 KB); nothing to cut.

## 5. Cross-stream notes

- **R4.**
  - `pr.generate` description (D1).
  - Project's `write_text` CRLF (W11).
  - `project_sync.py` side of D4.
  - Spec Kit's `register_hooks` purges Memory's `impact` binding on `before_specify` on `specify extension
    update memory`, because the manifest declares only `session` there. It comes back only when Memory's
    `install.py` runs again (`memory/extension.yml:45-46`).
- **R5.** `attempt record` and the legacy-attempt model lose their caller (D5).
- **R2.** W12. Scope also reads `workflow.py` by path (`workflow_policy.py:62-72`), so W9 re-exports must keep
  `verify_checkpoint_identity`.
- **R6.**
  - Catalog grows by about 206 characters (D1).
  - Removing `test_progress_shim.py` reshuffles the size-based Windows shards automatically.
  - `jsonschema` is a test dependency.

## 6. Recommended do-list

1. Fix first: W10, then W11, then W12 (with W15).
2. Decided items: W13 and W14 with D3 (after the confirmation run), W15 (D4), W16 (D5), W17 (D1).
3. Runtime: W6, then W18, then W19.
4. Instructions: W20, W21.
5. Tests: W22.
6. Last and mechanical, after everything above has merged: W9 phases 1-2, and W23.

Do not add the savings together. Remeasure each with `benchmark_front_half.py` in the same session as its
BEFORE run.
