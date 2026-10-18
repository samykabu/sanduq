"""E4: the PreToolUse guard denies coordinator-only commands for workers on Claude Code and Codex."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / 'hooks'
sys.path.insert(0, str(HOOKS))
import guard


def claude(command):
    return {'session_id': 's', 'hook_event_name': 'PreToolUse', 'tool_name': 'Bash',
            'tool_input': {'command': command, 'description': 'x'}, 'cwd': '/repo'}


def codex(command):
    return {'session_id': 's', 'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'turn_id': 't',
            'tool_input': {'command': command}, 'cwd': '/repo', 'model': 'gpt'}


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

    GIT = ('git add -A', 'git add .', 'git add --all', 'git stash', 'git stash pop',
           'cd src && git -C .. add -A', 'git status; git stash push -m x')
    LEDGER = ('python .specify/extensions/workflow/scripts/delegate_dispatch.py accept --run r',
              'python3 scripts/delegate_dispatch.py trust-reset --task T001',
              'python delegate_dispatch.py reassign x', 'python delegate_dispatch.py adopt x')

    def test_git_commands_are_denied_in_every_session_unless_coordinator(self):
        for shape in (claude, codex):
            for command in self.GIT:
                for payload in (shape(command), {**shape(command), 'agent_id': 'a1'}):
                    code, reason = self.run_guard(payload)
                    self.assertEqual(code, 2, (shape.__name__, command))
                    self.assertEqual(reason.count('\n'), 1, reason)
                    self.assertIn('SANDUQ_ROLE=coordinator allows it', reason)
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

    def test_allows_ordinary_and_read_only_commands(self):
        for command in ('git add src/a.py', 'git add ./src', 'git status', 'git stash list', 'git stash show',
                        'echo "git add -A"', 'python delegate_dispatch.py start --task T001',
                        'python delegate_dispatch.py collect', 'pytest -q', ''):
            self.assertEqual(self.run_guard(claude(command))[0], 0, command)

    def test_codex_argument_list_command(self):
        self.assertEqual(self.run_guard({'tool_name': 'Bash', 'tool_input': {'command': ['bash', '-lc', 'git add -A']}})[0], 2)

    def test_unexpected_input_never_blocks(self):
        for payload in ('', 'not json', '[]', '{"tool_input": "git add -A"}', '{"tool_input": {"command": 7}}',
                        json.dumps({'tool_name': 'Edit', 'tool_input': {'file_path': 'a'}}), 'git add "unclosed'):
            self.assertEqual(self.run_guard(payload)[0], 0, payload)

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
