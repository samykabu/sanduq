# Hosts: how Progress is invoked and what it reads

Verified on 2026-10-15 against the installed spec-kit (`specify_cli` 1.1.1.dev0, `specify_cli/events/__init__.py`
and `specify_cli/integrations/base.py`), https://code.claude.com/docs/en/hooks and `/statusline`. Items marked
**unverified** were not confirmed against a running host.

## Spec Kit event dispatch (verified in source)

1. The integration writes a native hook whose command is
   `<python> <project>/.specify/events.py <command-name> <event> [<timeout>] [<envelope>] [<native-event>]`.
2. The dispatcher locates the extension's command template (`.specify/extensions/<id>/commands/*.md`) by command
   name and parses its `scripts:` frontmatter, e.g. `scripts: { py: scripts/hook.py post_tool_use }`.
3. **The event name is not passed to the script.** The dispatcher accepts it only for argv compatibility. The script
   receives exactly the tokens written in the `scripts:` value. Progress therefore needs **one command template per
   event**, each baking the event into its `scripts:` line. The payload's own `hook_event_name` is a fallback only.
4. Variant selection (`IntegrationBase.select_script_variant`): the requested variant comes from
   `.specify/init-options.json` key `script` (`sh`|`ps`|`py`), default `ps` on Windows and `sh` elsewhere. If the
   requested variant is missing from `scripts:`, it falls back to the platform variant, then the other one, then
   `py`. **Declaring only a `py:` entry is therefore valid on every platform** and avoids a PowerShell or bash
   start-up on each hook. The `py` variant runs under the project's resolved interpreter
   (`resolve_python_interpreter`), with the script path anchored at `.specify/extensions/progress/` and confined to it.
5. Process contract: `subprocess.run(argv, input=<stdin text decoded as UTF-8>, capture_output=True, cwd=<project root>,
   timeout=<per-handler, default 120 s>)`. The environment is inherited (no extra variables). Stdin is capped at
   1 MiB. **Stdout is forwarded to the host as context**, so Progress must stay silent; a non-zero exit forwards
   stderr and the return code, so the hook always exits 0.
6. Only six canonical events exist: `session_start`, `pre_tool_use`, `post_tool_use`, `session_end`,
   `user_prompt_submit`, `stop`. There is **no subagent start or stop event**. Consequences:
   - a foreground subagent ends when its parent's `Task`/`Agent` tool result arrives;
   - a background subagent, and a Codex `spawn_agent` (its response says only that the agent exists), stays `running` until a `stop` payload carrying its `agent_id` is delivered
     (**unverified** that hosts deliver one); otherwise it ages into lane status `waiting` after
     `stale_after_seconds`, never into a fabricated `done`.

Suggested extension manifest fragment:

```yaml
events:
  session_start:      { command: speckit.progress.hook-session-start }
  post_tool_use:      { command: speckit.progress.hook-post-tool-use, matcher: ".*", timeout: 10 }
  pre_tool_use:       { command: speckit.progress.hook-pre-tool-use, matcher: "Task|Agent", timeout: 10 }
  stop:               { command: speckit.progress.hook-stop, timeout: 20 }
  session_end:        { command: speckit.progress.hook-session-end, timeout: 20 }
```

Each template contains `scripts:\n  py: scripts/hook.py <event>`, a standard-library entry that returns before importing Progress for an unbound
session (about 30 ms, the interpreter start-up) and otherwise runs the same handler as `progress.py hook <event>`.

## Claude Code payloads (verified from docs)

- Hooks: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `permission_mode`, `effort {level}`, and inside a
  subagent `agent_id` plus `agent_type`. Tool events add `tool_name`, `tool_input`, `tool_use_id`, and
  `tool_response` on post. The `Task`/`Agent` tool input fields (`subagent_type`, `description`, `model`,
  `run_in_background`) and the `tool_response` shape (`agentId`) are read defensively (**unverified**).
  A hook payload has no `model`; it is recorded only if present.
- Statusline stdin: `model {id, display_name}`, `effort {level}` (absent when unsupported),
  `context_window {used_percentage, context_window_size, total_input_tokens, current_usage}` (percentage may be null
  early; `total_input_tokens` is cumulative and unused, `used_tokens` is the sum of the `current_usage` counters or unknown), `cost {total_duration_ms, total_api_duration_ms}`, `session_id`, `transcript_path`, `workspace`.
  `total_duration_ms` is session run time, not active work time, so `orchestrator.active` stays unknown.
- `settings.json` shape: `"statusLine": {"type": "command", "command": "...", "padding": n}`.

## Codex payloads (partly unverified)

Fields taken from the task brief: `session_id`, `turn_id`, `agent_id`, `agent_type`, `transcript_path`, `model`,
`tool_name`/`tool_input`/`tool_response`. Host detection (`turn_id`, a `rollout-` or `.codex` transcript path)
defaults to Claude when ambiguous; `progress hook --host codex` forces it. Parent linkage keys tried:
`parent_session_id`, `parent_thread_id`, `forked_from_session_id`, `forked_from_id`.
Effort and context come from the rollout JSONL via `hosts/codex.py` (`ROLLOUT_ADAPTER`): last `turn_context`
(`model`, `effort` | `reasoning_effort` | `collaboration_mode.settings.reasoning_effort`) and last `token_count`
event (`info.last_token_usage`, `info.model_context_window`) in the final 512 KiB, fidelity `partial`. An unknown
shape yields unknown, never a guess. Only numbers and the model/effort words are retained.

## Binding

`progress init` or `progress bind` prints `bind=<nonce>`. The `post_tool_use` payload of that shell call binds the
session when the tool input mentions `progress` and (`bind`|`init`) with the nonce, or the tool response contains the
nonce, within 120 s, with `cwd` inside the worktree. `.specify/progress/bindings.json` is added to
`.git/info/exclude` because it holds local session ids. Unbound observations are dropped and logged in
`.specify/progress/diagnostics.log`.

## Statusline wrapper

`progress.py statusline install` points `statusLine.command` at `python[3] "<script>" statusline` (padding kept),
stores the previous object in `config.json` (`statusline.previous`, and `chained` when it was a command) and
restores it exactly on `uninstall`. At run time the wrapper records the snapshot for bound sessions only, then runs
the chained command with the same stdin and prints its stdout byte for byte.

## Integration notes for the theme module (Lane B)

Progress imports `sanduq_progress.theme` lazily and calls `resolve(project_root) -> dict`,
`render_css(resolved) -> str` and `cli(argv: list[str]) -> int`. For the `theme` verb, `argv` is every token after
`theme` (for example `["--preset", "cobalt"]`); the project root is passed through `SANDUQ_PROGRESS_ROOT`. After
`cli` returns 0 the verb regenerates `.view/theme.css` from `resolve`/`render_css`. If the import fails the verb
writes a minimal fallback `theme.css` and prints `progress: error PROGRESS_THEME_UNAVAILABLE` (exit 2).
UI files are copied from `extensions/progress/assets/ui/` at `init`; when that directory is absent a diagnostic is
logged and nothing is created.

## Projection details worth knowing

- `events` are chronological (oldest first), the last 30.
- Workflow lane ids: facts lanes `L#`; delegation identities without a facts lane `W#`; host children `C#`;
  plain mode adds `coordinator`. A facts lane whose `owner` equals a delegation identity absorbs that identity's attempts.
- `orchestrator.elapsed` is the statusline's session duration when present, otherwise wall time since
  `feature.started_at` (fidelity `estimated`).
