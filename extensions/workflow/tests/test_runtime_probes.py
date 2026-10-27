"""AHMED-24: HISTORY_UNRELATED at Scope start (prepare, start) and in doctor --project. AHMED-21: doctor probes
the interpreter the host hook commands name."""
import json
import os
import stat
import unittest
from unittest.mock import patch

import test_workflow as fixture
from test_workflow import w


class StubGitHub:
    def api(self, path):
        return {'number': 10, 'title': 'Refund approval'}


class HistoryTests(unittest.TestCase):
    setUp, configure = fixture.WorkflowTests.setUp, fixture.WorkflowTests.configure

    def point_origin_head_at(self, sha):
        w.git(self.root, 'update-ref', 'refs/remotes/origin/main', sha)
        w.git(self.root, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')

    def test_an_orphan_history_is_refused_before_the_feature_exists_and_reported_by_doctor(self):
        self.assertEqual(w.doctor(self.root, self.policy, project=True)['errors'], [])  # no origin/HEAD: nothing to compare
        main = w.git(self.root, 'branch', '--show-current')
        w.git(self.root, 'switch', '-q', '--orphan', 'other')
        w.git(self.root, 'commit', '-q', '--allow-empty', '-m', 'unrelated')
        orphan = w.git(self.root, 'rev-parse', 'HEAD')
        w.git(self.root, 'switch', '-q', main)
        self.point_origin_head_at(orphan)
        with self.assertRaisesRegex(w.WorkflowError, 'HISTORY_UNRELATED: HEAD shares no commit with origin/HEAD'):
            w.prepare_issue(self.root, '10', StubGitHub())
        with self.assertRaisesRegex(w.WorkflowError, 'HISTORY_UNRELATED'):
            w.Run(self.root, self.feature).start('acme/app#10')
        self.assertFalse((self.root / self.feature / 'workflow/checkpoint.json').exists())
        errors = w.doctor(self.root, self.policy, project=True)['errors']
        self.assertTrue(any(e.startswith('HISTORY_UNRELATED') for e in errors), errors)
        self.point_origin_head_at(w.git(self.root, 'rev-parse', 'HEAD'))
        self.assertEqual(w.doctor(self.root, self.policy, project=True)['errors'], [])
        self.assertEqual(w.prepare_issue(self.root, '10', StubGitHub())['branch_owner'], 'sanduq')


class HookPythonTests(unittest.TestCase):
    setUp, configure = fixture.WorkflowTests.setUp, fixture.WorkflowTests.configure

    def hooks(self, interpreter):
        path = self.root / '.codex/hooks.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [
            {'type': 'command', 'command': interpreter + ' -c "import runpy;runpy.run_path(\'.specify/extensions/'
                                                         'workflow/hooks/guard.py\')"'}]}]}}), encoding='utf-8')

    def warnings(self):
        return [item for item in w.doctor(self.root, self.policy, explicit=True)['warnings']
                if item.startswith('HOOK_PYTHON')]

    def test_a_missing_interpreter_is_a_warning_naming_the_hook_file(self):
        self.assertEqual(self.warnings(), [])  # no hook file: nothing to probe
        self.hooks('sanduq-no-such-python')
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertTrue(warnings[0].startswith('HOOK_PYTHON_MISSING: .codex/hooks.json runs hooks with '
                                               '"sanduq-no-such-python", which is not on PATH'), warnings[0])
        self.assertIn('install.py --apply', warnings[0])

    def test_an_old_interpreter_is_a_warning_naming_the_needed_version(self):
        stub = self.root / 'stub-bin'
        stub.mkdir()
        if os.name == 'nt':
            (stub / 'hookpy.cmd').write_text('@echo 3 8\n', encoding='utf-8')
        else:
            (stub / 'hookpy').write_text('#!/bin/sh\necho 3 8\n', encoding='utf-8')
            (stub / 'hookpy').chmod((stub / 'hookpy').stat().st_mode | stat.S_IXUSR)
        self.hooks('hookpy')
        with patch.dict(os.environ, {'PATH': str(stub) + os.pathsep + os.environ.get('PATH', '')}):
            warnings = self.warnings()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertTrue(warnings[0].startswith('HOOK_PYTHON_TOO_OLD: .codex/hooks.json runs hooks with "hookpy" '
                                               '(Python 3.8); the installed hooks need 3.11 or later'), warnings[0])
        with patch.dict(os.environ, {'PATH': str(stub) + os.pathsep + os.environ.get('PATH', '')}):
            self.assertEqual([i for i in w.doctor(self.root, self.policy)['warnings'] if i.startswith('HOOK_PYTHON')],
                             [])  # a claim's doctor never pays for the probe


if __name__ == '__main__':
    unittest.main()
