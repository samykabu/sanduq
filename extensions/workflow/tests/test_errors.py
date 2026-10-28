"""AHMED-05: the error registry (`wf_core.ERRORS`) and the `explain`/`next` fields the CLI adds; AHMED-35 and
AHMED-38: the fresh-install dependency message and `status --issue`."""
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_workflow as fixture
from test_workflow import w

SCRIPTS = Path(w.__file__).resolve().parent
# Codes a user meets through doctor, the core primitives and the issue binding; every one needs a registry entry.
REACHABLE_MODULES = ('wf_core.py', 'wf_health.py', 'wf_identity.py')
CODE = re.compile(r"'([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?::|')")


def raised_codes(names):
    return {code for name in names for code in CODE.findall((SCRIPTS / name).read_text(encoding='utf-8'))}


class RegistryTests(unittest.TestCase):
    def test_every_reachable_code_has_an_entry(self):
        missing = sorted(raised_codes(REACHABLE_MODULES) - set(w.ERRORS))
        self.assertEqual(missing, [], 'codes raised in ' + ', '.join(REACHABLE_MODULES) + ' without an entry in '
                         'wf_core.ERRORS (add one (what, why, next command) line per code): ' + ', '.join(missing))

    def test_no_entry_is_stale_and_each_prints_a_sentence_and_a_next_command(self):
        raised = raised_codes(p.name for p in SCRIPTS.glob('*.py'))
        self.assertEqual(sorted(set(w.ERRORS) - raised), [], 'registry entries no script raises any more')
        for code, (what, why, command) in w.ERRORS.items():
            with self.subTest(code=code):
                self.assertTrue(what.endswith('.') and why.endswith('.'), (what, why))
                self.assertTrue(command.strip())

    def test_explain_knows_codes_with_detail_and_fills_the_feature(self):
        self.assertEqual(w.explain('NOT_A_CODE: x'), {})
        result = w.explain('WORKFLOW_START_REQUIRED', 'specs/7-x')
        self.assertIn('start --feature specs/7-x', result['next'])
        self.assertTrue(result['explain'].endswith('.'))


class CliErrorTests(unittest.TestCase):
    setUp, configure, run_object = fixture.WorkflowTests.setUp, fixture.WorkflowTests.configure, fixture.WorkflowTests.run_object

    def command(self, **args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = w.run_command(SimpleNamespace(root=self.root, **args))
        return code, json.loads(out.getvalue())

    def test_workflow_init_required_prints_explain_and_next(self):
        with tempfile.TemporaryDirectory() as bare:
            done = subprocess.run([sys.executable, str(SCRIPTS / 'workflow.py'), '--root', bare, 'doctor'],
                                  capture_output=True, text=True, encoding='utf-8')
        result = json.loads(done.stdout)
        self.assertEqual(done.returncode, 1)
        self.assertTrue(result['error'].startswith('WORKFLOW_INIT_REQUIRED'), result)
        self.assertIn('init --qa', result['next'])
        self.assertIn('.specify/workflow.yml', result['explain'])

    def test_a_missing_key_is_named_not_printed_as_a_bare_quoted_key(self):
        with patch.object(w, 'load_policy', side_effect=KeyError('stage')):
            code, result = self.command(action='doctor', project=False)
        self.assertEqual((code, result['error']), (1, 'POLICY_KEY_MISSING: stage'))
        self.assertIn('doctor --project', result['next'])

    def test_status_accepts_the_issue_number(self):
        self.run_object()
        self.assertEqual(w.feature_for_issue(self.root, '10'), self.feature)
        code, result = self.command(action='status', feature=None, issue='10', runs=[])
        self.assertEqual(code, 0, result)
        code, result = self.command(action='status', feature=None, issue='11', runs=[])
        self.assertTrue(result['error'].startswith('ISSUE_NOT_BOUND: no feature checkpoint is bound to issue #11'))
        code, result = self.command(action='status', feature=None, issue=None, runs=[])
        self.assertTrue(result['error'].startswith('STATUS_TARGET_REQUIRED'))

    def test_dependency_unavailable_names_install_before_the_first_apply(self):
        registered = w.registry(self.root)
        registered['workflow'] = {'version': '1.18.0', 'enabled': True}
        registered['project'] = {'version': '1.0.0', 'enabled': True}
        w.write(self.root / '.specify/extensions/.registry', {'extensions': registered})
        error = [e for e in w.doctor(self.root, self.policy)['errors'] if e.startswith('DEPENDENCY_UNAVAILABLE: project')][0]
        self.assertIn('run "python .specify/extensions/workflow/scripts/install.py --apply"', error)
        w.write(self.root / '.specify/workflow/install-lock.json', {'host': 'codex'})
        error = [e for e in w.doctor(self.root, self.policy)['errors'] if e.startswith('DEPENDENCY_UNAVAILABLE: project')][0]
        self.assertIn('upgrade.py --version 1.18.0 --apply', error)


if __name__ == '__main__':
    unittest.main()
