"""Legacy supplemental attempts (Workflow shim) and the versioned `runs --json` contract."""
import json
import unittest

from helpers import Project, T0


class LegacyAttempts(Project):
    def usage_file(self, **fields):
        path = self.root / 'usage.json'
        path.write_text(json.dumps({'fidelity': 'exact', 'agent': 'worker-1', 'harness': 'claude', 'fresh_input': 10,
                                    'cache_read': 5, 'cache_write': 0, 'output': 3, 'reasoning': None,
                                    'since': '2026-10-15T11:00:00Z', 'until': '2026-10-15T11:30:00Z',
                                    'log': (self.root / 'logs' / 'a.jsonl').as_posix(), **fields}), encoding='utf-8')
        return str(path)

    def report(self):
        code, text = self.cli('status', '--json')
        self.assertEqual(code, 0, text)
        return json.loads(text)

    def test_record_is_one_line_labelled_legacy_and_upserts_by_run(self):
        self.init()
        self.cli('lane', 'L1', '--tasks', 'T001', '--owner', 'worker-1')
        code, line = self.cli('attempt', 'record', '--lane', 'L1', '--run', 'legacy-T001', '--status', 'running',
                              '--started', '2026-10-15T11:00:00Z')
        self.assertEqual((code, line), (0, 'progress: A1 running L1 run legacy-T001'))
        code, line = self.cli('attempt', 'record', '--lane', 'L1', '--run', 'legacy-T001', '--status', 'done',
                              '--started', '2026-10-15T11:00:00Z', '--ended', '2026-10-15T11:30:00Z',
                              '--usage-json', self.usage_file())
        self.assertEqual((code, line), (0, 'progress: A1 done L1 run legacy-T001'))
        facts = [json.loads(x) for x in self.ctx.facts.read_text(encoding='utf-8').splitlines() if '"attempt"' in x]
        self.assertEqual(len(facts), 2)
        self.assertEqual({(f['id'], f['actor'], f['source'], f['origin']) for f in facts},
                         {('A1', 'legacy', 'workflow-shim', 'legacy')})
        usage = facts[-1]['usage']
        self.assertEqual(usage['log'], 'logs/a.jsonl')  # inside the repo: stored relative
        self.assertEqual((usage['since'], usage['until'], usage['fresh_input'], usage['output']),
                         ('2026-10-15T11:00:00Z', '2026-10-15T11:30:00Z', 10, 3))
        attempt = self.report()['lanes'][0]['attempts']
        self.assertEqual([(a['run_id'], a['status'], a['origin'], a['fidelity']) for a in attempt],
                         [('legacy-T001', 'done', 'legacy', 'exact')])
        self.assertEqual(attempt[0]['tokens']['cache_read'], 5)

    def test_external_log_path_keeps_only_a_name_and_unavailable_stays_unknown(self):
        self.init()
        self.cli('lane', 'L1', '--tasks', 'T001')
        path = self.usage_file(log='C:/Users/someone/.claude/projects/x/a.jsonl', fidelity='unavailable',
                               reason='log not found', fresh_input=None)
        self.assertEqual(self.cli('attempt', 'record', '--lane', 'L1', '--run', 'r1', '--status', 'blocked',
                                  '--usage-json', path)[0], 0)
        last = json.loads(self.ctx.facts.read_text(encoding='utf-8').splitlines()[-1])
        self.assertEqual(last['usage']['log'], 'external:a.jsonl')
        attempt = self.report()['lanes'][0]['attempts'][0]
        self.assertIsNone(attempt['tokens'])
        self.assertEqual(attempt['fidelity'], 'unavailable')

    def test_overhead_attempt_has_no_lane(self):
        self.init()
        code, line = self.cli('attempt', 'record', '--overhead', 'orchestrator', '--run', 'ov1', '--status', 'done',
                              '--usage-json', self.usage_file())
        self.assertEqual((code, line), (0, 'progress: A1 done orchestrator run ov1'))
        self.assertEqual(self.report()['overhead'][0]['label'], 'orchestrator')

    def test_legacy_never_overrides_producer_state(self):
        self.workflow_file('delegations.json')
        self.workflow_file('checkpoint.json')
        self.init()
        before = self.report()
        lane = next(l for l in before['lanes'] if l['origin'] == 'workflow-delegation'
                    and any(a['run_id'] == 'run-a2' for a in l['attempts']))
        self.assertEqual(self.cli('attempt', 'record', '--lane', lane['id'], '--run', 'run-a2', '--status', 'done',
                                  '--ended', '2026-10-15T11:30:00Z')[0], 0)
        self.assertEqual(self.cli('attempt', 'record', '--lane', lane['id'], '--run', 'legacy-extra', '--status', 'done')[0], 0)
        after = self.report()
        mine = next(l for l in after['lanes'] if l['id'] == lane['id'])
        old = next(l for l in before['lanes'] if l['id'] == lane['id'])
        self.assertEqual([a for a in mine['attempts'] if a.get('origin') != 'legacy'], old['attempts'])
        self.assertEqual([a['run_id'] for a in mine['attempts'] if a.get('origin') == 'legacy'], ['legacy-extra'])
        self.assertEqual(mine['status'], old['status'])

    def test_bad_input_is_a_one_line_error(self):
        self.init()
        for args in (('--lane', 'banana', '--run', 'r', '--status', 'done'),
                     ('--lane', 'L1', '--run', 'r', '--status', 'done', '--started', 'yesterday'),
                     ('--lane', 'L1', '--run', 'r', '--status', 'done', '--usage-json', str(self.root / 'missing.json'))):
            got, line = self.cli('attempt', 'record', *args)
            self.assertEqual(got, 2, line)
            self.assertTrue(line.startswith('progress: error'), line)


class RunsContract(Project):
    def make(self, name, **files):
        folder = self.root / '.delegate' / 'runs' / name
        folder.mkdir(parents=True)
        for file, data in files.items():
            (folder / file).write_text(json.dumps(data), encoding='utf-8')

    def test_schema_fields_caveats_and_verdicts(self):
        self.make('live', **{'meta.json': {'run_id': 'live', 'harness': 'codex', 'started_at': '2026-10-15T11:59:00Z'}})
        self.make('done', **{'result.json': {
            'run_id': 'done', 'harness': 'claude', 'status': 'successful', 'started_at': '2026-10-15T10:00:00Z',
            'ended_at': '2026-10-15T10:05:00Z', 'task_verdict': 'pass', 'review_verdict': 'needs-work',
            'next_action': 'review it',
            'tokens': {'fidelity': 'exact', 'input_total': 10, 'input_fresh': 8, 'cache_read': 2, 'cache_write': 0,
                       'output_total': 5, 'reasoning': 1, 'total': 15}}})
        code, text = self.cli('runs', '--json')
        self.assertEqual(code, 0, text)
        data = json.loads(text)
        self.assertEqual(data['schema'], 'progress.runs.v1')
        self.assertEqual(data['generated_at'], T0)
        runs = {r['run_id']: r for r in data['runs']}
        self.assertEqual(runs['live']['phase'], 'active')
        self.assertEqual(runs['live']['task_verdict'], 'unknown')
        self.assertEqual((runs['done']['task_verdict'], runs['done']['review_verdict'], runs['done']['next_action']),
                         ('pass', 'needs-work', 'review it'))
        self.assertEqual(runs['done']['harness_status'], 'successful')  # harness verdict, not acceptance
        self.assertEqual(runs['done']['usage']['total'], 15)
        self.assertIsNone(runs['live']['usage'])
        self.assertEqual(len(data['caveats']), 3)
        self.assertTrue(any('not acceptance' in c for c in data['caveats']))
        self.assertTrue(any('heuristic' in c for c in data['caveats']))
        self.assertTrue(any('not active work time' in c for c in data['caveats']))

    def test_needs_no_initialised_feature_and_one_line_without_json(self):
        code, line = self.cli('runs')
        self.assertEqual((code, line), (0, 'progress: 0 runs, 0 live, 0 malformed'))
        self.assertEqual(self.cli('runs', '--json', '--now', 'garbage')[0], 2)

    def test_explicit_runs_dirs_merge_and_report_malformed(self):
        self.make('a', **{'meta.json': {'run_id': 'a', 'harness': 'codex', 'started_at': '2026-10-15T11:59:00Z'}})
        other = self.root / 'other' / 'b'
        other.mkdir(parents=True)
        (other / 'result.json').write_text(json.dumps({'run_id': 'b', 'status': 'failed'}), encoding='utf-8')
        bad = self.root / 'other' / 'bad'
        bad.mkdir()
        (bad / 'result.json').write_text('{}', encoding='utf-8')
        code, text = self.cli('runs', '--json', '--runs-dir', '.delegate/runs', '--runs-dir', 'other')
        data = json.loads(text)
        self.assertEqual(sorted(r['run_id'] for r in data['runs']), ['a', 'b'])
        self.assertEqual(len(data['malformed']), 1)


if __name__ == '__main__':
    unittest.main()
