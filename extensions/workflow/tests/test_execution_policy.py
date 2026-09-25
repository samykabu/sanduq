"""Exercise the distributable execution contract and its installed report helper."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('execution_package', ROOT / 'extensions/scripts/package.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class ExecutionPackageTests(unittest.TestCase):
    def test_archive_leaves_out_local_test_and_lint_caches(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'extensions/demo'
            content = {'extension.yml': 'extension: {}\n', 'scripts/run.py': 'print(1)\n'}
            generated = ('.pytest_cache/v/cache/lastfailed', '.pytest_cache/CACHEDIR.TAG',
                         'scripts/__pycache__/run.cpython-313.pyc', 'scripts/run.pyo',
                         '.mypy_cache/3.13/run.json', '.ruff_cache/0.5/state', '.hypothesis/examples/x',
                         '.tox/py/log', '.nox/py/log', 'htmlcov/index.html', '.coverage',
                         'node_modules/x/index.js', '.nyc_output/out.json')
            for name in (*content, *generated):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content.get(name, 'generated\n'), encoding='utf-8')
            package = packager.package('demo', output=root / 'demo.zip', root=root)
            with zipfile.ZipFile(package['archive']) as archive:
                self.assertEqual(sorted(archive.namelist()),
                                 ['demo/extension.yml', 'demo/package-inventory.json', 'demo/scripts/run.py'])
        # The real workflow archive too, even right after this suite has run in its folder.
        with tempfile.TemporaryDirectory() as folder:
            package = packager.package('workflow', output=Path(folder) / 'workflow.zip')
            with zipfile.ZipFile(package['archive']) as archive:
                cached = [name for name in archive.namelist()
                          if set(name.split('/')) & packager.EXCLUDE or name.endswith(('.pyc', '.pyo'))]
            self.assertEqual(cached, [])

    def test_archive_contains_both_composed_contracts_and_runnable_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            package = packager.package('workflow', output=root / 'workflow.zip')
            with zipfile.ZipFile(package['archive']) as archive:
                inventory = json.loads(archive.read('workflow/package-inventory.json'))
                for relative in ('skills/workflow/references/execution.md', 'scripts/progress.py'):
                    name = 'workflow/' + relative
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), inventory[name])
                protocol = '.specify/extensions/workflow/skills/workflow/references/execution.md'
                for executor in ('implement', 'superspec.execute'):
                    source = archive.read(f'workflow/presets/workflow/commands/speckit.{executor}.md').decode('utf-8-sig')
                    self.assertIn(protocol, source)
                    self.assertEqual(source.count('<!-- sanduq-workflow-managed:v1 -->'), 1)
                archive.extractall(root / 'installed')
            helper = root / 'installed/workflow/scripts/progress.py'
            tasks = root / 'tasks.md'
            tasks.write_text('- [ ] T001 Build feature\n- [ ] T002 Verify feature\n', encoding='utf-8')
            output = root / 'report'

            def run(*args):
                result = subprocess.run([sys.executable, str(helper), *args, '--output', str(output)],
                                        capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stderr)

            run('init', '--tasks', str(tasks))
            run('task', '--id', 'T001', '--status', 'running', '--agent', 'worker-1')
            run('event', '--message', 'Assigned T001; T002 depends on it')
            # Reinitializing during a resumed invocation must retain accepted work.
            run('init', '--tasks', str(tasks))
            state = json.loads((output / 'state.json').read_text(encoding='utf-8'))
            self.assertEqual(state['tasks'][0]['status'], 'running')
            self.assertEqual(state['tasks'][0]['agent'], 'worker-1')
            self.assertEqual(len(state['events']), 1)
            run('task', '--id', 'T001', '--status', 'done')
            run('task', '--id', 'T002', '--status', 'done')
            run('phase', '--name', 'Implementation', '--status', 'complete', '--commit', 'abc123')
            run('pr', '--url', 'https://github.com/example/repo/pull/1', '--status', 'merged')
            state = json.loads((output / 'state.json').read_text(encoding='utf-8'))
            self.assertTrue(all(task['status'] == 'done' for task in state['tasks']))
            self.assertIn('abc123', state['phases']['Implementation'])
            page = (output / 'index.html').read_text(encoding='utf-8')
            self.assertIn('2 of 2 tasks complete', page)
            self.assertIn('merged:', page)
            self.assertIn('http-equiv="refresh"', page)


if __name__ == '__main__':
    unittest.main()
