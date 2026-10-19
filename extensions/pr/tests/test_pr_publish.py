"""PR1: pr_publish.py splices the marked section, writes the exact body and lint receipt, refuses
on findings and publishes through gh. gh and git are replaced by a fake runner; the lint runs
Workflow's rule when its script is installed and the same rule in-process otherwise."""
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pr_publish  # noqa: E402

BODY = 'Fixes #10\n'
SECTION_OLD = pr_publish.START + '\n## Old\n\nold text\n' + pr_publish.END


class FakeRunner:
    def __init__(self, pr=None, branch='feat/x', default='origin/main', upstream=True):
        self.pr, self.branch, self.default, self.upstream, self.calls = pr, branch, default, upstream, []

    def __call__(self, args, cwd):
        self.calls.append(args)
        key = ' '.join(args[:3])
        if key == 'gh pr view' and 'number,url,body' in args:
            return self.done(json.dumps(self.pr)) if self.pr else self.fail('no pull requests found')
        if key == 'gh pr view':
            return self.done('https://github.com/acme/app/pull/12')
        if key in ('gh pr edit', 'gh pr create'):
            return self.done('')
        if key == 'git symbolic-ref --short':
            if args[3] == 'HEAD':
                return self.done(self.branch)
            return self.done(self.default) if self.default else self.fail('no origin/HEAD')
        if key == 'gh repo view':
            return self.done('main')
        if key == 'git rev-parse --abbrev-ref':
            return self.done('origin/' + self.branch) if self.upstream else self.fail('no upstream')
        if key == 'git push --set-upstream':
            return self.done('')
        raise AssertionError('unexpected call ' + ' '.join(args))

    @staticmethod
    def done(stdout):
        return subprocess.CompletedProcess([], 0, stdout, '')

    @staticmethod
    def fail(stderr):
        return subprocess.CompletedProcess([], 1, '', stderr)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'specs/001-x').mkdir(parents=True)
        (self.root / 'docs/001-x').mkdir(parents=True)
        (self.root / 'specs/001-x/scope-source.json').write_text(
            json.dumps({'repo': 'acme/app', 'issue': 10, 'dependencies': [9]}), encoding='utf-8')
        self.explained = self.root / 'docs/001-x/X-Explained.md'
        self.explained.write_bytes(('# Feature X\r\n\r\n' + BODY).encode('utf-8'))  # CRLF source, LF body

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, runner, *extra):
        out = io.StringIO()
        with patch.object(pr_publish, 'run', runner), redirect_stdout(out):
            code = pr_publish.main(['--root', str(self.root), '--feature', 'specs/001-x',
                                    '--explained', 'docs/001-x/X-Explained.md', *extra])
        return code, json.loads(out.getvalue())

    def body_and_lint(self, receipt):
        body = (self.root / receipt['pr_body_file']).read_bytes()
        lint = json.loads((self.root / receipt['pr_lint_file']).read_text(encoding='utf-8'))
        return body, lint

    def test_edit_replaces_only_the_marked_section_and_receipt_matches_the_file(self):
        runner = FakeRunner(pr={'number': 12, 'url': 'https://github.com/acme/app/pull/12',
                                'body': 'Intro\n\n' + SECTION_OLD + '\n\nOutro\n'})
        code, receipt = self.run_script(runner)
        self.assertEqual(code, 0, receipt)
        body, lint = self.body_and_lint(receipt)
        text = body.decode('utf-8')
        self.assertTrue(text.startswith('Intro\n\n' + pr_publish.START + '\n## ' + pr_publish.DEFAULT_HEADING + '\n\n# Feature X\n\n' + BODY))
        self.assertTrue(text.endswith(pr_publish.END + '\n\nOutro\n'))
        self.assertEqual(text.count(pr_publish.START), 1)
        self.assertNotIn('\r', text)
        self.assertEqual(receipt['pr_body_sha256'], hashlib.sha256(body).hexdigest())
        self.assertEqual(lint['body_sha256'], receipt['pr_body_sha256'])
        self.assertEqual(receipt['evidence'], [receipt['pr_body_file'], receipt['pr_lint_file']])
        self.assertEqual(receipt['pr_url'], 'https://github.com/acme/app/pull/12')
        self.assertEqual(sorted(receipt), ['evidence', 'pr_body_file', 'pr_body_sha256', 'pr_lint_file', 'pr_url'])
        edit = next(c for c in runner.calls if c[:3] == ['gh', 'pr', 'edit'])
        self.assertEqual(edit[3:5], ['12', '--body-file'])
        self.assertEqual(Path(edit[5]), self.root / receipt['pr_body_file'])

    def test_append_when_the_existing_body_has_no_markers(self):
        runner = FakeRunner(pr={'number': 12, 'url': 'https://github.com/acme/app/pull/12', 'body': 'Hand-written\n'})
        code, receipt = self.run_script(runner)
        self.assertEqual(code, 0)
        text = self.body_and_lint(receipt)[0].decode('utf-8')
        self.assertTrue(text.startswith('Hand-written\n\n' + pr_publish.START))
        self.assertTrue(text.endswith(pr_publish.END + '\n'))

    def test_create_pushes_when_no_upstream_and_uses_the_default_branch(self):
        runner = FakeRunner(pr=None, upstream=False)
        code, receipt = self.run_script(runner)
        self.assertEqual(code, 0, receipt)
        self.assertIn(['git', 'push', '--set-upstream', 'origin', 'feat/x'], runner.calls)
        create = next(c for c in runner.calls if c[:3] == ['gh', 'pr', 'create'])
        self.assertEqual(create[3:9], ['--base', 'main', '--head', 'feat/x', '--title', 'Feature X'])
        self.assertEqual(receipt['pr_url'], 'https://github.com/acme/app/pull/12')

    def test_create_refuses_on_the_default_branch_with_exit_3(self):
        code, result = self.run_script(FakeRunner(pr=None, branch='main'))
        self.assertEqual(code, 3)
        self.assertIn('base branch', result['error'])

    def test_lint_refusal_exits_1_and_never_publishes(self):
        self.explained.write_text('# X\n\nCloses #9 and fixes other/repo#3\n', encoding='utf-8')
        runner = FakeRunner(pr={'number': 12, 'url': 'u', 'body': ''})
        code, receipt = self.run_script(runner)
        self.assertEqual(code, 1)
        self.assertEqual(sorted(v['code'] for v in receipt['violations']), ['FOREIGN_REPO_CLOSE', 'PREREQUISITE_CLOSE'])
        self.assertFalse(any(c[:3] in (['gh', 'pr', 'edit'], ['gh', 'pr', 'create']) for c in runner.calls))
        self.assertFalse(self.body_and_lint(receipt)[1]['ok'])

    def test_no_pr_lints_only(self):
        runner = FakeRunner(pr={'number': 12, 'url': 'u', 'body': ''})
        code, receipt = self.run_script(runner, '--no-pr')
        self.assertEqual((code, receipt['pr_url'], runner.calls), (0, None, []))
        self.assertTrue(self.body_and_lint(receipt)[1]['ok'])

    def test_workflow_lint_is_imported_by_path_when_installed(self):
        tools = self.root / pr_publish.WORKFLOW_TOOLS
        tools.parent.mkdir(parents=True)
        tools.write_text('def pr_lint(body, repo, issue, prerequisites=()):\n'
                         '    return {"ok": True, "body_sha256": "stub", "seen": [repo, issue, list(prerequisites)]}\n',
                         encoding='utf-8')
        code, receipt = self.run_script(FakeRunner(pr={'number': 12, 'url': 'u', 'body': ''}), '--no-pr')
        self.assertEqual((code, receipt['pr_body_sha256']), (0, 'stub'))
        self.assertEqual(self.body_and_lint(receipt)[1]['seen'], ['acme/app', 10, [9]])

    def test_fallback_lint_equals_workflow_pr_lint(self):
        sys.path.insert(0, str(ROOT / 'extensions/workflow/scripts'))
        import execution_tools
        body = 'Closes #10, fixes #9, resolves other/repo#4 `closes #99`\n```\nfixes #98\n```\n'
        self.assertEqual(pr_publish.lint(self.root, body, 'Acme/App', 10, [9]),
                         execution_tools.pr_lint(body, 'Acme/App', 10, [9]))

    def test_missing_document_exits_2(self):
        self.explained.unlink()
        self.assertEqual(self.run_script(FakeRunner())[0], 2)


if __name__ == '__main__':
    unittest.main()
