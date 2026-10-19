#!/usr/bin/env python3
"""Publish the feature-details section to the branch's pull request, with the lint receipt.

    python .specify/extensions/pr/scripts/pr_publish.py --feature specs/<slug> \
        --explained docs/<slug>/<Feature>-Explained.md [--heading "<text>"] [--title "<text>"] \
        [--repo owner/repo --issue N] [--prerequisite N ...] [--base <branch>] [--no-pr]

Fetches the existing PR body (`gh pr view`), replaces the text between `<!-- speckit-pr:start -->`
and `<!-- speckit-pr:end -->` or appends the marked section, writes the exact UTF-8/LF body to
`specs/<slug>/evidence/pr-body.md`, lints closing references (Workflow's `pr_lint` when installed,
else the same rule against the bound issue only) into the sibling `pr-body.lint.json`, refuses on
findings, then `gh pr edit` or `gh pr create`. Prints the PR receipt fragment as JSON on stdout:
`pr_url`, `pr_body_file`, `pr_lint_file`, `pr_body_sha256`, `evidence`.

Exit codes: 0 published (or linted only with --no-pr); 1 the body closes a foreign, prerequisite or
unbound issue (fix the document, rerun); 2 malformed input or a missing file; 3 gh or git failed
(the docs are written; report that the PR step was skipped and why). Standard library only.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

START, END = '<!-- speckit-pr:start -->', '<!-- speckit-pr:end -->'
DEFAULT_HEADING = 'What have been developed and how to review it'
WORKFLOW_TOOLS = '.specify/extensions/workflow/scripts/execution_tools.py'
LINT_SCHEMA = 'sanduq.execution.pr-lint.v1'
CLOSE_REF = re.compile(
    r'\b(?P<kw>close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+'
    r'(?:https?://github\.com/(?P<urepo>[\w.-]+/[\w.-]+)/issues/(?P<unum>\d+)|(?P<repo>[\w.-]+/[\w.-]+)?#(?P<num>\d+))',
    re.I)
FENCE = re.compile(r'```.*?```|~~~.*?~~~|`[^`\n]*`', re.S)


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def run(args, cwd):
    """Every external call goes through here (tests replace it)."""
    try:
        return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding='utf-8', timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure(3, args[0] + ' unavailable: ' + str(exc)) from exc


def gh(root, *args):
    result = run(['gh', *args], root)
    if result.returncode:
        raise Failure(3, 'gh ' + ' '.join(args[:2]) + ' failed: ' + (result.stderr or result.stdout).strip())
    return result.stdout


def splice(existing, section):
    start, end = existing.find(START), existing.find(END)
    if start >= 0 and end > start:
        return existing[:start] + section + existing[end + len(END):]
    return (existing.rstrip('\n') + '\n\n' + section + '\n') if existing.strip() else section + '\n'


def lint(root, body, repo, issue, prerequisites):
    """Workflow's pr_lint when installed, else the same closing-reference rule in-process."""
    tools = root / WORKFLOW_TOOLS
    if tools.is_file():
        sys.path.insert(0, str(tools.parent))
        spec = importlib.util.spec_from_file_location('execution_tools', tools)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.pr_lint(body, repo, issue, prerequisites)
    prereqs = {int(p) for p in prerequisites}
    closes, violations = [], []
    for match in CLOSE_REF.finditer(FENCE.sub('', body)):
        ref_repo = (match.group('urepo') or match.group('repo') or repo).lower()
        number = int(match.group('unum') or match.group('num'))
        closes.append({'keyword': match.group('kw').lower(), 'repo': ref_repo, 'issue': number})
        code = ('FOREIGN_REPO_CLOSE' if ref_repo != repo.lower() else 'PREREQUISITE_CLOSE' if number in prereqs
                else 'UNBOUND_ISSUE_CLOSE' if number != int(issue) else None)
        if code:
            violations.append({'code': code, 'repo': ref_repo, 'issue': number})
    return {'schema': LINT_SCHEMA, 'ok': not violations, 'body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
            'bound': {'repo': repo.lower(), 'issue': int(issue)}, 'closes': closes, 'violations': violations}


def branches(root):
    head = run(['git', 'symbolic-ref', '--short', 'HEAD'], root)
    if head.returncode:
        raise Failure(3, 'not on a branch: ' + head.stderr.strip())
    default = run(['git', 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD'], root)
    if default.returncode:  # no origin/HEAD locally: ask GitHub
        default_name = gh(root, 'repo', 'view', '--json', 'defaultBranchRef', '-q', '.defaultBranchRef.name').strip()
    else:
        default_name = default.stdout.strip().split('/', 1)[-1]
    return head.stdout.strip(), default_name


def publish(root, args):
    feature = Path(args.feature)
    explained = root / args.explained
    if not explained.is_file():
        raise Failure(2, 'missing ' + args.explained)
    source = {}
    if (root / feature / 'scope-source.json').is_file():
        source = json.loads((root / feature / 'scope-source.json').read_text(encoding='utf-8'))
    repo, issue = args.repo or source.get('repo'), args.issue or source.get('issue')
    prerequisites = args.prerequisite or source.get('dependencies') or []
    if (repo is None) != (issue is None):
        raise Failure(2, '--repo and --issue go together')
    content = explained.read_text(encoding='utf-8-sig').replace('\r\n', '\n').strip('\n')
    section = START + '\n## ' + args.heading + '\n\n' + content + '\n' + END
    existing = None
    if not args.no_pr:
        view = run(['gh', 'pr', 'view', '--json', 'number,url,body'], root)
        existing = json.loads(view.stdout) if view.returncode == 0 else None
    body = splice(existing['body'] if existing else '', section).replace('\r\n', '\n')
    body_path = root / feature / 'evidence' / 'pr-body.md'
    lint_path = body_path.with_suffix('.lint.json')
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(body.encode('utf-8'))
    result = lint(root, body, repo, issue, prerequisites) if issue is not None else {
        'schema': LINT_SCHEMA, 'ok': True, 'body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
        'bound': None, 'closes': [], 'violations': [], 'note': 'no bound issue; closing references not checked'}
    lint_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    label = lambda path: path.relative_to(root).as_posix()
    receipt = {'pr_url': existing['url'] if existing else None, 'pr_body_file': label(body_path),
               'pr_lint_file': label(lint_path), 'pr_body_sha256': result['body_sha256'],
               'evidence': [label(body_path), label(lint_path)]}
    if not result['ok']:
        receipt['violations'] = result['violations']
        return 1, receipt
    if args.no_pr:
        return 0, receipt
    if existing:
        gh(root, 'pr', 'edit', str(existing['number']), '--body-file', str(body_path))
        return 0, receipt
    head, default = branches(root)
    base = args.base or default
    if head == base:
        raise Failure(3, 'current branch ' + head + ' is the base branch; create the PR from a feature branch')
    if run(['git', 'rev-parse', '--abbrev-ref', '@{u}'], root).returncode:
        push = run(['git', 'push', '--set-upstream', 'origin', head], root)
        if push.returncode:
            raise Failure(3, 'git push failed: ' + push.stderr.strip())
    title = args.title or next((line[2:].strip() for line in content.splitlines() if line.startswith('# ')), feature.name)
    gh(root, 'pr', 'create', '--base', base, '--head', head, '--title', title, '--body-file', str(body_path))
    receipt['pr_url'] = gh(root, 'pr', 'view', '--json', 'url', '-q', '.url').strip()
    return 0, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--feature', required=True, help='specs/<slug>')
    parser.add_argument('--explained', required=True, help='docs/<slug>/<Feature>-Explained.md')
    parser.add_argument('--heading', default=DEFAULT_HEADING)
    parser.add_argument('--title', help='PR title when creating (default: the first # heading of the document)')
    parser.add_argument('--repo', help='bound owner/repo (default: scope-source.json)')
    parser.add_argument('--issue', type=int, help='bound issue number (default: scope-source.json)')
    parser.add_argument('--prerequisite', action='append', type=int, help='default: scope-source.json dependencies')
    parser.add_argument('--base', help='base branch when creating (default: the repository default branch)')
    parser.add_argument('--no-pr', action='store_true', help='write and lint the body only')
    parser.add_argument('--root', default='.', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        code, receipt = publish(Path(args.root).resolve(), args)
    except Failure as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return exc.code
    except (OSError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 2
    print(json.dumps(receipt, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
