"""UM3: manual_impact.py joins the changed inputs of `manual_state.py status`
with module evidence and page `source_evidence`, gated by lifecycle.impact_scope."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    'manual_impact', Path(__file__).resolve().parents[1] / 'scripts/manual_impact.py')
impact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(impact)

MANUAL = '''schema_version: "1.0"
lifecycle:
  impact_scope: {scope}
modules:
  - id: billing
    evidence: [src/Billing/, "docs/api/billing*.yaml"]
  - id: access
    evidence: [src/Access/]
'''


def page(module, audiences, evidence):
    return (f'---\nmodule: {module}\naudiences: [{", ".join(audiences)}]\n'
            f'source_evidence: [{", ".join(evidence)}]\n---\n# Page\n')


class ManualImpactTests(unittest.TestCase):
    def manual(self, scope):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        docs = root / 'User-Manual/docs/en'
        (docs / 'modules/billing').mkdir(parents=True)
        (docs / 'modules/access').mkdir(parents=True)
        (root / 'User-Manual/manual.yml').write_text(MANUAL.format(scope=scope), encoding='utf-8')
        (docs / 'modules/billing/index.md').write_text(page('billing', ['end-user'], ['src/Billing/']), encoding='utf-8')
        (docs / 'modules/billing/refunds.md').write_text(
            page('billing', ['end-user', 'technical'], ['src/Billing/Refunds.cs']), encoding='utf-8')
        (docs / 'modules/access/index.md').write_text(page('access', ['administrator'], ['src/Access/']), encoding='utf-8')
        (docs / 'index.md').write_text(page('system', ['end-user'], ['specs/001-example/spec.md']), encoding='utf-8')
        return root

    def test_evidence_scope_lists_only_affected_modules_pages_and_audiences(self):
        root = self.manual('evidence')
        status = {'current': False, 'reason': 'stale-input-or-output',
                  'changed_inputs': ['src/Billing/Refunds.cs', 'src/Other/thing.py', 'specs/001-example/spec.md']}
        result = impact.impact(root, status)
        self.assertEqual(result['modules'], ['billing', 'system'])
        self.assertEqual(result['pages'], ['User-Manual/docs/en/index.md', 'User-Manual/docs/en/modules/billing/index.md',
                                           'User-Manual/docs/en/modules/billing/refunds.md'])
        self.assertEqual(result['audiences'], ['end-user', 'technical'])
        self.assertEqual(result['unmatched'], ['src/Other/thing.py'])
        self.assertEqual(result['impact_scope'], 'evidence')

    def test_glob_evidence_matches(self):
        result = impact.impact(self.manual('evidence'), {'changed_inputs': ['docs/api/billing-v2.yaml']})
        self.assertEqual(result['modules'], ['billing'])
        self.assertEqual(result['unmatched'], [])

    def test_scalar_source_evidence_is_one_path(self):
        root = self.manual('evidence')
        (root / 'User-Manual/docs/en/modules/access/index.md').write_text(
            '---\nmodule: access\naudiences: [administrator]\nsource_evidence: src/Access/Roles.cs\n---\n',
            encoding='utf-8')
        result = impact.impact(root, {'changed_inputs': ['s/x']})
        self.assertEqual(result['modules'], [])
        self.assertEqual(result['unmatched'], ['s/x'])

    def test_all_scope_and_missing_state_list_everything(self):
        for scope, status in (('all', {'changed_inputs': ['src/Other/thing.py']}),
                              ('evidence', {'current': False, 'reason': 'missing'})):
            with self.subTest(scope=scope):
                result = impact.impact(self.manual(scope), status)
                self.assertEqual(result['modules'], ['access', 'billing'])
                self.assertEqual(len(result['pages']), 4)
                self.assertEqual(result['audiences'], ['end-user', 'administrator', 'technical'])
                self.assertEqual(result['unmatched'], [])

    def test_unknown_scope_is_refused(self):
        with self.assertRaises(SystemExit):
            impact.impact(self.manual('some'), {'changed_inputs': []})


class InitWritesTheDefaultScope(unittest.TestCase):
    def test_init_manual_writes_impact_scope_all(self):
        spec = importlib.util.spec_from_file_location(
            'init_manual', Path(__file__).resolve().parents[1] / 'scripts/init_manual.py')
        init_manual = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(init_manual)
        text = init_manual.manual_yaml('Demo', [], False, None)
        import yaml
        self.assertEqual(yaml.safe_load(text)['lifecycle'], {'impact_scope': 'all'})


if __name__ == '__main__':
    unittest.main()
