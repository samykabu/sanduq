# Progress contracts (v1)

These contracts are normative. Code and tests follow them. Change them only with a version bump.

## Principles

1. The report is a **projection**. It is rebuilt from producers on every refresh and can be deleted at any time.
2. Producers keep their authority: `tasks.md` owns task text and checkbox state, Workflow owns checkpoint, delegation
   ledger and decisions. Progress never writes to producer files.
3. `facts.jsonl` holds only facts no producer records: lane assignment, blocker, plain spec-kit decision, note.
4. Every measured value carries provenance. Unknown is a value, never a guess.
5. A successful automatic refresh writes nothing to stdout. Model-visible output exists only for explicit CLI verbs,
   and is one line.
6. Never spawn, keep alive, message or poll an agent only to maintain the report.
7. Progress must not import Workflow code. It reads Workflow files as versioned JSON/Markdown only.

## Layout

```
specs/<feature>/progress/
  facts.jsonl            tracked in git (owner decision D4)
  .view/                 git-ignored (Progress writes `specs/*/progress/.view/` to .git/info/exclude at init)
    report.json          projection, schema sanduq.progress.v2
    data.js              window.__SANDUQ_PROGRESS__ = <report.json>;   (file:// safe)
    index.html           static shell, copied from assets/ui at init/upgrade, never templated with data
    blocks.js            static block renderers + data.js poller
    base.css             static layout styles (copied like index.html)
    theme.css            generated from the resolved theme (tokens only)
    layout.js            generated: window.__SANDUQ_PROGRESS_LAYOUT__ (block order, hidden, density, title, logo)
    host/<host>-<session>.json   host snapshots (progress.host.v1)
    state.json           collector cursors, debounce stamp, dirty flag, last refresh rev
    diagnostics.log      bounded (rotate at 256 KB, keep 1)
    lock                 per-feature lock held by the OS for the life of the process (msvcrt.locking on Windows,
                         fcntl.flock elsewhere); the OS drops it if the process dies, so there is no stale recovery.
                         The file content {"pid", "host", "started_at", "token"} is diagnostic only
.specify/progress/
  config.json            {"feature_dir_mode": "auto", "debounce_seconds": 5, "stale_after_seconds": 600,
                          "statusline": {"enabled": bool, "chained": "<previous command or null>"}}
  theme.json             progress.theme.v1 (optional; preset default "sanduq")
  bindings.json          session bindings (see Binding)
```

A feature directory is always `specs/<dir>`: `.` and `..` components are rejected, and the resolved directory must be a
direct child of the resolved `specs/` directory (a symlinked feature pointing elsewhere is refused). The `progress/`
and `.view/` output directories must also resolve inside it; otherwise the command fails with `PROGRESS_NO_FEATURE`
(hooks drop the event) before anything is written.

The feature directory is resolved in order: `--feature <dir>`; `SPECIFY_FEATURE` env; Workflow checkpoint `feature`;
current git branch matching `specs/<branch>`; else error `PROGRESS_NO_FEATURE` (one line).

## facts.jsonl (`progress.facts.v1`)

One JSON object per line, UTF-8, `\n` terminated, appended with flush+fsync under the lock. Readers skip a torn
final line and report it in diagnostics. Lines are never rewritten; later lines supersede earlier ones by `id`.

Common fields: `v` (1), `ts` (UTC ISO-8601 `Z`), `kind`, `id`, `actor` (`user` | `agent:<stable-id>` | `hook` |
`legacy`; `<stable-id>` is 1-64 characters of `A-Za-z0-9._-`, anything else is refused), `source` (`cli` |
`workflow-shim` | `import`).

Forbidden content: secrets, tokens, absolute paths outside the repo, prompt or transcript text. Free text fields are
capped at 200 characters and stripped of control characters. The whole record is validated before it is appended, not
only the free text: every string in it (including `actor`, `owner`, `label`, `requested.*`, `usage.*`) is checked for
secrets and absolute paths. An absolute path is a drive path (`C:\...`), a UNC path (`\\host\share`, `//host/share`)
or a POSIX path starting with `/`, on any platform; it is allowed only when it lies inside the repository root by path
components (`<root>-other/x` is outside; `..` segments are resolved first). Log paths in attempt usage follow the same
rule: inside the repo they are stored repo-relative, any other absolute path (Windows or POSIX, whatever the executing
platform) becomes `external:<name>`.

| kind | fields |
|---|---|
| `lane` | `id` (`L1`…), `tasks` (list of task ids), `owner` (stable agent id or null), `label` (≤60), `requested` {`harness`,`model`,`effort`} (requested values, never observed), `state` (`open`/`closed`) |
| `block` | `id` (`B1`…, assigned by CLI), `target` (task id or lane id), `by` {`type`: `lane`/`task`/`decision`/`external`, `ref`: id or text}, `state` (`open`/`resolved`), `resolved_at` |
| `decision` | `id` (`D1`…; plain spec-kit only), `question` (≤200), `options` (list), `status` (`pending`/`made`/`withdrawn`), `selected`, `decided_by` (`user`/`agent-recommendation`/`assumption`), `evidence` (≤200, e.g. URL or "chat") |
| `note` | `id` (`N1`…), `text` (≤200), `target` (optional task/lane id) |
| `attempt` | legacy/shim only (`progress attempt record`): `lane` (or null with `label` for overhead), `run`, `status`, `started_at`, `ended_at`, `usage` {`fidelity` exact\|reported\|unavailable, `agent`, `harness`, `model`, `fresh_input`, `cache_read`, `cache_write`, `output`, `reasoning`, `since`, `until`, `log` (repo-relative, or `external:<name>`), `reason`}, `origin`=`legacy`; `actor` `legacy`, `source` `workflow-shim`. One fact per (lane, run); a later record supersedes it. |

Legacy attempts are supplemental. The projection appends them to the lane's `attempts` with `origin:"legacy"` after the
producer's attempts, skips a run id a producer already reports for that lane, and never lets them change a lane's
status. Attempts without a lane appear under a top-level `overhead` list (only when present).

When Workflow's `decisions.json` exists, `decision` facts are refused (`PROGRESS_DECISION_AUTHORITY`).

## Host snapshot (`progress.host.v1`)

File `host/<host>-<session_id>.json`, merged field-by-field under the lock (never replaces unrelated fields).

```json
{"v":1,"host":"claude|codex","session_id":"…","parent_session_id":null,"agent_id":null,
 "bound_feature":"specs/…","first_seen":"…","last_observed_at":"…",
 "model":   {"value":"…","source":"statusline|hook|rollout","observed_at":"…","fidelity":"exact|partial|unknown"},
 "effort":  {…same shape…},
 "context": {"value":{"used_percent":41.2,"used_tokens":82000,"window":200000}, …},
 "elapsed_ms": {…}, "api_ms": {…},
 "children": {"<tool_use_id|agent_id>": {"kind":"subagent","subagent_type":"…","description":"…(≤80)",
              "model":{…},"background":true,"started_at":"…","ended_at":null,"last_observed_at":"…","status":"running|done|failed|unknown"}}}
```

Child `model` and `effort` are measurements. A child model with `fidelity:"partial"` is the requested alias from the
launching `Task`/`Agent` call and never replaces an exact (observed) model, whichever event arrives first. A child's
effort comes from the `effort.level` of the hook payload fired inside that child. `context.value.used_tokens` is the
sum of the integer `current_usage` counters of the Claude statusline (`input_tokens`,
`cache_creation_input_tokens`, `cache_read_input_tokens`), i.e. what the context holds now; the cumulative
`total_input_tokens` is never used, and without current usage the token count is `null` (unknown).

`ended_at` stays null until terminal evidence exists (tool result, stop event of that child). `last_observed_at` is
separate. Parent usage is never attributed to children.

## Binding

A CLI process cannot know the host session id, so binding is a two-step explicit handshake:

1. `progress init` / `progress bind` (run by the coordinator through its shell tool) writes a pending bind
   `{feature, worktree, nonce, created_at}` to `bindings.json` (expires after 120 s) and prints the nonce in its line.
2. The host's `post_tool_use` payload for that same shell call (tool input contains `progress` + `bind`/`init` and the
   nonce, or the tool response contains the nonce) carries `session_id`; the hook converts the pending bind into
   `{session_id, host, feature, worktree, bound_at}`.

A fresh pending handshake that matches the tool call takes precedence over an existing binding for that session: the
session is rebound to the feature that was just initialised (observations then go to the new feature).

`progress bind --session <id>` binds directly when the id is known (tests, hosts without hooks).
A later `session_start` with a bound `session_id` (resume) keeps the binding. Hooks attach observations only to a bound
session, or to a child whose parent is verified from the payload (Claude: same `session_id` with `agent_id`; Codex:
`agent_id`/parent thread fields when present). Cwd inside the bound worktree validates a binding; it never creates one.
Unbound or ambiguous observations are dropped and counted in diagnostics.

## Projection (`sanduq.progress.v2`)

```json
{
 "schema":"sanduq.progress.v2","rev":17,"generated_at":"…","stale_after_seconds":600,
 "collection":{"automatic":true,"hosts":["claude"],"dirty":false,"last_event_at":"…","diagnostics":0},
 "feature":{"id":"624-…","title":"…","dir":"specs/624-…","branch":"…","issue":{"number":624,"url":"…"}|null,
            "stage":{"value":"execute","source":"workflow-checkpoint"}|null,"started_at":"…","workflow":true},
 "orchestrator":{"host":"claude","session_id":"…","model":M,"effort":M,"context":M,
                 "elapsed":M,"active":M,"since":"…"},
 "lanes":[{"id":"L1","label":"…","owner":"…","origin":"facts|workflow-delegation|host-child|coordinator",
           "requested":{"harness":"…","model":"…","effort":"…"},
           "observed":{"model":M,"effort":M},
           "status":"pending|active|waiting|blocked|done|failed",
           "elapsed":M,"active":M,"last_observed_at":"…",
           "attempts":[{"run_id":"…","status":"…","started_at":"…","ended_at":null,"tokens":{…}|null,"fidelity":"…"}],
           "tasks":{"active":["T003"],"waiting":["T004"],"blocked":[{"task":"T005","by":[{"type":"lane","ref":"L2","blocker":"B3"}]}],"done":["T001","T002"]}}],
 "unassigned_tasks":{"active":[],"waiting":[],"blocked":[],"done":[]},
 "tasks":{"T001":{"title":"…(≤160)","phase":"…","done":true,"parallel":false,"depends_on":["T000"],"lane":"L1"}},
 "decisions":{"pending":[D],"made":[D]},          // D = {id, question, options, selected, decided_by, at, url, source}
 "blockers":[{"id":"B3","target":"T005","by":{"type":"lane","ref":"L2"},"since":"…","source":"facts|workflow-pause|delegation"}],
 "events":[{"at":"…","kind":"…","text":"…(≤120)"}],   // last 30, derived; notes included
 "summary":{"tasks_total":40,"tasks_done":12,"lanes_active":2,"blocked":1,"decisions_pending":1}
}
```

`M` = measurement `{"value":…, "source":"…", "observed_at":"…", "fidelity":"exact|partial|estimated|unknown"}`.

**Units.** Every duration in the projection (`orchestrator.elapsed`, `orchestrator.active`, `lanes[].elapsed`,
`lanes[].active`) is a whole number of **seconds**; the UI formats them as `1h 2m` / `3m 4s` / `5s`. Host snapshots keep
the host's own `*_ms` fields (`elapsed_ms`, `api_ms`) and the projection converts them. Timestamps are ISO-8601 strings.

`elapsed` = wall time since start. `active` = sum of observed active intervals, and is unknown (`value:null`,
`fidelity:"unknown"`) unless a producer supplies them: a delegation attempt may carry `active_intervals`
(`[{"start","end"}]`, an open end counts to the generation time) and the lane's `active` is their sum with
`fidelity:"partial"`. An attempt's start-to-end span is wall time and is never reported as active work time. Elapsed is
never labelled as work time.

**Observed vs requested model.** `lanes[].observed.model` comes only from explicit evidence: the delegation ledger's
`actual_model` (fidelity `exact`, or `partial` while its evidence is `pending`), a model the run result reports it
actually ran (`model_reported` / `model_observed` in `result.json`, fidelity `partial`, source `run-result`), or a
child's own hook payload. A model that was only asked for (ledger `requested_model`, a run's `model`, a `Task` call's
`model`) goes under `requested` and the observed model stays unknown.

Task state per lane: `done` = checkbox checked in tasks.md; `blocked` = open blocker targeting the task or its lane;
`active` = lane active and task is the lane's first not-done, not-blocked task (or explicitly started by a
delegation attempt); `waiting` = everything else not done. `depends_on` is parsed only from documented annotations
in the task line: `(depends on T001, T002)` or `(after T001)`; `[P]` sets `parallel:true` only. Task IDs inside code
spans/blocks or other prose are ignored.

Host children and assigned lanes. A host child is merged into an assigned lane (facts or delegation lane) when that
lane's `owner` equals, case-insensitively, the child's agent id, the `tool_use_id` it was launched with (the key in
`children`), or its `description` label. A merged child contributes its observed model and effort, and its last
observation time, to the lane; it does not change the lane's status or tasks, and it gets no `C<n>` lane. Only children
that match no lane owner become `host-child` lanes (`C1`, `C2`, ... numbered over the unmatched children).

Workflow decisions. `decisions[].selected` is the option text for a single-selection decision and a list of option texts
for a multiple-selection decision (Workflow stores `selected: ["A","C"]` with `option: null` in that mode, and
`selected: ["B"]` plus `option: "B"` in single mode). `at` is the latest answer timestamp (`updated_at`, falling back to
`created_at`/`at`). A pending or conflicting decision has `selected:null`.

Workflow lanes: one lane per delegation identity (retries and resumes become attempts of the same lane), task ids from
the delegation identity/owned task list when present. Plain spec-kit: one `coordinator` lane by default; host children
appear as `host-child` lanes (unmapped = no tasks, shown as such).

## CLI (one-line output)

```
progress init [--feature DIR] [--statusline yes|no] [--theme PRESET]   -> "progress: ready specs/…/progress/.view/index.html"
progress bind [--session ID]                                            -> "progress: bound <session>"
progress refresh [--final]                                              -> silent on success unless --verbose
progress status [--json]                                                -> one-line summary or projection JSON
progress lane L1 --tasks T001-T004,T009 [--owner ID] [--label T] [--harness H --model M --effort E] [--close]
progress block T007 --by L2|T003|SD2|ext:"text"                         -> "progress: B4 open T007 by L2"
progress unblock B4 | --all-for T007
progress decide ask "question" --options a,b,c                          -> "progress: D2 pending"
progress decide made D2 b --by user|agent-recommendation|assumption [--evidence URL]
progress note "text" [--target T005]
progress theme --preset sanduq|cobalt|emerald|classic | --from-illustrate | --file theme.json | --show
progress export [--format md|json] [--out PATH]                         -> deterministic, same projection
progress attempt record (--lane L1 | --overhead LABEL) --run ID --status S [--started T] [--ended T] [--usage-json PATH]
progress runs [--json] [--runs-dir DIR]... [--now T] [--stall-seconds N]  -> progress.runs.v1
progress hook <event>                                                   -> reads host JSON on stdin; never prints on success
```

Exit codes: 0 ok, 2 usage error, 3 refused (authority/binding), 4 lock busy (the OS lock is held by another process; verbs retry 3× with 200 ms backoff first).
Error lines start with `progress: error <CODE>`.

## Runs contract (`progress.runs.v1`)

`progress runs --json` prints one JSON object built from `.delegate/runs/*/{meta.json,journal.jsonl,result.json}` (or
each `--runs-dir`, relative to the repository root). It needs no initialised feature. It is the only supported way for
another extension to read this projection; callers must not import Progress code.

```json
{"schema":"progress.runs.v1","generated_at":"…","stall_seconds":300,
 "runs":[{"run_id":"…","harness":"…","source":"<run dir name>","model":null,"model_reported":null,"started_at":"…","ended_at":null,
          "harness_status":"running|finalizing|stalled|successful|failed|…","phase":"active|finishing|stalled|done",
          "usage":null,"elapsed_seconds":0,"journal_events":0,"latest_event":null,"latest_event_at":null,
          "task_verdict":"unknown","review_verdict":"unknown","next_action":null,"conflict":["harness"]}],
 "duplicates":["run id seen twice"],"malformed":[{"source":"…","error":"…"}],"caveats":["…","…","…"]}
```

`usage` is null unless the harness reported exact counters. The three caveats are part of the contract: elapsed is wall
time and not active time; `stalled` is a heuristic; `harness_status` is a harness verdict and not acceptance. Verdict
words and `next_action` come from a final `result.json` and read `unknown`/null when absent. A final record beats a live
one for the same run id; real disagreement is listed in `conflict`, and the conflicts of every duplicate (across all `--runs-dir` roots) accumulate on the retained record. `model` is the launch request; `model_reported` is the model the harness says it ran (`null` when it did not say), and only that is evidence of the model that ran.

## Hook behaviour

`progress hook <event>`: parse stdin (tolerate empty/invalid → diagnostics, exit 0). Update the host snapshot under the
lock. Debounce: if the last refresh is younger than `debounce_seconds`, set `dirty=true` and exit; else refresh.
`stop` and `session_end` always refresh. A deferred (debounced) event is not invisible: the hook patches the current
`report.json`/`data.js` with `collection.dirty:true` and `collection.last_event_at` and advances `rev` (no producer is
read, nothing is rebuilt) so the UI shows its pending banner; the first hook after the window, a statusline update after
it, `stop`, or any verb performs the real refresh and clears the flag. Any exception → diagnostics, exit 0, no stdout (never block the host).

## Theme (`progress.theme.v1`)

```json
{"v":1,"preset":"sanduq","title":null,"logo":null,"density":"comfortable|compact",
 "blocks":["header","orchestrator","lanes","boards","decisions","blockers","events"],
 "hidden":[],
 "tokens":{"light":{"bg":"#…","surface":"…","text":"…","muted":"…","line":"…","brand":"…","accent":"…",
                    "active":"…","waiting":"…","blocked":"…","done":"…","failed":"…"},
           "dark":{…same keys…}},
 "font":{"sans":"system-ui, sans-serif","mono":"ui-monospace, monospace"}}
```

Colors are validated as `#rgb`/`#rrggbb`. Unknown keys are rejected with a one-line error. `--from-illustrate` maps
Illustrate roles explicitly: paper→bg, paper-2→surface, ink→text, muted→muted, rule→line, accent→accent,
link→brand, accent-tint→active. Status colours keep the preset's values unless set.

## UI

`index.html` loads `theme.css`, `blocks.js`, then `data.js?rev=<n>` by script injection every 3 s (one in-flight load;
older/equal `rev` ignored; load error keeps the last good view and shows a banner). All strings are inserted with
`textContent`. A stale banner shows when `now - generated_at > stale_after_seconds` or `collection.dirty`.
No network, no CDN, no framework.
