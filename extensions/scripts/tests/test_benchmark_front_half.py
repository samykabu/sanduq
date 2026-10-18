"""End-to-end check of the front-half benchmark harness (S0) against this checkout, and of the compare table.

The harness runs in a subprocess so the runtime it imports (and the sibling modules on its sys.path) never
leak into other tests in the same discover run.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
import benchmark_compare  # noqa: E402


class BenchmarkFrontHalfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / 'result.json'
        cls.proc = subprocess.run([sys.executable, str(SCRIPTS / 'benchmark_front_half.py'), '--repo', str(REPO),
                                   '--out', str(cls.out), '--source-files', '50'],
                                  capture_output=True, text=True, timeout=600)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def result(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-3000:])
        return json.loads(self.out.read_text(encoding='utf-8'))

    def test_harness_runs_the_feature_to_pr_and_records_every_metric(self):
        result = self.result()
        totals = result['totals']
        for key in ('commands', 'wall_ms', 'stdout_bytes', 'claim_stdout_bytes', 'complete_stdout_bytes',
                    'stages_run', 'model_passes', 'doctor', 'fingerprint_files', 'source_fingerprints', 'git',
                    'checkpoint_bytes', 'handoff_bytes', 'instruction_bytes', 'instruction_tokens'):
            self.assertIn(key, totals)
        self.assertEqual(result['stage_sequence'][0]['stage'], 'scope')
        self.assertEqual(result['stage_sequence'][-1]['stage'], 'pr')
        self.assertGreater(totals['doctor'], 0)
        self.assertGreater(totals['handoff_bytes'], 0)
        self.assertLessEqual(totals['model_passes'], totals['stages_run'])
        self.assertIn('scope', result['instructions']['per_stage'])
        self.assertIn('tokens = bytes / 4', result['meta']['assumptions'])
        self.assertTrue(result['meta']['recovery_path'])
        for command in result['commands']:
            self.assertEqual(set(command['counters']), {'doctor', 'fingerprint_files', 'source_fingerprints', 'git',
                                                        'git_subprocess'})

    def test_compare_renders_every_metric_with_deltas(self):
        before = self.result()
        after = json.loads(json.dumps(before))
        after['totals']['instruction_bytes'] = before['totals']['instruction_bytes'] // 2
        text = benchmark_compare.render(before, after)
        self.assertIn('| instruction_bytes |', text)
        self.assertIn('-50.0%', text)
        self.assertIn('| claim.count |', text)
        self.assertIn('| instructions.scope |', text)


class CompareUnitTests(unittest.TestCase):
    def test_delta_handles_zero_and_missing(self):
        self.assertEqual(benchmark_compare.delta(0, 0), '0%')
        self.assertEqual(benchmark_compare.delta(0, 3), 'new')
        self.assertEqual(benchmark_compare.delta(None, 3), 'n/a')
        self.assertEqual(benchmark_compare.delta(4, 3), '-25.0%')


if __name__ == '__main__':
    unittest.main()
