"""MARWA-23: one model-free feature driven through every stage to PR for each tier (lite, standard, full).

The front-half benchmark harness (extensions/scripts/benchmark_front_half.py) drives the runtime's own CLI
with the unit tests' minimal receipts. Here Scope's real `bind` (with Scope's fake GitHub) writes
scope-source.json, as it does in a live run, instead of the hand-written file the harness and the unit
fixtures use. That is the gap that hid the Workflow 1.10.0 to 1.16.0 defect: every lean (lite or standard)
PR stage failed with PR_LINT_SCOPE_PREREQUISITES_REQUIRED because Scope never wrote `dependencies`.

Each tier runs in a subprocess (this file with --drive), so the runtime it loads and the harness's
instrumentation never leak into other tests. SANDUQ_E2E_REPO points the drive at another checkout's
runtime and Scope (for example a known-bad commit extracted with `git archive`); the harness always comes
from this checkout.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
CHECKOUT = HERE.parents[3]
REPO = Path(os.environ.get('SANDUQ_E2E_REPO') or CHECKOUT).resolve()
HARNESS = CHECKOUT / 'extensions/scripts'
# Scope effort dimensions whose sum lands in the tier's band (Scope's effort(): <=3 -> 2, <=7 -> 5, <=13 -> 13).
DIMENSIONS = {'lite': [1, 1, 0, 0, 0], 'standard': [2, 2, 1, 1, 0], 'full': [3, 3, 2, 2, 2]}


def drive(tier, out, defect=None):
    """Run one feature to PR at `tier` and write what happened to `out` (JSON). `defect` 'scope-1.9' makes
    bind write scope-source.json without `dependencies`, as every Scope before 1.10.0 did."""
    sys.path.insert(0, str(HARNESS))
    import benchmark_front_half as bench
    sys.path.insert(0, str(REPO / 'extensions/scope/tests'))
    import test_scope as scope_fixture
    sm = scope_fixture.m

    class Lifecycle(bench.Bench):
        def receipt(self, stage, merged=()):
            if stage == 'specify' and not (self.root / bench.FEATURE / 'scope-source.json').exists():
                self.scope_bind()
            return super().receipt(stage, merged)

        def scope_bind(self):
            """Scope publishes #10 with the tier's score, then its real bind writes scope-source.json."""
            spec = self.root / bench.FEATURE / 'spec.md'
            spec.parent.mkdir(parents=True, exist_ok=True)
            if not spec.exists():
                spec.write_text('# Fixture spec.md', encoding='utf-8')
            self.w.write(self.root / '.specify/feature.json', {'feature_directory': bench.FEATURE})
            gh = scope_fixture.FakeGitHub()
            gh.add(10)
            app = sm.Scope(self.root, gh)
            snapshot = app.inspect('10')
            node = scope_fixture.node(score=bench.TIER_SCORES[tier])
            node['dimensions'] = dict(zip(sm.DIMENSIONS, DIMENSIONS[tier]))
            analysis = {'issue': 10, 'fingerprint': snapshot['fingerprint'], 'requirements': ['AC-1'],
                        'alignment': 'Reuses tested existing behavior', 'evidence': ['src/feature.py:10'],
                        'images': [], 'tree': node}
            app.approve(snapshot, analysis, 0, 'test owner', 'I approve this exact proposal.')
            app.publish(snapshot, analysis, True)
            app.bind('10', apply=True)
            if defect == 'scope-1.9':
                source = self.root / bench.FEATURE / 'scope-source.json'
                self.w.write(source, {k: v for k, v in self.w.read(source).items() if k != 'dependencies'})

    result = {'tier': tier, 'error': None}
    real_run = subprocess.run
    with tempfile.TemporaryDirectory() as tmp:
        consumer = Path(tmp).resolve() / 'app'
        consumer.mkdir()
        lifecycle = None
        try:
            lifecycle = Lifecycle(REPO, consumer, tier, 4)
            lifecycle.recovery_error = None
            lifecycle.run()
        except Exception as exc:  # recorded for the assertions, never swallowed silently
            result['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            subprocess.run = real_run
        if lifecycle is not None:
            feature = consumer / bench.FEATURE
            result['claimed'] = lifecycle.claimed
            result['commands'] = [{k: c.get(k) for k in ('phase', 'action', 'stage', 'exit')} for c in lifecycle.commands]
            result['state'] = lifecycle.w.read(feature / 'workflow/checkpoint.json', {})
            result['scope_source'] = lifecycle.w.read(feature / 'scope-source.json', {})
    Path(out).write_text(json.dumps(result, indent=1, default=str), encoding='utf-8')


FIRST_PASS = {
    'lite': ['scope', 'specify', 'clarify', 'plan', 'analyze', 'taskstoissues', 'execute'],
    'standard': ['scope', 'specify', 'clarify', 'plan', 'qa_analyze', 'manual_analyze', 'analyze', 'taskstoissues',
                 'execute'],
    'full': ['scope', 'specify', 'clarify', 'plan', 'tasks', 'qa_analyze', 'manual_analyze', 'analyze',
             'taskstoissues', 'execute'],
}
FINISH = {'lite': ['verify', 'review', 'ready', 'pr'],
          'standard': ['verify', 'review', 'qa_document', 'manual_update', 'ready', 'pr'],
          'full': ['verify', 'review', 'qa_document', 'manual_update', 'ready', 'pr']}
SKIPPED = {'lite': {'tasks', 'qa_analyze', 'manual_analyze', 'qa_document', 'manual_update'},
           'standard': {'tasks'}, 'full': set()}
# Lean execution (on by default for lite and standard) binds the PR receipt to the recomputed body lint.
LEAN = {'lite': True, 'standard': True, 'full': False}


def start(tier, folder, defect=None):
    out = Path(folder) / f'{tier}-{defect or "ok"}.json'
    args = [sys.executable, str(HERE), '--drive', tier, str(out)] + ([defect] if defect else [])
    return out, subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


class LifecycleToPrTests(unittest.TestCase):
    """CI fails when any tier cannot reach PR, and when the 1.10 to 1.16 lean PR defect comes back."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        runs = {tier: start(tier, cls.tmp.name) for tier in FIRST_PASS}
        runs['defect'] = start('lite', cls.tmp.name, 'scope-1.9')
        cls.results, cls.logs = {}, {}
        for key, (out, proc) in runs.items():  # in parallel: each is about half a minute
            cls.logs[key] = proc.communicate(timeout=900)[0]
            cls.results[key] = json.loads(out.read_text(encoding='utf-8')) if out.is_file() else None

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def result(self, key):
        result = self.results[key]
        self.assertIsNotNone(result, self.logs[key][-3000:])
        return result

    def test_every_tier_reaches_pr_through_its_stage_sequence(self):
        for tier in FIRST_PASS:
            with self.subTest(tier=tier):
                result = self.result(tier)
                self.assertIsNone(result['error'], self.logs[tier][-2000:])
                claimed = [(c['phase'], c['stage']) for c in result['claimed']]
                expected = ([('first-pass', s) for s in FIRST_PASS[tier]]
                            + [('recovery', 'revalidate-upstream'), ('recovery', 'execute')]
                            + [('finish', s) for s in FINISH[tier]])
                self.assertEqual(expected, claimed)
                self.assertFalse([c for c in result['commands'] if c['exit']], 'a CLI command exited non-zero')

    def test_final_receipts_cover_every_stage_and_the_pr(self):
        for tier in FIRST_PASS:
            with self.subTest(tier=tier):
                state = self.result(tier)['state']
                stages = FIRST_PASS[tier] + FINISH[tier]
                self.assertEqual(stages, state['stage_plan']['stages'])
                self.assertEqual(set(stages), set(state['receipts']))
                self.assertEqual({'passed'}, {r['outcome'] for r in state['receipts'].values()})
                self.assertEqual(SKIPPED[tier], set(state.get('skipped') or {}))
                self.assertEqual(tier, state['profile']['tier'])
                self.assertIsNone(state['active'])
                self.assertIsNone(state['next_action']['stage'])
                pr = state['receipts']['pr']
                self.assertEqual('https://github.com/acme/app/pull/11', pr['pr_url'])
                self.assertEqual('speckit.pr.generate', pr['command'])
                self.assertEqual(LEAN[tier], 'pr_lint_binding' in pr)
                if LEAN[tier]:
                    self.assertEqual({'repo': 'acme/app', 'issue': 10}, pr['pr_lint_binding']['bound'])
                    self.assertEqual([], pr['pr_lint_binding']['prerequisites'])

    def test_scope_bind_wrote_the_binding_the_pr_stage_reads(self):
        for tier in FIRST_PASS:
            with self.subTest(tier=tier):
                source = self.result(tier)['scope_source']
                self.assertEqual(('acme/app', 10, []), (source['repo'], source['issue'], source['dependencies']))
                self.assertEqual(self.result(tier)['state']['profile']['score'], source['score'])

    def test_the_known_lean_pr_defect_fails_the_lifecycle_at_pr(self):
        """Workflow 1.10.0 to 1.16.0 with the Scope of the time: the lean PR stage was refused."""
        result = self.result('defect')
        self.assertIn('PR_LINT_SCOPE_PREREQUISITES_REQUIRED', result['error'] or '')
        self.assertEqual('pr', result['claimed'][-1]['stage'])
        self.assertNotIn('pr', result['state']['receipts'])


if __name__ == '__main__':
    if sys.argv[1:2] == ['--drive']:
        drive(*sys.argv[2:5])
        sys.exit(0)
    unittest.main()
