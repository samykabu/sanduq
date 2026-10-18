# Progress verbs

Output is one line (`refresh` prints nothing without `--verbose`). Exit codes: 0 ok, 2 usage or not found, 3 refused (authority, binding, hook installer), 4 lock busy (retried 3 times first).
Error lines start with `progress: error CODE`. The full contract is `docs/contracts.md`; every flag and example is in `docs/commands.md`.

**Which report.** Every verb below except `init`, `runs`, `theme` and `hooks` takes `--plan NAME|PATH` (plan mode) or `--feature DIR` (Spec Kit). Put the flag right after the verb. With exactly one initialised plan or feature it can be left out; otherwise the error `PROGRESS_NO_FEATURE` lists the candidates.

| Verb | Writes | Notes |
| --- | --- | --- |
| `init --plan PATH [--name N] [--dir D] [--rebind] [--statusline yes\|no] [--theme PRESET]` | `.progress/<name>/` (`facts.jsonl`, `plan.json`, `.view/`), project config, pending bind | Plan mode. Reads any Markdown checklist, never writes it. Prints `progress: ready <report path> bind=<nonce>`. The next host hook for that shell call completes the bind. A plan outside the repo is stored as `external:<name>`. |
| `init [--feature DIR] [--statusline yes\|no] [--theme PRESET]` | `specs/<feature>/progress/`, project config, pending bind | Spec Kit mode. Same output line. |
| `bind [--session ID]` (prints `progress: pending bind=<nonce>` without `--session`) | project `bindings.json` | Needed again only when `init` was not run in this session. `--session` binds directly where hooks are absent. `bind --host H --model M [--effort E]` records a coordinator self-report in `.host/` instead (shown as self-reported; the host's own observation wins). |
| `refresh` | `.view/`, `plan.json` ids | Silent on success. `--verbose` prints one line. |
| `status [--json [--schema v2\|v3]]` | nothing | One line, or the projection (v3 by default; v2 is the compatibility document). |
| `lane L1 --tasks P001-P004,T009 [--owner ID] [--label T] [--harness H --model M --effort E] [--close]` | `facts.jsonl` | Task ids are the plan's (`T001`, `US3`) or the auto ids (`P001`). Harness, model and effort are the values you requested, never observed ones. |
| `block P007 --by L2\|P003\|SD2\|ext:"text"` | `facts.jsonl` | Prints the blocker id, for example `B4`. |
| `unblock B4` or `unblock --all-for P007` | `facts.jsonl` | |
| `decide ask "question" --options a,b,c` | `facts.jsonl` | Refused when Workflow's `decisions.json` exists (`PROGRESS_DECISION_AUTHORITY`). Flags go before `ask`. |
| `decide made D2 b --by user\|agent-recommendation\|assumption [--evidence URL]` | `facts.jsonl` | |
| `note "text" [--target P005]` | `facts.jsonl` | Retries and failures worth a human's attention. |
| `attempt record (--lane L1 \| --overhead LABEL) --run ID --status S [--started T] [--ended T] [--usage-json PATH]` | `facts.jsonl` | Integration verb for the Workflow legacy shim. Writes a `kind:"attempt"` fact with origin `legacy`; it never overrides a producer's attempt or lane status. |
| `runs [--json] [--runs-dir DIR]...` | nothing | `progress.runs.v1`: normalized `.delegate/runs` projections for other tools. Needs no initialised report. |
| `hooks install\|uninstall --host claude\|codex [--scope project\|user] [--python CMD] [--force-both]` | the host's hook file | Tagged entries only; other settings kept. Commands end in `; exit 0`. Refuses (exit 3): Spec Kit's Progress hooks registered (`PROGRESS_HOOKS_SPECKIT`), target file not valid JSON (`_SETTINGS`), project scope needing an absolute path (`_PATH`), entries already in the other scope unless `--force-both` (`_DUPLICATE`), a file changing twice or locked (`_CONFLICT`), a symlinked settings file (`PROGRESS_UNSAFE_TARGET`). Appends `bind=<nonce>` when one report exists. |
| `hooks status [--host claude\|codex]` | nothing | One line: tagged entries per host and scope, and whether Spec Kit's hooks exist. |
| `statusline [install\|uninstall\|run]` | Claude `settings.json` | Chains the previous status line command and restores it on uninstall. |
| `theme --preset sanduq\|cobalt\|emerald\|classic \| --from-illustrate \| --file theme.json \| --show` | project `theme.json` | |
| `export [--format md\|json] [--out PATH]` | the output file | Deterministic. |
| `hook EVENT [--host H]` | host snapshot | Internal. Called by the host's hooks; prints nothing and always exits 0. |

## What is collected without a command

| Fact | Source |
| --- | --- |
| Task done, reopened, dependencies, parallel marker | The plan file (plan mode) or `tasks.md` (Spec Kit) |
| Stage, delegation attempts, retries, decisions | Workflow checkpoint and ledger, when installed (Spec Kit mode) |
| Model, effort, context, elapsed, child agents | Host hooks and status line; fidelity is shown per value |

Facts the hosts do not provide appear as unknown. They are never filled with an estimate.
