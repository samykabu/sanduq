import json
import os
import statistics
import subprocess
import sys
import time
import unittest

import helpers
from helpers import FIXTURES, SCRIPTS, T0, Project, fixture
from sanduq_progress import snapshot, statusline
from sanduq_progress.hosts import codex
from datetime import datetime, timezone

SCRIPT = str(SCRIPTS / 'progress.py')


def bash_bind_payload(project, session, nonce, command='python .specify/extensions/progress/scripts/progress.py bind'):
    return {'session_id': session, 'cwd': project.root.as_posix(), 'hook_event_name': 'PostToolUse', 'tool_name': 'Bash',
            'tool_input': {'command': command}, 'tool_response': {'stdout': f'progress: pending bind={nonce}'},
            'tool_use_id': 'toolu_bind'}


class Binding(Project):
    def test_handshake_binds_only_the_session_that_ran_the_command(self):
        nonce = self.init()
        self.assertEqual(self.hook('post_tool_use', self.payload('claude_child_event.json', agent_id=None, session_id='other')), 'dropped')
        self.assertEqual(self.hook('post_tool_use', bash_bind_payload(self, 'claude-sess-1', nonce)), 'dirty')
        bindings = json.loads(self.ctx.bindings.read_text())
        self.assertEqual(bindings['pending'], [])
        self.assertEqual(bindings['sessions']['claude:claude-sess-1']['feature'], 'specs/001-demo')
        self.assertIsNotNone(self.snap('claude-sess-1'))
        self.assertIsNone(self.snap('other'))

    def test_unbound_and_cwd_only_observations_are_dropped(self):
        self.init()
        self.assertEqual(self.hook('post_tool_use', self.payload('claude_pre_task.json')), 'dropped')  # cwd is inside, still no bind
        self.assertEqual(list(self.ctx.host_dir.glob('*.json')), [])
        self.assertIn('unbound', (self.root / '.specify/progress/diagnostics.log').read_text())

    def test_pending_bind_expires_after_120_seconds_and_needs_the_nonce(self):
        nonce = self.init()
        late = '2026-10-15T12:02:01Z'
        self.assertEqual(self.hook('post_tool_use', bash_bind_payload(self, 's-late', nonce), now=late), 'dropped')
        self.assertEqual(self.hook('post_tool_use', bash_bind_payload(self, 's-guess', 'deadbeef0000')), 'dropped')
        self.assertEqual(self.hook('post_tool_use', bash_bind_payload(self, 's-nocmd', nonce, command='cat notes.txt')), 'dropped')

    def test_session_start_resume_keeps_binding_and_cwd_outside_worktree_is_dropped(self):
        self.init()
        self.bind()
        self.assertIn(self.hook('session_start', self.payload('claude_pre_task.json', tool_name=None)), ('dirty', 'refreshed'))
        self.assertEqual(self.hook('post_tool_use', self.payload('claude_pre_task.json', cwd=str(self.root.parent))), 'dropped')

    def test_parent_child_attribution(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.hook('pre_tool_use', self.payload('claude_pre_task.json'))
        child = self.snap()['children']['toolu_01TASK']
        self.assertEqual((child['status'], child['ended_at'], child['started_at']), ('running', None, T0))
        self.assertEqual(child['model']['fidelity'], 'partial')  # requested alias, not observed
        self.hook('post_tool_use', self.payload('claude_child_event.json'))  # fires inside a subagent
        snap = self.snap()
        self.assertEqual(snap['effort']['value'], 'high')  # parent fields come from the parent's own event
        self.assertEqual(list(snap['children']), ['toolu_01TASK'])  # the one open launch and its agent are one child
        self.assertEqual(snap['children']['toolu_01TASK']['agent_id'], 'agent-9f')
        self.hook('post_tool_use', self.payload('claude_post_task.json', tool_response={'agentId': 'agent-9f'}))
        snap = self.snap()
        self.assertEqual(len(snap['children']), 1, snap['children'])  # still one child once the tool result names the agent
        self.assertEqual(snap['children']['toolu_01TASK']['status'], 'done')
        self.assertIsNotNone(snap['children']['toolu_01TASK']['ended_at'])
        self.assertNotIn('model', {k for k in snap if k == 'model' and snap[k]['value'] == 'sonnet'})

    def test_background_child_ends_only_on_its_own_stop(self):
        self.init(debounce_seconds=0)
        self.bind()
        launch = self.payload('claude_post_task.json', tool_input={'subagent_type': 'x', 'description': 'bg', 'run_in_background': True},
                              tool_response={'agentId': 'agent-bg'})
        self.hook('post_tool_use', launch)
        key = 'toolu_01TASK'
        self.assertEqual((self.snap()['children'][key]['status'], self.snap()['children'][key]['ended_at']), ('running', None))
        self.hook('stop', self.payload('claude_child_event.json', agent_id='agent-bg'), now='2026-10-15T12:05:00Z')
        done = self.snap()['children'][key]
        self.assertEqual((done['status'], done['ended_at']), ('done', '2026-10-15T12:05:00Z'))

    def test_codex_child_is_attributed_through_agent_id_and_rollout_is_tolerant(self):
        self.init(debounce_seconds=0)
        self.bind('codex-sess-1', 'codex')
        self.hook('stop', self.payload('codex_hook.json'), host='codex')
        snap = self.snap('codex-sess-1', 'codex')
        self.assertEqual(snap['model']['value'], 'gpt-6.1-sol')
        self.assertEqual(snap['effort'], {'value': 'high', 'source': 'rollout', 'observed_at': T0, 'fidelity': 'partial'})
        self.assertEqual(snap['context']['value']['window'], 258000)
        self.assertEqual(snap['context']['value']['used_percent'], 0.4)
        self.hook('post_tool_use', self.payload('codex_child_hook.json'))
        self.assertEqual(self.snap('codex-sess-1', 'codex')['children']['codex-child-1']['model']['value'], 'gpt-6-luna')
        self.assertEqual(self.snap('codex-sess-1', 'codex')['model']['value'], 'gpt-6.1-sol')  # child model never leaks up
        self.assertEqual(codex.read_rollout(self.root / 'missing.jsonl', datetime.now(timezone.utc)), {})


class SnapshotMerge(Project):
    def test_field_preserving_merge_and_no_regression_to_older_observations(self):
        self.init(debounce_seconds=0)
        self.bind()
        stat = json.loads(fixture('claude_statusline.json', CWD=self.root.as_posix()))
        statusline.record(json.dumps(stat), self.root, datetime(2026, 10, 15, 12, 0, 5, tzinfo=timezone.utc))
        first = self.snap()
        self.assertEqual((first['model']['value'], first['effort']['value'], first['elapsed_ms']['value']), ('claude-opus-5-5', 'xhigh', 45000))
        self.assertEqual(first['context']['value'], {'used_percent': 41.2, 'used_tokens': 82000, 'window': 200000})
        self.hook('pre_tool_use', self.payload('claude_pre_task.json', tool_name='Bash', tool_input={}), now='2026-10-15T12:00:09Z')
        merged = self.snap()
        self.assertEqual(merged['model']['value'], 'claude-opus-5-5')  # hook carried no model: preserved
        self.assertEqual(merged['effort']['value'], 'high')  # newer observation replaced it
        self.hook('pre_tool_use', self.payload('claude_pre_task.json', tool_name='Bash', tool_input={}, effort={'level': 'low'}),
                  now='2026-10-15T12:00:01Z')
        self.assertEqual(self.snap()['effort']['value'], 'high')  # older observation never wins


class HookBehaviour(Project):
    def test_debounce_dirty_and_forced_final_refresh(self):
        self.init(debounce_seconds=1000)
        self.bind()
        rev = lambda: json.loads(self.ctx.state.read_text())
        before = rev()['rev']
        self.assertEqual(self.hook('post_tool_use', self.payload('claude_pre_task.json', tool_name='Bash', tool_input={})), 'dirty')
        state = rev()
        # the deferred event is published to the browser as a pending-freshness document: rev advances, dirty is set
        self.assertEqual((state['rev'], state['dirty']), (before + 1, True))
        self.assertEqual(self.hook('stop', self.payload('claude_pre_task.json', tool_name=None)), 'refreshed')
        state = rev()
        self.assertEqual((state['rev'], state['dirty']), (before + 2, False))
        self.assertEqual(self.report()['collection']['dirty'], False)
        self.assertEqual(self.hook('session_end', self.payload('claude_pre_task.json', tool_name=None)), 'refreshed')

    def test_zero_debounce_refreshes_every_event(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.assertEqual(self.hook('post_tool_use', self.payload('claude_pre_task.json', tool_name='Bash', tool_input={})), 'refreshed')

    def run_hook(self, event, stdin, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, 'hook', event], input=stdin, capture_output=True, text=True,
                              cwd=str(cwd or self.root), timeout=60, env={**os.environ, 'SANDUQ_PROGRESS_ROOT': str(self.root)})

    def test_hook_is_silent_on_success_and_on_garbage_and_never_fails(self):
        self.init(debounce_seconds=0)
        self.bind()
        ok = self.run_hook('post_tool_use', json.dumps(self.payload('claude_pre_task.json', tool_name='Bash', tool_input={})))
        self.assertEqual((ok.returncode, ok.stdout, ok.stderr), (0, '', ''))
        self.assertTrue(self.snap())
        for junk in ('', 'not json', '{"session_id": ', '[1,2]', '\x00\x01', '{}'):
            result = self.run_hook('post_tool_use', junk)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''), junk)
        self.assertEqual(self.run_hook('no_such_event', '{"session_id":"x"}').returncode, 0)
        self.assertIn('invalid payload', (self.root / '.specify/progress/diagnostics.log').read_text())

    def test_hook_swallows_internal_exceptions(self):
        self.init(debounce_seconds=0)
        self.bind()
        self.ctx.state.write_text('{"rev": "oops"')  # corrupt state: tolerated or logged, never raised
        result = self.run_hook('stop', json.dumps(self.payload('claude_pre_task.json', tool_name=None)))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_warm_hook_path_timing_is_reported(self):
        self.init(debounce_seconds=1000)
        self.bind()
        raw = json.dumps(self.payload('claude_pre_task.json', tool_name='Bash', tool_input={}))
        self.run_hook('post_tool_use', raw)  # warm the filesystem cache
        process, inproc = [], []
        for _ in range(7):
            started = time.perf_counter()
            self.run_hook('post_tool_use', raw)
            process.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            self.hook('post_tool_use', json.loads(raw))
            inproc.append((time.perf_counter() - started) * 1000)
        sys.stderr.write(f'\n[timing] warm hook: process median {statistics.median(process):.0f} ms '
                         f'(min {min(process):.0f}), in-process median {statistics.median(inproc):.1f} ms\n')


class StatuslineChain(Project):
    def run_status(self, stdin):
        return subprocess.run([sys.executable, SCRIPT, 'statusline'], input=stdin, capture_output=True, cwd=str(self.root),
                              timeout=60, env={**os.environ, 'SANDUQ_PROGRESS_ROOT': str(self.root)})

    def test_chain_preserves_stdout_and_records_only_for_bound_sessions(self):
        self.init(debounce_seconds=0)
        chain = f'"{sys.executable}" -c "import sys; d=sys.stdin.buffer.read(); sys.stdout.buffer.write(b\'CHAIN \'+str(len(d)).encode()+b\'\\n\\xc3\\xa9\')"'
        data = json.loads(self.ctx.config.read_text())
        data['statusline'] = {'enabled': True, 'chained': chain}
        self.ctx.config.write_text(json.dumps(data))
        raw = fixture('claude_statusline.json', CWD=self.root.as_posix()).encode()
        unbound = self.run_status(raw)
        self.assertEqual(unbound.stdout, f'CHAIN {len(raw)}\né'.encode())  # byte for byte, same stdin
        self.assertIsNone(self.snap())
        self.bind()
        bound = self.run_status(raw)
        self.assertEqual(bound.stdout, unbound.stdout)
        self.assertEqual(self.snap()['model']['source'], 'statusline')

    def test_minimal_line_without_a_chained_command_and_on_garbage(self):
        self.init()
        out = self.run_status(fixture('claude_statusline.json', CWD=self.root.as_posix()).encode())
        self.assertEqual(out.stdout.decode().strip(), 'Opus 5.5 | ctx 41%')
        self.assertIn('ctx 41%', out.stdout.decode())
        self.assertEqual(self.run_status(b'garbage').stdout.decode().strip(), 'Claude')

    def test_install_uninstall_round_trip_preserves_other_keys(self):
        self.init()
        settings = self.root / '.claude' / 'settings.json'
        settings.parent.mkdir()
        original = {'permissions': {'allow': ['Bash(ls)']}, 'statusLine': {'type': 'command', 'command': 'my-line.sh', 'padding': 2},
                    'env': {'A': '1'}}
        settings.write_text(json.dumps(original, indent=2))
        self.assertEqual(self.cli('statusline', 'install'), (0, 'progress: statusline installed'))
        installed = json.loads(settings.read_text())
        self.assertEqual({k: v for k, v in installed.items() if k != 'statusLine'}, {k: v for k, v in original.items() if k != 'statusLine'})
        self.assertIn('progress.py', installed['statusLine']['command'])
        self.assertEqual(installed['statusLine']['padding'], 2)
        config = json.loads(self.ctx.config.read_text())
        self.assertEqual(config['statusline']['chained'], 'my-line.sh')
        self.cli('statusline', 'install')  # idempotent: the previous line is not lost
        self.assertEqual(json.loads(self.ctx.config.read_text())['statusline']['chained'], 'my-line.sh')
        self.assertEqual(self.cli('statusline', 'uninstall'), (0, 'progress: statusline removed'))
        self.assertEqual(json.loads(settings.read_text()), original)

    def test_uninstall_without_previous_removes_only_our_key(self):
        self.init()
        settings = self.root / '.claude' / 'settings.json'
        settings.parent.mkdir()
        settings.write_text(json.dumps({'model': 'opus'}))
        self.cli('statusline', 'install')
        self.assertIn('statusLine', json.loads(settings.read_text()))
        self.cli('statusline', 'uninstall')
        self.assertEqual(json.loads(settings.read_text()), {'model': 'opus'})


if __name__ == '__main__':
    unittest.main()
