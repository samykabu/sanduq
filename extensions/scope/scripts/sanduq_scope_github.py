"""Scope's GitHub client: `gh` calls through `sanduq_gh`, with the GraphQL-to-REST switch for Project operations
and the REST Projects API transport (`ProjectRest`). Stdlib only, without Scope or Workflow, so Workflow's
decisions reach the same Project transport without loading `scope.py`. Errors are `GitHubError`; Scope uses that
class as its `ScopeError`."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import sys
import time
from pathlib import Path

try:
    import sanduq_gh
except ModuleNotFoundError:
    # Source checkout only; release archives bundle the canonical helper next to this file.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_gh

rate_limited = sanduq_gh.rate_limited
PAGE_TIMEOUT = 120


class GitHubError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise GitHubError(message)


def probe(args):
    """(True, stdout) or (False, stderr and stdout) of a read-only `gh` check; a timeout is a failure."""
    try:
        return True, sanduq_gh.run_gh(args, timeout=30)
    except sanduq_gh.GhError as error:
        return False, (error.stderr or '') + (error.stdout or '')


class GitHub:
    """`gh` CLI client. `gh project` is GraphQL-only; while GraphQL is rate-limited, Project
    operations are served from the REST Projects API (a separate budget) and GraphQL is
    tried again once the reported reset time has passed."""

    def __init__(self):
        # Project board settings (owner, ownerType, projectNumber) for the REST fallback; set by Scope.
        self.project_cfg = None
        self.transports = set()
        self._rest_until = 0.0
        self._rest = None
        self._project_verified = False

    @property
    def project_transport(self):
        """Transport that served this process's Project operations, or None if there were none."""
        if not self.transports:
            return None
        return '+'.join(sorted(self.transports, key=('graphql', 'rest').index))

    def command(self, args, payload=None, timeout=30, retry=False):
        is_project = bool(args) and args[0] == 'project' and self.project_cfg is not None
        if is_project and time.time() < self._rest_until:
            return self._project_rest(args)
        try:
            out = sanduq_gh.run_gh(args, payload=payload, timeout=timeout, retry=retry)
        except sanduq_gh.GhError as error:
            if error.timeout:
                raise GitHubError(f'GitHub request timed out ({" ".join(args[:3])}) after {timeout} s.') from None
            if is_project and error.returncode != sanduq_gh.GH_MISSING and self.graphql_exhausted(error.stderr, args):
                return self._project_rest(args)
            raise GitHubError(f'GitHub request failed ({" ".join(args[:3])}): {error.stderr.strip()[:700]}') from None
        data = json.loads(out) if out.strip() else None
        # A comment Scope posts is Sanduq's own, never a human answer to a decision.
        if args[:1] == ['api'] and '--method' in args and args[args.index('--method') + 1] == 'POST'                 and isinstance(data, dict) and data.get('id') and sanduq_gh._ISSUE_COMMENTS.search(args[1]):
            sanduq_gh._record_posted_comment(None, args[1], data)
        if is_project:
            if self._rest_until:
                self._rest_until = 0.0
                print('[scope] GraphQL budget recovered; Project operations use GraphQL again.', file=sys.stderr)
            self.transports.add('graphql')
        return data

    def _project_rest(self, args):
        if self._rest is None:
            self._rest = ProjectRest(self, self.project_cfg)
        self._rest.validate(args)
        self.verify_project()
        self.transports.add('rest')
        return self._rest.run(args)

    def graphql_exhausted(self, stderr='', args=None):
        """True when GraphQL is rate-limited. The failed request's own message naming a rate limit is
        enough, even while the cheap budget probe still reports points left (a costly query can be
        refused first). `gh project` can also report exhaustion as an unrelated error (for example
        "unknown owner type"), so the real budget is checked for every other failure; that masked owner error
        is accepted only when `masked_owner_failure` verifies it."""
        explicit = rate_limited(stderr)
        ok, text = probe(['api', 'graphql', '-f', 'query={rateLimit{remaining resetAt}}'])
        reset = None
        if not ok:
            exhausted = explicit or rate_limited(text)
        else:
            try:
                limit = json.loads(text)['data']['rateLimit']
                exhausted = explicit or limit['remaining'] <= 0
                reset = datetime.fromisoformat(limit['resetAt'].replace('Z', '+00:00')).timestamp()
            except (ValueError, KeyError, TypeError, AttributeError):
                exhausted = explicit
        if not exhausted and self.masked_owner_failure(stderr, args):
            exhausted = True
        if exhausted:
            # Unknown reset: re-check GraphQL after a minute rather than before every operation.
            self._rest_until = max(reset or 0, time.time() + 60)
            when = datetime.fromtimestamp(reset, timezone.utc).strftime('%H:%M UTC') if reset else 'unknown'
            print(f'[scope] GraphQL rate-limited (resets {when}); using the REST Projects API for Project operations.',
                  file=sys.stderr)
        return exhausted

    def masked_owner_failure(self, stderr, args=None):
        """True when `gh project` reported "unknown owner type" for a block that is not the configured owner's
        fault: the request itself targets the configured Project, and a direct owner query is rate-limited or
        the REST Projects API resolves the same configured owner, type, number and node ID. A mismatched
        request, a failed or mismatched REST lookup keeps the original error."""
        cfg = self.project_cfg or {}
        if 'unknown owner type' not in (stderr or '').lower() or not cfg.get('owner') or not cfg.get('projectNumber'):
            return False
        try:
            ProjectRest(self, cfg).validate(args or [])
        except GitHubError:
            return False
        ok, text = probe(['api', 'graphql', '-f', 'query=query($login:String!){repositoryOwner(login:$login){login}}',
                          '-f', f'login={cfg["owner"]}'])
        if not ok and rate_limited(text):
            return True
        try:
            self.verify_project()
        except GitHubError:
            return False
        return True

    def verify_project(self):
        """Require the live REST Project to be the configured one (owner, owner type, number, node ID)."""
        if self._project_verified:
            return
        cfg = self.project_cfg
        base = ProjectRest(self, cfg).base
        project = self.api(base) or {}
        owner = project.get('owner') or {}
        kind = 'Organization' if cfg.get('ownerType', 'user') == 'org' else 'User'
        require(str(project.get('number')) == str(cfg['projectNumber'])
                and str(owner.get('login', '')).casefold() == str(cfg['owner']).casefold()
                and owner.get('type', kind) == kind
                and (not cfg.get('projectId') or project.get('node_id') == cfg['projectId']),
                f'REST fallback: {base} is not the configured Project (owner, owner type, number or node ID differ).')
        self._project_verified = True

    def api(self, endpoint, method='GET', payload=None, pages=False):
        args = ['api', endpoint, '-H', 'Accept: application/vnd.github+json']
        if pages:
            args += ['--paginate', '--slurp']
        if method != 'GET':
            args += ['--method', method]
        if payload is not None:
            args += ['--input', '-']
        # A paginated read of a large repository takes one call per 100 items; 120 s as Project's sync allows.
        data = self.command(args, payload, PAGE_TIMEOUT if pages else 30, retry=method == 'GET' and payload is None)
        return [item for page in data for item in page] if pages else data

    def graphql(self, query, **variables):
        data = self.command(['api', 'graphql', '--input', '-'], {'query': query, 'variables': variables})
        require(not data.get('errors'), f'GraphQL failed: {data.get("errors")}')
        return data['data']


class ProjectRest:
    """REST equivalents of the `gh project` subcommands Scope uses, returning `gh`'s JSON shapes.

    `gh project` addresses fields and items by node ID; REST addresses them by database ID.
    Both appear in the REST listings, which are fetched once per instance and cached.
    """
    FIELD_TYPES = {'single_select': 'ProjectV2SingleSelectField', 'iteration': 'ProjectV2IterationField'}
    CONTENT_FIELDS = {'title', 'type', 'repository', 'assignees', 'labels', 'linked pull requests', 'milestone',
                      'reviewers', 'parent issue', 'sub-issues progress'}

    def __init__(self, gh, cfg):
        self.gh, self.cfg = gh, cfg
        owner_path = 'orgs' if cfg.get('ownerType', 'user') == 'org' else 'users'
        self.base = f'{owner_path}/{cfg["owner"]}/projectsV2/{cfg["projectNumber"]}'
        self._fields = None
        self._item_ids = None

    # Options each `gh project` subcommand may carry when served over REST; anything else is refused.
    ALLOWED = {'field-list': {'--owner', '--format', '--limit'}, 'item-list': {'--owner', '--format', '--limit'},
               'item-add': {'--owner', '--format', '--url'},
               'field-create': {'--owner', '--format', '--name', '--data-type', '--single-select-options'},
               'item-edit': {'--id', '--project-id', '--field-id', '--single-select-option-id', '--text'}}

    def validate(self, args):
        """Refuse a request that names another owner, Project number or Project ID, or carries unsupported
        arguments, before any REST operation (a throttle must not retarget the request)."""
        action = args[1] if len(args) > 1 else ''
        allowed = self.ALLOWED.get(action)
        require(allowed is not None, f'REST fallback does not support `gh project {action}`; retry after the GraphQL rate limit resets.')
        rest = list(args[2:])
        positional = []
        while rest and not rest[0].startswith('--'):
            positional.append(rest.pop(0))
        require(len(rest) % 2 == 0 and all(rest[i].startswith('--') for i in range(0, len(rest), 2)),
                f'REST fallback: malformed `gh project {action}` arguments.')
        options = {}
        for i in range(0, len(rest), 2):
            require(rest[i] in allowed and rest[i] not in options,
                    f'REST fallback: unsupported argument {rest[i]} for `gh project {action}`.')
            options[rest[i]] = rest[i + 1]
        if action == 'item-edit':
            require(not positional and self.cfg.get('projectId') and options.get('--project-id') == self.cfg['projectId'],
                    'REST fallback: request Project ID differs from the configured Project.')
            require(('--single-select-option-id' in options) != ('--text' in options) and '--id' in options and '--field-id' in options,
                    'REST fallback: item-edit needs --id, --field-id and exactly one value.')
            return
        require(positional == [str(self.cfg['projectNumber'])], 'REST fallback: request Project number differs from the configured Project.')
        require(str(options.get('--owner', '')).casefold() == str(self.cfg['owner']).casefold(),
                'REST fallback: request owner differs from the configured Project owner.')
        require(options.get('--format', 'json') == 'json', 'REST fallback supports --format json only.')
        if action == 'field-create':
            require(options.get('--data-type') == 'SINGLE_SELECT' and '--name' in options and '--single-select-options' in options,
                    'REST fallback does not support `gh project field-create` without SINGLE_SELECT, --name and options.')

    def run(self, args):
        options = {args[i]: args[i + 1] for i in range(2, len(args) - 1) if args[i].startswith('--')}
        action = args[1] if len(args) > 1 else ''
        if action == 'field-list':
            self._fields = None  # field creation and verification must see current remote state
            fields = [self.field_row(f) for f in self.fields()]
            return {'fields': fields, 'totalCount': len(fields)}
        if action == 'field-create':
            require(options.get('--data-type') == 'SINGLE_SELECT', 'REST fallback does not support `gh project field-create` without SINGLE_SELECT.')
            field = self.gh.api(f'{self.base}/fields', 'POST', {
                'name': options['--name'], 'data_type': 'single_select',
                'single_select_options': [{'name': name, 'color': 'GRAY', 'description': ''}
                                          for name in options['--single-select-options'].split(',')]})
            self._fields = None
            return self.field_row(field)
        if action == 'item-list':
            items = [self.item_row(raw) for raw in self.raw_items()]
            return {'items': items, 'totalCount': len(items)}
        if action == 'item-add':
            match = re.search(r'github\.com/([^/]+/[^/]+)/issues/(\d+)', options.get('--url', ''))
            require(match, f'REST fallback: item-add needs an issue URL, got {options.get("--url")!r}.')
            issue = self.gh.api(f'repos/{match[1]}/issues/{match[2]}')
            existing = self.existing_issue_item(match[1], issue)
            if existing:
                return {'id': existing}
            try:
                item = self.gh.api(f'{self.base}/items', 'POST', {'type': 'Issue', 'id': issue['id']})
            except GitHubError as error:
                # `gh project item-add` is idempotent; REST answers 422 when the issue is already on the board.
                # Accept it only if one fresh reread finds that exact issue; any other failure is raised.
                existing = self.existing_issue_item(match[1], issue) if 'already exists' in str(error).lower() else None
                if not existing:
                    raise
                return {'id': existing}
            if self._item_ids is not None:
                self._item_ids[item['node_id']] = item['id']
            return {'id': item['node_id']}
        if action == 'item-edit':
            field = next((f for f in self.fields() if f['node_id'] == options.get('--field-id')), None)
            require(field, f'REST fallback: unknown Project field {options.get("--field-id")}.')
            if '--single-select-option-id' in options:
                value = options['--single-select-option-id']
            elif '--text' in options:
                value = options['--text'] or None  # an empty text value clears the field
            else:
                raise GitHubError('REST fallback supports single-select and text field edits only.')
            item_id = self.item_database_id(options.get('--id'))
            self.gh.api(f'{self.base}/items/{item_id}', 'PATCH', {'fields': [{'id': field['id'], 'value': value}]})
            return None
        raise GitHubError(f'REST fallback does not support `gh project {action}`; retry after the GraphQL rate limit resets.')

    def fields(self):
        if self._fields is None:
            self._fields = self.gh.api(f'{self.base}/fields?per_page=100', pages=True)
        return self._fields

    def raw_items(self):
        ids = ','.join(str(f['id']) for f in self.fields())
        rows = self.gh.api(f'{self.base}/items?per_page=100&fields={ids}', pages=True)
        self._item_ids = {raw['node_id']: raw['id'] for raw in rows}
        return rows

    def existing_issue_item(self, repo, issue):
        """Node ID of the configured board's item for exactly this issue (repository and number), from a fresh
        paginated listing; None when the issue is not on the board."""
        for raw in self.raw_items():
            content = raw.get('content') or {}
            repository = re.sub(r'^https://api\.github\.com/repos/', '', content.get('repository_url') or '')
            if (raw.get('content_type') == 'Issue' and content.get('number') == issue['number']
                    and repository.casefold() == repo.casefold()
                    and content.get('id', issue['id']) == issue['id']):
                return raw['node_id']
        return None

    def item_database_id(self, node_id):
        if self._item_ids is None or node_id not in self._item_ids:
            self.raw_items()
        require(node_id in self._item_ids, f'REST fallback: Project item {node_id} not found.')
        return self._item_ids[node_id]

    @classmethod
    def field_row(cls, field):
        row = {'id': field['node_id'], 'name': field['name'],
               'type': cls.FIELD_TYPES.get(field.get('data_type'), 'ProjectV2Field')}
        if field.get('options') is not None:
            row['options'] = [{'id': o['id'], 'name': cls.text(o.get('name'))} for o in field['options']]
        return row

    @staticmethod
    def text(value):
        return value.get('raw') if isinstance(value, dict) else value

    @classmethod
    def item_row(cls, raw):
        content = raw.get('content') or {}
        kind = raw.get('content_type') if raw.get('content_type') in ('Issue', 'PullRequest') else 'DraftIssue'
        repo = re.sub(r'^https://api\.github\.com/repos/', '', content.get('repository_url') or '')
        row = {'id': raw['node_id'], 'title': content.get('title'),
               'content': {'type': kind, 'number': content.get('number'), 'title': content.get('title'),
                           'repository': repo, 'url': content.get('html_url'), 'body': content.get('body')}}
        for field in raw.get('fields') or []:
            key, value = field['name'].lower(), field.get('value')
            if key in cls.CONTENT_FIELDS or value is None:
                continue
            if isinstance(value, dict):
                value = cls.text(value.get('name', value.get('title', value)))
            row[key] = value
        return row
