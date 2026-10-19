# Round 2 review: memory (stream R4)

Read-only review of `extensions/memory` on the `feat/round-2` worktree at its base commit. Every number
below was measured on the files named; line references are to those files. Nothing was run or changed.

## Summary

- `commands/run.md` is 21,150 bytes, 319 lines, 2,821 words and 40 prohibitions (1.42 per 100 words); 9,464 bytes (45%) is the delta-candidate section and at least 17 of the 40 prohibitions restate a guard that `archive.py`, `memory_delta.py`, `memory_store.py` or `orchestration.py` already raises as an error.
- The file is loaded whole for every archive, including once per feature in an automatic session (`memory-lifecycle.md:42`), although only one of its three paths (v2 small, v2 large, format 1) and rarely the override section (2,136 bytes) apply to a run.
- The seven descriptions come from three divergent sources (file frontmatter, `extension.yml`, `install.py` `COMMANDS`); all seven open with an imperative verb and none states when to use the command or a trigger phrase. `install.py` overwrites the skill files Spec Kit renders, so its table is what both hosts list.
- Two of the seven catalog entries (`prepare`, `session`) are hook- or dispatcher-invoked only, yet they are user-invocable on both hosts; the workflow extension already has the helper that hides such skills on Claude (`hosts.py:226-258`).
- Cross-file exact repetition is zero (no shared paragraph of 25 words or sentence of 10 words across the seven commands, the README and the dispatcher's memory references), but the same rules are written four to five times in different words: the `pending --gate` rule, the rollback rule, the override rule and the "never load memory wholesale" rule.

## Findings per lens

### Lens 1: the model is told to do what a script already does

Mapping of run.md prose to the guard that enforces it (prohibition count in the regex sense; the script raises the listed message):

| run.md | Prose | Enforced at |
| --- | --- | --- |
| 47 | Prepare refuses while any run is active | `archive.py:641` |
| 51-53 | reason nonempty, single-line, at most 500 characters | `archive.py:75` |
| 57 | omit `--check` in override mode | `archive.py:647` |
| 63 | automatic mode and `--all-completed` reject the override | `archive.py:1407` |
| 79 | do not edit the journal to bypass verification | `archive.py:749` |
| 80 | `finalize` accepts no skip flag | argparse, `archive.py:1343-1350` (no such flag) |
| 121 | unknown top-level keys are rejected | `memory_delta.py:148` |
| 128-129 | an id in at most one link list, never the entry's own id | `memory_store.py:325` |
| 130 | new ids must not exist or be retired | `memory_delta.py:170,172` |
| 130-132 | every updated id anchored or carries a reason | `memory_delta.py:328` |
| 136-139 | `expected_hash` must match | `memory_delta.py:184` |
| 144 | evidence never under `specs/`, present at the checkpoint | `memory_delta.py:278,287,385` |
| 155-161 | removal needs reason, inventoried `source_unit`, live `replacement`; no double touch | `memory_delta.py:198,214,218,220,226` |
| 162-165 | taxonomy op, kebab-case, Windows reserved names | `memory_delta.py:237-243` |
| 167-171 | every unit in exactly one coverage group; omitted needs reason, others need live ids with provenance | `memory_delta.py:72,74,78,314-319,381` |
| 172-175 | budgets entry 1024, INDEX 3000, catalog 1500; views regenerated | `memory_store.py:315,342,346,349` |
| 176-177 | text trimmed, no h1/h2, no TODO or conflict markers, references resolve | `memory_store.py:84,311,314,322` |
| 192 | re-packeting refused once fragments exist | `orchestration.py:107` |
| 263-264 | stray files under `specs/memory` refused | `memory_delta.py:149`, `archive.py:770` |
| 296-299 | memory moved since prepare: validate and finalize refuse | `memory_delta.py:143`, `archive.py:898` |
| 307 | abandon forbidden after publication | `archive.py:1005` |
| 312 | rollback refuses after the final commit or unexpected edits | `archive.py:967,979` |

Two things the model is told to compute that a script could hand it:

- `run.md:136-139` tells the model to run a Python one-liner to compute `expected_hash` for every update and removal. Only `packets` emits that hash (`orchestration.py:171`); `memory show` and `memory query` do not (`memory_query.py` has no sha256), so a small run hashes by hand once per touched entry.
- `run.md:258-299` tells the model the order preflight, review, validate, finalize and the conditions for each. `status` returns `policy_hash`, `pending` and the active run (`archive.py:1202-1205`); it does not name the next command, so the procedure text is the only source of ordering.

Deterministic versus judgement steps in run.md: 17 distinct `A <verb>` forms are named; the only numbered procedure is the large-run packets flow (7 numbered steps, lines 189-221). The rest of the file is paragraphs that mix a script call with the judgement around it (for example lines 28-39 contain three calls, `preflight`, `verify`, `prepare`, inside 258 words of conditions).

### Lens 2: text repeated inside the extension and against the dispatcher

Measured: 0 exact paragraphs of 25 or more words and 0 sentences of 10 or more words shared between the seven command files, `README.md`, `memory-lifecycle.md` and `dispatcher-operations.md`. The repetition is semantic, each copy worded differently:

| Rule | Copies |
| --- | --- |
| `pending --gate` before a new specification, branch or broad commit | `session.md:22-23`, `run.md:314-315`, `install.py` `SESSION` lines 28-30 (written into `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`), `memory-lifecycle.md:39-40`, and the guard itself in `guard-patches.json` (`create-new-feature.*`, `auto-commit.*`) |
| rollback restores recorded bytes, preserves checkpoint, removes queue entry, refuses after final commit | `run.md:308-313`, `session.md:17-20`, `README.md:186` |
| verification override rules (reason limits, automatic rejects it, reviewer binds `verification_override`, no journal edit) | `run.md:49-80` (2,136 bytes), `README.md:198-220` |
| large-run packets, fragments, merge, review-packets | `run.md:187-226`, `README.md:150-164` |
| do not load `specs/memory/` wholesale or `memory export` | `run.md:90-91`, `impact.md:37`, `session.md:8`, `SESSION` line 12 |
| command descriptions | `commands/*.md` frontmatter, `extension.yml:22-45`, `install.py:12-20`; for `run` the three texts are 68, 83 and 48 characters and all differ |
| hook registration | `extension.yml:46-58` (three hooks) versus `install.py:159-162` (four: `impact` is added to `before_specify` as well) |

Against the dispatcher the overlap is small and one-directional: `memory-lifecycle.md` (70 lines) tells the dispatcher which memory command to invoke and repeats three memory rules (`:13-14` do not invoke prepare again, `:38-39` never finalize, abandon, roll back or remove a lock automatically, `:45-46` no retirement, `--all-completed` or override in automatic mode). Those three also live in `session.md:14-20,34-36` and `run.md:24,63`.

### Lens 3: stages that reread large inputs they do not need

- `run.md` is read whole (21,150 bytes, about 5.3k tokens) on every invocation. Per-run path analysis by section bytes: preamble 883, resolve and verify 1,925, override 2,136, read inputs 1,198, author delta 9,464 (of which the packets sub-procedure, lines 187-226, is about 3,500), format 1 677, migrations 837, review and publication 2,780, recovery 1,242. A small v2 run without override uses about 15,000 of the 21,150 bytes; the override (10%), format-1 (3%) and large-run (17%) text is loaded regardless.
- In an automatic session `run` is dispatched once per ready feature, "one feature at a time, then refresh the handoff" (`memory-lifecycle.md:42`; `session.md:32-34`), so the 21 KB is loaded N times per session for N features.
- Format 1 is a migrated-away format (`README.md:166` "Upgrading from 1.x", `archive.py:1165-1187` `migrate` is one-way); its instructions (`run.md:16-18, 228-240`) are dead text for every project that has migrated.
- The reading of memory and run state is already bounded: `inspect` views default to 16,384 bytes with a cursor (`archive.py:1288-1292`), `memory query` to an 8,000-token budget (`archive.py:1317`), and `session.md:8` forbids loading memory for the pending check. No change needed there.

### Lens 4: descriptions and catalog slots

Measured on the command files' frontmatter (what Spec Kit renders, `spec-kit/.../extensions/__init__.py:1083-1084`) and on `install.py` `COMMANDS` (what `init` writes over the same `.agents/skills` and `.claude/skills` paths, `install.py:148-153`):

| Command | File description (chars) | install.py description (chars) | Third person | When | Triggers |
| --- | --- | --- | --- | --- | --- |
| init | Configure Sanduq Memory for this Spec Kit project (49) | Configure project memory, verification checks and lifecycle integrations (71) | no | no | no |
| prepare | Queue an implemented feature without deleting it (48) | Queue implemented work for archival after merge (47) | no | no | no |
| run | Archive selected verified specifications into current product memory (68) | Archive selected verified feature specifications (48) | no | no | no |
| session | Process pending merged archives in the next local agent session (63) | Process approved pending archives in this local session (54) | no | no | no |
| enable | Review and enable the current automatic archive policy (54) | Review and enable automatic archival policy (43) | no | no | no |
| impact | Consult relevant current product knowledge for specification and impact analysis (80) | Consult current product knowledge for specification impact (58) | no | no | no |
| status | Inspect pending archival and recovery state (43) | Inspect pending archival and recovery state (43) | no | no | no |

All are under 1,024 characters (total 405 file, 364 install.py), so the failure is under-description, not budget: no "use when", no quoted phrases, every one opens with an imperative verb. `install.py:150-151` writes only `name`, `description` and `compatibility`, so Spec Kit's Claude-only `user-invocable`, `disable-model-invocation` and `argument-hint` (first report, standards table) are lost after `init`.

Hook-bound commands: `prepare` is the `after_implement` hook and is otherwise only dispatched by `memory_handoff.py:121` when check selection is missing (`memory-lifecycle.md:13-14` forbids invoking it again by hand). `session` is the `before_specify` hook and the dispatcher's session entry (`memory-lifecycle.md:37-41`, `SESSION` block). Neither has a user use case; both occupy a catalog entry on both hosts (2 of 7). `impact` is a hook (`before_analyze`, `before_specify`) and a user command ("consult memory", `impact.md:7`), so it stays visible. `status`, `enable`, `init`, `run` are user commands.

### Lens 5: rules a hook could enforce

- `run.md:9-10` "No push, PR creation, stash, reset, clean, broad staging" and `run.md:314-315` "while any transaction is active, do not start another specification, branch or broad staging/commit workflow". The second is already a script guard (`guard-patches.json` inserts `archive.py pending --gate` into `create-new-feature.*` and `auto-commit.*`), so the prose is a restatement. The first has no guard; the workflow extension already registers a PreToolUse guard hook on both hosts (`hosts.py:register_guard`, `guard_hooks`), and the memory extension ships no `hooks/hooks.json`.
- `run.md:99-100` "edit only candidate.json, never `specs/memory/`, the registry or feature files" is enforced only at finalize (`archive.py:770` stray files) and preflight (`memory_delta.py:149`), that is after the model has written. A PreToolUse deny on Write and Edit under `specs/memory/**` while `sanduq-memory/active.json` exists would fail at the first wrong write.
- `run.md:266-272` "never let the reviewer change repository files; do not claim independence if you reviewed your own synthesis" is a role definition; the workflow extension generates read-only role agents (`hosts.py:install_roles`) and memory does not.

### Lens 6: where Claude Code and Codex diverge

- `run.md:12-13` carries a per-host spelling note (hyphens for Codex and Claude skills, dots for Copilot) in every run. It belongs in the wrapper that `install.py` writes per host, not in the command body.
- `install.py:148-157` writes byte-identical skill files to `.agents/skills` and `.claude/skills` and a Copilot agent plus prompt pair. Spec Kit's Claude-specific frontmatter is overwritten (see lens 4), so the two hosts are more uniform than Spec Kit intends and Claude loses `argument-hint`.
- `install.py:171-180` appends the same 13-line `SESSION` block to `AGENTS.md`, `CLAUDE.md` and `.github/copilot-instructions.md`. Claude Code reads `CLAUDE.md`; Codex reads `AGENTS.md` under a 32 KiB combined cap (first report, standing instructions). The block is consistent across hosts; the cost is that it restates `session.md` and `impact.md` (lens 2).
- Hooks: memory has no `hooks.json`, so Codex's per-hash hook approval does not apply today. Any option in lens 5 inherits that requirement for Codex.
- Registry: `install.py:166` hard-codes `"version": "2.1.0"` while `extension.yml:5` says `2.2.1`; both hosts see a stale version in `.specify/extensions/.registry`.

## Defects

| Defect | Effect | Where |
| --- | --- | --- |
| Registry version hard-coded to 2.1.0 | `.registry` reports a stale version after `init`; `manifest_hash` is correct, the version is not | `install.py:166` vs `extension.yml:5` |
| Three divergent description sources | Catalog text depends on install order; the yml text is never shown; Spec Kit's render is overwritten by `init` | `commands/*.md` frontmatter, `extension.yml:22-45`, `install.py:12-20,148-153` |
| `init` drops Spec Kit's Claude frontmatter | `argument-hint`, `user-invocable`, `disable-model-invocation`, `metadata.source` lost on Claude | `install.py:150-151` |
| Hook truth split between two files | `extension.yml` lists three hooks; `install.py` registers four (`impact` also on `before_specify`) | `extension.yml:46-58`, `install.py:159-162` |
| `run.md` loaded whole per feature | 21 KB per archive, times N in automatic sessions; 30% of it off the common path | `run.md`; `memory-lifecycle.md:42` |
| Format-1 instructions in a 2.x command | Dead text for migrated projects, two schema shapes to reconcile | `run.md:16-18,228-240`; `README.md:166` |
| 17 or more prohibitions restate script guards | Attention spent on rules the helper already returns as an error message | table in lens 1 |
| `expected_hash` computed by hand | A shell one-liner per touched entry; copy errors are refused only at preflight | `run.md:136-139`; `orchestration.py:171` is the only emitter |
| `prepare` and `session` are user-invocable | Two catalog entries on both hosts for commands the user never calls | `extension.yml:26-33`, `install.py:148-153` |
| CLI defaults repeated in prose | `inspect` 16,384-byte default and 1,048,576 maximum, `--budget 8000` restated; drift risk on the next CLI change | `run.md:85-87,94`; `archive.py:1288-1292,1317` |

## Candidate options

Cost basis used for every `tok` and `time` estimate. One small v2 archive run reads about: `run.md` 5.3k tokens; `inspect` status and inventory 2 x 4k (up to 16k with checks and coverage); one to three `memory query` results at the 8k budget (8k to 24k); preflight, validate, finalize JSON about 1k each; the candidate the model writes 2k to 6k; the independent reviewer rereads candidate plus units, 10k to 20k. Total 45k to 80k tokens; instruction text is 7% to 12% of it. A large run adds packets and partitions and roughly doubles the total, so the instruction share halves. `time` counts tool round-trips (about 12 per small run) and model reconciliation of rules; a reference read is one round-trip.

### ME1. Restructure run.md into a short procedure plus references loaded by step

- title: Procedure entry plus step references for `speckit.memory.run`
- what: Cut `commands/run.md` to about 6 KB: an 8-line preamble (checkout, JSON `success`, `A` alias), a numbered procedure of about 12 steps, one `A` call per step with the condition that gates it (prepare, inspect, author, preflight, review, validate, finalize), and a one-line pointer per reference. Move the rest into `extensions/memory/references/`: `candidate-v2.md` (today lines 102-186, 9.4 KB, trimmed to about 6 KB by dropping the 17 guard restatements in the lens-1 table and keeping the JSON shape, the kinds, the anchoring and evidence semantics and the "organize by capability" paragraph), `verification-override.md` (lines 49-80, 2.1 KB, loaded only when the owner asks for `--skip-verification`), `large-runs.md` (lines 187-226, 3.5 KB, loaded when `packets` is chosen), `format-1.md` (lines 228-240 plus the memory-format note, 0.8 KB, loaded only when `.archive-index.json` lacks `memory_format: 2`), `review-and-publish.md` (lines 256-299, 2.8 KB trimmed to about 2.2 KB), `recovery.md` (lines 301-318, 1.2 KB, loaded only on a blocked or interrupted run; `session.md:17-20` and `status.md` point at it instead of restating rollback). Expected common-path bytes for a small v2 run: 6 + 6 + 2.2 = about 14 KB against 21.2 KB today (34% less); a large run 17.5 KB; override adds 2.1 KB only when requested. The references are read by path (`.specify/extensions/memory/references/<file>`), one level deep, under the extension directory Spec Kit installs whole, so both hosts load them identically and no catalog entry is added.
- effort: M
- tok: [0.02, 0.04]. Derivation: 7.2 KB less on the common path is about 1.8k tokens of a 45k to 80k run (2.2% to 4%); the saving repeats per feature in an automatic session.
- time: [0.01, 0.02]. One or two extra reference round-trips per run offset part of the shorter first read; fewer conditional rules to reconcile while authoring.
- obs: unchanged. Journal, receipts, checkpoint and final commit, review.json bindings and every guard stay as they are; only prose moves.
- policy: none.
- pros: Removes the override, format-1 and large-run text from the common path; keeps `run.md` under the 500-line and 5,000-token guidance with room to spare; each reference is self-sufficient for its step; the lens-1 restatements go because the helper's error message already names the rule.
- cons: Six new files to keep in step with the CLI; a reviewer must confirm no semantic rule (anchoring, evidence, coverage reasons, tombstones) is dropped while trimming; `install.py` copies only `commands/*.md` bodies into wrappers, so the reference paths must be spelled as installed paths, not relative links.
- files: `extensions/memory/commands/run.md`, `extensions/memory/references/{candidate-v2,verification-override,large-runs,format-1,review-and-publish,recovery}.md`, `extensions/memory/commands/session.md` (point at recovery.md), `extensions/memory/commands/status.md`, `extensions/memory/README.md` (link the two duplicated sections instead of restating), `CHANGELOG.md`, `extension.yml` version.
- tests: Keep green: `test_install.py` (seven wrappers exist, `test_preserves_other_extensions_and_orders_hooks`, `test_external_wrapper_link_is_never_followed`), all of `test_archive.py`, `test_archive_v2.py`, `test_orchestration.py`, `test_retro_tooling.py` (none pin run.md text). Add one: every `references/<file>` path named in `commands/*.md` exists and each reference is under 500 lines.

### ME2. One description source with what, when and triggers

- title: Rewrite the seven descriptions once and derive the other two copies
- what: Write third-person descriptions with the key use case first, a "use when" clause and quoted trigger phrases into each `commands/*.md` frontmatter (for example `run`: "Archives selected verified feature folders into project memory through a checkpoint, a reviewed delta candidate and a scoped final commit. Use when asked to 'archive the feature', 'run the memory archive' or when the session handoff returns `speckit.memory.run`."). Make `install.py` take the description from the frontmatter it already splits (`install.py:148`) instead of its `COMMANDS` table (keep the table's keys for the command list), and make `extension.yml` `provides.commands[].description` match verbatim. Keep every one under 200 characters so the Codex 8,000-character budget and Claude's 1% budget are unaffected.
- effort: S
- tok: [0, 0.005]. Catalog chars rise from about 400 to about 1,100 across seven entries (about 180 tokens per session on each host); routing accuracy is the gain, not tokens.
- time: [0, 0.01]. Fewer mis-routed invocations (`run` versus `session` versus `status`).
- obs: improved. The registry and both host catalogs show the same text.
- policy: none.
- pros: Removes two of the three sources; Spec Kit render and `init` agree; descriptions pass the catalog rules.
- cons: Slightly larger catalog; `install.py` must parse YAML frontmatter it currently treats as opaque text (a one-line regex is enough).
- files: `extensions/memory/commands/*.md` (frontmatter only), `extensions/memory/extension.yml`, `extensions/memory/scripts/install.py`.
- tests: Keep green: `test_install.py::test_preserves_other_extensions_and_orders_hooks` (asserts 7 commands). Add: the wrapper written for each host carries the file's frontmatter description.

### ME3. Hide the two hook-only commands on Claude

- title: `user-invocable: false` for `prepare` and `session` on Claude
- what: In `install.py` add `user-invocable: false` to the frontmatter it writes for `.claude/skills/speckit-memory-prepare` and `speckit-memory-session` (it builds that frontmatter itself at `install.py:150-151`, so no parsing is needed); leave `disable-model-invocation` unset so the dispatcher and the hooks can still invoke them (`memory_handoff.py:121`, `memory-lifecycle.md:37-41`). Codex has no hide flag, so nothing changes there. `impact`, `status`, `enable`, `init` and `run` stay visible. Same policy the first report applied to Scope's hook commands (A5) and the workflow installer already implements (`hosts.py:245-258`).
- effort: S
- tok: [0.002, 0.005] of the catalog listing on Claude (two of seven entries leave the menu; descriptions are still loaded for model invocation, so the saving is the menu only).
- time: [0, 0].
- obs: unchanged.
- policy: none.
- pros: Two fewer menu entries for the user; no behaviour change for hooks or the dispatcher.
- cons: A user who typed `/speckit-memory-session` by habit loses the menu entry (the dispatcher still runs it); no effect on Codex.
- files: `extensions/memory/scripts/install.py`, `extensions/memory/README.md` (command table note).
- tests: Keep green: `test_install.py` wrapper-exists assertions. Add: the Claude wrapper for `prepare` and `session` contains `user-invocable: false` and the Codex wrapper does not.

### ME4. Let the helper hand over the facts the model is told to compute

- title: Emit `expected_hash` from `memory show` and `memory query --format json`; `status` names the next command
- what: `memory_query.py` adds `expected_hash` (sha256 of the entry file, the same digest `orchestration.py:171` already computes for packets) to each entry it prints in `show` and in `query --format json`, so `run.md:136-139` and its shell one-liner go. `archive.py` `status` and `inspect --view status` add `next: {"command": "...", "reason": "..."}` derived from `phase` and the presence of `review.json` (synthesis: `preflight --run`; guards passed without review: independent review; review present: `validate --run`; valid and passed: `finalize --run`; blocked: the error already recorded). The procedure in run.md then says "run `A status` and do what `next` says" for the publication half.
- effort: M
- tok: [0.01, 0.02]. One fewer Bash call per touched entry (typically 2 to 6 per run) and the publication section of run.md (2.8 KB) shrinks to a few lines on top of ME1.
- time: [0.02, 0.04]. Wrong-order calls (validate before preflight, finalize before review) today cost a failed round-trip each; `next` removes the guesswork.
- obs: improved. The journal already records `phase`; `next` is derived from it, nothing new is stored.
- policy: none.
- pros: The script owns ordering and hashing, which it already validates; the model reads less and copies less.
- cons: `status` output grows by one object; `test_retro_tooling.py::test_native_inspection_is_valid_json_inside_the_complete_stdout_byte_budget` bounds `inspect` output and must still pass.
- files: `extensions/memory/scripts/memory_query.py`, `extensions/memory/scripts/archive.py` (`status`, `inspect`), `extensions/memory/commands/run.md` (or ME1's `review-and-publish.md`).
- tests: Keep green: `test_memory_query.py::test_cli_query_show_provenance_catalog`, `test_retro_tooling.py` inspection tests, `test_archive_v2.py::test_validate_reports_bindings_while_review_is_missing`. Add: `show` prints a hash equal to `hashlib.sha256` of the file; `status.next` for each phase.

### ME5. Guard hook for the active-transaction rules

- title: PreToolUse deny for forbidden git verbs and `specs/memory` writes while an archive is active
- what: Add `extensions/memory/hooks/hooks.json` in the shape the workflow extension already registers on both hosts (`hosts.py:guard_hooks`, `register_guard`): while `sanduq-memory/active.json` exists, deny Bash commands matching `git (push|stash|reset|clean)` and Write or Edit under `specs/memory/**`, with the message naming `candidate.json` and the recovery reference. `install.py` registers it only when the policy key is on. Remove the prose at `run.md:9-10` and `run.md:99-100`. The `pending --gate` sentence stays as a one-line pointer because its guard already exists in the feature scripts.
- effort: M
- tok: [0.002, 0.005]. Less than 300 bytes of prose leave run.md; the value is a wrong write failing at the first tool call instead of at finalize (`archive.py:770`).
- time: [0, 0.02]. One failed finalize and re-prepare avoided when it would have happened; otherwise neutral.
- obs: improved. Denials are visible in the host hook log; the archive journal is untouched.
- policy: `guard_hooks` in `archive-policy.json`, default `false` (unchanged behaviour until a project turns it on; Codex also needs its per-hash hook approval).
- pros: Enforces the two rules the script cannot see until later; same mechanism and file shape the workflow extension ships, so both hosts are covered by one file.
- cons: Codex requires per-hash approval in `/hooks` for project hooks; a denied `git stash` during a legitimate manual recovery needs the owner to disable the archive first (`abandon` or `rollback`), which is the documented path anyway.
- files: `extensions/memory/hooks/hooks.json` (new), `extensions/memory/scripts/install.py`, `extensions/memory/archive-policy.json`, `extensions/memory/commands/run.md`, `README.md`.
- tests: Keep green: `test_install.py::test_reinitialize_preserves_policy_customizations_and_guards`, `test_install.py::test_invalid_existing_policy_preserves_files`. Add: with the key on, the hook file is registered for each installed host; with it off, nothing is written.

### ME6. Registry version and hook truth from `extension.yml`

- title: Read version and hooks from the manifest instead of hard-coding them
- what: `install.py:166` writes `extension.yml`'s `version` into the registry instead of `"2.1.0"`. For hooks, `extension.yml` can list one command per event, so it cannot express `impact` on both `before_specify` and `before_analyze`; keep `install.py` as the registrar but add a comment line in `extension.yml` under `hooks:` stating that `init` also binds `impact` to `before_specify`, and have `test_install.py` assert the four registrations against a list in one place.
- effort: S
- tok: [0, 0]
- time: [0, 0]
- obs: improved. The registry stops lying about the version.
- policy: none.
- pros: One-line fix for a visible defect; the hook mismatch becomes documented instead of silent.
- cons: None of substance; the hook model stays split between the manifest and the installer until Spec Kit allows two commands per event.
- files: `extensions/memory/scripts/install.py`, `extensions/memory/extension.yml`, `extensions/memory/tests/test_install.py`.
- tests: Keep green: `test_install.py::test_preserves_other_extensions_and_orders_hooks` (asserts hook order session, impact, workflow.scope). Add: registry `version` equals the manifest version.

### ME7. One recovery text for `run`, `session` and `status`

- title: Shared recovery reference instead of three rollback paragraphs
- what: The rollback and abandon rules are written in `run.md:303-313`, `session.md:17-20` and `README.md:186` in different words. With ME1's `references/recovery.md` as the single text, `session.md` and `status.md` each keep one sentence and a pointer; the README links the reference. Also trim the `SESSION` block in `install.py:22-34` from 13 lines to the four facts a standing instruction needs (run `pending` at session start; follow `session.md` when it reports work; `pending --gate` before a new specification; follow `impact.md` for specify and analyze), since `session.md` and `impact.md` carry the detail.
- effort: S
- tok: [0.003, 0.008]. About 600 bytes less in `session.md` on every session start and about 500 bytes less standing instruction on every turn of every session (the `SESSION` block is in `CLAUDE.md` or `AGENTS.md`).
- time: [0, 0.005].
- obs: unchanged.
- policy: none.
- pros: The standing-instruction cost is paid on every turn, so the smallest cut here repeats most often; one text to keep right.
- cons: Depends on ME1's `recovery.md` existing; `test_install.py` checks the `SESSION` marker count, not its text, so no test guards the wording and one should be added.
- files: `extensions/memory/commands/session.md`, `extensions/memory/commands/status.md`, `extensions/memory/scripts/install.py` (`SESSION`), `extensions/memory/README.md`.
- tests: Keep green: `test_install.py` (`SANDUQ MEMORY SESSION START` appears once). Add: the `SESSION` block names `session.md`, `impact.md` and `pending --gate`.

### ME8. Retire the format-1 path from the command

- title: Format-1 instructions behind `migrate`, not in every run
- what: `run.md:16-18` and `228-240` describe the legacy single-document candidate. `migrate` is one-way (`archive.py:1165-1187`) and the README calls format 1 "Upgrading from 1.x". Move the format-1 text to `references/format-1.md` (ME1 does this) and, in addition, have `prepare` return `"memory_format": 1` together with the reference path in its result so the model opens the file only on a format-1 project; `run.md` stops mentioning format 1 at all. No deprecation of format 1 itself; `test_archive.py` (format 1 end to end) stays as is.
- effort: S
- tok: [0.003, 0.006]. About 1 KB of conditional text (the two format notes and the "(v2)" markers in six headings) leaves the common path on top of ME1.
- time: [0, 0.005].
- obs: unchanged.
- policy: none.
- pros: One schema shape in front of the model on a 2.x project; fewer "(v2)" conditionals to evaluate.
- cons: A format-1 project pays one extra read; the format-1 reference must stay correct though rarely exercised.
- files: `extensions/memory/commands/run.md`, `extensions/memory/references/format-1.md`, `extensions/memory/scripts/archive.py` (`prepare` result).
- tests: Keep green: all format-1 tests in `test_archive.py` and `test_retro_tooling.py::MemoryToolingTests`, `test_migration_discovery.py::LegacyMigrationDiscoveryTests`. Add: `prepare` on a format-1 fixture reports `memory_format: 1` and the reference path.

## Double-counting notes for the orchestrator

ME7 and ME8 are carve-outs of ME1 (the recovery reference and the format-1 reference); count their `tok` only when ME1 is not chosen. ME4's publication-section saving overlaps ME1's `review-and-publish.md` trim by about 1 KB. ME2, ME3, ME5 and ME6 are independent of the rest.
