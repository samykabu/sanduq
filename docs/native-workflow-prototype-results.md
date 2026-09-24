# Sanduq native workflow prototype result

Status: **no-go for production scheduling**. Tested against the local Spec Kit
1.0.11 source checkout on 2026-09-24. The production path remains Sanduq's
existing receipt-based dispatcher. The prototype is isolated at
`prototypes/sanduq-delivery/` and is not installed into consumer projects.

## Evidence collected

- `WorkflowEngine.validate` accepts `workflow.yml` with no errors.
- The command-step probe dispatches `speckit.specify` into the Claude and Codex
  integration CLIs using argument arrays. These were mocked subprocess calls;
  no live agent completion was claimed.
- A successful CLI exit makes native `CommandStep` report `completed` even when
  no Sanduq checkpoint or stage receipt exists. This is observed directly by
  `test_command_success_does_not_require_receipt`.
- A separate static shell guard checks the selected feature's stage receipt and
  freshness. With no feature selected, it fails with
  `PROTOTYPE_FEATURE_NOT_SELECTED`. The shell command contains no issue title,
  agent output, or other untrusted interpolation.
- `specify workflow add --dev` installed the isolated prototype in a disposable
  greenfield project; `specify workflow info sanduq-delivery` reported the
  intended six command/guard steps. No live native run was executed.

Commands run:

```text
uv run --project D:\Projects\Personal\spec-kit python -m unittest discover -s prototypes/sanduq-delivery -p test_native_probe.py
Ran 3 tests; OK

python prototypes/sanduq-delivery/receipt_guard.py --root . --stage specify
exit 1: PROTOTYPE_FEATURE_NOT_SELECTED
```

## Production decision

The static guard closes the simple false-completion path, but this prototype
has not proven stage claiming, repeated runs, changed-input invalidation,
remote-question pause/resume, competing claims, or partial-write recovery across
both integrations. Native command steps alone do not enforce those contracts.
The command subprocess test was mocked, so it does not certify live Claude or
Codex execution. Sanduq's dispatcher keeps ownership of these semantics while
the GitHub decision adapter and optional CI policy are developed independently.

Before reconsidering native scheduling, run the complete scenario matrix in
the [design report](sanduq-native-workflow-prototype.html) with controlled
GitHub fixtures and both actual integrations. Do not edit Spec Kit's native
`state.json` to manufacture a pass.
