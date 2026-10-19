"""assure_scan.py: fixture tree classification, exclusions, --check writes nothing, reruns are stable."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import assure_init  # noqa: E402
import assure_scan  # noqa: E402


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = assure_scan.main(list(argv))
    return code, out.getvalue()


class AssureScanTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        files = {
            'package.json': {'name': 'root', 'private': True, 'workspaces': ['web', 'mobile']},
            'web/package.json': {'dependencies': {'react': '18', 'vite': '5'},
                                 'devDependencies': {'@playwright/test': '1'}, 'scripts': {'dev': 'vite', 'test': 'x'}},
            'web/vite.config.ts': '',
            'web/public/favicon.ico': '',
            'mobile/package.json': {'dependencies': {'react-native': '0.74', 'react': '18'}},
            'mobile/android/build.gradle': '',
            'api/pyproject.toml': '[project]\nname = "api"\n',
            'deploy/Dockerfile': 'FROM scratch\n',
            'node_modules/vite/package.json': {'dependencies': {'react': '18'}},
            'generated/package.json': {'dependencies': {'vue': '3'}},
            '.specify/extensions/assure/extension.yml': 'extension: {}\n',
            'turbo.json': '{}',
        }
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content) if isinstance(content, dict) else content, encoding='utf-8')
        self.memory = self.root / assure_scan.MEMORY

    def test_classifies_projects_and_honours_exclusions(self):
        projects, found = assure_scan.scan(self.root, set(assure_scan.DEFAULT_EXCLUDE))
        roles = {p['path']: p['role'] for p in projects}
        self.assertEqual(roles['web'], 'web')
        self.assertEqual(roles['mobile'], 'mobile')
        self.assertEqual(roles['api'], 'backend')
        self.assertEqual(roles['deploy'], 'infrastructure')
        self.assertEqual(roles['.'], 'tooling')
        self.assertEqual(roles['generated'], 'web')
        self.assertNotIn('node_modules/vite', roles)
        self.assertFalse(any(p.startswith('.specify') for p in roles))
        web = next(p for p in projects if p['path'] == 'web')
        self.assertEqual((web['runner'], web['qa_root'], web['commands']), ('playwright', 'web/public/qa', ['dev', 'test']))
        self.assertEqual(found, ['package.json workspaces', 'turbo.json'])

    def test_config_exclude_replaces_the_default(self):
        config = self.root / assure_scan.CONFIG
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('lifecycle:\n  mode: manual\nscan:\n  exclude:\n    - node_modules\n    - generated\n', encoding='utf-8')
        run('--root', str(self.root))
        text = self.memory.read_text(encoding='utf-8')
        self.assertNotIn('| generated |', text)
        self.assertIn('| web | web | implemented | web |', text)

    def test_check_writes_nothing_and_write_is_stable(self):
        code, out = run('--root', str(self.root), '--check')
        self.assertEqual(code, 0)
        self.assertFalse(self.memory.exists())
        self.assertIn('memory: would write', out)
        self.assertIn('Last scanned: ', out)
        run('--root', str(self.root))
        first = self.memory.read_bytes()
        _, out = run('--root', str(self.root))
        self.assertEqual(self.memory.read_bytes(), first)
        self.assertIn('memory: unchanged', out)
        for section in ('Frontend Coverage Summary', 'Frontend Project Inventory', 'Detected Projects',
                        'Scan Markers', 'Maintenance Rules'):
            self.assertIn('## ' + section, first.decode('utf-8'))

    def test_a_later_day_rewrites_only_when_the_inventory_changes(self):
        # D5: the memory file is a freshness input of the document and manual states.
        run('--root', str(self.root))
        first = self.memory.read_bytes()
        later = mock.Mock(wraps=date)
        later.today.return_value = date(2099, 1, 2)
        with mock.patch.object(assure_scan, 'date', later):
            _, out = run('--root', str(self.root))
            self.assertEqual(self.memory.read_bytes(), first)
            self.assertIn('memory: unchanged', out)
            _, out = run('--root', str(self.root), '--check')
            self.assertIn('memory: unchanged', out)
            (self.root / 'svc').mkdir()
            (self.root / 'svc/go.mod').write_text('module svc\n', encoding='utf-8')
            _, out = run('--root', str(self.root))
        self.assertIn('memory: written', out)
        self.assertIn('Last scanned: 2099-01-02', self.memory.read_text(encoding='utf-8'))

    def test_text_outside_the_markers_survives(self):
        self.memory.parent.mkdir(parents=True)
        self.memory.write_text('Intro\n\n' + assure_scan.START + '\nold\n' + assure_scan.END
                               + '\n\n| admin | apps/admin | planned/spec-only | specs/001/plan.md |\n', encoding='utf-8')
        run('--root', str(self.root))
        text = self.memory.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('Intro\n\n' + assure_scan.START))
        self.assertNotIn('\nold\n', text)
        self.assertIn('planned/spec-only | specs/001/plan.md', text)

    def test_no_frontend_is_stated(self):
        projects, found = assure_scan.scan(self.root / 'api', set())
        block = assure_scan.render_block(projects, found, '2026-01-01')
        self.assertIn('No implemented web or mobile frontend was detected.', block)

    def test_init_writes_the_default_exclude_list(self):
        written = yaml.safe_load(assure_init.config_text('manual'))['scan']['exclude']
        template = yaml.safe_load((SCRIPTS.parent / 'assure-config.template.yml').read_text(encoding='utf-8'))
        self.assertEqual(written, assure_scan.DEFAULT_EXCLUDE)
        self.assertEqual(template['scan']['exclude'], assure_scan.DEFAULT_EXCLUDE)
        # The template is the only literal copy: init substitutes the mode into it.
        self.assertFalse(hasattr(assure_init, 'SCAN_EXCLUDE'))
        self.assertNotIn("'node_modules'", (SCRIPTS / 'assure_scan.py').read_text(encoding='utf-8'))
        self.assertEqual(assure_init.config_text('manual'),
                         (SCRIPTS.parent / 'assure-config.template.yml').read_text(encoding='utf-8'))
        integrated = yaml.safe_load(assure_init.config_text('integrated'))
        self.assertEqual(integrated['lifecycle'], {'mode': 'integrated', 'require_analyze_before_implement': True,
                                                   'require_document_before_pr': True})
        config = self.root / 'assure-config.yml'
        config.write_text(assure_init.config_text('integrated'), encoding='utf-8')
        parsed = assure_scan.read_config(config)
        self.assertEqual(parsed['scan']['exclude'], assure_scan.DEFAULT_EXCLUDE)
        self.assertIs(parsed['lifecycle']['require_document_before_pr'], True)


if __name__ == '__main__':
    unittest.main()
