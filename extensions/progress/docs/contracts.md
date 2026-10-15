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
    lock                 per-feature lock: {"pid", "host", "started_at"}
.specify/progress/
  config.json            {"feature_dir_mode": "auto", "debounce_seconds": 5, "stale_after_seconds": 600,
                          "statusline": {"enabled": bool, "chained": "<previous command or null>"}}
  theme.json             progress.theme.v1 (optional; preset default "sanduq")
  bindings.json          session bindings (see Binding)
```

The feature directory is resolved in order: `--feature <dir>`; `SPECIFY_FEATURE` env; Workflow checkpoint `feature`;
current git branch matching `specs/<branch>`; else error `PROGRESS_NO_FEATURE` (one line).

## facts.jsonl (`progress.facts.v1`)

One JSON object per line, UTF-8, `\n` terminated, appended with flush+fsync under the lock. Readers skip a torn
final line and report it in diagnostics. Lines are never rewritten; later lines supersede earlier ones by `id`.

Common fields: `v` (1), `ts` (UTC ISO-8601 `Z`), `kind`, `id`, `actor` (`user` | `agent:<stable-id>` | `hook` |
`legacy`), `source` (`cli` | `workflow-shim` | `import`).

Forbidden content: secrets, tokens, absolute paths outside the repo, prompt or transcript text. Free text fields are
capped at 200 characters and stripped of control characters.

| kind | fields |
|---|---|
| `lane` | `id` (`L1`…), `tasks` (list of task ids), `owner` (stable agent id or null), `label` (≤60), `requested` {`harness`,`model`,`effort`} (requested values, never observed), `state` (`open`/`closed`) |
| `block` | `id` (`B1`…, assigned by CLI), `target` (task id or lane id), `by` {`type`: `lane`/`task`/`decision`/`external`, `ref`: id or text}, `state` (`open`/`resolved`), `resolved_at` |
| `decision` | `id` (`D1`…; plain spec-kit only), `question` (≤200), `options` (list), `status` (`pending`/`made`/`withdrawn`), `selected`, `decided_by` (`user`/`agent-recommendation`/`assumption`), `evidence` (≤200, e.g. URL or "chat") |
| `note` | `id` (`N1`…), `text` (≤200), `target` (optional task/lane id) |
| `attempt` | legacy/shim only: `lane`, `agent`, `status`, `started_at`, `ended_at`, `usage` (as in legacy progress.py), `origin`=`legacy` |

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

`ended_at` stays null until terminal evidence exists (tool result, stop event of that child). `last_observed_at` is
separate. Parent usage is never attributed to children.

## Binding

A CLI process cannot know the host session id, so binding is a two-step explicit handshake:

1. `progress init` / `progress bind` (run by the coordinator through its shell tool) writes a pending bind
   `{feature, worktree, nonce, created_at}` to `bindings.json` (expires after 120 s) and prints the nonce in its line.
2. The host's `post_tool_use` payload for that same shell call (tool input contains `progress` + `bind`/`init` and the
   nonce, or the tool response contains the nonce) carries `session_id`; the hook converts the pending bind into
   `{session_id, host, feature, worktree, bound_at}`.

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
`elapsed` = wall time since start; `active` = sum of observed active intervals (only when a host provides interval
evidence, else `fidelity:"unknown"`). Elapsed is never labelled as work time.

Task state per lane: `done` = checkbox checked in tasks.md; `blocked` = open blocker targeting the task or its lane;
`active` = lane active and task is the lane's first not-done, not-blocked task (or explicitly started by a
delegation attempt); `waiting` = everything else not done. `depends_on` is parsed only from documented annotations
in the task line: `(depends on T001, T002)` or `(after T001)`; `[P]` sets `parallel:true` only. Task IDs inside code
spans/blocks or other prose are ignored.

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
progress hook <event>                                                   -> reads host JSON on stdin; never prints on success
```

Exit codes: 0 ok, 2 usage error, 3 refused (authority/binding), 4 lock busy (verbs retry 3× with 200 ms backoff first).
Error lines start with `progress: error <CODE>`.

## Hook behaviour

`progress hook <event>`: parse stdin (tolerate empty/invalid → diagnostics, exit 0). Update the host snapshot under the
lock. Debounce: if the last refresh is younger than `debounce_seconds`, set `dirty=true` and exit; else refresh.
`stop` and `session_end` always refresh. Any exception → diagnostics, exit 0, no stdout (never block the host).

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
