#!/usr/bin/env python3
"""Mirror a Spec Kit feature onto a GitHub Project (v2).

Keeps a parent feature issue's Status column in step with the lifecycle, creates one native
sub-issue per task and closes sub-issues as their tasks are checked off. Idempotent and
no-regress (the card never moves back unless --force). Stdlib only; needs `gh` authenticated
with the `project` scope. GraphQL (`gh project`, `gh issue`, `gh pr`) is preferred; when its
budget is exhausted the same operations use the REST API, which has a separate budget.
A missing precondition (gh, auth, scope, GitHub remote, config.json) is logged and exits 0 so
it never blocks a hook; the summary says `skipped`, never `ok`.

Usage: project_sync.py --phase <open|analysis|engineer-review|ready|in-progress|in-review|done|auto>
       [--feature <slug>] [--dry-run] [--no-sub-issues] [--force] [--json] [--summary]

--summary prints exactly one stdout line: `ok issue=<n> status=<status> created=<n> closed=<n>`,
`skipped reason=<why>` or `error exit=<rc> reason=<message>`; the run log moves to stderr.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path
from urllib.parse import quote

PHASES = ('open', 'analysis', 'engineer-review', 'ready', 'in-progress', 'in-review', 'done', 'auto')
CONFIG = Path('.specify/extensions/project/config.json')
TASK_LINE = re.compile(r'^\s*-\s*\[([ xX])\]\s*\**(T\d+)\**\s*(.*)$')
WORKFLOW = Path('.specify/extensions/workflow/scripts/workflow.py')
TIMEOUT = 120
SUB_ISSUE_MUTATION = 'mutation($p:ID!,$c:ID!){addSubIssue(input:{issueId:$p,subIssueId:$c}){subIssue{number}}}'


class Skip(Exception):
    """A missing precondition: logged, exit 0, never `ok`."""


def gh_raw(args, stdin=None):
    """(returncode, output) of `gh <args>`; stderr joins the output only on failure. 127: no gh."""
    try:
        done = subprocess.run(['gh', *args], input=stdin, capture_output=True, text=True, encoding='utf-8',
                              timeout=TIMEOUT)
    except FileNotFoundError:
        return 127, 'gh CLI not installed'
    except subprocess.TimeoutExpired:
        raise RuntimeError('timeout: gh ' + ' '.join(args[:2]) + ' gave no answer in ' + str(TIMEOUT) + ' s') from None
    out = done.stdout.strip()
    return done.returncode, out if done.returncode == 0 else (out + '\n' + done.stderr.strip()).strip()


def git(*args):
    """Stripped stdout, or '' on failure or when git is missing (the run then skips)."""
    try:
        done = subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', timeout=TIMEOUT)
    except FileNotFoundError:
        return ''
    except subprocess.TimeoutExpired:
        raise RuntimeError('timeout: git ' + ' '.join(args[:2]) + ' gave no answer in ' + str(TIMEOUT) + ' s') from None
    return done.stdout.strip() if done.returncode == 0 else ''


def _strip_dotgit(path):
    return path[:-4] if path[-4:].lower() == '.git' else path


def _normalize_path_remote(path):
    path = path.replace('\\', '/')
    while len(path) > 1 and path.endswith('/'):
        path = path[:-1]
    path = _strip_dotgit(path)
    drive = re.match(r'[A-Za-z]:(?=/|$)', path)
    return drive.group().lower() + path[drive.end():] if drive else path


def normalize_remote_url(url):
    """Copy of Workflow's `normalize_remote_url` (used instead when Workflow is installed): scheme,
    credentials, host case, default ports and `.git` fold away; the repository path keeps its case."""
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == 'file':
        return _normalize_path_remote(parts.path or url)
    if parts.scheme and parts.netloc:
        try:
            host = parts.hostname
            if host is None:
                raise ValueError('no host')
            host = host.rstrip('.').lower()
            port = parts.port
            if port and port != {'ssh': 22, 'https': 443, 'http': 80}.get(parts.scheme):
                host += ':' + str(port)
            return host + '/' + _strip_dotgit(parts.path.strip('/'))
        except ValueError:
            pass
    if '://' not in url:
        scp = re.fullmatch(r'(?:[^@/\s]*@)?([^@/:\s]+):(.+)', url)
        if scp:
            host, path = scp.groups()
            if not (len(host) == 1 and host.isalpha()):
                return host.rstrip('.').lower() + '/' + _strip_dotgit(path.rstrip('/'))
    return _normalize_path_remote(url)


def github_repo(remote):
    """`owner/repo` of a GitHub remote in any form, through Workflow's normaliser when installed."""
    normalize = normalize_remote_url
    if WORKFLOW.is_file():
        try:
            spec = importlib.util.spec_from_file_location('sanduq_workflow', WORKFLOW)
            module = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(WORKFLOW.parent.resolve()))
            spec.loader.exec_module(module)
            normalize = module.normalize_remote_url
        except Exception:  # an unreadable Workflow install must not stop the sync: the copy is identical
            pass
    match = re.fullmatch(r'github\.com(?::\d+)?/([^/]+/[^/]+)', normalize(remote)) if remote else None
    return match.group(1) if match else None


def token_scopes(auth):
    """The scopes on gh's `Token scopes:` lines, as a set ('project' is not 'read:project')."""
    return {scope for line in auth.splitlines() if 'Token scopes:' in line for scope in re.findall(r"'([^']+)'", line)}


def as_json(value, default):
    """A gh text result or a REST (already parsed) result as data; empty means `default`."""
    if value is None or value == '':
        return default
    return json.loads(value) if isinstance(value, str) else value


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


class Sync:
    def __init__(self, args):
        self.args = args
        self.created = self.closed = 0
        self.transport = 'graphql'

    def log(self, message, level='info'):
        prefix = '[project][warn]' if level == 'warn' else '[project]'
        print(prefix + ' ' + message, file=sys.stderr if self.args.summary else sys.stdout)

    # -- transport ---------------------------------------------------------

    def use_rest(self):
        """True when REST should serve the operation (switching to it once GraphQL is exhausted)."""
        if self.transport == 'rest':
            return True
        rc, out = gh_raw(['api', 'graphql', '-f', 'query={rateLimit{remaining}}', '--jq', '.data.rateLimit.remaining'])
        exhausted = (out.isdigit() and int(out) <= 0) if rc == 0 else 'rate limit' in out.lower()
        if not exhausted:
            return False
        self.transport = 'rest'
        self.log('GraphQL rate-limited; using the GitHub REST API for Project and issue operations', 'warn')
        return True

    def rest(self, path, method='GET', body=None, paginate=False):
        args = ['api', path, '-H', 'Accept: application/vnd.github+json']
        if method != 'GET':
            args += ['--method', method]
        if paginate:
            args += ['--paginate', '--slurp']
        if body is not None:
            args += ['--input', '-']
        rc, out = gh_raw(args, stdin=json.dumps(body) if body is not None else None)
        if rc != 0:
            raise RuntimeError('gh api ' + path + ' failed: ' + out)
        data = as_json(out, None)
        return [row for page in data for row in page] if paginate and data else data

    def call(self, gh_args, rest=None, allow_fail=False, mutating=False):
        """A GraphQL-backed gh command, or its REST equivalent `rest()` once GraphQL is exhausted."""
        if mutating and self.args.dry_run:
            self.log('DRYRUN gh ' + ' '.join(gh_args))
            return None
        if self.transport != 'rest':
            rc, out = gh_raw(gh_args)
            if rc == 0:
                return out
            if rest is None or not self.use_rest():
                if allow_fail:
                    return None
                raise RuntimeError('gh ' + ' '.join(gh_args[:2]) + ' failed: ' + out)
        try:
            return rest()
        except RuntimeError:
            if allow_fail:
                return None
            raise

    # -- GitHub objects ----------------------------------------------------

    def issue_node(self, number, allow_fail=False):
        out = self.call(['issue', 'view', str(number), '--repo', self.repo, '--json', 'id'],
                        lambda: {'id': self.rest(f'repos/{self.repo}/issues/{number}')['node_id']}, allow_fail=allow_fail)
        return (as_json(out, {}) or {}).get('id', '')

    def create_issue(self, title, body, labels, color, allow_fail=False):
        """Creates the labels and the issue; returns the issue number (None when allowed to fail)."""
        for label in labels:
            gh_raw(['label', 'create', label, '--repo', self.repo, '--color', color, '--force'])
        label_args = [arg for label in labels for arg in ('--label', label)]
        url = self.call(['issue', 'create', '--repo', self.repo, '--title', title, '--body', body, *label_args],
                        lambda: self.rest(f'repos/{self.repo}/issues', 'POST',
                                          {'title': title, 'body': body, 'labels': list(labels)})['html_url'],
                        allow_fail=allow_fail)
        match = re.search(r'/issues/(\d+)', url or '')
        return int(match.group(1)) if match else None

    def rest_db_id(self, kind, node_id):
        """REST addresses Project fields and items by database id; `gh project` by node id."""
        rows = self.rest(f'{self.rest_base}/{kind}?per_page=100', paginate=True) or []
        return next((row['id'] for row in rows if row.get('node_id') == node_id), None)

    # -- feature state -----------------------------------------------------

    def ensure_parent(self):
        fs, cfg = self.fs, self.cfg
        labels = cfg.get('parentIssue', {}).get('labels', ['spec-feature'])
        if self.managed:
            binding_path = self.fdir / 'scope-source.json'
            if not binding_path.is_file():
                raise RuntimeError('Managed workflow requires scope-source.json')
            binding = read_json(binding_path)
            bound = str(binding.get('issue', ''))
            if str(binding.get('repo', '')).lower() != self.repo.lower() or not bound.isdigit() or int(bound) <= 0:
                raise RuntimeError('Managed parent binding mismatch')
            if fs['issue'] and fs['issue'] != int(bound):
                raise RuntimeError('Project state conflicts with Scope parent binding')
            fs['issue'] = int(bound)
            fs['issueNodeId'] = self.issue_node(fs['issue']) or fs['issueNodeId']
            return
        if fs['issue'] and fs['issue'] > 0:
            return
        found = self.call(['issue', 'list', '--repo', self.repo, '--state', 'all', '--label', ','.join(labels),
                           '--search', 'in:title ' + self.slug, '--json', 'number,title,id', '--limit', '20'],
                          lambda: [{'number': row['number'], 'title': row['title'], 'id': row['node_id']}
                                   for row in self.rest(f'repos/{self.repo}/issues?state=all&labels='
                                                        f'{quote(",".join(labels))}&per_page=100', paginate=True) or []
                                   if not row.get('pull_request')], allow_fail=True)
        for row in as_json(found, []):
            if self.slug.lower() in row['title'].lower():
                fs['issue'], fs['issueNodeId'] = row['number'], row['id']
                self.log(f'found existing parent issue #{row["number"]}')
                return
        if self.args.dry_run:
            self.log('DRYRUN create parent issue for ' + self.slug)
            fs['issue'] = -1
            return
        template = cfg.get('parentIssue', {}).get('titleTemplate', '[{slug}] {title}')
        title = template.replace('{slug}', self.slug).replace('{title}', self.title)
        body = (f'Tracking issue for Spec Kit feature `{self.slug}` (branch `{self.branch}`). '
                'Managed by the sanduq project extension.')
        fs['issue'] = self.create_issue(title, body, labels, 'BFD4F2')
        fs['issueNodeId'] = self.issue_node(fs['issue'], allow_fail=True)
        self.log(f'created parent issue #{fs["issue"]}')

    def ensure_in_project(self):
        fs, cfg = self.fs, self.cfg
        if not fs['issue'] or fs['issue'] <= 0 or fs['itemId']:
            return
        number, owner = str(cfg['projectNumber']), cfg['owner']
        url = f'https://github.com/{self.repo}/issues/{fs["issue"]}'

        def rest_add():
            issue_id = self.rest(f'repos/{self.repo}/issues/{fs["issue"]}')['id']
            return {'id': self.rest(f'{self.rest_base}/items', 'POST', {'type': 'Issue', 'id': issue_id})['node_id']}
        added = self.call(['project', 'item-add', number, '--owner', owner, '--url', url, '--format', 'json'],
                          rest_add, allow_fail=True, mutating=True)
        try:
            fs['itemId'] = (as_json(added, {}) or {}).get('id') or ''
        except ValueError:
            pass
        if not fs['itemId'] and not self.args.dry_run:
            def rest_list():
                repo_url = f'https://api.github.com/repos/{self.repo}'
                rows = self.rest(f'{self.rest_base}/items?per_page=100', paginate=True) or []
                return {'items': [{'id': row['node_id'], 'content': {'number': row['content']['number']}}
                                  for row in rows if row.get('content_type') == 'Issue'
                                  and row.get('content', {}).get('repository_url') == repo_url]}
            items = self.call(['project', 'item-list', number, '--owner', owner, '--format', 'json', '--limit', '200'],
                              rest_list, allow_fail=True)
            for item in (as_json(items, {}) or {}).get('items', []):
                if item.get('content', {}).get('number') == fs['issue']:
                    fs['itemId'] = item['id']
                    break
        if fs['itemId']:
            self.log(f'issue #{fs["issue"]} on Project #{number}')

    def status_index(self, status):
        order = self.cfg.get('statusOrder', [])
        return order.index(status) if status in order else 0

    def set_status(self, status):
        fs, cfg = self.fs, self.cfg
        option = cfg.get('statusOptions', {}).get(status)
        if not option:
            self.log(f"column '{status}' not on this board (phase unmapped); skipping", 'warn')
            return
        current = fs['status']
        if current and not self.args.force and self.status_index(status) < self.status_index(current):
            self.log(f"no-regress: card '{current}'; not moving to '{status}'")
            return
        if current == status:
            self.log(f"status already '{status}'")
            return
        if not fs['itemId']:
            self.log('no project item id; cannot set status', 'warn')
            return

        def rest_edit():
            item_id, field_id = self.rest_db_id('items', fs['itemId']), self.rest_db_id('fields', cfg['statusFieldId'])
            if not item_id or not field_id:
                raise RuntimeError('REST: Project item or Status field not found')
            self.rest(f'{self.rest_base}/items/{item_id}', 'PATCH', {'fields': [{'id': field_id, 'value': option}]})
        self.call(['project', 'item-edit', '--id', fs['itemId'], '--project-id', cfg['projectId'],
                   '--field-id', cfg['statusFieldId'], '--single-select-option-id', option], rest_edit, mutating=True)
        fs['status'] = status
        self.log('status -> ' + status)

    def parse_tasks(self):
        if not self.tasks.is_file():
            return []
        tasks = []
        for line in self.tasks.read_text(encoding='utf-8-sig').splitlines():
            match = TASK_LINE.match(line)
            if match:
                desc = re.sub(r'\s*\[[Pp]\]\s*', ' ', match.group(3).replace('**', '')).strip()
                tasks.append({'id': match.group(2), 'done': match.group(1) != ' ', 'desc': desc[:90].rstrip()})
        return tasks

    def sync_sub_issues(self):
        fs, sub = self.fs, self.cfg.get('subIssues', {})
        if not sub.get('enabled') or self.args.no_sub_issues:
            return
        if not fs['issueNodeId']:
            self.log('no parent node id; skipping sub-issues', 'warn')
            return
        tasks = self.parse_tasks()
        if not tasks:
            self.log('no tasks found in tasks.md', 'warn')
            return
        to_create = [task for task in tasks if task['id'] not in fs['subIssues']]
        if sub.get('warnAboveCount', 0) > 0 and len(to_create) > sub['warnAboveCount']:
            self.log(f'{len(to_create)} sub-issues to create for {self.slug} (adds that many issues to {self.repo})', 'warn')
        cap = int(sub.get('maxCount', 0) or 0)
        labels = sub.get('labels', ['spec-task'])
        template = sub.get('titleTemplate', '{slug} {taskId}: {desc}')
        for task in to_create:
            if cap > 0 and self.created >= cap:
                self.log(f'reached maxCount={cap}; {len(to_create) - self.created} tasks left WITHOUT sub-issues', 'warn')
                break
            title = template.replace('{slug}', self.slug).replace('{taskId}', task['id']).replace('{desc}', task['desc'])
            if self.args.dry_run:
                self.log(f"DRYRUN create sub-issue '{title}' (parent #{fs['issue']})")
                self.created += 1
                continue
            number = self.create_issue(title, f"Task `{task['id']}` of feature `{self.slug}` (parent #{fs['issue']}).",
                                       labels, 'D4C5F9', allow_fail=True)
            if not number:
                self.log(f"failed to create sub-issue for {task['id']}", 'warn')
                continue
            node = self.issue_node(number, allow_fail=True)
            linked = self.call(['api', 'graphql', '-H', 'GraphQL-Features: sub_issues', '-f', 'query=' + SUB_ISSUE_MUTATION,
                                '-f', 'p=' + fs['issueNodeId'], '-f', 'c=' + node],
                               lambda: self.rest(f'repos/{self.repo}/issues/{fs["issue"]}/sub_issues', 'POST',
                                                 {'sub_issue_id': self.rest(f'repos/{self.repo}/issues/{number}')['id']}),
                               allow_fail=True)
            if linked is None:
                self.log(f"sub-issue link failed for {task['id']}", 'warn')
            fs['subIssues'][task['id']] = {'number': number, 'nodeId': node, 'closed': False}
            self.created += 1
        if self.created:
            self.log(f'created {self.created} sub-issue(s)')

    def sync_progress(self):
        fs = self.fs
        if self.managed:
            self.log('Task issue states are owned by the workflow adapter')
            return
        if not fs['subIssues']:
            return
        done_ids = {task['id'] for task in self.parse_tasks() if task['done']}
        for task_id, sub in fs['subIssues'].items():
            if task_id in done_ids and not sub.get('closed'):
                self.call(['issue', 'close', str(sub['number']), '--repo', self.repo, '--reason', 'completed'],
                          lambda: self.rest(f'repos/{self.repo}/issues/{sub["number"]}', 'PATCH',
                                            {'state': 'closed', 'state_reason': 'completed'}),
                          allow_fail=True, mutating=True)
                sub['closed'] = True
                self.closed += 1
        if self.closed:
            self.log(f'closed {self.closed} completed sub-issue(s)')
        done = sum(1 for sub in fs['subIssues'].values() if sub.get('closed'))
        self.log(f'sub-issue progress: {done}/{len(fs["subIssues"])}')

    def has_open_pr(self):
        head = quote(self.repo.split('/')[0] + ':' + self.branch)
        prs = self.call(['pr', 'list', '--repo', self.repo, '--head', self.branch, '--state', 'open', '--json', 'number', '--limit', '1'],
                        lambda: self.rest(f'repos/{self.repo}/pulls?state=open&head={head}&per_page=1'), allow_fail=True)
        try:
            return len(as_json(prs, [])) > 0
        except ValueError:
            return False

    def resolve_auto(self):
        phase_status, tasks = self.cfg['phaseToStatus'], self.parse_tasks()
        if tasks:
            done = sum(task['done'] for task in tasks)
            phase = 'ready' if done == 0 else 'in-progress' if done < len(tasks) else 'in-review'
            return phase_status.get(phase)
        return phase_status.get('analysis' if self.plan.is_file() else 'open')

    def save_state(self):
        if self.args.dry_run:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2) + '\n', encoding='utf-8')

    # -- run ---------------------------------------------------------------

    def run(self):
        args = self.args
        root = git('rev-parse', '--show-toplevel')
        if not root:
            raise Skip('not a git repo')
        os.chdir(root)
        if not CONFIG.is_file():
            raise Skip('not configured - run /speckit-project-init first')
        self.cfg = cfg = read_json(CONFIG)
        if not cfg.get('projectId') or not cfg.get('statusFieldId'):
            raise Skip('config.json is missing projectId/statusFieldId - re-run project init')
        rc, auth = gh_raw(['auth', 'status'])
        if rc == 127:
            raise Skip(auth)
        if rc != 0:
            raise Skip('gh not authenticated')
        if 'project' not in token_scopes(auth):
            raise Skip("gh token lacks 'project' scope - run: gh auth refresh -h github.com -s project,read:project")
        remote = git('config', '--get', 'remote.origin.url')
        self.repo = github_repo(remote)
        if not self.repo:
            raise Skip(f'remote is not GitHub ({remote})')
        owner_path = 'orgs' if cfg.get('ownerType') == 'org' else 'users'
        self.rest_base = f'{owner_path}/{cfg["owner"]}/projectsV2/{cfg["projectNumber"]}'

        feature = args.feature
        if not feature and Path('.specify/feature.json').is_file():
            feature = Path(read_json('.specify/feature.json').get('feature_directory', '')).name
        self.branch = git('rev-parse', '--abbrev-ref', 'HEAD')
        self.slug = feature or self.branch
        if not self.slug:
            raise Skip('could not resolve feature slug')
        self.fdir = Path('specs') / self.slug
        self.plan, self.tasks = self.fdir / 'plan.md', self.fdir / 'tasks.md'
        self.managed = Path('.specify/workflow.yml').is_file()
        if self.managed:
            args.no_sub_issues = True
        self.title = self.slug
        spec = self.fdir / 'spec.md'
        if spec.is_file():
            for line in spec.read_text(encoding='utf-8-sig').splitlines():
                heading = re.match(r'#\s+(.+?)\s*$', line)
                if heading:
                    self.title = re.sub(r'^(Feature Specification|Spec):\s*', '', heading.group(1))
                    break

        self.state_path = Path(cfg.get('stateFile', '.specify/project-sync-state.json'))
        try:
            self.state = read_json(self.state_path) if self.state_path.is_file() else {}
        except ValueError:
            self.state = {}
        if not isinstance(self.state, dict):
            self.state = {}
        self.fs = fs = self.state.setdefault(self.slug, {})
        for key, default in (('issue', 0), ('issueNodeId', ''), ('itemId', ''), ('status', ''), ('subIssues', {})):
            if not isinstance(fs.get(key), type(default)):
                fs[key] = default

        phase = args.phase
        self.log(f"feature '{self.slug}' -> repo {self.repo}, Project #{cfg['projectNumber']}, phase '{phase}'")
        self.ensure_parent()
        self.ensure_in_project()
        phase_status = cfg['phaseToStatus']
        target = self.resolve_auto() if phase == 'auto' else phase_status.get(phase)
        if phase == 'ready' or (phase == 'auto' and target == phase_status.get('ready')):
            self.sync_sub_issues()
        if phase in ('in-progress', 'in-review', 'done', 'auto'):
            self.sync_progress()
        if phase in ('in-progress', 'in-review', 'auto'):
            in_review = phase_status.get('in-review')
            if in_review and self.status_index(target) < self.status_index(in_review) and self.has_open_pr():
                self.log(f"open PR detected for '{self.branch}' -> advancing to in-review")
                target = in_review
        self.set_status(target or '')
        self.save_state()
        self.log(f"done: issue #{fs['issue']}, status '{fs['status']}', phase '{phase}' (transport: {self.transport})")
        return {'feature': self.slug, 'repo': self.repo, 'issue': fs['issue'], 'project': cfg['projectNumber'],
                'status': fs['status'], 'phase': phase, 'subIssues': len(fs['subIssues']), 'dryRun': args.dry_run,
                'transport': self.transport}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mirror a Spec Kit feature onto a GitHub Project (v2).')
    parser.add_argument('--phase', choices=PHASES, default='auto')
    parser.add_argument('--feature', help='feature slug (default: .specify/feature.json, else the branch)')
    for flag in ('--dry-run', '--no-sub-issues', '--force', '--json', '--summary'):
        parser.add_argument(flag, action='store_true')
    args, unknown = parser.parse_known_args(argv)
    for arg in unknown:
        print('[project][warn] unknown arg: ' + arg, file=sys.stderr)
    if args.summary and args.json:
        print('error exit=2 reason=--summary and --json cannot be combined')
        return 2
    sync = Sync(args)
    try:
        result = sync.run()
    except Skip as skip:
        sync.log('skipped: ' + str(skip), 'warn')
        if args.summary:
            print('skipped reason=' + str(skip))
        elif args.json:
            print(json.dumps({'skipped': True, 'reason': str(skip)}))
        return 0
    except Exception as exc:  # a genuine mid-run failure: one line under --summary, never `ok`
        message = ' '.join(str(exc).split()) or type(exc).__name__
        if args.summary:
            print('error exit=1 reason=' + message)
        else:
            print('[project][error] ' + message, file=sys.stderr)
        return 1
    if args.summary:
        print(f"ok issue={result['issue']} status={result['status']} created={sync.created} closed={sync.closed}")
    elif args.json:
        print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
