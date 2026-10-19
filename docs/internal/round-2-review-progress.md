# Round 2 review: progress (stream R5)

Paths are relative to `extensions/progress/` unless they start with `extensions/` or `C:`. Timings were measured on
this machine (Windows 11, CPython from PATH, median of 5 runs) in a scratch project built from this worktree with the
installed Spec Kit's generated `.specify/events.py` (specify_cli 1.1.4.dev0 at
`C:\Users\sabus\AppData\Roaming\uv\tools\specify-cli\Lib\site-packages\specify_cli\events\__init__.py`). Everything under
`scripts/`, `assets/ui/`, `docs/`, `skills/progress/references/` and `assets/skill/SKILL.md` is vendored from
sanduq-skills `agent-tools-v1.4.3` (`vendor.lock.json`); options that touch those files are labelled **upstream**.

## Summary

1. Progress costs runtime, not instruction bytes: one `PostToolUse` hook on every tool call at 200 to 251 ms through Spec Kit's dispatcher (two Python launches), 87 to 137 ms when `scripts/hook.py` is called directly, and 686 to 728 ms when the hook's interpreter can import `specify_cli`. The agent-facing text is 5 commands of 333 to 380 bytes plus a 2,314-byte skill.
2. `speckit.progress.hook` does not occupy a catalog slot on either host: Spec Kit renders only `provides.commands` (installed `extensions/__init__.py:1117,1655,2527`) and the file is deliberately unlisted (`extension.yml:25-40`, `CHANGELOG.md:21`). Five slots per host remain, and the descriptions the hosts see are the command files' (23 to 71 characters, imperative, no "when"), not the longer ones in `extension.yml`.
3. Every one of the five commands loads the whole skill for a one-line CLI call; the skill is 86 percent of each command's instruction bytes, and in the vendored benchmark the two skill reloads (resume, compaction) are 1,774 of 2,419 update tokens (73 percent).
4. The 126 KB of docs (`contracts.md` 60 KB, `commands.md` 51 KB, `hosts.md` 15 KB) are reachable by an agent only through a second hop (`references/verbs.md:4`); nothing a command or the skill says loads them. They and 257 KB of PNGs ship to every consumer project.
5. Hosts diverge on wiring, not behaviour: Spec Kit writes 5 Codex events into `.codex/config.toml`; the extension's own installer writes 4 into `.codex/hooks.json` (no SessionEnd, `hooks_install.py:36`); Workflow's bridge recognises only the Spec Kit command strings (`progress_bridge.py:33`); the status line is Claude-only (`statusline.py:1,77`).

## Cost shape, with numbers

| Cost | Measured | Where |
| --- | --- | --- |
| Interpreter floor | `python -c pass` 58 ms | scratch run |
| Event, unbound session, via `.specify/events.py` | 200 ms (min 180) | dispatcher spawns `hooks/dispatch.py`, which `exec`s `scripts/hook.py` |
| Event, bound session, post_tool_use (debounced) | 251 ms (min 203, max 410) | same chain, full package import 82 ms, `publish_pending` once per window |
| Event, bound session, stop (forced refresh) | 251 ms (min 240) | `refresh.after_update(force=True)`; 22 file opens, 14 distinct |
| Same events calling `hooks/dispatch.py` directly | 87 / 137 / 143 ms | one interpreter instead of two |
| Dispatcher when `specify_cli` is importable | 686 to 728 ms | template prefers `from specify_cli.events import ...` (events module lines 418 to 437); the import alone is 487 ms |
| Model-visible tokens per feature (vendored benchmark, o200k) | 3,322 = setup 903 + updates 2,419 | `docs/token-benchmark.md` results table |
| Instruction bytes per user command | 333 to 380 (command) + 2,314 (skill) | `commands/*.md`, `skills/progress/SKILL.ext.md` |
| Catalog | 5 entries per host, 235 description characters as rendered (383 in `extension.yml`, unused) | installed Spec Kit `extensions/__init__.py:1741` |

For a 300-tool-call session the PostToolUse hook alone is 60 to 75 s of wall time through the dispatcher (206 to 218 s when
`specify_cli` is importable), against about 3,300 model tokens for the whole feature. Whether the host waits for the hook
before returning the tool result was not verified here.

## Findings by lens

### 1. Model does what a script does

- Clean on the whole: the commands are pointers to one CLI line each, every verb prints one line and the hooks collect task
  state, lanes `W#`/`C#`, runs and decisions without a verb (`SKILL.ext.md:29-31`, benchmark classes `start_task`,
  `complete_task`, `reopen_task`, `noop_refresh` at 0 tokens).
- The agent retypes the 56-character prefix `python .specify/extensions/progress/scripts/progress.py` on every verb
  (`SKILL.ext.md:11-13`); the vendored benchmark measures that prefix at 13 tokens per line ("Reading the result",
  `docs/token-benchmark.md`). Over the 14 typed verbs of the trace that is about 180 of 2,419 update tokens. No cheap
  fix exists inside Spec Kit's path confinement (`_script_under_base`, events module lines 109 to 121), so no option.
- Three rules the skill asks the model to obey are already enforced by the CLI: rule 3 `decide` refused under Workflow
  (`PROGRESS_DECISION_AUTHORITY`, `references/verbs.md` decide row), rule 4 secrets, absolute paths and the 200-character
  cap (`facts.sanitise`, `scripts/sanduq_progress/facts.py:46-48`, called from `cmd_note`, `scripts/progress.py:584`),
  rule 6 the error format. See lens 5.

### 2. Repeated text

- The line `Load \`.specify/extensions/progress/skills/progress/SKILL.md\`, then run from the repository root:` is the
  first line of all five user commands (`commands/init.md:5`, `refresh.md:5`, `status.md:5`, `theme.md:5`,
  `export.md:5`).
- "Reporting is a deterministic projection. Never spawn, retain, message or poll an agent solely to maintain it." appears
  in `SKILL.ext.md:8`, `assets/skill/SKILL.md:10`, `extensions/workflow/README.md:168` and
  `extensions/workflow/skills/workflow/references/reporting.md:5`, and two tests assert it (`tests/test_extension.py:52`,
  `tests/test_token_budget.py:74`).
- The verbs table exists three times: `SKILL.ext.md:15-29`, `assets/skill/SKILL.md:28-40` (plan-mode variant with `P001`
  ids and a `hooks install` row that Sanduq never uses) and `references/verbs.md:8-30` (full flags). The Workflow stage
  reference repeats the `lane`, `block`, `unblock`, `note`, `refresh --final` lines once more (`reporting.md:27`).
- The Codex approval paragraph (trust level, `hooks.state` hash, "approve the five Progress hooks") is in
  `extensions/workflow/README.md:159-167`, `reporting.md:19-24` and `docs/hosts.md:46-52`.
- `extension.yml:25-40` carries a second, longer description per command that the hosts never see (lens 4).

### 3. Rereading large inputs

- Each command invocation reads 333 to 380 bytes of command plus the 2,314-byte skill: the skill is 86 percent of the
  bytes, and `status`, `export`, `theme` and `refresh` use nothing from it (their bodies already hold the full CLI line
  and the one relay rule). Only `init` (bind semantics) and the record verbs (`lane`, `block`, `decide`, `note`, which
  have no command of their own) need the skill.
- The benchmark's `resume` and `compaction` rows (887 tokens each) are the skill reload plus one status line; together
  1,774 of 2,419 update tokens (73 percent) for a trace whose typed verbs cost 645.
- Docs: `contracts.md` (60,289 B, 17 sections), `commands.md` (51,189 B, 34 headings) and `hosts.md` (14,568 B) are
  linked from `references/verbs.md:4` and `assets/skill/SKILL.md:52` only; no command, the skill or any Workflow reference
  links them. They are human documentation, two hops from a command (beyond the one-level rule), and `package.py`
  ships them with the 257 KB of screenshots (`EXCLUDE` at `extensions/scripts/package.py:12-15` lists neither `docs` nor
  `assets/skill`).
- Per forced refresh the hook opens 22 files, 14 distinct; `config.json`, `workflow/checkpoint.json`,
  `workflow/delegations.json` and `.view/state.json` are each opened twice (measured with an `open` counter around
  `hook.handle('stop', ...)`). Upstream, small.
- On Codex only, `session_start`, `stop` and `session_end` also tail-read the rollout transcript
  (`scripts/sanduq_progress/hook.py:16,61-63`, `hosts/codex.py:52-58`, capped at `TAIL_BYTES`).

### 4. Descriptions and catalog slots

- Spec Kit builds the skill description from the command file's frontmatter (`original_desc = frontmatter.get("description")`,
  installed `extensions/__init__.py:1741`), so the hosts list: "Create the progress report for the active feature and bind
  this session" (71), "Force a projection snapshot now" (31), "Print a one-line summary of the progress report" (47),
  "Choose the report theme" (23), "Write the progress projection as deterministic Markdown or JSON" (63). All five open
  with an imperative verb, none says when or gives a trigger phrase, all are under 1,024 characters. The longer manifest
  descriptions (`extension.yml:25-40`, 62 to 107 characters) are dead text.
- `speckit.progress.hook`: hook-only, 507 bytes, listed under `events:` only. It does not occupy a slot: the installed
  renderer iterates `manifest.commands` (`extensions/__init__.py:1117,1655,2527`) and the dispatcher finds the file by
  name (`_find_command_template`, events module line 124). `tests/test_extension.py:13-25` guards this. Since 1.1.2 it
  replaced five listed hook commands that cost ten skills and tripped Codex's budget (`CHANGELOG.md:21`). Nothing to do.
- Catalog weight: 5 entries per host; about 500 tokens of metadata on Claude at the documented 100 tokens per skill;
  235 of Codex's 8,000 characters.

### 5. Hooks that could replace prose

- Already enforced by the CLI (see lens 1): `decide` refusal, note sanitising and cap, error format. The prose repeats
  them in `SKILL.ext.md:33-37`.
- "Never spawn ... an agent solely to maintain it" is not enforceable by a hook with evidence available here (a
  PreToolUse deny would need to read intent); keep one copy.
- The five host events are themselves the hook that replaces the legacy prose; the remaining cost is their launch chain,
  not prose.

### 6. Claude Code versus Codex

- Wiring: Spec Kit emits Claude entries into `.claude/settings.json` (`events_config_file`, installed
  `integrations/claude/__init__.py:67`) and Codex entries into `.codex/config.toml` as `[[hooks.<Event>]]` blocks
  (`integrations/codex/__init__.py:44`, events module lines 1483 to 1500). Both carry `matcher`, timeout 10 + 5
  (`EVENT_TIMEOUT_BUFFER`, events module line 72) and the same `python .specify/events.py speckit.progress.hook <event> 10`.
  Claude's command is prefixed with `${CLAUDE_PROJECT_DIR}/`; Codex's is relative, so Codex must start at the repository
  root (`docs/hosts.md:26`).
- Event count: Spec Kit maps `session_end` for Codex too (`integrations/codex/__init__.py:40`) and Workflow tells the user
  to approve five Codex hooks (`extensions/workflow/README.md:160-162`); the extension's own installer writes four
  (`CODEX_EVENTS` excludes SessionEnd, `hooks_install.py:36`) and `docs/hosts.md:22` calls the Codex session end event
  "unverified: none is documented", while the first report's verified table lists SessionEnd among Codex's 12 events.
- Host detection inside the hook is heuristic (`scripts/hook.py:52-57`: `turn_id`, `/.codex/`, `rollout-`, or
  `CODEX_HOME` without `permission_mode`); the dispatcher passes no host. Claude is the default.
- Status line: Claude only (`statusline.py:1`, writes `.claude/settings.json` at line 77). Codex gets model and effort
  from the rollout tail instead (`hosts/codex.py:71-96`).
- Approval: every change to the Codex command string forces a re-approval of all five hooks (`CHANGELOG.md:22`); the
  bridge cannot see a stale approval (`reporting.md:24-25`).
- `docs/hosts.md:7` says it was verified against specify_cli 1.1.1.dev0; the installed version is 1.1.4.dev0.

## Defects

| Defect | Effect | Where |
| --- | --- | --- |
| Two Python launches per host event: the dispatcher runs `hooks/dispatch.py` as a subprocess | 200 to 251 ms per event instead of 87 to 137 ms (measured); on every tool call | events module `_run_inline` lines 289 to 327; `extension.yml:49-64` |
| Dispatcher tries `import specify_cli.events` first | +487 ms per event whenever the hook interpreter can import it (686 to 728 ms measured with the uv tool Python) | events module template lines 418 to 437 |
| `post_tool_use` has no matcher | Fires for every tool, including sessions Progress drops after the first log line (200 ms each for nothing) | `extension.yml:58-60`; `scripts/hook.py:94-119` |
| Hosts see the command-file descriptions, not the manifest's | Catalog shows "Choose the report theme"; the better text in `extension.yml` is never rendered | installed `extensions/__init__.py:1741`; `commands/*.md:2`; `extension.yml:25-40` |
| Five commands load the skill for a one-line CLI call | 2,314 of about 2,680 instruction bytes per invocation are unused by four of them | `commands/{status,export,theme,refresh}.md:5` |
| Bridge markers miss natively installed hooks | With `progress hooks install` (command ends `hook.py <event> --managed-by=progress-report`) Workflow reports `refresh` and the coordinator adds a `progress refresh` per attempt while the hooks already refresh | `hooks_install.py:164-174`; `extensions/workflow/scripts/progress_bridge.py:33,110` |
| Codex event count differs by installer (4 vs 5) and the docs disagree with the verified host facts | A natively installed Codex project never gets `session_end`; readers get contradictory guidance | `hooks_install.py:36`; `docs/hosts.md:22`; `extensions/workflow/README.md:160-162` |
| `assets/skill/SKILL.md` is vendored but used by nothing in Sanduq | 3,343 bytes with a diverging verbs table (plan-mode ids, `hooks install`) packaged into every consumer | only `vendor.lock.json` map and `extensions/scripts/benchmark_instructions.py:25` reference it |
| Docs and screenshots ship to consumers; the only agent path to them is two hops deep | 126 KB text + 257 KB PNG per project; an agent following `verbs.md:4` can pull 60 KB into context | `extensions/scripts/package.py:12-15`; `references/verbs.md:4` |
| Four files opened twice per forced refresh | Minor I/O; upstream | measured; `refresh.py:18-20,46-48`, `theme.resolve` |
| Three prose rules duplicate CLI enforcement; the "never spawn" sentence lives in four files | Prohibition density 1.5 per 100 words in the skill; contradictory wording ("solely", "only", "additional") | `SKILL.ext.md:33-37`; see lens 2 |

## Options

Fractions are of the extension's own cost per run. For `tok` the base is the model-visible tokens per feature
(about 3,300 in the vendored benchmark, of which 1,774 are skill reloads); for `time` the base is the hook wall time
per session (N tool calls times 200 to 251 ms), which dwarfs the CLI verbs. Catalog slots are counted separately.

### PG1. Rewrite the five command descriptions where the hosts read them

- **what**: Write a third-person description with what, when and two trigger phrases into the frontmatter of
  `commands/init.md`, `refresh.md`, `status.md`, `theme.md` and `export.md` (the source Spec Kit renders) and copy the
  same text into `extension.yml` so the two stop diverging. Example for `status`: "Prints the one-line state of the
  Sanduq progress report (stage, lanes, blockers, decisions) or its JSON projection with `--json`. Use when asked
  'where are we', 'progress status' or 'show the report state'." Add a test that every command description is under
  1,024 characters, does not open with an imperative verb, contains "Use when" and a quoted phrase.
- **effort**: S. **tok**: [0, 0]. **time**: [0, 0]. **obs**: improved (routing accuracy; the report's own records are
  untouched). **policy**: none.
- **pros**: Zero risk, both hosts benefit, fixes the dead manifest text. **cons**: Codex re-renders the skills on the
  next `specify extension` run; none otherwise.
- **files**: `commands/*.md` (five), `extension.yml`, `tests/test_extension.py`. **tests**: new description assertions in
  `tests/test_extension.py`; `extensions/scripts/validate_skills.py` unchanged.

### PG2. Load the skill only where it is needed

- **what**: Remove the "Load ... SKILL.md, then run" line from `status.md`, `export.md`, `theme.md` and `refresh.md`;
  their bodies already carry the full CLI line and the relay rule. Keep it in `init.md`, and add to `init.md` the one
  sentence the agent needs later ("record lanes, blockers and notes with the verbs in the skill"). Leave
  `SKILL.ext.md` as the entry for the record verbs. The skill is then read once per feature (init) and on
  re-orientation, not on every status or export call.
- **effort**: S. **tok**: [0.10, 0.30] (each avoided skill read is about 580 tokens of a 3,300-token feature; the
  benchmark's resume and compaction rows are 887 each). **time**: [0, 0.02]. **obs**: unchanged. **policy**: none.
- **pros**: Largest instruction saving available; four commands become self-contained pointers like Workflow's.
  **cons**: An agent that calls `status` first in a fresh session will not have seen the "never spawn an agent to
  maintain it" rule until it runs `init` or reads the skill; mitigated by keeping the relay sentence in each body.
- **files**: `commands/status.md`, `export.md`, `theme.md`, `refresh.md`, `init.md`. **tests**:
  `tests/test_extension.py` (assert only `init.md` loads the skill); `test_skill_entry_is_short_and_deterministic` unchanged.

### PG3. Call `scripts/hook.py` directly from the host hook files (drop the dispatcher layer)

- **what**: Replace the five `events:` entries in `extension.yml` with native hook entries written at install time by the
  Sanduq installer (`extensions/workflow/scripts/install.py --with progress` calling `progress hooks install --host
  <host>`), so each event is one interpreter running `scripts/hook.py <event>` instead of
  `.specify/events.py` plus a subprocess. Delete `hooks/dispatch.py` and `commands/speckit.progress.hook.md`. Extend
  `progress_bridge.py` `HOOK_MARKERS` to recognise `hook.py` entries (today it would report `refresh` mode). Add
  SessionEnd to `CODEX_EVENTS` (upstream, one line) so both installers write five events.
- **effort**: M. **tok**: [0, 0]. **time**: [0.40, 0.55] (per event 251 to 137 ms bound, 200 to 87 ms unbound; and the
  +487 ms `specify_cli` import can no longer happen). **obs**: unchanged (same `hook.py`, same payload, same files).
  **policy**: `progress.hook_wiring: speckit | native`, default `speckit`; `--with progress` keeps today's behaviour
  unless the key is set.
- **pros**: Halves the per-tool-call cost with code that already exists (`hooks_install.py` is 19 KB and tested
  upstream); one entry path on both hosts; Spec Kit's path-confinement and interpreter resolution no longer matter.
  **cons**: Spec Kit no longer tracks or removes the hooks (`specify extension remove progress` leaves entries; the
  installer must call `progress hooks uninstall`); Codex users re-approve five hooks once; `specify extension add
  progress` alone wires nothing until the installer runs; the `events:` block that Spec Kit validates disappears, so
  `tests/test_extension.py:13-25` is rewritten.
- **files**: `extension.yml`, `hooks/dispatch.py` (delete), `commands/speckit.progress.hook.md` (delete), `README.md`,
  `tests/test_extension.py`; cross-cutting `extensions/workflow/scripts/install.py`,
  `extensions/workflow/scripts/progress_bridge.py`, `extensions/workflow/tests/test_progress_shim.py`; **upstream**
  `scripts/sanduq_progress/hooks_install.py:36` (Codex SessionEnd) and `docs/hosts.md:22`. **tests**: bridge mode tests
  with a native `hook.py` entry; installer test that `--with progress` writes and removes the five entries per host.

### PG4. Opt-in matcher for `post_tool_use`

- **what**: Add `progress.post_tool_matcher` (default empty, meaning every tool, exactly as today). When set, the
  installer writes it as the `PostToolUse` matcher on both hosts (Spec Kit path: `extension.yml` `matcher:`; native path:
  `hooks_install.py` group). A sensible value is `Bash|Task|Agent|spawn_agent`: the bind handshake needs only the
  shell tool (`scripts/hook.py:116,132-133`), child lanes need only the sub-agent tools (`hosts/claude.py:46-47`), and
  rollout fields are read on other events (`sanduq_progress/hook.py:16,61`).
- **effort**: S. **tok**: [0, 0]. **time**: [0.30, 0.60] (fraction equals the share of tool calls that do not match;
  the share was not measured here and depends on the session's tool mix). **obs**: reduced when the key is set:
  `last_event_at` and the stale banner move only on matched tools, so a long run of Read and Edit calls looks idle for
  up to `stale_after_seconds` (600). Unchanged at the default. **policy**: `progress.post_tool_matcher`, default "".
- **pros**: The biggest runtime lever that needs no new code path; a user who wants exact activity keeps the default.
  **cons**: Reduces observability by design; the manifest is static, so the matcher is applied at install time (a change
  needs a reinstall or `progress hooks install`).
- **files**: `extension.yml`, `README.md` (document the key and its effect on the banner); **upstream**
  `scripts/sanduq_progress/hooks_install.py:34-36` if the native path is also to honour it. **tests**: manifest test
  that the matcher is written only when the key is set.

### PG5. Cut the two-hop path into the docs and drop the unused vendored skill entry

- **what**: Change `references/verbs.md:4` to name `docs/contracts.md` and `docs/commands.md` as human references ("not
  needed to run a verb") so an agent following "Details" stops at 4.8 KB (**upstream**, one line). Remove the
  `assets/skill/SKILL.md` mapping from `vendor.lock.json` (it is read by nothing in Sanduq) and the matching glob in
  `extensions/scripts/benchmark_instructions.py:25`. Add `docs/assets` (257 KB of PNGs) to `package.py` `EXCLUDE` or
  move the three screenshots to the repository's docs so consumers do not receive them.
- **effort**: S. **tok**: [0, 0.03] (only sessions whose agent followed both hops lose the 60 KB read; most do not).
  **time**: [0, 0]. **obs**: unchanged. **policy**: none.
- **pros**: Removes a diverging second verbs table and 260 KB per consumer project; aligns with the one-level rule.
  **cons**: README image links must move with the PNGs; the upstream line waits for an agent-tools release and a vendor
  bump.
- **files**: `vendor.lock.json`, `extensions/scripts/benchmark_instructions.py`, `extensions/scripts/package.py`,
  `README.md`; **upstream** `references/verbs.md`. **tests**: `tests/test_extension.py:43-47` (stable paths) unchanged;
  package test that `docs/assets` is absent from the archive.

### PG6. Fold `hooks/dispatch.py` into `scripts/hook.py` (cheap variant when PG3 is not taken)

- **what**: `sanduq_progress.hook.handle` already derives the event from `hook_event_name` when the argument is empty
  (`sanduq_progress/hook.py:39`); only the fast path `quick_unbound` needs the event (`scripts/hook.py:116`). Make
  `scripts/hook.py` sniff `"hook_event_name"` from the raw payload when `argv[1]` is empty (**upstream**, about six
  lines, the regex from `dispatch.py:18-22`), then point `commands/speckit.progress.hook.md` at
  `scripts: py: scripts/hook.py` and delete `hooks/dispatch.py`.
- **effort**: S. **tok**: [0, 0]. **time**: [0, 0.03] (one `importlib` exec and a regex per event; the interpreter
  launches stay). **obs**: unchanged. **policy**: none.
- **pros**: One entry file for both the Spec Kit path and the native path; one less Sanduq-owned file to test.
  **cons**: Needs an agent-tools release first; the saving is small.
- **files**: `commands/speckit.progress.hook.md`, `hooks/dispatch.py` (delete), `tests/test_extension.py:27-36`;
  **upstream** `scripts/hook.py`. **tests**: move `test_dispatch_reads_the_event_from_the_payload` to the upstream
  `hook.py` test.

### PG7. Remove the rules the CLI enforces and keep one copy of the shared sentences

- **what**: In `SKILL.ext.md` drop rules 3 and 4 (the CLI refuses `decide` under Workflow and sanitises notes) and
  replace them with one line "the CLI refuses what the contract forbids; fix the cause the error names"; keep rule 1,
  2, 5. Keep the "never spawn" sentence in the skill (two tests assert it) and make `reporting.md:5` and
  `extensions/workflow/README.md:168` point to it instead of restating it with different wording. Collapse the three
  Codex approval paragraphs to the one in `extensions/workflow/README.md` and link it from `reporting.md`.
- **effort**: S. **tok**: [0.02, 0.05] (about 90 words out of the skill and 120 out of the Workflow stage reference,
  read on every Execute claim). **time**: [0, 0]. **obs**: unchanged. **policy**: none.
- **pros**: Fewer prohibitions (6 to 3 in the skill), one wording for the rule, no behaviour change. **cons**: Touches
  Workflow's `reporting.md` (cross-cutting); `test_skill_entry_is_short_and_deterministic` must keep passing.
- **files**: `skills/progress/SKILL.ext.md`, cross-cutting `extensions/workflow/skills/workflow/references/reporting.md`,
  `extensions/workflow/README.md`. **tests**: `tests/test_extension.py:49-53`, `extensions/workflow` reference tests
  that grep `reporting.md`.

## Not proposed, and why

- A shorter verb prefix (13 tokens per typed verb, about 180 per feature): Spec Kit confines event scripts to the
  extension directory and the hosts give no PATH entry, so every shim is another file to install for a 7 percent saving
  on typed verbs. Left out.
- A resident process for the hooks: removes the 58 ms interpreter floor but adds a daemon to both hosts' lifecycles.
  PG3 and PG4 reach most of the saving with code that already exists.
- Registering fewer than five user commands: each maps to a verb a user types; `refresh` is the only candidate and
  Workflow's `refresh` mode calls it.
