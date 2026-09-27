"""The canonical source key `bunyan-source-key/1` (workflow 1.6.0, B3)."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_key as sk  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures/source-key.fixtures.json'
# The shared fixture file is byte-identical in Bunyan (eng/ci/source-key.fixtures.json); both repositories pin it.
FIXTURES_SHA256 = '3585a9b4125bb22284f899f676b4f013563c41442e8a2284411772efeb400312'


def fixture_cases():
    return json.loads(FIXTURES.read_bytes().decode('utf-8'))['cases']


def git(root, *args, data=None):
    result = subprocess.run(['git', *args], cwd=root, input=data, capture_output=True, check=True)
    return result.stdout


class SharedFixtureTests(unittest.TestCase):
    def test_fixture_file_is_pinned(self):
        self.assertEqual(hashlib.sha256(FIXTURES.read_bytes()).hexdigest(), FIXTURES_SHA256)

    def test_contract_constants_match_the_fixture_file(self):
        data = json.loads(FIXTURES.read_bytes().decode('utf-8'))
        self.assertEqual(data['algorithm'], sk.KEY_VERSION)
        self.assertEqual(tuple(data['excludedPrefixes']), sk.EXCLUDED_PREFIXES)

    def test_every_case_reproduces_from_entries(self):
        for case in fixture_cases():
            with self.subTest(case=case['name']):
                self.assertEqual(sk.key_from_entries(case['entries']), case['key'])
                # Bytes and tuples give the same key as strings and dicts.
                as_bytes = [tuple(entry[f].encode('utf-8') for f in ('mode', 'type', 'object', 'path'))
                            for entry in case['entries']]
                self.assertEqual(sk.key_from_entries(as_bytes), case['key'])

    def test_every_case_reproduces_through_git_ls_tree(self):
        """Each case written as a real tree (objects need not exist) and keyed through git."""
        for case in fixture_cases():
            with self.subTest(case=case['name']), tempfile.TemporaryDirectory() as tmp:
                git(tmp, 'init', '-q')
                env_index = Path(tmp) / 'case.index'
                records = b''.join(
                    '{mode} {type} {object}\t{path}'.format(**entry).encode('utf-8') + b'\0'
                    for entry in case['entries'])
                env = {**os.environ, 'GIT_INDEX_FILE': str(env_index)}
                subprocess.run(['git', 'update-index', '-z', '--index-info'], cwd=tmp, input=records,
                               env=env, check=True, capture_output=True)
                tree = subprocess.run(['git', 'write-tree', '--missing-ok'], cwd=tmp, env=env, check=True,
                                      capture_output=True).stdout.decode().strip()
                self.assertEqual(sk.source_key(tmp, tree), case['key'])

    def test_markdown_suffix_and_prefixes_are_matched_on_bytes(self):
        self.assertFalse(sk.is_source_path(b'src/NOTES.mD'))
        self.assertFalse(sk.is_source_path('docs/a.cs'))
        self.assertTrue(sk.is_source_path('Docs/a.cs'))  # case-sensitive prefix
        self.assertTrue(sk.is_source_path('docs'))  # the slash is part of the prefix
        self.assertTrue(sk.is_source_path('src/readme.mdx'))
        self.assertTrue(sk.is_source_path(b'caf\xc3\xa9/\xff.cs'))  # not valid UTF-8: never decoded

    def test_parse_rejects_a_malformed_record(self):
        with self.assertRaises(sk.SourceKeyError):
            sk.parse_ls_tree(b'100644 blob\tno-object\0')


class RepositoryKeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for args in (('init', '-q'), ('config', 'user.name', 'Test'), ('config', 'user.email', 't@example.invalid'),
                     ('config', 'core.autocrlf', 'false')):
            git(self.root, *args)
        self.write('src/app.cs', 'code')
        self.write('README.md', 'words')
        self.write('specs/001/spec.md', 'spec')
        self.commit()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def commit(self):
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-qm', 'change')
        return git(self.root, 'rev-parse', 'HEAD').decode().strip()

    def test_commit_and_its_tree_have_the_same_key(self):
        tree = sk.tree_of(self.root, 'HEAD')
        self.assertEqual(sk.source_key(self.root, 'HEAD'), sk.source_key(self.root, tree))

    def test_words_and_workflow_state_do_not_move_the_key(self):
        before = sk.source_key(self.root)
        self.write('README.md', 'more words')
        self.write('specs/001/workflow/checkpoint.json', '{}')
        self.commit()
        self.assertEqual(sk.source_key(self.root), before)
        self.write('src/app.cs', 'changed code')
        self.commit()
        self.assertNotEqual(sk.source_key(self.root), before)

    def test_dirty_source_paths_ignore_excluded_paths(self):
        self.assertEqual(sk.dirty_source_paths(self.root), [])
        self.write('README.md', 'edited words')
        self.write('specs/001/new.json', '{}')
        self.assertEqual(sk.dirty_source_paths(self.root), [])
        self.write('src/new.cs', 'untracked code')
        self.write('src/app.cs', 'edited code')
        self.assertEqual(sk.dirty_source_paths(self.root), ['src/app.cs', 'src/new.cs'])

    def test_an_explicit_tree_is_required(self):
        with self.assertRaises(sk.SourceKeyError):
            sk.source_key(self.root, '')
        with self.assertRaises(sk.SourceKeyError):
            sk.source_key(self.root, 'no-such-ref')

    def test_command_line_prints_the_key(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/source_key.py'
        result = subprocess.run([sys.executable, str(script), 'HEAD', '--root', str(self.root)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), sk.source_key(self.root))


if __name__ == '__main__':
    unittest.main()
