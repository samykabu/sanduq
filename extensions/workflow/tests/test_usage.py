import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import usage as u  # noqa: E402

SPEC = importlib.util.spec_from_file_location('progress', SCRIPTS / 'progress.py')
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


def jsonl(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(e) + '\n' for e in entries), encoding='utf-8')
    return path


def claude_line(message_id, stamp, output, fresh=2, write=100, read=1000, model='claude-test'):
    return {'type': 'assistant', 'timestamp': stamp, 'message': {
        'id': message_id, 'model': model, 'content': [{'type': 'text', 'text': 'SECRET prompt text'}],
        'usage': {'input_tokens': fresh, 'cache_creation_input_tokens': write,
                  'cache_read_input_tokens': read, 'output_tokens': output}}}


def codex_count(stamp, inp, cached, out, reasoning=0):
    return {'timestamp': stamp, 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
        'total_token_usage': {'input_tokens': inp, 'cached_input_tokens': cached, 'cache_write_input_tokens': 0,
                              'output_tokens': out, 'reasoning_output_tokens': reasoning}}}}


class ReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_claude_counts_each_streamed_response_once_at_its_final_output(self):
        log = jsonl(self.root / 'agent.jsonl', [
            claude_line('m1', '2026-09-25T10:00:00Z', 7),
            claude_line('m1', '2026-09-25T10:00:01Z', 167),
            claude_line('m1', '2026-09-25T10:00:01Z', 167),
            {'type': 'user', 'timestamp': '2026-09-25T10:00:02Z', 'message': {'content': 'tool result'}},
            claude_line('m2', '2026-09-25T10:05:00Z', 30, fresh=5, write=0, read=2000),
            'not json',
        ])
        result = u.claude(log)
        self.assertEqual(result, {'fresh_input': 7, 'cache_read': 3000, 'cache_write': 100, 'output': 197,
                                  'reasoning': None, 'model': 'claude-test', 'harness': 'claude'})

    def test_claude_window_selects_responses_by_their_start(self):
        log = jsonl(self.root / 'agent.jsonl', [
            claude_line('m1', '2026-09-25T10:00:00Z', 10),
            claude_line('m2', '2026-09-25T11:00:00Z', 20),
        ])
        result = u.claude(log, u.instant('2026-09-25T10:30:00+00:00'), None)
        self.assertEqual(result['output'], 20)
        with self.assertRaises(u.UsageUnavailable):
            u.claude(log, u.instant('2026-09-25T12:00:00Z'), None)

    def test_codex_normalises_inclusive_input_and_subtracts_the_window_baseline(self):
        log = jsonl(self.root / 'rollout-2026-09-25T10-00-00-abc123.jsonl', [
            {'timestamp': '2026-09-25T10:00:00Z', 'type': 'turn_context', 'payload': {'model': 'gpt-test'}},
            codex_count('2026-09-25T10:01:00Z', 1000, 600, 50, 20),
            codex_count('2026-09-25T10:10:00Z', 5000, 4000, 300, 100),
            codex_count('2026-09-25T10:20:00Z', 9000, 7000, 700, 150),
        ])
        whole = u.codex(log)
        self.assertEqual((whole['fresh_input'], whole['cache_read'], whole['output'], whole['reasoning'], whole['model']),
                         (2000, 7000, 700, 150, 'gpt-test'))
        window = u.codex(log, u.instant('2026-09-25T10:05:00Z'), u.instant('2026-09-25T10:15:00Z'))
        # 5000-1000 input of which 4000-600 cached; output 300-50.
        self.assertEqual((window['fresh_input'], window['cache_read'], window['output']), (600, 3400, 250))

    def test_delegate_result_uses_the_drivers_normalised_counts(self):
        path = self.root / 'result.json'
        path.write_text(json.dumps({'run_id': 'codex-1', 'harness': 'codex', 'model': 'gpt-test', 'tokens': {
            'input_total': 379599, 'input_fresh': 56143, 'cache_read': 323456, 'cache_write': 0,
            'output_total': 5644, 'reasoning': 3089, 'fidelity': 'exact'}}), encoding='utf-8')
        self.assertEqual(u.delegate(path), {'fresh_input': 56143, 'cache_read': 323456, 'cache_write': 0,
                                            'output': 5644, 'reasoning': 3089, 'model': 'gpt-test', 'harness': 'codex'})
        path.write_text(json.dumps({'run_id': 'copilot-1', 'tokens': {'fidelity': 'unavailable'}}), encoding='utf-8')
        with self.assertRaises(u.UsageUnavailable):
            u.delegate(path)

    def test_locate_finds_agent_logs_by_host_id_and_refuses_to_guess(self):
        jsonl(self.root / 'claude/proj/session/subagents/agent-a1b2.jsonl', [])
        jsonl(self.root / 'codex/2026/09/25/rollout-2026-09-25T10-00-00-0199aa.jsonl', [])
        with patch.dict(os.environ, {'SANDUQ_CLAUDE_PROJECTS': str(self.root / 'claude'),
                                     'SANDUQ_CODEX_SESSIONS': str(self.root / 'codex')}):
            self.assertEqual(u.locate('claude', 'a1b2').name, 'agent-a1b2.jsonl')
            self.assertEqual(u.locate('claude', 'agent-a1b2').name, 'agent-a1b2.jsonl')
            self.assertTrue(u.locate('codex', '0199aa').name.endswith('0199aa.jsonl'))
            with self.assertRaises(u.UsageUnavailable):
                u.locate('claude', 'missing')
            jsonl(self.root / 'claude/proj/other/subagents/agent-a1b2.jsonl', [])
            with self.assertRaisesRegex(u.UsageUnavailable, 'Several'):
                u.locate('claude', 'a1b2')

    def test_timestamps_need_a_zone(self):
        with self.assertRaises(ValueError):
            u.instant('2026-09-25T10:00:00')


class ReportUsageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.tasks = self.root / 'tasks.md'
        self.tasks.write_text('# Tasks: Demo\n## Phase 1: Setup\n- [ ] T001 One\n- [ ] T002 Two\n'
                              '## Phase 2: Build\n- [ ] T003 Three\n', encoding='utf-8')
        self.out = self.root / 'report'
        self.cli('init', '--tasks', str(self.tasks))

    def cli(self, *args):
        p.main([args[0], '--output', str(self.out), *args[1:]])

    def state(self):
        return json.loads((self.out / 'state.json').read_text(encoding='utf-8'))

    def page(self):
        return (self.out / 'index.html').read_text(encoding='utf-8')

    def claude_log(self, name, entries):
        return jsonl(self.root / 'logs' / name, entries)

    def test_task_phase_and_feature_totals_render_without_copying_log_content(self):
        one = self.claude_log('one.jsonl', [claude_line('m1', '2026-09-25T10:00:00Z', 100)])
        three = self.claude_log('three.jsonl', [claude_line('m3', '2026-09-25T10:00:00Z', 400, fresh=50)])
        self.cli('usage', '--id', 'T001', '--agent', 'w1', '--collect', 'claude', '--log', str(one))
        self.cli('usage', '--id', 'T003', '--agent', 'w3', '--collect', 'claude', '--log', str(three))
        self.cli('usage', '--overhead', 'orchestrator', '--agent', 'orch', '--fresh-input', '10',
                 '--cached-input', '90', '--output-tokens', '5')
        state, page = self.state(), self.page()
        self.assertNotIn('SECRET', json.dumps(state))
        self.assertNotIn('SECRET', page)
        self.assertEqual(state['tasks'][0]['usage'][0]['fidelity'], 'exact')
        # Task row carries its figures for the filtered footer total.
        self.assertIn('data-fresh="2" data-cached="1100" data-out="100"', page)
        self.assertIn('data-fresh="" data-cached="" data-out=""', page)  # T002 measured nothing
        self.assertRegex(page, r'Phase 1: Setup</th><td class="num partial">2</td>')  # T002 has no measurement
        self.assertRegex(page, r'Phase 2: Build</th><td class="num">50</td><td class="num">1,100</td><td class="num">400</td>')
        self.assertRegex(page, r'overhead</th><td class="num partial">10</td>')
        self.assertIn('Feature total</th><td class="num partial">62</td><td class="num partial">2,290</td>'
                      '<td class="num partial">505</td>', page)
        self.assertIn('Implementation tokens: 62 fresh input, 2,290 cached input, 505 output.', page)
        self.assertIn('Implementation only', page)
        self.assertIn('2 of 3', page)

    def test_recollecting_replaces_instead_of_double_counting(self):
        log = self.claude_log('one.jsonl', [claude_line('m1', '2026-09-25T10:00:00Z', 100)])
        for _ in range(3):
            self.cli('usage', '--id', 'T001', '--agent', 'w1', '--collect', 'claude', '--log', str(log))
            self.cli('usage', '--overhead', 'orchestrator', '--agent', 'orch', '--collect', 'claude', '--log', str(log))
        state = self.state()
        self.assertEqual(len(state['tasks'][0]['usage']), 1)
        self.assertEqual(len(state['overhead']), 1)

    def test_a_reused_worker_is_split_by_task_attempt(self):
        log = self.claude_log('shared.jsonl', [])
        # Each task update reads the clock twice: the attempt boundary, then the report's updated time.
        clock = iter([moment for minute in ('00', '10', '20', '30')
                      for moment in ('2026-09-25T10:' + minute + ':00+00:00',) * 2])
        with patch.object(p, 'stamp', side_effect=lambda: next(clock, '2026-09-25T11:00:00+00:00')):
            self.cli('task', '--id', 'T001', '--status', 'running', '--agent', 'w')   # 10:00
            self.cli('task', '--id', 'T001', '--status', 'done')                       # 10:10
            self.cli('task', '--id', 'T002', '--status', 'running', '--agent', 'w')   # 10:20
            self.cli('task', '--id', 'T002', '--status', 'done')                       # 10:30
        jsonl(log, [claude_line('a', '2026-09-25T10:05:00Z', 11), claude_line('b', '2026-09-25T10:25:00Z', 22)])
        self.cli('usage', '--id', 'T001', '--agent', 'w', '--collect', 'claude', '--log', str(log))
        self.cli('usage', '--id', 'T002', '--agent', 'w', '--collect', 'claude', '--log', str(log))
        tasks = self.state()['tasks']
        self.assertEqual(tasks[0]['usage'][0]['output'], 11)
        self.assertEqual(tasks[1]['usage'][0]['output'], 22)

    def test_reused_worker_without_an_attempt_window_is_refused(self):
        log = self.claude_log('shared.jsonl', [claude_line('a', '2026-09-25T10:05:00Z', 11)])
        self.cli('task', '--id', 'T001', '--status', 'done', '--agent', 'w')
        self.cli('task', '--id', 'T002', '--status', 'done', '--agent', 'w')
        with self.assertRaises(SystemExit):
            self.cli('usage', '--id', 'T002', '--agent', 'w', '--collect', 'claude', '--log', str(log))

    def test_missing_log_is_recorded_as_a_visible_gap_not_zero(self):
        self.cli('usage', '--id', 'T001', '--agent', 'gone', '--collect', 'claude',
                 '--log', str(self.root / 'missing.jsonl'))
        state, page = self.state(), self.page()
        self.assertEqual(state['tasks'][0]['usage'][0]['fidelity'], 'unavailable')
        self.assertTrue(any('Token usage unavailable for gone' in e for e in state['events']))
        self.assertIn('No token usage recorded yet.', page)
        self.assertNotIn('>0<', page)

    def test_reopened_and_removed_tasks_keep_their_usage(self):
        log = self.claude_log('one.jsonl', [claude_line('m1', '2026-09-25T10:00:00Z', 100)])
        self.cli('usage', '--id', 'T001', '--agent', 'w1', '--collect', 'claude', '--log', str(log))
        self.cli('usage', '--id', 'T003', '--agent', 'w3', '--collect', 'claude', '--log', str(log))
        self.tasks.write_text('# Tasks: Demo\n## Phase 1: Setup\n- [ ] T001 One revised\n- [ ] T002 Two\n',
                              encoding='utf-8')
        self.cli('init', '--tasks', str(self.tasks))
        state, page = self.state(), self.page()
        self.assertEqual(state['tasks'][0]['usage'][0]['output'], 100)
        self.assertEqual(state['archived_tasks'][0]['usage'][0]['output'], 100)
        self.assertIn('Removed tasks</th>', page)
        self.assertIn('Implementation tokens: 4 fresh input, 2,200 cached input, 200 output.', page)

    def test_report_uses_the_sanduq_mark_as_its_page_icon(self):
        self.assertIn('<link rel="icon" type="image/png" sizes="128x128" href="sanduq-icon.png">', self.page())
        self.assertEqual((self.out / 'sanduq-icon.png').read_bytes(), (p.ASSETS / p.ICON).read_bytes())


if __name__ == '__main__':
    unittest.main()
