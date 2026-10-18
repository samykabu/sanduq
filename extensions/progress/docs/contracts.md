# Progress contracts (v1)

These contracts are normative. Code and tests follow them. Change them only with a version bump.

## Principles

1. The report is a **projection**. It is rebuilt from producers on every refresh. Deleting `.view/` loses nothing but the
   projection: host observations (child identity) live in `.host/`, outside it.
2. Producers keep their authority: `tasks.md` owns task text and checkbox state, Workflow owns checkpoint, delegation
   ledger and decisions. Progress never writes to producer files.
3. `facts.jsonl` holds only facts no producer records: lane assignment, blocker, plain spec-kit decision, note.
4. Every measured value carries provenance. Unknown is a value, never a guess.
5. A successful automatic refresh writes nothing to stdout. Model-visible output exists only for explicit CLI verbs,
   and is one line.
6. Never spawn, keep alive, message or poll an agent only to maintain the report.
7. Progress must not import Workflow code. It reads Workflow files as versioned JSON/Markdown only.

## Layout

A report is either a Spec Kit **feature** report (`specs/<feature>/progress/`, tasks from `tasks.md`) or a **plan**
report (`.progress/<name>/` by default, tasks from a Markdown checklist). The two have the same files and the same
contracts below; only the places named in this section and in "Plan mode" differ. The examples say `specs/<feature>`.

```
specs/<feature>/progress/
  facts.jsonl            tracked in git (owner decision D4)
  .host/                 git-ignored, NOT disposable: host snapshots (progress.host.v1), the durable home of child identity
    .gitignore           a single `*` line, written atomically with the directory (git applies the closest .gitignore first,
                         so a parent rule such as `!claude-*.json` cannot expose a snapshot; the `*` ignores this file too)
    <host>-<session>.json   (older versions kept them in .view/host; the first access moves them here)
    self-report.json     the coordinator's self-report from `progress bind --model/--effort` (see Self-report)
  .view/                 git-ignored and disposable (Progress writes `specs/*/progress/.view/` and `.host/` to .git/info/exclude at init;
                         it also carries the same single-`*` .gitignore; a link at either path is refused)
    report.json          projection, schema sanduq.progress.v3
    data.js              window.__SANDUQ_PROGRESS__ = <report.json>;   (file:// safe). With theme layout "classic" it holds the v2 document instead
    index.html           static shell, copied from assets/ui at init/upgrade, never templated with data
    blocks.js            static block renderers + data.js poller
    base.css             static layout styles (copied like index.html)
    theme.css            generated from the resolved theme (tokens only)
    layout.js            generated: window.__SANDUQ_PROGRESS_LAYOUT__ (block order, hidden, density, title, logo, preset, layout)
    state.json           collector cursors, debounce stamp, dirty flag, last refresh rev (child lane numbers are not kept here: see Host children below)
    diagnostics.log      bounded (rotate at 256 KB, keep 1); never written through a link, by the main writer and by the
                         fast hook entry alike (both use `scripts/sanduq_progress/safelog.py`)
    lock                 per-feature lock held by the OS for the life of the process (msvcrt.locking on Windows,
                         fcntl.flock elsewhere); the OS drops it if the process dies, so there is no stale recovery.
                         The file content {"pid", "host", "started_at", "token"} is diagnostic only
.specify/progress/        (Spec Kit project; `.progress/.project/` when the project has no `.specify`, see Plan mode)
  config.json            {"debounce_seconds": 5, "stale_after_seconds": 600,
                          "statusline": {"enabled": bool, "chained": "<previous command or null>"}}
  theme.json             progress.theme.v1 (optional; preset default "sanduq")
  bindings.json          session bindings (see Binding)
  bindings.lock, diagnostics.log[.1]   runtime files, local only
```

`init` adds the runtime files (`bindings.json`, `*.lock`, `diagnostics.log*` under `.specify/progress/`, and each
`.view/`) to `.git/info/exclude`.

A write never goes through a link: before `facts.jsonl`, any `.view` file (including the lock and copied assets) is
written or opened, a symbolic link or Windows junction at that path is refused with `PROGRESS_UNSAFE_TARGET` (exit 3;
a hook drops the event). Other reparse points, such as cloud placeholders, are ordinary files.

A feature directory is always `specs/<dir>`: `.` and `..` components are rejected, and the resolved directory must be a
direct child of the resolved `specs/` directory (a symlinked feature pointing elsewhere is refused). The `progress/`
and `.view/` output directories must also resolve inside it; otherwise the command fails with `PROGRESS_NO_FEATURE`
(hooks drop the event) before anything is written.

The report is resolved in order: `--plan <name|path>` or `--feature <dir>` (exclusive; a wrong value is an error);
`SPECIFY_FEATURE` env; Workflow checkpoint `feature`; current git branch matching `specs/<branch>` (these three only when
that feature is initialised); the only initialised report; else error `PROGRESS_NO_FEATURE` (one line, listing the
candidates when any exist).

## Plan mode

```
.progress/<name>/            or the --dir directory: any directory inside the repository, never under `specs/`
  facts.jsonl                tracked, identical to feature mode
  plan.json                  tracked, progress.plan.v1: {"schema", "name", "source", "ids": [{"id", "fp"}], "next"}; `fp` is the first 16 hex digits of SHA-256 of the normalised item text. No item text is ever tracked
  .host/                     git-ignored; also holds plan-source.json {"path": "<absolute>", "fingerprint"} for an external
                             plan and plan-keys.json {"<id>": "<normalised text>"}, the only place item text is kept
  .view/                     git-ignored and disposable, identical to feature mode; `.host/` and `.view/` each hold a
                             `.gitignore` with a single `*`. Default `.progress/<name>` needs no extra exclude lines (the wildcards cover it)
.progress/plans.json         tracked; {"dirs": [...]}, only when a --dir outside .progress/ is used
.progress/.project/          project state when there is no .specify/progress: config.json, theme.json, bindings.json,
                             bindings.lock, diagnostics.log[.1]. bindings, locks, the log and config.json are git-ignored
```

- **Target id.** The `feature` value in bindings and in `feature.dir` of the projection is the report directory
  (`.progress/launch`) for a plan. A value of the form `specs/<dir>` is always a feature; anything else is a plan.
- **Project directory.** `.specify/progress` if it exists, else `.progress/.project` if it exists, else
  `.specify/progress` when `.specify/` exists, else `.progress/.project`. The standard-library hook entry applies the
  same rule.
- **Confinement.** The plan report directory has no `.`/`..` components, is not the repository root, is not under `.git`,
  is not under `specs/`, and (links resolved) lies inside the repository, as do its `.view/` and `.host/`.
  Otherwise `PROGRESS_NO_FEATURE` (hooks drop the event).
- **Source reference.** `plan.json` `source` is a repo-relative posix path, or `external:<file name>` for a plan outside
  the repository. Tracked files never hold an absolute path or item text (so nothing in them needs a secret scan); the
  absolute path of an external plan and its path fingerprint are only in `.host/plan-source.json`. Another external file
  with the same name is refused unless `--rebind`. The plan file is only read (at most 1 MiB). `init` writes into a
  `--dir` only when its `plan.json` is absent or `progress.plan.v1`, and only after `git check-ignore` confirms that
  `.view/` and `.host/` are ignored.
- **Items.** A list item `- [ ]`/`- [x]` (markers `-`, `*`, `+`; any indent) outside fenced blocks. Phase: the nearest
  preceding heading of level 2 or deeper. Title: the first level-1 heading. Explicit id: at the start of the item,
  optionally bold, followed by `:`, `.`, `)` or a space; one to three capital letters, an optional dash, digits, and not a
  lane, blocker, decision or note id shape (`L`, `W`, `C`, `B`, `D`, `N`, `SD` plus digits). Unless bold, the id needs two
  digits or more, or the prefix `T` or `US` (so `MP3`, `GPT-4`, `Q3`, `A4`, `ES6` are text). An id already used by an earlier
  item turns the later item into an auto item and writes one diagnostics line. `(depends on …)` and
  `(after …)` list task ids; `[P]` marks a parallel item.
- **Auto ids.** `P<nnn>` (three digits or more), assigned from `plan.json` `ids` in three steps: equal fingerprint,
  then text at least 60 percent similar to the local `.host/plan-keys.json` text (difflib ratio, best first), then `next + 1`. `next` only grows. Normalised text
  is lower-cased, without `*`, `_`, backticks and `~`, whitespace collapsed, 120 characters at most. `plan.json` is
  rewritten under the report lock on a refresh, and only when the map changed; read-only verbs compute the same ids
  without writing.
- **Projection.** Same as for a feature report (v3 by default, v2 on request), with no Workflow stages. `feature` gains `mode: "plan"` and `source`; `feature.id` is the plan
  name, `feature.title` the plan title (else the name), `stage` is null and `workflow` false. No Workflow files are
  read for a plan.

## Native hooks installer

`progress hooks install|uninstall|status` edits the host's hook file (see the commands reference). Every entry it writes
has a command containing `hook.py` and the argument `--managed-by=progress-report`; an entry is "ours" if and only if
both appear. Entries registered by Spec Kit's dispatcher contain `speckit.progress.hook`; when one exists in a file of
the target host the installer writes nothing and exits 3. Commands end in `; exit 0` and use `${CLAUDE_PROJECT_DIR}` (braced)
for Claude project scope. Installs run under one OS-held lock (`<user settings file>.progress-lock`, never taken over by age) that also covers the Spec Kit and other-scope checks, which repeat on every attempt. Writes happen only when the file bytes are unchanged since they were
read (one re-read, then `PROGRESS_HOOKS_CONFLICT`). Entries of this installer in the other scope are refused
(`PROGRESS_HOOKS_DUPLICATE`) unless `--force-both`.

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

File `.host/<host>-<session_id>.json`, merged field-by-field under the lock (never replaces unrelated fields).

```json
{"v":1,"host":"claude|codex","session_id":"…","parent_session_id":null,"agent_id":null,
 "bound_feature":"specs/…","first_seen":"…","last_observed_at":"…",
 "model":   {"value":"…","source":"statusline|hook|rollout","observed_at":"…","fidelity":"exact|partial|unknown"},
 "effort":  {…same shape…},
 "context": {"value":{"used_percent":41.2,"used_tokens":82000,"window":200000}, …},
 "elapsed_ms": {…}, "api_ms": {…},
 "children": {"<tool_use_id|agent_id>": {"kind":"subagent","subagent_type":"…","description":"…(≤80)","agent_id":"…",
              "model":{…},"background":true,"started_at":"…","ended_at":null,"last_observed_at":"…","status":"running|done|failed|unknown",
              "status_at":"…","generation":2,"lane_no":2,"lane_aliases":[3],"agent_link":"provisional"}}}
```

Child `model` and `effort` are measurements. A child model with `fidelity:"partial"` is the requested alias from the
launching `Task`/`Agent` call and never replaces an exact (observed) model, whichever event arrives first. A child's
effort comes from the `effort.level` of the hook payload fired inside that child. `context.value.used_tokens` is the
sum of the integer `current_usage` counters of the Claude statusline (`input_tokens`,
`cache_creation_input_tokens`, `cache_read_input_tokens`), i.e. what the context holds now; the cumulative
`total_input_tokens` is never used, and without current usage the token count is `null` (unknown).

`ended_at` stays null until terminal evidence exists (tool result, stop event of that child). `last_observed_at` is
separate. Parent usage is never attributed to children.

Child identity. A launch is keyed by its `tool_use_id`; the child's own hook events are keyed by its agent id. They are one
child once the tool result carries `agentId`. Before that, an agent-keyed event that matches no entry attaches to the single
running launch of the session that has no agent id yet (`agent_link:"provisional"`); with zero or several open launches it
stays a separate entry. The tool result then confirms the link (same `agentId`) or splits it (a different `agentId`: the
attached agent becomes its own entry and the launch keeps the id the host reported). Only Agent/Task results'
`agentId`/`agent_id` count, plus `id` for Codex `spawn_agent`; no other `id` is an agent id.
`lane_no` is the child's durable `C<n>` number: assigned once, when the entry is created, one above every number any
snapshot ever held. `lane_aliases` are the numbers of entries later found to be the same child; they keep resolving.
Because the number sits in the host snapshot (durable host data, not the disposable view), deleting `.view/` (it is only the projection) or re-keying an
entry (agent id <-> tool_use id) changes no lane id.

## Binding

(`bindings.json` is in the project directory.) A CLI process cannot know the host session id, so binding is a two-step explicit handshake:

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

## Projection (`sanduq.progress.v3`)

`report.json` holds the v3 projection, and `status --json` prints it by default. The Timeline view reads it. The
[v2 projection](#projection-sanduqprogressv2-compatibility) is still available for one release.

**The rule behind every field: no inference from proximity.** A time gap, adjacency, matching text, a model name or
overlapping timestamps never establish identity, a retry, a revalidation, a rejection, an acceptance or membership.
When no explicit record supports a fact, the field is `null` (or an `unknown` measurement) and the UI says so.

```json
{
 "schema":"sanduq.progress.v3","rev":17,"generated_at":"…","stale_after_seconds":600,
 "collection":{"automatic":true,"hosts":["claude"],"dirty":false,"last_event_at":"…","diagnostics":0},
 "feature":{"id":"…","title":"…","dir":"specs/…","branch":"…","issue":{"number":842,"url":"…"}|null,"workflow":true,
            "started_at":M,
            "stage":{"value":"execute","status":"running","validity":"unknown","source":"workflow-checkpoint|workflow-receipts","checkpoint_status":"in-progress"}|null,
            "next_action":{"text":"…","stage":"execute"|null,"kind":"active-claim|next-stage"|null,"evaluated_at":"…"|null,"generation":9|null,"source":"workflow-checkpoint"}|null},
 "orchestrator":{"host":"codex"|null,"session_id":"…"|null,"model":M,"effort":M,"context":M,"host_elapsed":M,"active":M,"since":"…",
                 "provenance":{"model":"host-hook|self-report|none","effort":"…","context":"…","host_elapsed":"…","active":"…"},"note":"…"|null},
 "attention":[{"id":"…","kind":"blocker|decision|failure|stale|telemetry","severity":"high|medium|info","text":"(≤160)","refs":["…"],"since":"…"|null}],
 "stages":[{"id":"execute","label":"Execute","order":10,"selected":true,"status":"pending|running|accepted|excluded",
            "validity":"current|stale|unknown","accepted_at":"…"|null,
            "episodes":[{"id":"execute#ep1","n":1,"source":"workflow-lifecycle|checkpoint-receipt|checkpoint-recovery","fidelity":"exact|partial",
                         "claim_id":"…"|null,"started_at":"…"|null,"ended_at":"…"|null,
                         "outcome":"accepted|rejected-completion|recovered|paused|invalidated|running|unknown","runs":["run id"],"reason":"(≤120)"|null}],
            "unknown_runs":["run id"],"run_count":6,"failed_runs":1,
            "run_time":{"value":123,"source":"delegation-ledger","observed_at":"…","fidelity":"partial","complete":true,"sources":["delegation-ledger"],"label":"summed, may overlap"},
            "models":["…"],"first_start":"…"|null,"last_end":"…"|null,"open":false,"timing":"open|closed|end-unknown|unknown"}],
 "workstreams":[{"id":"tag:A|L3|shared","label":"Workstream A","description":"…"|null,"origin":"facts-marked|tasks-tag|shared",
                 "tasks":{"done":["T001"],"blocked":[],"active":[],"waiting":[]},
                 "owners":[{"agent":"…","from":"…","to":"…"|null}],"run_ids":["…"],"conflicts":[{"task":"T003","workstreams":["L1","L2"]}]}],
 "tasks":{"T001":{"title":"…","phase":"…","done":true,"parallel":false,"depends_on":[],"workstream":"tag:A"}},
 "runs":[{"run_id":"…","identity":"…","stage":"plan"|null,"tasks":["T002"],"episode_id":"…"|null,"workstream":"…"|null,
          "harness":"…","requested_model":"…"|null,"actual_model":M,"effort":M,"started_at":"…","ended_at":"…"|null,"duration":M,
          "worker_status":"successful|failed|abandoned|unverified|running|…","evidence_accepted":true|false|null,
          "candidate_accepted":true|false|null,"retry_of":"run id"|null,"summary":"(≤160)"|null,"conflict":["status"]}],
 "dispatch":[{"intent_id":"…","identity":"…","created_at":"…"|null,"state":"…"}],
 "decisions":{"pending":[D],"made":[D],"sources":[{"name":"facts|workflow|clarification","state":"available|absent|unsupported|invalid","note":"…"}]},
 "timeline":[{"id":"tl-…","at":"…","kind":"stage|decision|failure|recovery|revalidation|note|blocker","text":"(≤140)","refs":["…"],"fidelity":"recorded|partial|observed|inferred"}],
 "history":{"lane_aliases":{"L4":"run:…|identity:…|workstream:L3|lane:L2"},"unresolved":[{"id":"L4","label":"…","owners":[{"agent":"…","from":"…","to":"…"|null}],"reason":"…"}]},
 "sources":[{"name":"workflow-checkpoint","path":"specs/…/workflow/checkpoint.json","fingerprint":"16 hex","generation":111|null,"read_at":"…","bytes":4096,"consistent":true,"note":"…"}],
 "summary":{"tasks_total":23,"tasks_done":23,"stages_selected":16,"stages_accepted":16,"runs_total":89,"runs_failed":5,"decisions_pending":0,"blockers_open":0}
}
```

`M` is a measurement `{"value","source","observed_at","fidelity"}`. `fidelity` is `exact`, `partial`, `estimated` or
`unknown`; `source` says where the value came from (`host-hook`, `self-report`, `delegation-ledger`, `harness`,
`timestamps`, `workflow-checkpoint`, `earliest-evidence`). An aggregate (`run_time`) also carries `complete` (false when a
run has no duration), `sources` and a `label`. A decision is
`D = {key, source, source_id, question, options, answer:{kind:single|multiple|text, value, index}|null, state, revision, answer_digest,
evidence:["display text"], evidence_links:[{text, url}], url, decided_by, observed_at, answered_at, applied:{at, evidence:["…"]}|null, stage}`.

`data.js` also carries `ui: {layout}` (`timeline` or `classic`) beside the document, so an open page switches renderer with the next
data revision after `progress theme --layout`; `report.json` does not have it.

`rev` rises on every refresh and on the cheap patch a debounced hook event makes; the UI uses it as its refresh counter.
`collection`, `rev`, `generated_at` and `stale_after_seconds` mean what they mean in v2.

**Runs.** One entry per delegation `run_id`. If the ledger holds a run twice, the finished record wins and the fields that
disagreed are listed in `conflict`. A ledger row with an `intent_id` and no `run_id` is a `dispatch` intent (it is dropped
once a run carries the same `intent_id`) and is never counted as a run. A host-session child is a run whose id and identity
are `host:<session>:<child>`; it joins a delegation run only when the child record names that `run_id`. The stage suffix
(`stage:plan`) and task suffix (`T002`) of an identity are read only when the identity starts with a feature directory this
report knows: the report's own, the checkpoint's or the ledger's `feature`. An explicit `tasks` list on a ledger row is kept as written.
`stage` of a task run is set only through a recorded claim link (below); otherwise it is `null`, and the run is not in any episode.

- `worker_status` is the harness verdict. `evidence_accepted` is the dispatcher's own acceptance (`accepted_at`): `true` when
  it is recorded, otherwise `null`. A failed or abandoned worker does not make it `false`; no acceptance evidence means unknown.
  `candidate_accepted` is Workflow's exact-claim acceptance of one run: `true` when an `accepted` lifecycle event names the run
  in `candidate_run_id`, `false` when a `rejected-completion` event does, else `null` (the latest event for the run wins).
  `delegation_run_ids` is claim membership. It places a run in an episode and never makes it the accepted candidate, so a failed
  attempt and its replacement under one claim are not both accepted. A later receipt for the same stage is not evidence. Stage
  acceptance (`stages[].accepted_at`) is a third, separate fact.
- `retry_of` comes from `replaces_run_id`, else `parent_run_id`. Running the same identity again, or revalidating, is not a retry.
- `duration` is the harness-recorded duration (`exact`); else end minus start (`estimated`, source `timestamps`); a running run
  counts to the snapshot time; a finished run with no recorded end stays `unknown` and never grows with the clock. Stage
  `run_time` sums the runs it holds and says that concurrent runs may overlap.
- `actual_model` is observed-model evidence only. `effort` is `unknown` unless the ledger carries `actual_effort`
  (`exact`) or `requested_effort` / `effort` (`partial`: a request, not an observation).

**Stages.** Workflow's published `stage_plan` gives the selected stages and their order. Without one, the list is
Workflow's canonical order; the `qa_*` and `manual_*` stages follow the checkpoint's policy snapshot (`policy.processes`)
when it has one, and otherwise count as selected only if some record mentions them. Stages outside the plan are listed as
`excluded` (never `waived`), after the planned ones. Plain Spec Kit and plan reports have `stages: []`.

- `accepted_at` is the latest passed receipt or `accepted`/`revalidated` lifecycle event. It is history. `validity` is the
  current state: `stale` when the receipt carries `stale: true` or the last lifecycle event for the stage is `invalidated`
  or `revalidation-stale`; `current` when the last such event is `accepted` or `revalidated`; otherwise `unknown`. A receipt
  alone does not prove it is current.
- Episodes come from lifecycle events that share an explicit `episode_id`; a `claim` or `resume` event without one is grouped by
  its own `claim_id`. Every other event is loose: a claim-time `invalidated` event, a feature-level `paused` or `recovered`
  event, and an event that names only a claim feed validity and the timeline but create no episode. An episode starts at its
  `claim` or `resume` event and never at an invalidation. A `rejected-completion` does not end the episode. For a stage with no
  lifecycle events, the episodes come from the passed receipt and from `recoveries` (`source` `checkpoint-receipt` /
  `checkpoint-recovery`, `fidelity` `partial`). A stage that also has lifecycle events keeps these historical episodes. Workflow
  1.12.0 writes the same `claim_id` on a receipt (`receipts[stage].claim_id`), on a recovery (`claim.claim_id`) and on the lifecycle
  events of that claim. A checkpoint receipt episode is dropped only when an `accepted` or `revalidated` event of the same stage
  carries the same `claim_id`, and a checkpoint recovery episode only when a `recovered` event of the same stage does. The same
  rule keeps the timeline to one row per fact. A record with no `claim_id` (older Workflow) is always kept. A shared stage or a
  shared timestamp never suppresses anything; the checkpoint episodes carry the record's `claim_id` when it has one. A recovery is read from Workflow's `{claim: {stage, claimed_at, mode,
  delegation: {identity}}, reason, at}` record (a flat `{stage, reason, at}` too): `claimed_at` is its start, the delegation
  identity is kept as `identity`, and the claim token is never read. Runs of a stage that no event or shared claim places in an
  episode are listed in `unknown_runs`.
- A run joins an episode only when a lifecycle event names it in `delegation_run_ids`, or when its `claim_id` matches exactly
  one episode. A failed worker does not reject a stage.
- `open` is true only when something confirms the stage is running now: a live run, a running episode or the active claim.
  `timing` is `open`, `closed` (a start and an end), `end-unknown` or `unknown` (no start). A stage is `closed` only when
  every relevant run and episode has a resolved end, whatever its start: a run that is not live and records no end is unresolved
  unless its own episode has an end (an `accepted`, `recovered` or `invalidated` event bounds it), and an episode that is neither
  running nor ended is unresolved. Otherwise it is `end-unknown`, and `last_end` keeps the last end that was recorded, apart from
  the verdict. `first_start` and `last_end` take the runs and the episode boundaries; `last_end` is `null` while the stage is `open`. The UI
  extends a bar to the snapshot time only when `open` is true and draws `end-unknown` as a short bar with a broken edge.
- `feature.stage.status` is the status of that stage's entry; `checkpoint_status` is the checkpoint's own.

**Workstreams.** A task belongs to one workstream, decided in this order: (1) a lane in `facts.jsonl` marked
`semantics: "workstream"` that lists the task (`progress lane L1 --tasks … --workstream`; if two marked lanes list it, the later
record wins and the task is in `conflicts` on both); (2) a workstream tag at the start of the task line that `tasks.md` declares
in its legend; (3) `shared`. A legend is a table row whose first cell holds bracket tags and whose second cell says "lane" or
"workstream" (`` | `[A]` / `[B]` | Coding lane: **A** … | ``), or a bold `**Workstream A**`. Role markers (`[Impl]`, `[QA]`,
`[Docs]`, `[Collect]`, `[Review]`), `[P]` and phase headings are never workstream tags. A task with two legend tags is `shared`.
Buckets hold task ids: checkbox done first, then an open blocker on the task or a marked lane, then a task with a running
linked run, and the rest wait. A run's `workstream` is set when every task it holds belongs to the same workstream at its
start (replayed from dated lane records for marked lanes), otherwise `null`. A run whose `started_at` is missing or not a time
has no start to place against those records, so its workstream is `null` unless the ledger row names a marked lane in
`workstream` or `lane_id` that holds all of its tasks. Lane facts that carry no marker are not
workstreams, whatever Workflow version is installed.

**Decisions.** Keys are `<feature id>:<source>:<source id>`; two decisions are never merged because their text matches.
`facts` maps pending, made and withdrawn. `workflow` keeps the ledger's `pending`, `conflict`, `answered` and `applied`, its
`answer_digest` and the application evidence names. `clarification` keeps `answered`, `applied`, `waived`, `superseded` and
the rest of the states in `clarifications.json`; a lower revision of the same `source_id` is shown as `superseded` under the key
`<source id>@r<revision>`. `decided_by` is set only from a recorded author or editor; a checkbox edit has none, and the UI says
"editor not recorded". A missing answer time stays `null`. `evidence` is a list of display strings (each at most 200
characters) and `evidence_links` holds the `{text, url}` of those that carry an https URL. `answer.value` is always option text
(or a list of texts) and `answer.index` is the explicit position (an int, a list for `multiple`, or `null` when the text names no
option). The adapters decode once: Workflow's ledger and Scope's records store choices as letters (`A`, `B`, ...), and an in-range
ASCII letter (`A`-`Z`, `a`-`z`) becomes the option at that position (any other character, such as `ß`, is kept as exact text with
`index` `null`, and never raises); facts and free-text answers are matched by exact option text only. The UI highlights by
`index`, else by exact option text. It never decodes a letter, so with options `S`, `M`, `L` the answer `M` is the option `M`. `pending` holds `pending` and `conflict`. `sources` states which
adapters ran; "none recorded" is only true for the sources that were `available`.

**Attention.** Open blockers (high); pending and conflicting decisions (medium); failed or abandoned runs with no later
`successful` run of the same identity, worded "no recovery recorded" (medium); and a telemetry gap that names a diagnosed
cause (`codex hooks not approved`), only when no host session was observed. The `stale` kind is added by the UI from its own
clock (age against `stale_after_seconds`, or a newer source fingerprint); the Python side never emits it.

**Timeline.** Curated events with ids that depend only on the event: lifecycle events (accepted, rejected-completion, paused,
recovered, invalidated, revalidated, revalidation-stale), failures, recoveries, answered decisions, blockers opened and
resolved, and every coordinator note (all notes are kept; the UI bounds the default view). A recovery has `fidelity`
`recorded` when a retry link says so, and `inferred` ("Later successful run … no retry link recorded") when only a later
successful run of the same identity exists. A `paused` or `recovered` event with no stage reads "Feature paused" or
"Feature recovered". The timeline is not capped: `report.json` and `data.js` keep every entry, because the UI's "show all" needs
them. On the frozen #842 run that is 97 entries, about 22 KB of a 139 KB document; it grows linearly with notes and lifecycle
events. A cap is only worth adding if the token benchmark regresses.

**History.** `lane_aliases` maps legacy lane ids (`L`, `W`, `C`) to `run:<id>`, `identity:<identity>`, `workstream:<id>` or
`lane:<id>`, only through an explicit link (a lane owned by a run id or a delegation identity, a folded duplicate, a marked
lane). Every other legacy lane is listed in `unresolved` with its owner history, so a note or blocker that names it stays
navigable. `facts.jsonl` is never rewritten. The UI lists both in a collapsed History section with a stable id per row, and
a timeline, episode or history reference that names a run, a stage or a workstream is a button that opens and focuses it.

**Sources.** `sources` lists every producer file that was read, its repository-relative path, a 16-hex SHA-256 prefix of
the bytes that were parsed, the producer's generation when it has one, the read time and the file size. The hash, size and time
are taken during collection, from the same bytes the collector parsed, never from a second read afterwards. `consistent` is
`false` when the file changed on disk after it was read, or was read twice with different bytes. Then the report is marked
`collection.dirty` with `collection.inconsistent_sources`, the next refresh is flagged, and the UI shows that the snapshot may mix
generations; the fingerprint still describes what was parsed, not the newer file. A source read through a byte cap carries a
`note` ("only N of M bytes read"). The browser cannot find newer files on its own; the existing producer boundaries (hooks,
Workflow writes) mark the report dirty, and a refresh publishes the new fingerprints.

## Projection (`sanduq.progress.v2`, compatibility)

This is the document `progress status --json --schema v2` prints, and the one the Workflow shim, `progress export --schema v2`
and the `classic` layout read. Its contract has not changed. The one-line `progress status` summary still reads its keys.

```json
{
 "schema":"sanduq.progress.v2","rev":17,"generated_at":"…","stale_after_seconds":600,
 "collection":{"automatic":true,"hosts":["claude"],"dirty":false,"last_event_at":"…","diagnostics":0},
 "feature":{"id":"624-…","title":"…","dir":"specs/624-…","branch":"…","issue":{"number":624,"url":"…"}|null,
            "stage":{"value":"execute","source":"workflow-checkpoint|workflow-receipts","status":"in-progress"}|null,"started_at":"…","workflow":true},
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
 "events":[{"at":"…","kind":"…","text":"…(≤120)"}],   // bounded (≤95), derived; stage, failure, decision, block and workflow lines (50), notes (`NOTE_LIMIT`, 15) and all other lines (30) each keep their own budget
 "summary":{"tasks_total":40,"tasks_done":12,"lanes_active":2,"blocked":1,"decisions_pending":1}
}
```

`M` = measurement `{"value":…, "source":"…", "observed_at":"…", "fidelity":"exact|partial|estimated|unknown"}`.

**Units.** Every duration in the projection (`orchestrator.elapsed`, `orchestrator.active`, `lanes[].elapsed`,
`lanes[].active`) is a whole number of **seconds**; the UI formats them as `1h 2m` / `3m 4s` / `5s`. Host snapshots keep
the host's own `*_ms` fields (`elapsed_ms`, `api_ms`) and the projection converts them. Timestamps are ISO-8601 strings.

**Stage.** `feature.stage.value` is the stage of the active claim when there is one (`source: "workflow-checkpoint"`).
With no claim it is the stage of the latest accepted receipt (`outcome: "passed"`, ordered by `completed_at`, then
receipt order) with `source: "workflow-receipts"` and `status` copied from the checkpoint (`in-progress`, ...). Only a
checkpoint without receipts falls back to a terminal checkpoint status; otherwise `stage` is null.

**Pause.** A checkpoint `pause` becomes the `WP` blocker (`source: "workflow-pause"`) only while it is the latest word: the
checkpoint status is still `paused`, no new claim (`active.claimed_at`) is newer than the pause, and no accepted receipt
was completed after it. Workflow's `claim` moves the status off `paused` but never clears `pause`, so any of the three
makes the pause history: no blocker, and the event reads `paused (superseded: <reason>): ...` with the real reason (`status is <x>`, `newer claim` or
`later accepted receipt`).

**One run, one lane.** A facts lane and a Workflow delegation describe the same work when a durable id says so, and
only then. Two rules: the lane `owner` is a delegation `identity`, or the `owner` is a delegation `run_id`. Time
windows and matching requested harness or model never link a lane and a run; a run no lane names by id keeps its own
`W<n>` lane. A lane's status comes from its attempts: a closed lane's closure counts only while no absorbed attempt
started after the lane closed; a newer attempt decides instead (running: `active`, failed: `failed`, blocked:
`blocked`, successful but not yet accepted: `waiting`, or the derived status). Facts lanes that end up holding attempts of one identity fold into one lane per identity: the lowest lane id
survives, `owner` becomes the identity, and a blocker that targets a folded id, or a retired `W<n>` id, resolves to the surviving lane (blocker targets,
`by.ref` and lane references all go through the alias). Labels are never compared. Every attempt appears in exactly one
lane; an identity named in a multi-identity workstream lane keeps its share there and is not also folded elsewhere
unless its own lane exists, so a task id can appear in two lanes' attempts (T021 on the #842 fixture).

**Lane time.** A lane with attempts reports `elapsed` as the sum of its attempts' own durations (start to end, or to
now while one runs; a finished attempt with no end uses the harness-measured duration), never the span between the
first start and the last end, so reuse gaps are not work. A facts lane with no attempts counts from the first record
of its current owner (a reused lane id restarts) and stops at its close record, or at its merged children's last end;
only an open lane runs to now.

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
`children`), or its `description` label. A merged child contributes its observed model and effort, and its last observation time, to the lane, and it gets no
`C<n>` lane. Its terminal status also decides the lane's status: a failed child fails the lane and a finished child
leaves the lane `waiting` while tasks are unchecked (the tasks.md checkbox stays the task's truth). An open blocker
targeting the lane outranks that terminal evidence, so the lane reports `blocked`. A `description` match merges only
when it identifies exactly one child; if several children share the label, none merges on that label and each stays a
`host-child` lane. Agent id and `tool_use_id` matches are unique by construction. Only children that match no lane
owner become `host-child` lanes (`C<lane_no>`). The number is assigned once, when the child is first seen, and lives in the
host snapshot (`lane_no`); it is never reused or renumbered when another child later merges into an assigned lane, when the
view is deleted or when the entry's key changes, so a blocker that targets `C2` keeps pointing at the same child. A blocker
on a retired number (`lane_aliases`) resolves to the surviving lane. A snapshot entry written before numbers existed is numbered
above all known numbers, in start order, for display until its next observation stores a number.

Child lifecycle. A launch by a synchronous `Task`/`Agent` call ends with its tool result. An asynchronous launch
(`run_in_background`, or Codex `spawn_agent`) only proves the child exists: the launch response never sets `done` or
`ended_at`; the child's own `stop` does. A child that has ended can run again: a running observation newer than its
`ended_at` starts a new generation (`generation` counts up, `ended_at` is cleared, `started_at` is that observation); a
running observation at or before `ended_at` is stale and is ignored. Lifecycle updates are validated together against the
entry's last accepted lifecycle observation (`status_at`): a status with its start and end times that is older than
`status_at` is dropped as a whole, so a delayed `done` from 12:05 cannot end a generation that started at 12:10.

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
progress init --plan PATH [--name NAME] [--dir DIR]                     -> "progress: ready .progress/<name>/.view/index.html bind=…"
progress bind [--session ID]                                            -> "progress: bound <session>"
progress refresh [--final]                                              -> silent on success unless --verbose
progress status [--json [--schema v2|v3]]                               -> one-line summary, or the projection JSON (v3 by default)
progress lane L1 --tasks T001-T004,T009 [--owner ID] [--label T] [--harness H --model M --effort E] [--close] [--workstream]
progress block T007 --by L2|T003|SD2|ext:"text"                         -> "progress: B4 open T007 by L2"
progress unblock B4 | --all-for T007
progress decide ask "question" --options a,b,c                          -> "progress: D2 pending"
progress decide made D2 b --by user|agent-recommendation|assumption [--evidence URL]
progress note "text" [--target T005]
progress theme --preset sanduq|cobalt|emerald|classic | --from-illustrate | --file theme.json | --layout timeline|classic | --show
progress export [--format md|json] [--schema v2|v3] [--out PATH]        -> deterministic; v3 by default
progress bind --host claude|codex --model M [--effort E] [--session ID]  -> coordinator self-report, stored in .host/
progress attempt record (--lane L1 | --overhead LABEL) --run ID --status S [--started T] [--ended T] [--usage-json PATH]
progress runs [--json] [--runs-dir DIR]... [--now T] [--stall-seconds N]  -> progress.runs.v1
progress hook <event>                                                   -> reads host JSON on stdin; never prints on success
progress hooks install|uninstall --host claude|codex [--scope project|user] [--python CMD] [--force-both]   -> one line
progress hooks status [--host claude|codex]                              -> one line
```

Every verb that works on one report also takes `--plan NAME|PATH` or `--feature DIR`.

Exit codes: 0 ok, 2 usage error, 3 refused (authority/binding), 4 lock busy (the OS lock is held by another process; verbs retry 3× with 200 ms backoff first).
Error lines start with `progress: error <CODE>`.

## Producer files Progress reads (Workflow and Scope)

Progress never imports Workflow or Scope code and never writes their files. Every file below is optional; an older
producer simply leaves the matching fields empty or labelled `partial`.

**`workflow/lifecycle.jsonl`** (Workflow 1.12.0). One JSON object per line:
`{v, event_id, workflow_run_id, generation, at, stage, event, episode_id, claim_id, caused_by_claim_id, candidate_run_id, delegation_run_ids, reason}`.
`v` is 1. `event` is `claim`, `resume`, `accepted`, `rejected-completion`, `recovered`, `paused`, `invalidated`,
`revalidated` or `revalidation-stale`. `workflow_run_id`, `episode_id`, `claim_id`, `caused_by_claim_id` and `candidate_run_id`
may be `null`, and null means unknown. `claim_id` is a non-credential id, never the claim token.

- `candidate_run_id` (on `accepted` and `rejected-completion`) is the exact run whose candidate Workflow validated, or `null`.
  `delegation_run_ids` is claim membership, every delegation run linked to the claim, and never implies acceptance.
- A claim-time `invalidated` event, which removes a downstream receipt, has `claim_id` and `episode_id` `null` and names the claim
  that caused it in `caused_by_claim_id`.
- `stage` may be `null` only for `paused` and `recovered`, which are feature-level when no claim is held. Any other event with no
  stage is skipped. Skipped records are counted in the source's `note` ("N unusable record(s) skipped").

The reader skips a torn final line (a crashed append), counts and skips a corrupt complete line, skips records with an unknown
`v` or `event`, and keeps the first record of a repeated `event_id` (a replayed append); a repeat that differs is reported in the
source's `note`. Read cap: at most 8 MiB. A larger file is read from its tail, so the newest events are kept; the cut line is dropped
(not counted as corrupt) and the `note` says "older events not read".

**`workflow/checkpoint.json`**, new fields. `stage_plan: {v, generation, stages}` where `stages` is an ordered list of ids or
`{id, label}` objects, already filtered by policy (`v` 1 only; anything else is ignored and the canonical list is used).
`next_action: {text, stage, kind, evaluated_at, generation}` where `kind` is `active-claim` or `next-stage`; Progress shows it
with its age and never computes one. `generation` is the checkpoint generation. Read as before: `receipts`, `recoveries`,
`pause`, `active`, `branch_history`, and `policy.processes.qa` / `.user_manual` when present. Each `recoveries` entry is
`{claim: {stage, claim_id, claimed_at, mode, delegation: {identity}, …}, reason, at}` and each receipt may carry `claim_id`; Progress reads only those fields, never the claim
`token`.

**`workflow/delegations.json`**, new attempt fields: `intent_id`, `claim_id` (non-credential), `parent_run_id` and
`replaces_run_id`. Optional: `tasks` (explicit task ids), `actual_effort`, `requested_effort`, `accepted_at`.
The top-level `feature` prefixes every identity.

**`workflow/clarifications.json`** (Scope 1.7.0).
`{"v":1,"items":[{source_id, revision, question, options, answer:{kind, value}|null, state, url, editor|null, observed_at, answered_at|null, applied:{at, evidence:["…"]}|null, evidence:[{kind, url|null, comment_id|null, explanation|null}]}]}`.
`state` is `pending`, `conflict`, `answered`, `applied`, `waived`, `superseded` or `withdrawn`; an item with another state is skipped and
counted in the source's `note`. `url` must be https. Render makes no GitHub call.

Evidence types: `evidence` is a list of objects `{kind, url, comment_id, explanation}` and `applied.evidence` is a list of strings.
The reader also accepts plain strings in `evidence` and one string for `applied.evidence` (it is wrapped in a list). An object is
flattened to a display string of at most 200 characters: its `kind`, then `comment <comment_id>` and the `explanation` when it has
them, or its `url` when it has neither. A `url` that is https is kept as a link (`evidence_links`); any other scheme is text only.
Input cap: 2 MiB. A larger file is `invalid`, is not parsed, and the source's `note` says "file over the size cap".

**`facts.jsonl`** lane records may carry `semantics: "workstream"` (`progress lane … --workstream`).

**Read caps.** The two files a producer can grow without bound are capped: `lifecycle.jsonl` at 8 MiB (tail) and
`clarifications.json` at 2 MiB (all or nothing). Both are hashed while they stream in 64 KiB chunks, so memory stays bounded by the
cap. The other producer files are small by construction (checkpoint, ledger, decisions) or written by Progress itself (facts,
self-report).

## Self-report

`progress bind --host H --model M --effort E` writes `.host/self-report.json`: `{v, feature, worktree, host, session_id, actor, fields:{model:{value, at}, effort:{value, at}}}`. It is durable (not under `.view`, so deleting the view
keeps it) and git-ignored. It applies only to the feature and worktree it was written in. With `--session ID` it applies to that session;
without one it is an explicit "session unknown" report that applies to whichever session is bound, and to a report with no host
session at all. Binding the same session again keeps the fields the new call does not restate; another session replaces the report.
The projection takes each field from the host's own observation first and fills a gap from the self-report, with `source: "self-report"`,
`fidelity: "estimated"` and `orchestrator.provenance.<field>: "self-report"`. Values go through the same secret and path filter as notes.

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

Hooks run `scripts/hook.py <event>` (standard library only). It exits before importing Progress when Progress was never
initialised in the project (no project directory, `.specify/progress/` or `.progress/.project/`; nothing is written) or when the session is not bound, has no pending
handshake and its drop is already logged; an unbound session is logged once per session id. Anything else is handed to
`progress hook <event>` (same code, `progress.py hook` stays available): parse stdin (tolerate empty/invalid → diagnostics,
exit 0). Update the host snapshot under the
lock. Debounce: if the last refresh is younger than `debounce_seconds`, set `dirty=true` and exit; else refresh.
`stop` and `session_end` always refresh. A deferred (debounced) event is not invisible: the first one in a window patches the current
`report.json`/`data.js` with `collection.dirty:true` and `collection.last_event_at` and advances `rev` (no producer is
read, nothing is rebuilt) so the UI shows its pending banner. That clean-to-dirty transition is written once per window;
later events only move the timestamps in `state.json`, and the next real refresh publishes the latest values; the first hook after the window, a statusline update after
it, `stop`, or any verb performs the real refresh and clears the flag. Any exception → diagnostics, exit 0, no stdout (never block the host).

## Theme (`progress.theme.v1`)

```json
{"v":1,"preset":"sanduq","title":null,"logo":null,"density":"comfortable|compact","layout":"timeline|classic",
 "blocks":["header","orchestrator","lanes","boards","decisions","blockers","events"],
 "hidden":[],
 "tokens":{"light":{"bg":"#…","surface":"…","text":"…","muted":"…","line":"…","brand":"…","accent":"…",
                    "active":"…","waiting":"…","blocked":"…","done":"…","failed":"…"},
           "dark":{…same keys…}},
 "font":{"sans":"system-ui, sans-serif","mono":"ui-monospace, monospace"}}
```

`layout` picks the view. `timeline` (the default) is the v3 Timeline view and `data.js` carries the v3 document. `classic` is the v2
lanes view for one more release, and `data.js` then carries the v2 document (`report.json` stays v3). `progress theme --layout classic|timeline`
changes only this key and keeps every other customization; picking a new preset or `--from-illustrate` keeps the layout. When the
layout changes, the command also rebuilds each initialised report under its own report lock, so `data.js` carries the matching
document at once. A report whose lock is busy is named on a second line and keeps its old `data.js` until the next refresh. The
generated `layout.js` carries it as `"layout":"classic"`. Colors are validated as `#rgb`/`#rrggbb`. Unknown keys are rejected with a one-line error. `--from-illustrate` maps
Illustrate roles explicitly: paper→bg, paper-2→surface, ink→text, muted→muted, rule→line, accent→accent,
link→brand, accent-tint→active. Status colours keep the preset's values unless set.

## UI

`index.html` loads `theme.css`, `blocks.js`, then `data.js?rev=<n>` by script injection every 3 s (one in-flight load;
older/equal `rev` ignored; load error keeps the last good view and shows a banner). All strings are inserted with
`textContent`. A stale banner shows when `now - generated_at > stale_after_seconds` or `collection.dirty`.
No network, no CDN, no framework.
