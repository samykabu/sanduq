# Progress verbs

Output is one line (`refresh` prints nothing without `--verbose`). Exit codes: 0 ok, 2 usage, 3 refused (authority or binding), 4 lock busy (retried 3 times first).
Error lines start with `progress: error CODE`. The full contract is in `docs/contracts.md` of the extension source; every flag and example is in `docs/commands.md`.

| Verb | Writes | Notes |
| --- | --- | --- |
| `init [--feature DIR] [--statusline yes\|no] [--theme PRESET]` | `.view/` shell, config, pending bind | Prints `progress: ready <report path> bind=<nonce>`. The next host hook for that shell call completes the bind. |
| `bind [--session ID]` (prints `progress: pending bind=<nonce>` without `--session`) | `.specify/progress/bindings.json` | Needed again only when `init` was not run in this session. `--session` binds directly where hooks are absent. |
| `refresh [--final]` | `.view/` | Silent on success. `--verbose` prints one line. |
| `status [--json]` | nothing | One line, or the projection. |
| `lane L1 --tasks T001-T004,T009 [--owner ID] [--label T] [--harness H --model M --effort E] [--close]` | `facts.jsonl` | Harness, model and effort are the values you requested, never observed ones. |
| `block T007 --by L2\|T003\|SD2\|ext:"text"` | `facts.jsonl` | Prints the blocker id, for example `B4`. |
| `unblock B4` or `unblock --all-for T007` | `facts.jsonl` | |
| `decide ask "question" --options a,b,c` | `facts.jsonl` | Plain Spec Kit only. Refused when Workflow's `decisions.json` exists (`PROGRESS_DECISION_AUTHORITY`). |
| `decide made D2 b --by user\|agent-recommendation\|assumption [--evidence URL]` | `facts.jsonl` | |
| `note "text" [--target T005]` | `facts.jsonl` | Retries and failures worth a human's attention. |
| `attempt record (--lane L1 \| --overhead LABEL) --run ID --status S [--started T] [--ended T] [--usage-json PATH]` | `facts.jsonl` | Integration verb for the Workflow legacy shim. Writes a `kind:"attempt"` fact with origin `legacy`; it never overrides a producer's attempt or lane status. |
| `runs [--json] [--runs-dir DIR]...` | nothing | `progress.runs.v1`: normalized `.delegate/runs` projections for other tools. Needs no initialised feature. |
| `statusline [install\|uninstall\|run]` | Claude `settings.json` | Chains the previous status line command and restores it on uninstall. |
| `theme --preset sanduq\|cobalt\|emerald\|classic \| --from-illustrate \| --file theme.json \| --show` | `.specify/progress/theme.json` | |
| `export [--format md\|json] [--out PATH]` | the output file | Deterministic. |
| `hook EVENT [--host H]` | host snapshot | Internal. Called by the host's hooks; prints nothing and always exits 0. |

## What is collected without a command

| Fact | Source |
| --- | --- |
| Task done, reopened, dependencies, parallel marker | `tasks.md` |
| Stage, delegation attempts, retries, decisions | Workflow checkpoint and ledger, when installed |
| Model, effort, context, elapsed, child agents | Host hooks and status line; fidelity is shown per value |

Facts the hosts do not provide appear as unknown. They are never filled with an estimate.
