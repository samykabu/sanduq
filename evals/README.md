# Workflow entry evals

These cases check that Claude picks the right Sanduq workflow entry skill from plain phrasing:

| Case | Prompt | Expected skill |
| :- | :- | :- |
| `scope-issue` | scope issue #42 | `speckit-workflow-scope`, and no other skill |
| `plan-issue` | plan issue 42 | `speckit-workflow-continue`, and no Scope hook skill |
| `continue-feature` | continue the feature | `speckit-workflow-continue` |
| `finalize-pr` | finalize the PR | `speckit-workflow-finalize` |
| `open-pull-request` | open the pull request | `speckit-workflow-finalize` |
| `have-another-agent` | have another agent fix the failing test | anything but `delegate-task` |

Each case has `tool_used: Skill` graders; a grader with `min: 0` and `max: 0` asserts a skill never fired. They follow the
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
cp -r dist/install-tests/claude-*/project/.claude/skills/speckit-scope evals/skills/  # the short alias, with --with-aliases
python -c "import sys, pathlib; sys.path.insert(0, 'extensions/workflow/scripts'); import delegation; \
  delegation.install_skill(pathlib.Path('dist/install-tests/claude-x/project').resolve(), 'claude', 'project')"
cp -r dist/install-tests/claude-*/project/.claude/skills/delegate-task evals/skills/
claude plugin eval evals --trust-plugin --ablation none --model sonnet --json evals/cases/results/latest.json
```

Use the newest `dist/install-tests/claude-*` folder if there are several (and its name in place of `claude-x`
above; `install_skill` writes the managed delegate-task copy the way a project's first delegation does, with
`disable-model-invocation: true` and the driver description). A case passes when its
skill was invoked in every run (the default `--threshold 1.0`). A skill that does not fire usually
means its `description` does not match how people ask; fix the command's description and rerun.
