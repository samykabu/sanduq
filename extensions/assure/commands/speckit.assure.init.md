---
description: 'Sets whether QA analysis and the QA manual are lifecycle gates or manual steps. Use when setting up Assure or asked to "make QA mandatory".'
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

1. Explain the two policies in plain language:
   - `integrated`: `speckit.assure.analyze` is mandatory before `speckit.implement`, and the sanduq
     PR workflow must run `speckit.assure.document` when its feature evidence is missing or stale.
   - `manual`: both commands remain available, but their lifecycle hooks are optional.
2. If `--mode` is absent and the session is interactive, ask which policy to use. Recommend
   `integrated`. In a non-interactive first run, default to `manual`.
3. Run the installed script from the repository root:

   ```text
   python .specify/extensions/assure/scripts/assure_init.py --mode <integrated|manual>
   ```

   Forward `--dry-run` when supplied.
4. Verify that `.specify/extensions/assure/assure-config.yml` and `.specify/extensions.yml` reflect the
   selected mode. Tell the user to commit both files so every checkout uses the same policy. Pass on
   any line the script prints about local edits in `documentation-gates.yml`.

Never claim that direct `gh pr create` or the GitHub web UI can execute agent commands. The
installed PR extension enforces the document preflight; CI can detect bypasses.
