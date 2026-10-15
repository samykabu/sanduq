# Progress

**Purpose:** show a live report for one Spec Kit feature: lanes, tasks, blockers, decisions and what the orchestrating
agent is using. The report is a deterministic projection of `tasks.md`, the optional Workflow ledger and the host's
native hook payloads. No agent is spent keeping it current.

| | |
| --- | --- |
| Lifecycle phase | After `tasks` through `implement`; native hooks keep it fresh |
| Hooks | Two optional lifecycle hooks and five native host events ([hooks](../reference/hooks.md)) |
| Commands | `init`, `refresh`, `status`, `theme`, `export` ([reference](../reference/commands.md#progress)) |
| Requires | Nothing; Python 3.11 or later. Workflow and Illustrate are optional |
| Standalone | Yes |
| License | PolyForm Noncommercial 1.0.0 |

## Setup

```bash
specify extension add progress
```

```text
$speckit-progress-init Create the progress report for specs/412-refund-approval.
```

Open `specs/412-refund-approval/progress/.view/index.html` in a browser. It polls every 3 seconds and needs no server.

## Example

```text
$speckit-progress-status Show the one-line progress status.
$speckit-progress-theme Use the cobalt theme for the progress report.
$speckit-progress-export Export the progress report as Markdown.
```

The agent records only what no other source holds: a lane assignment, a blocker, a plain Spec Kit decision or a note.
The skill at `extensions/progress/skills/progress/SKILL.ext.md` lists the verbs. Task state comes from `tasks.md`;
model, effort and context come from host hooks and are shown as unknown when a host does not send them.

## More

The [package README](../../extensions/progress/README.md) has the hosts table, theming and token results.
