---
description: "Configure whether QA analysis and documentation are required parts of the project lifecycle."
---

# Initialize QA

Configure QA once for the current Spec Kit project.

## User input

```text
$ARGUMENTS
```

Supported flags:

- `--mode integrated|manual`
- `--non-interactive`
- `--dry-run`

## Instructions

1. Load `.specify/extensions/qa/skills/qa/SKILL.md`.
2. Explain the two policies in plain language:
   - `integrated`: `QA.Analyze` is mandatory before `speckit.implement`, and the sanduq PR
     workflow must run `QA.Document` when its feature evidence is missing or stale.
   - `manual`: both commands remain available, but their lifecycle hooks are optional.
3. If `--mode` is absent and the session is interactive, ask which policy to use. Recommend
   `integrated`. In a non-interactive first run, default to `manual`.
4. Run the installed script from the repository root:

   ```text
   python .specify/extensions/qa/scripts/qa_init.py --mode <integrated|manual>
   ```

   Forward `--dry-run` when supplied.
5. Verify that `.specify/extensions/qa/qa-config.yml` and `.specify/extensions.yml` reflect the
   selected mode. Tell the user to commit both files so every checkout uses the same policy.

Never claim that direct `gh pr create` or the GitHub web UI can execute agent commands. The
installed PR extension enforces the document preflight; CI can detect bypasses.
