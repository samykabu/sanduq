"""X23: `release.py check-bumps` fails when a package's shipped files changed without a version above the catalog's;
`prepare` records the inventory hash it compares with."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release  # noqa: E402

CONSUMERS = ('scope', 'workflow', 'project', 'pr')  # package.SHARED['sanduq_gh.py']


def manifest(name, version):
    return (f'schema_version: "1.0"\nextension:\n  id: {name}\n  name: {name}\n  version: "{version}"\n'
            f'  repository: https://github.com/samykabu/sanduq\n')


class CheckBumps(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        for name in CONSUMERS + ('memory',):
            self.write(f'extensions/{name}/extension.yml', manifest(name, '1.0.0'))
            self.write(f'extensions/{name}/commands/speckit.{name}.run.md', 'Run it.\n')
            self.write(f'extensions/{name}/README.md', 'Read me.\n')
        for helper in ('sanduq_gh.py', 'check_inputs.py', 'bounded_json.py', 'evidence_snapshot.py'):
            self.write('extensions/scripts/shared/' + helper, 'TIMEOUT = 60\n')
        self.write('presets/scope-gate/preset.yml', 'id: scope-gate\n')
        self.catalog({name: '1.0.0' for name in CONSUMERS + ('memory',)})
        self.pending({})

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())

    def catalog(self, versions, hashes=True):
        entries = {name: {'version': version, **({'inventory_sha256': release.inventory_sha256(name, self.root)}
                                                 if hashes else {})} for name, version in versions.items()}
        release.write(self.root / 'catalog.json', {'extensions': entries})

    def pending(self, versions):
        release.write(self.root / 'extensions/pending-releases.json', {'versions': versions, 'status': 'pending'})

    def failed(self):
        return sorted(line.split(':')[0] for line in release.check_bumps(self.root)['failures'])

    def test_unchanged_tree_passes(self):
        self.assertEqual(release.check_bumps(self.root), {'ok': True, 'failures': [], 'notices': []})

    def test_command_change_without_a_bump_fails(self):
        self.write('extensions/pr/commands/speckit.pr.run.md', 'Run it differently.\n')
        result = release.check_bumps(self.root)
        self.assertFalse(result['ok'])
        self.assertEqual(result['failures'], ['pr: shipped files changed since 1.0.0 was released; '
                                              'run `release.py bump pr <X.Y.Z>`'])

    def test_human_docs_are_exempt_and_nested_agent_inputs_are_not(self):
        for rel in ('README.md', 'CHANGELOG.md', 'LICENSE', 'docs/guide.md'):
            self.write('extensions/memory/' + rel, 'Edited.\n')
        self.assertEqual(self.failed(), [])
        for rel in ('templates/CHANGELOG.md', 'skills/x/README.md', 'commands/docs.md'):
            with self.subTest(rel=rel):
                self.write('extensions/project/' + rel, 'Agent input.\n')
                self.assertEqual(self.failed(), ['project'])
                (self.root / 'extensions/project' / rel).unlink()

    def test_crlf_working_copy_hashes_as_lf(self):
        self.write('extensions/pr/commands/speckit.pr.run.md', 'Run it.\r\n')
        self.assertEqual(self.failed(), [])

    def test_injected_helper_change_fails_in_every_consumer(self):
        self.write('extensions/scripts/shared/sanduq_gh.py', 'TIMEOUT = 120\n')
        self.assertEqual(self.failed(), sorted(CONSUMERS))

    def test_bundled_preset_change_fails_in_its_packages(self):
        self.write('presets/scope-gate/preset.yml', 'id: scope-gate\nversion: 2\n')
        self.assertEqual(self.failed(), ['scope', 'workflow'])

    def test_a_manifest_or_pending_version_above_the_catalog_passes(self):
        self.write('extensions/scripts/shared/sanduq_gh.py', 'TIMEOUT = 120\n')
        self.write('extensions/scope/extension.yml', manifest('scope', '1.0.1'))
        self.pending({'workflow': '1.1.0'})
        self.assertEqual(self.failed(), ['pr', 'project'])

    def test_pending_with_an_equal_version_does_not_count(self):
        self.write('extensions/pr/commands/speckit.pr.run.md', 'Changed.\n')
        self.pending({'pr': '1.0.0'})
        self.assertEqual(self.failed(), ['pr'])
        self.pending({'pr': '0.9.0'})
        self.assertEqual(self.failed(), ['pr'])

    def test_entry_without_inventory_is_skipped_with_a_notice(self):
        self.catalog({'pr': '1.0.0'}, hashes=False)
        self.write('extensions/pr/commands/speckit.pr.run.md', 'Changed.\n')
        result = release.check_bumps(self.root)
        self.assertTrue(result['ok'])
        self.assertEqual(result['notices'], ['pr 1.0.0: no inventory_sha256 in catalog.json; its next release records it'])

    def test_prepare_records_the_inventory_hash(self):
        self.write('.gitignore', 'dist/\n')
        self.write('extensions/pr/extension.yml', manifest('pr', '1.1.0'))
        self.pending({'pr': '1.1.0'})
        release.write(self.root / 'extensions/catalog.json', release.read(self.root / 'catalog.json'))
        for args in (('init', '-q'), ('config', 'user.name', 'T'), ('config', 'user.email', 't@example.invalid'),
                     ('add', '.'), ('commit', '-qm', 'Source')):
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        entry = release.prepare(self.root, development=True)['catalog']['extensions']['pr']
        self.assertEqual(entry['inventory_sha256'], release.inventory_sha256('pr', self.root))
        release.write(self.root / 'catalog.json', release.prepare(self.root, development=True)['catalog'])
        self.assertEqual(self.failed(), [])

    def test_command_line_exits_1_on_a_failure(self):
        scripts = Path(release.__file__).parent
        code = ('import runpy, sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import package; '
                'package.ROOT = Path(sys.argv[2]); sys.argv = ["release.py", "check-bumps"]; '
                'runpy.run_path(str(Path(package.__file__).with_name("release.py")), run_name="__main__")')
        run = lambda: subprocess.run([sys.executable, '-c', code, str(scripts), str(self.root)],  # noqa: E731
                                     capture_output=True, text=True, timeout=120)
        self.assertEqual(run().returncode, 0)
        self.write('extensions/pr/commands/speckit.pr.run.md', 'Changed.\n')
        result = run()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('pr: shipped files changed since 1.0.0', result.stdout)


if __name__ == '__main__':
    unittest.main()
