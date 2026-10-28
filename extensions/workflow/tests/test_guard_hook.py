"""E4: the PreToolUse guard denies coordinator-only commands for workers on Claude Code and Codex,
and (PR6) PR publication without a matching lint receipt or from the default branch."""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1] / 'hooks'
sys.path.insert(0, str(HOOKS))
import guard


def claude(command):
    return {'session_id': 's', 'hook_event_name': 'PreToolUse', 'tool_name': 'Bash',
            'tool_input': {'command': command, 'description': 'x'}, 'cwd': '/repo'}


def codex(command):
    return {'session_id': 's', 'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'turn_id': 't',
            'tool_input': {'command': command}, 'cwd': '/repo', 'model': 'gpt'}


def powershell(command):
    return {**claude(command), 'tool_name': 'PowerShell'}


class GuardTests(unittest.TestCase):
    def run_guard(self, payload, env=None):
        stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
        stderr = io.StringIO()
        old, sys.stderr = sys.stderr, stderr
        try:
            code = guard.main(stdin, env or {})
        finally:
            sys.stderr = old
        return code, stderr.getvalue()

    GIT = ('git add -A', 'git add .', 'git add --all', 'git add -u', 'git add --update', 'git stash', 'git stash pop',
           'cd src && git -C .. add -A', 'git status; git stash push -m x', 'git commit -am x', 'git commit -a -m x',
           'git commit --all -m x', 'git commit -qam x')
    LEDGER = ('python .specify/extensions/workflow/scripts/delegate_dispatch.py accept --run r',
              'python3 scripts/delegate_dispatch.py trust-reset --task T001',
              'python delegate_dispatch.py reassign x', 'python delegate_dispatch.py adopt x')

    def test_git_commands_are_denied_in_every_session_unless_coordinator(self):
        for shape in (claude, codex, powershell):
            for command in self.GIT:
                for payload in (shape(command), {**shape(command), 'agent_id': 'a1'}):
                    code, reason = self.run_guard(payload)
                    self.assertEqual(code, 2, (shape.__name__, command))
                    self.assertEqual(reason.count('\n'), 1, reason)
                    # AHMED-20: the refusal names the intended action, never an environment bypass.
                    self.assertNotIn('SANDUQ_ROLE', reason)
                    if 'stash' not in command:
                        self.assertIn('git add -- <path>', reason)
                self.assertEqual(self.run_guard(shape(command), {'SANDUQ_ROLE': 'coordinator'})[0], 0)
                self.assertEqual(self.run_guard(shape(command), {'SANDUQ_ROLE': 'worker'})[0], 2)

    def test_ledger_verbs_are_denied_only_in_a_worker_context(self):
        for shape in (claude, codex):
            for command in self.LEDGER:
                self.assertEqual(self.run_guard(shape(command))[0], 0, command)  # the top-level session
                for payload, env in (({**shape(command), 'agent_id': 'a1'}, {}),
                                     ({**shape(command), 'agent_type': 'sanduq-worker'}, {}),
                                     (shape(command), {'SANDUQ_DELEGATED_RUN': 'run-1'}),
                                     (shape(command), {'SANDUQ_ROLE': 'worker'}),
                                     # A subagent inherits the coordinator's environment; it is still a worker.
                                     ({**shape(command), 'agent_id': 'a1'}, {'SANDUQ_ROLE': 'coordinator'})):
                    code, reason = self.run_guard(payload, env)
                    self.assertEqual(code, 2, (command, env, sorted(payload)))
                    self.assertIn('delegated worker or subagent may not run it', reason)
                    self.assertEqual(reason.count('\n'), 1, reason)

    def test_fallback_confirmation_is_refused_in_a_worker_subagent_or_orchestrator(self):
        """SEC-24: --confirm-fallback is the user's word; only the top-level session may pass it."""
        for shape in (claude, codex):
            for command in ('python .specify/extensions/workflow/scripts/delegate_dispatch.py collect --feature '
                            'specs/1-x --run-id codex-1 --confirm-fallback gpt-6-sol=default',
                            'python delegate_dispatch.py collect --run-id r --confirm-fallback=a=b'):
                self.assertEqual(self.run_guard(shape(command))[0], 0, command)  # the top-level session
                for payload, env in (({**shape(command), 'agent_id': 'a1'}, {}),
                                     ({**shape(command), 'agent_type': 'general-purpose'}, {}),
                                     (shape(command), {'SANDUQ_DELEGATED_RUN': 'run-1'}),
                                     (shape(command), {'SANDUQ_DELEGATED_ROLE': 'orchestrator'}),
                                     (shape(command), {'SANDUQ_ROLE': 'worker'})):
                    code, reason = self.run_guard(payload, env)
                    self.assertEqual(code, 2, (command, env, sorted(payload)))
                    self.assertIn("--confirm-fallback is the user's confirmation", reason)
                    self.assertEqual(reason.count('\n'), 1, reason)

    def test_native_attestation_is_refused_in_a_worker_subagent_or_orchestrator(self):
        """SAMY-03: attest-native is the top-level session's own word, refused exactly like --confirm-fallback."""
        command = ('python .specify/extensions/workflow/scripts/delegate_dispatch.py attest-native --feature specs/1-x '
                   '--id stage:plan --claim-token t --requested-model sonnet')
        for shape in (claude, codex):
            self.assertEqual(self.run_guard(shape(command))[0], 0)  # the top-level session
            for payload, env in (({**shape(command), 'agent_id': 'a1'}, {}),
                                 ({**shape(command), 'agent_type': 'general-purpose'}, {}),
                                 (shape(command), {'SANDUQ_DELEGATED_RUN': 'run-1'}),
                                 (shape(command), {'SANDUQ_DELEGATED_ROLE': 'orchestrator'}),
                                 (shape(command), {'SANDUQ_ROLE': 'worker'})):
                code, reason = self.run_guard(payload, env)
                self.assertEqual(code, 2, (env, sorted(payload)))
                self.assertIn("attest-native is the top-level session's own attestation", reason)
                self.assertEqual(reason.count('\n'), 1, reason)

    def test_hook_matcher_covers_both_shell_tools(self):
        matcher = json.loads((HOOKS / 'hooks.json').read_text(encoding='utf-8'))['hooks']['PreToolUse'][0]['matcher']
        for tool in ('Bash', 'PowerShell', 'shell'):
            self.assertTrue(re.search(matcher, tool), tool)
        self.assertIsNone(re.search(matcher, 'Edit'))

    def test_allows_ordinary_and_read_only_commands(self):
        for command in ('git add src/a.py', 'git add ./src', 'git status', 'git stash list', 'git stash show',
                        'git commit -m a', 'git commit --amend -m x', 'git commit -m "add -A"', 'git add -p src/a.py',
                        'echo "git add -A"', 'python delegate_dispatch.py start --task T001',
                        'python delegate_dispatch.py collect', 'pytest -q', ''):
            self.assertEqual(self.run_guard(claude(command))[0], 0, command)

    def test_posting_a_gate_waiver_is_denied_but_reading_one_is_not(self):
        marker = '<!-- sanduq-gate-waiver {"version":1} -->'
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'w.md').write_text(marker + '\nReason: x', encoding='utf-8')
            env = {'CLAUDE_PROJECT_DIR': folder}
            for command in ("gh pr comment 7 --body '" + marker + "'", 'gh pr comment 7 --body-file w.md',
                            "curl -d '" + marker + "' https://api.github.com/x"):
                code, reason = self.run_guard(claude(command), env)
                self.assertEqual(code, 2, command)
                self.assertIn('waiver', reason)
            self.assertEqual(self.run_guard(claude('grep -rn sanduq-gate-waiver docs'), env)[0], 0)

    def test_codex_argument_list_command(self):
        self.assertEqual(self.run_guard({'tool_name': 'Bash', 'tool_input': {'command': ['bash', '-lc', 'git add -A']}})[0], 2)

    def test_unexpected_input_never_blocks(self):
        for payload in ('', 'not json', '[]', '{"tool_input": "git add -A"}', '{"tool_input": {"command": 7}}',
                        json.dumps({'tool_name': 'Edit', 'tool_input': {'file_path': 'a'}}), 'git add "unclosed'):
            self.assertEqual(self.run_guard(payload)[0], 0, payload)

    def pr_project(self, folder, managed=True, lint='match'):
        root = Path(folder)
        if managed:
            (root / '.specify').mkdir()
            (root / '.specify/workflow.yml').write_text('version: 1\n', encoding='utf-8')
        body = root / 'specs/001-x/evidence/pr-body.md'
        body.parent.mkdir(parents=True)
        body.write_bytes(b'Closes #10\n')
        if lint:
            sha = hashlib.sha256(b'Closes #10\n').hexdigest() if lint == 'match' else '0' * 64
            body.with_suffix('.lint.json').write_text(json.dumps({'ok': True, 'body_sha256': sha}), encoding='utf-8')
        return root

    def test_pr_body_file_needs_a_matching_lint_receipt_in_a_managed_project(self):
        edit = 'gh pr edit 12 --body-file specs/001-x/evidence/pr-body.md'
        create = 'gh pr create --base main --head feat/x --title T --body-file=specs/001-x/evidence/pr-body.md'
        with patch.object(guard, 'on_default_branch', return_value=False):
            for lint, expected in (('match', 0), ('mismatch', 2), (None, 2)):
                with tempfile.TemporaryDirectory() as folder:
                    root = self.pr_project(folder, lint=lint)
                    for shape in (claude, codex):
                        for command in (edit, create, 'git status && ' + edit):
                            env_code, reason = self.run_guard(shape(command), {'CLAUDE_PROJECT_DIR': str(root)})
                            self.assertEqual(env_code, expected, (lint, command, reason))
                            cwd_code = self.run_guard({**shape(command), 'cwd': str(root)})[0]
                            self.assertEqual(cwd_code, expected, (lint, command))
                            if expected:
                                self.assertIn('pr-body.lint.json', reason)
                                self.assertEqual(reason.count('\n'), 1, reason)
            with tempfile.TemporaryDirectory() as folder:  # unmanaged: no lint rule
                root = self.pr_project(folder, managed=False, lint=None)
                self.assertEqual(self.run_guard(claude(edit), {'CLAUDE_PROJECT_DIR': str(root)})[0], 0)
            self.assertEqual(self.run_guard(claude('gh pr view --json body'), {'CLAUDE_PROJECT_DIR': '/missing'})[0], 0)

    def test_inline_pr_body_is_denied_in_a_managed_project_only(self):
        commands = ('gh pr edit 12 --body "Closes #10"', 'gh pr edit 12 -b x', 'gh pr create --title T --body=x',
                    'git status && gh pr create -t T -b "Fixes other/repo#1"', 'gh pr edit 12 --body ""')
        with patch.object(guard, 'on_default_branch', return_value=False):
            for managed, expected in ((True, 2), (False, 0)):
                with tempfile.TemporaryDirectory() as folder:
                    root = self.pr_project(folder, managed=managed)
                    for shape in (claude, codex):
                        for command in commands:
                            code, reason = self.run_guard(shape(command), {'CLAUDE_PROJECT_DIR': str(root)})
                            self.assertEqual(code, expected, (managed, command, reason))
                            if expected:
                                self.assertIn('pr_publish.py', reason)
                                self.assertEqual(reason.count(chr(10)), 1, reason)
                    self.assertEqual(self.run_guard(claude('gh pr edit 12 --body-file specs/001-x/evidence/pr-body.md'),
                                                    {'CLAUDE_PROJECT_DIR': str(root)})[0], 0)

    def test_pr_create_without_a_linted_body_file_is_denied_in_a_managed_project_only(self):
        commands = ('gh pr create --fill', 'gh pr create --fill-first --title T', 'gh pr create -t T')
        with patch.object(guard, 'on_default_branch', return_value=False):
            for managed, expected in ((True, 2), (False, 0)):
                with tempfile.TemporaryDirectory() as folder:
                    root = self.pr_project(folder, managed=managed)
                    for shape in (claude, codex):
                        for command in commands:
                            code, reason = self.run_guard(shape(command), {'CLAUDE_PROJECT_DIR': str(root)})
                            self.assertEqual(code, expected, (managed, command, reason))
                            if expected:
                                self.assertIn('pr_publish.py', reason)
                    self.assertEqual(self.run_guard(claude('gh pr edit 12 --title T'), {'CLAUDE_PROJECT_DIR': str(root)})[0], 0)

    def test_pr_create_is_denied_on_the_default_branch_only(self):
        create, edit = 'gh pr create --fill', 'gh pr edit 12 --title T'
        for head, default, expected in (('main', 'origin/main', 2), ('feat/x', 'origin/main', 0), ('main', '', 0), ('', 'origin/main', 0)):
            with patch.object(guard, 'git_output', side_effect=lambda root, *args: head if args[-1] == 'HEAD' else default):
                code, reason = self.run_guard(claude(create))
                self.assertEqual(code, expected, (head, default, reason))
                self.assertEqual(self.run_guard(codex(edit))[0], 0)
                if expected:
                    self.assertIn('default branch', reason)
                self.assertEqual(self.run_guard(claude('gh pr create --head feat/y --fill'))[0], 0)
            with patch.object(guard, 'git_output', return_value='origin/main'):  # on any branch, --head main is denied
                self.assertEqual(self.run_guard(claude('gh pr create --head main --fill'))[0], 2)
                self.assertEqual(self.run_guard(claude('gh pr create -H feat/y -F b.md'))[0], 0)

    def test_hook_command_runs_the_guard_and_tolerates_a_missing_script(self):
        command = json.loads((HOOKS / 'hooks.json').read_text(encoding='utf-8'))['hooks']['PreToolUse'][0]['hooks'][0]['command']
        command = command.replace('{python} ', '"' + sys.executable + '" ', 1)
        env = {k: v for k, v in os.environ.items()
               if k not in ('SANDUQ_ROLE', 'SANDUQ_DELEGATED_RUN', 'CLAUDE_PROJECT_DIR')}
        with tempfile.TemporaryDirectory() as folder:
            missing = subprocess.run(command, shell=True, cwd=folder, input=json.dumps(claude('git add -A')),
                                     capture_output=True, text=True, env=env)
            self.assertEqual(missing.returncode, 0, missing.stderr)
            target = Path(folder) / '.specify/extensions/workflow/hooks'
            target.mkdir(parents=True)
            (target / 'guard.py').write_bytes((HOOKS / 'guard.py').read_bytes())
            denied = subprocess.run(command, shell=True, cwd=folder, input=json.dumps(claude('git add -A')),
                                    capture_output=True, text=True, env=env)
            self.assertEqual(denied.returncode, 2, denied.stderr)
            self.assertIn('Sanduq guard', denied.stderr)
            allowed = subprocess.run(command, shell=True, cwd=folder, input=json.dumps(codex('git status')),
                                     capture_output=True, text=True, env=env)
            self.assertEqual(allowed.returncode, 0, allowed.stderr)


if __name__ == '__main__':
    unittest.main()
