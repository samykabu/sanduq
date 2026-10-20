"""One source for the GitHub remote reading (D4) and the PR lint (PM21): the shared module's cases, its archive
copies, an installed-layout import without Workflow or PyYAML, and no second definition in a consumer."""
import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared'))
import package  # noqa: E402
import sanduq_remote as r  # noqa: E402

SHARED = package.ROOT / 'extensions/scripts/shared'
GITHUB = {
    'https://github.com/acme/app': 'acme/app',
    'https://github.com/acme/app.git': 'acme/app',
    'https://github.com/acme/app/': 'acme/app',
    'https://github.com/acme/app.git/': 'acme/app',
    'http://github.com/acme/app': 'acme/app',
    'https://github.com:443/acme/app': 'acme/app',
    'https://x-access-token:TOKEN@github.com/acme/app': 'acme/app',
    'https://user:pass@Github.com/Acme/App.git': 'Acme/App',
    'https://github.com./acme/app': 'acme/app',
    'git@github.com:acme/app.git': 'acme/app',
    'git@github.com:acme/app.GIT': 'acme/app',
    'git@github.com:acme/app/': 'acme/app',
    'github.com:acme/app': 'acme/app',
    'ssh://git@github.com/acme/app': 'acme/app',
    'ssh://git@github.com:22/acme/app': 'acme/app',
    'ssh://git@GitHub.COM/Acme/App.git': 'Acme/App',
    'ssh://git@github.com:443/acme/app': 'acme/app',
    'git://github.com/acme/app': 'acme/app',
    'https://github.com/acme/my.app.git': 'acme/my.app',
    '  https://github.com/acme/app.git\n': 'acme/app',
}
NOT_GITHUB = (
    'https://evil.example/github.com/acme/app',  # GitHub in the path, not the host
    'git@evil.example:github.com/acme/app',
    'https://github.com@evil.example/acme/app',  # userinfo trick
    'https://evil.example:github.com/acme/app',  # non-numeric port
    'https://github.com.evil.example/acme/app',
    'https://notgithub.com/acme/app',
    'https://gitlab.com/acme/app',
    'https://github.com/acme',
    'https://github.com/acme/app/issues/1',
    '/home/me/github.com/acme/app',
    'C:\\repos\\github.com\\acme\\app',
    'file:///github.com/acme/app',
    '',
    None,
)


def blocked_import_prelude(scripts):
    """Python source that refuses PyYAML and packaging, then imports from `scripts` only."""
    return textwrap.dedent(f'''
        import sys
        class Block:
            def find_spec(self, name, path=None, target=None):
                if name.split('.')[0] in ('yaml', 'packaging'):
                    raise ImportError('blocked: ' + name)
        sys.meta_path.insert(0, Block())
        sys.path.insert(0, {str(scripts)!r})
    ''')


class RemoteCases(unittest.TestCase):
    def test_github_remotes_and_look_alikes(self):
        for url, slug in GITHUB.items():
            with self.subTest(url=url):
                self.assertEqual(r.github_slug(url), slug)
        for url in NOT_GITHUB:
            with self.subTest(url=url):
                self.assertIsNone(r.github_slug(url))

    def test_normalisation_folds_host_scheme_and_credentials_but_keeps_path_case(self):
        same = {r.normalize_remote_url(u) for u in ('https://user:pass@Github.com/Acme/App.git',
                                                    'git@github.com:Acme/App.git', 'ssh://git@github.com/Acme/App/')}
        self.assertEqual(same, {'github.com/Acme/App'})
        self.assertNotEqual(r.normalize_remote_url('ssh://host:2222/team/app'), r.normalize_remote_url('https://host/2222/team/app'))
        self.assertEqual(r.normalize_remote_url('C:\\Repos\\App.git'), 'c:/Repos/App')
        self.assertNotEqual(r.normalize_remote_url('/srv/App'), r.normalize_remote_url('/srv/app'))

    def test_same_repository_is_case_insensitive_and_none_safe(self):
        self.assertTrue(r.same_github_repository('Acme/App', 'acme/app'))
        self.assertFalse(r.same_github_repository('acme/app', 'acme/other'))
        self.assertFalse(r.same_github_repository(None, 'acme/app'))
        self.assertFalse(r.same_github_repository(None, None))

    def test_origin_url_reads_remote_origin_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git', 'init', '-q'], cwd=tmp, check=True)
            self.assertIsNone(r.origin_url(tmp))
            subprocess.run(['git', 'remote', 'add', 'origin', 'git@github.com:Acme/App.git'], cwd=tmp, check=True)
            self.assertEqual(r.origin_url(tmp), 'git@github.com:Acme/App.git')
            self.assertEqual(r.github_slug(r.origin_url(tmp)), 'Acme/App')


class PackagedCopies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.archives = {}
        for extension in sorted({e for consumers in package.SHARED.values() for e in consumers}):
            output = Path(cls.tmp.name) / (extension + '.zip')
            package.package(extension, output=output)
            cls.archives[extension] = output

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_each_consumer_archive_carries_the_source_bytes_in_its_inventory(self):
        self.assertEqual(package.SHARED['sanduq_remote.py'], ('workflow', 'project', 'scope'))
        for helper, consumers in package.SHARED.items():
            source = (SHARED / helper).read_bytes()
            for extension in consumers:
                with self.subTest(helper=helper, extension=extension), zipfile.ZipFile(self.archives[extension]) as z:
                    member = f'{extension}/scripts/{helper}'
                    self.assertEqual(z.read(member), source)
                    inventory = json.loads(z.read(extension + '/package-inventory.json'))
                    self.assertEqual(inventory[member], hashlib.sha256(source).hexdigest())

    def installed(self, extension, project):
        with zipfile.ZipFile(self.archives[extension]) as z:
            z.extractall(project / '.specify/extensions')
        return project / '.specify/extensions' / extension / 'scripts'

    def run_python(self, code, cwd):
        return subprocess.run([sys.executable, '-c', code], cwd=cwd, capture_output=True, text=True, timeout=60)

    def test_installed_copies_import_without_workflow_or_pyyaml(self):
        for helper, consumers in package.SHARED.items():
            for extension in consumers:
                with self.subTest(helper=helper, extension=extension), tempfile.TemporaryDirectory() as tmp:
                    scripts = self.installed(extension, Path(tmp))
                    call = ("print(m.github_slug('git@github.com:Acme/App.git'))" if helper == 'sanduq_remote.py'
                            else "print(m.pr_lint('Fixes #2', 'Acme/App', 1)['violations'][0]['code'])")
                    code = blocked_import_prelude(scripts) + textwrap.dedent(f'''
                        import {helper[:-3]} as m
                        assert m.__file__.startswith({str(scripts)!r}), m.__file__
                        {call}
                    ''')
                    result = self.run_python(code, tmp)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(result.stdout.strip(), ('Acme/App', 'UNBOUND_ISSUE_CLOSE'))

    def test_project_normalisation_route_never_loads_workflow_py(self):
        """Project alone, PyYAML blocked, and a Workflow whose workflow.py leaves a mark when it is loaded.
        Only Project's route is pinned: Scope loads workflow.py on purpose for checkpoint identity."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            scripts = self.installed('project', project)
            mark = project / 'workflow-was-loaded'
            workflow = project / '.specify/extensions/workflow/scripts/workflow.py'
            workflow.parent.mkdir(parents=True)
            workflow.write_text(f'open({str(mark)!r}, "w").close()\nraise SystemExit("workflow.py loaded")\n')
            code = blocked_import_prelude(scripts) + textwrap.dedent('''
                import project_sync
                print(project_sync.github_repo('git@github.com:Acme/App.git'))
                print(project_sync.github_repo('https://evil.example/github.com/acme/app'))
            ''')
            result = self.run_python(code, project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.split(), ['Acme/App', 'None'])
            self.assertFalse(mark.exists(), 'project_sync loaded the installed workflow.py')


class OneDefinition(unittest.TestCase):
    """No consumer script keeps its own copy (they import the shared module and re-export its names)."""
    MOVED = {'sanduq_remote.py': {'normalize_remote_url', '_normalize_path_remote', '_strip_dotgit'},
             'sanduq_pr_lint.py': {'pr_lint', 'CLOSE_REF'}}

    def test_moved_names_are_defined_only_in_the_shared_files(self):
        copies = []
        for path in sorted(package.ROOT.glob('extensions/*/scripts/**/*.py')):
            if 'illustrate' in path.relative_to(package.ROOT).parts[1:2] or 'tests' in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                names = ({node.name} if isinstance(node, ast.FunctionDef) else
                         {t.id for t in node.targets if isinstance(t, ast.Name)} if isinstance(node, ast.Assign) else set())
                for helper, moved in self.MOVED.items():
                    copies += [f'{path.relative_to(package.ROOT).as_posix()}: {name} (move to {helper})'
                               for name in names & moved]
        self.assertEqual(copies, [])


if __name__ == '__main__':
    unittest.main()
