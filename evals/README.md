# Workflow entry evals

These cases check that Claude picks the right Sanduq workflow entry skill from plain phrasing:

| Case | Prompt | Expected skill |
| :- | :- | :- |
| `scope-issue` | scope issue #42 | `speckit-workflow-scope` |
| `continue-feature` | continue the feature | `speckit-workflow-continue` |
| `finalize-pr` | finalize the PR | `speckit-workflow-finalize` |
| `open-pull-request` | open the pull request | `speckit-workflow-finalize` |

Each case has one `tool_used: Skill` grader. They follow the
[`claude plugin eval`](https://code.claude.com/docs/en/plugin-evals) format: this folder is the plugin
root, `.claude-plugin/plugin.json` points the suite at `cases/`, and `skills/` is generated.

## When they run

Only on the release branch, before a workflow release. They call a model, cost money and vary from
run to run, so pull requests and `main` do not run them.

## How to run

The skills are the ones Spec Kit renders from `extensions/workflow/commands/`, so build them from a
smoke install first, then run the suite from the repository root:

```bash
python extensions/scripts/smoke_install.py --host claude
rm -rf evals/skills && mkdir -p evals/skills
cp -r dist/install-tests/claude-*/project/.claude/skills/speckit-workflow-* evals/skills/
claude plugin eval evals --trust-plugin --ablation none --model sonnet --json evals/cases/results/latest.json
```

Use the newest `dist/install-tests/claude-*` folder if there are several. A case passes when its
skill was invoked in every run (the default `--threshold 1.0`). A skill that does not fire usually
means its `description` does not match how people ask; fix the command's description and rerun.
