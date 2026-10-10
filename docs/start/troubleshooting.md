# Troubleshooting

Find the symptom, then run the check. For managed features, `$speckit-workflow-doctor` and
`$speckit-workflow-gate-explain` name the next step for most problems.

| Symptom | Check | Fix |
| --- | --- | --- |
| A command is missing | The integration you initialized (`codex` or `claude`) and the host's command directory | Reinstall the extension, then start a new host session. Workflow's `workflow.py host` operation repairs or switches Codex and Claude Code registrations. |
| The wrong Scope package is installed | The package origin and Workflow's dependency lock | Install Workflow and let its installer add Sanduq's Scope. Another catalog uses the same ID. |
| A QA or manual stage never runs | `.specify/workflow.yml` | Installing a package does not [enable](../reference/glossary.md#enabled) it. Select the process with `$speckit-workflow-init`. |
| GitHub board or auth fails | `gh auth status`, the Project scopes and the board mappings | Run `gh auth refresh -h github.com -s project,read:project`, then `workflow.py doctor --project`. |
| An old extension version installs | The catalog and the Spec Kit extension cache | Confirm the cache's absolute path, clear only that project's cache, then reinstall. |
| PNG export fails | Playwright and Chromium | Install them as in [prerequisites](prerequisites.md#playwright-and-chromium). |
| PDF build fails | The PDF libraries and `User-Manual/requirements.lock` | Install them as in [prerequisites](prerequisites.md#mkdocs-and-pdf-libraries). Report a failed build as failed. |
| A receipt is stale or a claim was interrupted | `$speckit-workflow-status` | Follow [recovery](../workflow/operating-guide.md#host-identity-and-interrupted-claims). Check for remote writes before you recover. |
| An extension says Illustrate is missing | `.specify/extension-dependencies.yml` | Approve the install when asked, set `update_policy: auto`, or run `specify extension add illustrate`. |

## Limits

- A logged "graceful skip" from Project or PR means the remote step did not run. It is not a success.
- Never delete a Memory journal or reset Git to get past a blocked archive. Use the recovery
  command the archive prints.
