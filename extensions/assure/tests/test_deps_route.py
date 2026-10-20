"""deps.py's non-zero line names its own next step under each policy (AU17), so commands say one sentence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
import deps  # noqa: E402

DEPENDENCIES = ('schema_version: "1.0"\ndependencies:\n  - id: illustrate\n    version: ">=2.0.0,<3.0.0"\n'
                'defaults:\n  update_policy: prompt\n  check_interval_hours: 24\n')


class DependencyRouteTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.deps_file = self.root / 'dependencies.yml'
        self.deps_file.write_text(DEPENDENCIES, encoding='utf-8')

    def ensure(self, policy, registry=None):
        policy_file = self.root / '.specify/extension-dependencies.yml'
        policy_file.parent.mkdir(parents=True, exist_ok=True)
        policy_file.write_text(f'update_policy: {policy}\n', encoding='utf-8')
        if registry:
            (self.root / '.specify/extensions').mkdir(parents=True, exist_ok=True)
            (self.root / '.specify/extensions/.registry').write_text(json.dumps({'extensions': registry}), encoding='utf-8')
        calls = []
        ok, message = deps.ensure('illustrate', self.root, self.deps_file,
                                  runner=lambda *a, **k: calls.append(a) or deps._FakeCompleted(0, '', ''))
        self.assertFalse(ok)
        self.assertEqual(calls, [])
        self.assertEqual(len(message.splitlines()), 1)
        return message

    def test_prompt_names_the_approval_route(self):
        self.assertEqual(self.ensure('prompt'), 'illustrate: absent (policy prompt); run: specify extension add '
                         'illustrate; after the user agrees, re-run with --approve')

    def test_manual_names_the_user_route(self):
        message = self.ensure('manual', {'illustrate': {'version': '1.0.0', 'enabled': True}})
        self.assertEqual(message, 'illustrate: installed 1.0.0 is outside >=2.0.0,<3.0.0 (policy manual); run: '
                         'specify extension update illustrate; the user runs it, then re-runs the command')


if __name__ == '__main__':
    unittest.main()
