# Memory

**Purpose:** keep current product knowledge in `specs/memory/`. After a feature merges, Memory
reconciles what it learned into memory entries and archives the feature folder through reviewed,
recoverable Git commits.

| | |
| --- | --- |
| Lifecycle phase | Before `specify`, before `analyze`, after `implement`; next local session after merge |
| Hooks | Three mandatory hooks, `impact` also before `specify` ([hooks](../reference/hooks.md)); an optional guard hook |
| Commands | `init`, `prepare`, `run`, `session`, `enable`, `impact`, `status` ([reference](../reference/commands.md#memory)) |
| Requires | Nothing; Python 3.11 or later, Git, Spec Kit 1.x |
| Standalone | Yes |
| License | PolyForm Noncommercial 1.0.0 |

## Setup

```bash
specify extension add memory
python .specify/extensions/memory/scripts/install.py --target-branch main
```

```text
$speckit-memory-init Configure main as the merge branch and register our real test commands and covered paths.
```

Use your real merge branch and checks that verify your code. Init does not enable automatic
archiving. `$speckit-memory-enable` shows the policy for your review first.

## Example

```text
$speckit-memory-impact Consult current refund constraints and settlement decisions relevant to this change.
$speckit-memory-run specs/412-refund-approval Archive this verified, fully completed feature.
```

```bash
python .specify/extensions/memory/scripts/archive.py memory query --text refund
python .specify/extensions/memory/scripts/archive.py memory check
```

## Preflight and bounded inspection

The Memory 2.2.0 package exposes the same early guards used by verification and preparation:

```bash
python .specify/extensions/memory/scripts/archive.py preflight --spec specs/412-refund-approval --check docs
python .specify/extensions/memory/scripts/archive.py inspect --run <run-id> --view checks --max-bytes 16384
```

Preflight reports repairable references and candidate-only checks separately. It does not replace
independent critique or authorize deletion. Inspection returns whole records and continuation data
within a byte budget, so you can inspect a large journal without printing it in full.

Check reuse requires an explicit complete input declaration and intact passing evidence. Missing or
unknown dependencies retain conservative freshness. Both memory formats and recovery data remain
supported. See the [package contract and examples](../../extensions/memory/README.md).

`archive.py status` names the next command for an active run (`next: {command, reason}`), and
`memory show` and `memory query --format json` print each entry's `expected_hash`, so the agent
copies the hash a delta update needs instead of computing it. The `run` command is a short
procedure that reads its references (candidate format, large runs, verification override, format 1,
review and publication, recovery) only at the step that needs one. On Claude Code, `prepare` and
`session` leave the slash menu because hooks and the dispatcher call them.

## Optional guard hook

Set `"guard_hooks": true` in `.specify/memory-policy.json` and rerun `install.py`. It registers one
PreToolUse hook for Claude Code (`.claude/settings.json`) and Codex (`.codex/hooks.json`; approve it
in `/hooks`). While an archive run is active, the hook refuses `git push`, `stash`, `reset` and
`clean` and any write under `specs/memory/`, and names the run's `candidate.json` and the recovery
reference. It is off by default.

## How it runs

![Memory sequence: memory.init configures policy; memory.impact runs as a required hook before Analyze; memory.prepare queues finished work after implementation; after the merge, the next session or memory.run checks eligibility and evidence, migrates knowledge with an independent review, and commits a recoverable checkpoint before the final archive.](../diagrams/extension-memory.animated.svg)

Impact reads current knowledge before Analyze. Prepare queues finished work. After the merge, the
next local session checks the approved policy and the real checks, then reconciles knowledge,
reviews it, and commits before it removes the feature folder.
[Editable source](../diagrams/extension-memory.html).

## Limits

- Automatic mode runs in a local session. There is no daemon and no remote merge trigger.
- Changing the policy or the scripts withdraws the approval. Review and enable again.
- Checked tasks and a merge do not prove a feature is complete. Memory runs your checks.
- Never delete a journal or reset Git to get past a blocked archive. Use the printed recovery steps.

Package details: [Memory README](../../extensions/memory/README.md).
