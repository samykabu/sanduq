#!/usr/bin/env python3
"""Publish the feature-details section to the branch's pull request, with the lint receipt.

    python .specify/extensions/pr/scripts/pr_publish.py --feature specs/<slug> \
        --explained docs/<slug>/<Feature>-Explained.md [--heading "<text>"] [--title "<text>"] \
        [--repo owner/repo --issue N] [--prerequisite N ...] [--base <branch>] [--no-pr]

Fetches the existing PR body (`gh pr view`), replaces the text between `<!-- speckit-pr:start -->`
and `<!-- speckit-pr:end -->` or appends the marked section (a body whose markers are unpaired or
repeated is refused, never appended to), rewrites each relative image path to the commit-pinned
`https://github.com/<repo>/blob/<HEAD sha>/<path>?raw=true` and each relative link `[text](path)` to
`https://github.com/<repo>/blob/<HEAD sha>/<path>[#anchor]` after checking the file is committed at
HEAD and readable through the contents API at that commit (pushing a new PR's branch first when it has
no upstream or its upstream is behind), adds `Closes <repo>#<issue>` for the bound issue when the
document does not close it already, writes the exact UTF-8/LF body to
`specs/<slug>/evidence/pr-body.md`, lints closing references with the shared `sanduq_pr_lint` rule (the one Workflow's `pr-lint`
runs) into the sibling `pr-body.lint.json`, refuses on
findings, then `gh pr edit` or `gh pr create`. Prints the PR receipt fragment as JSON on stdout:
`pr_url`, `pr_body_file`, `pr_lint_file`, `pr_body_sha256`, `evidence`.

Exit codes: 0 published (or linted only with --no-pr); 1 the body closes a foreign, prerequisite or
unbound issue (fix the document, rerun); 2 malformed input or a missing file; 3 gh or git failed
(the docs are written; report that the PR step was skipped and why), including a PR lookup that
fails for any reason other than "no pull requests found", a branch whose PR is merged or closed (it
is never edited), and an image that cannot be verified on the remote. Standard library only.
"""
import argparse
import hashlib
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote

try:
    import sanduq_gh
    from sanduq_pr_lint import FENCE, PR_LINT_SCHEMA, pr_lint
except ModuleNotFoundError:
    # Source checkout only; release archives bundle the shared helpers next to this script.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
    import sanduq_gh
    from sanduq_pr_lint import FENCE, PR_LINT_SCHEMA, pr_lint

START, END = '<!-- speckit-pr:start -->', '<!-- speckit-pr:end -->'
DEFAULT_HEADING = 'What have been developed and how to review it'
IMG_TAG = re.compile(r'(<img\b[^>]*?\bsrc=["\'])([^"\']+)', re.I)
# a Markdown image (group 1 is "!") or link up to its destination; zero-width, so an image inside a link's text
# is found too; the text allows one nested [..]
LINK = re.compile(r'(?:(!)|(?<!!))(?=(\[(?:[^\[\]\n]|\[[^\[\]\n]*\])*\]\([ \t]*))')
ESCAPE = re.compile(r'\\([!-/:-@\[-`{-~])')  # CommonMark backslash-escaped ASCII punctuation
REMOTE = re.compile(r'[a-z][a-z0-9+.-]*:|//|#', re.I)
NO_PR = 'no pull requests found'


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def gh_process(args, cwd, timeout):
    """`gh <args>` through the shared transport (never retried) as a CompletedProcess; raises `GhError` only
    when gh is missing or timed out (pr_changelog uses it too)."""
    try:
        return subprocess.CompletedProcess(['gh', *args], 0, sanduq_gh.run_gh(args, cwd=str(cwd), timeout=timeout), '')
    except sanduq_gh.GhError as exc:
        if exc.timeout or exc.returncode == sanduq_gh.GH_MISSING:
            raise
        return subprocess.CompletedProcess(['gh', *args], exc.returncode, exc.stdout, exc.stderr)


def run(args, cwd):
    """Every external call goes through here (tests replace it); gh through the shared transport."""
    try:
        if args[0] == 'gh':
            return gh_process(args[1:], cwd, 120)
        return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding='utf-8', timeout=120)
    except (OSError, subprocess.TimeoutExpired, sanduq_gh.GhError) as exc:
        raise Failure(3, args[0] + ' unavailable: ' + str(exc)) from exc


def gh(root, *args):
    result = run(['gh', *args], root)
    if result.returncode:
        raise Failure(3, 'gh ' + ' '.join(args[:2]) + ' failed: ' + (result.stderr or result.stdout).strip())
    return result.stdout


def splice(existing, section):
    starts, ends = existing.count(START), existing.count(END)
    start, end = existing.find(START), existing.find(END)
    if (starts, ends) == (1, 1) and end > start:
        return existing[:start] + section + existing[end + len(END):]
    if starts or ends:
        raise Failure(2, 'the PR body has %d start and %d end speckit-pr markers; leave exactly one pair (start '
                         'before end) or none, then rerun' % (starts, ends))
    return (existing.rstrip('\n') + '\n\n' + section + '\n') if existing.strip() else section + '\n'


def link_targets(text):
    """(start, end, is_image) of each Markdown image or link destination in text: `<...>`, or bare with balanced
    parentheses and backslash escapes, ending at whitespace (an optional title follows) or the closing parenthesis."""
    spans = []
    for m in LINK.finditer(text):
        i, image = m.end() + len(m.group(2)), bool(m.group(1))
        if text[i:i + 1] == '<':
            end = text.find('>', i)
            if end > i + 1 and '\n' not in text[i:end]:
                spans.append((i + 1, end, image))
            continue
        depth, j = 0, i
        while j < len(text) and not text[j].isspace():
            if text[j] == '\\':
                j += 1
            elif text[j] == '(':
                depth += 1
            elif text[j] == ')':
                if not depth:
                    break
                depth -= 1
            j += 1
        if j > i and depth == 0:
            spans.append((i, j, image))
    return spans


def pin_markdown(text, urls, link_urls):
    for start, end, image in sorted(link_targets(text), reverse=True):  # last destination first: offsets hold
        target = text[start:end]
        text = text[:start] + (urls if image else link_urls).get(target, target) + text[end:]
    return text


def pin_images(root, content, explained, push):
    """Relative image paths and links (outside code) become commit-pinned GitHub URLs, each verified first."""
    parts, fences = FENCE.split(content), FENCE.findall(content)
    spans = [(part[a:b], image) for part in parts for a, b, image in link_targets(part)]
    images = {m.group(2) for part in parts for m in IMG_TAG.finditer(part)} | {t for t, image in spans if image}
    links = {t for t, image in spans if not image}
    targets = sorted(t for t in images | links if t and not REMOTE.match(t))
    if not targets:
        return content
    push()
    repo = gh(root, 'repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner').strip()
    head = run(['git', 'rev-parse', 'HEAD'], root)
    if head.returncode:
        raise Failure(3, 'git rev-parse HEAD failed: ' + head.stderr.strip())
    sha, folder, urls, link_urls = head.stdout.strip(), posixpath.dirname(explained), {}, {}
    for target in targets:
        kind = 'image' if target in images else 'link'
        clean, _, anchor = ESCAPE.sub(r'\1', target).partition('#')
        clean = unquote(clean.split('?')[0])
        path = posixpath.normpath(clean.lstrip('/') if clean.startswith('/') else posixpath.join(folder, clean))
        if path == '..' or path.startswith('../'):
            raise Failure(2, kind + ' ' + target + ' points outside the repository')
        if run(['git', 'cat-file', '-e', sha + ':' + path], root).returncode:
            raise Failure(2, kind + ' ' + target + ' (' + path + ') is not committed at HEAD: git add "' + path +
                             '" && git commit, then git push when the PR exists, and rerun')
        check = run(['gh', 'api', 'repos/%s/contents/%s?ref=%s' % (repo, quote(path), sha), '--silent'], root)
        if check.returncode:
            raise Failure(3, kind + ' ' + path + ' is not readable on ' + repo + ' at ' + sha[:12] +
                             ' (git push, then rerun): ' + (check.stderr or check.stdout).strip())
        blob = 'https://github.com/%s/blob/%s/%s' % (repo, sha, quote(path))
        urls[target], link_urls[target] = blob + '?raw=true', blob + ('#' + anchor if anchor else '')
    pin = lambda m: m.group(1) + urls.get(m.group(2), m.group(2))
    pinned = [IMG_TAG.sub(pin, pin_markdown(part, urls, link_urls)) for part in parts]
    return ''.join(text + (fences[i] if i < len(fences) else '') for i, text in enumerate(pinned))


def default_branch(root):
    """The repository's default branch name: origin/HEAD, else GitHub's answer (pr_changelog uses it too)."""
    default = run(['git', 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD'], root)
    if default.returncode:  # no origin/HEAD locally: ask GitHub
        return gh(root, 'repo', 'view', '--json', 'defaultBranchRef', '-q', '.defaultBranchRef.name').strip()
    return default.stdout.strip().split('/', 1)[-1]


def branches(root):
    head = run(['git', 'symbolic-ref', '--short', 'HEAD'], root)
    if head.returncode:
        raise Failure(3, 'not on a branch: ' + head.stderr.strip())
    return head.stdout.strip(), default_branch(root)


def ensure_branch(root, args):
    """(head, base) for a new PR; pushes the head when it has no upstream yet or the upstream is behind."""
    head, default = branches(root)
    base = args.base or default
    if head == base:
        raise Failure(3, 'current branch ' + head + ' is the base branch; create the PR from a feature branch')
    if run(['git', 'rev-parse', '--abbrev-ref', '@{u}'], root).returncode:
        push = run(['git', 'push', '--set-upstream', 'origin', head], root)
    else:
        ahead = run(['git', 'rev-list', '--count', '@{u}..HEAD'], root)
        push = run(['git', 'push'], root) if ahead.returncode or ahead.stdout.strip() != '0' else None
    if push is not None and push.returncode:
        raise Failure(3, 'git push failed: ' + push.stderr.strip())
    return head, base


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
    if START in content or END in content:
        raise Failure(2, args.explained + ' contains a speckit-pr marker; remove it and rerun')
    existing = None
    if not args.no_pr:
        view = run(['gh', 'pr', 'view', '--json', 'number,url,body,state'], root)
        if view.returncode and NO_PR not in (view.stderr + view.stdout).lower():
            raise Failure(3, 'gh pr view failed: ' + (view.stderr or view.stdout).strip())
        existing = json.loads(view.stdout) if view.returncode == 0 else None
        # gh falls back to the branch's newest closed or merged PR when none is open: never edit that one
        if existing and existing.get('state') != 'OPEN':
            raise Failure(3, 'PR #%s is %s; nothing published (open a new branch for further changes)'
                          % (existing.get('number'), str(existing.get('state')).lower()))
    created = []  # a new PR's (head, base), pushed early when images must be verified on the remote

    def push():
        if not (args.no_pr or existing or created):
            created.append(ensure_branch(root, args))
    content = pin_images(root, content, Path(args.explained).as_posix(), push)
    if issue is not None and not any(c['repo'] == repo.lower() and c['issue'] == int(issue)
                                     for c in pr_lint(content, repo, issue)['closes']):
        content += '\n\nCloses %s#%d' % (repo, int(issue))  # merging closes the bound issue (1.24.1, N1)
    section = START + '\n## ' + args.heading + '\n\n' + content + '\n' + END
    body = splice(existing['body'] if existing else '', section).replace('\r\n', '\n')
    body_path = root / feature / 'evidence' / 'pr-body.md'
    lint_path = body_path.with_suffix('.lint.json')
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(body.encode('utf-8'))
    result = pr_lint(body, repo, issue, prerequisites) if issue is not None else {
        'schema': PR_LINT_SCHEMA, 'ok': True, 'body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
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
    head, base = created[0] if created else ensure_branch(root, args)
    title = args.title or next((line[2:].strip() for line in content.splitlines() if line.startswith('# ')), feature.name)
    created_url = gh(root, 'pr', 'create', '--base', base, '--head', head, '--title', title, '--body-file', str(body_path))
    receipt['pr_url'] = (created_url.strip().splitlines() or [''])[-1].strip()  # gh pr create prints the URL last
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
