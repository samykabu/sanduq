#!/usr/bin/env python3
"""Deterministic GitHub plumbing for the human/agent-authored Scope analysis.

Python standard library only. No shell evaluation, model API, or implicit writes.
All mutations require a publish/bind/reconcile command and explicit --apply.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# The extension is also loaded directly by its test suite.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow_policy
try:
    import sanduq_remote
except ModuleNotFoundError:
    # Source checkout only; release archives bundle the canonical helper.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_remote

BEGIN, END = '<!-- speckit-scope:start -->', '<!-- speckit-scope:end -->'
META = re.compile(r'<!-- speckit-scope:metadata (.*?) -->', re.S)
MANAGED = re.compile(re.escape(BEGIN) + r'.*?' + re.escape(END), re.S)
BLOCKS = re.compile(r'(?im)^(?:#{1,6}\s+Blocks\b[^\n]*|\*\*Blocks\*\*[^\n]*)\n(?:[ \t]*\n|[ \t]*[-*]\s+[^\n]*(?:\n|$))*')
READY = {'In review', 'Done'}
DIMENSIONS = ('breadth', 'integration', 'data_security', 'verification', 'uncertainty')
EFFORTS = (1, 2, 3, 5, 8, 13, 21)
BOARD_CACHE = '.specify/scope/board-cache.json'
BOARD_LAG_RETRY = (2, 4)  # seconds before each live re-read when the gate's issue is missing from the board
RENDERED = '<!-- sanduq-scope:rendered '
PAGE_TIMEOUT = 120


def leaf_prompt(number, score, text):
    """The Specify prompt publish writes into a leaf's scope receipt."""
    return f'GitHub issue #{number}\nEffort: {score}\n\n{text}'


def analysis_hash(analysis):
    return hashlib.sha256(json.dumps(analysis, sort_keys=True).encode()).hexdigest()


# Fields whose change the owner would care about when a decomposition is revised after
# approval. Kept narrow on purpose: prose churn in rationale/evidence is not a scope change.
REVISION_FIELDS = ('title', 'scope', 'out_of_scope', 'score', 'acceptance', 'covers',
                   'depends_on', 'specify_prompt')


def flatten_tree(tree):
    """Flatten an analysis tree into {key: node} without re-running validation."""
    flat = {}

    def walk(node):
        key = node.get('key')
        if not key or key in flat:
            return
        flat[key] = node
        for child in node.get('children', []) or []:
            walk(child)

    if isinstance(tree, dict):
        walk(tree)
    return flat


def analysis_difference(baseline_nodes, current_nodes):
    """Describe how a revised decomposition departs from the approved baseline.

    This is the audit record that replaces the approval pause for revisions
    (constitution, Principle I): it must be recorded even when nothing changed.
    """
    added = sorted(set(current_nodes) - set(baseline_nodes))
    removed = sorted(set(baseline_nodes) - set(current_nodes))
    changed = {}
    for key in sorted(set(baseline_nodes) & set(current_nodes)):
        before, after = baseline_nodes[key], current_nodes[key]
        fields = {}
        for field in REVISION_FIELDS:
            if before.get(field) != after.get(field):
                fields[field] = {'before': before.get(field), 'after': after.get(field)}
        if fields:
            changed[key] = fields
    summary = []
    for key in added:
        summary.append(f'added leaf/parent "{key}" ({current_nodes[key].get("title")})')
    for key in removed:
        summary.append(f'removed "{key}" ({baseline_nodes[key].get("title")})')
    for key, fields in changed.items():
        summary.append(f'changed "{key}": ' + ', '.join(sorted(fields)))
    if not summary:
        summary.append('no field-level change to the proposed decomposition')
    return {'added': added, 'removed': removed, 'changed': changed,
            'child_count_before': max(len(baseline_nodes) - 1, 0),
            'child_count_after': max(len(current_nodes) - 1, 0),
            'summary': summary}


class ScopeError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ScopeError(message)


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    # Windows indexers can briefly retain a handle on the destination.
    for attempt in range(5):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def unscoped(body):
    return MANAGED.sub('', body or '').strip()


def fingerprint(issue):
    # Reverse dependency display changes are not changes to this issue's scope.
    raw = issue['title'] + '\n' + BLOCKS.sub('', unscoped(issue.get('body'))).strip()
    return hashlib.sha256(raw.encode()).hexdigest()


def metadata(body):
    found = META.findall(body or '')
    require(len(found) <= 1, 'Multiple scope receipts; repair the issue before proceeding.')
    return json.loads(found[0]) if found else {}


def replace_block(body, content):
    block = BEGIN + '\n' + content.strip() + '\n' + END
    return (MANAGED.sub(lambda _: block, body) if BEGIN in body else body.rstrip() + '\n\n' + block) + '\n'


def retire_prompts(body):
    # Remove executable prompt sections, preserving all other original requirements.
    pattern = r'(?ims)^#{1,6}\s+[^\n]*(?:speckit[ .-]*specify|specify prompt)[^\n]*\n.*?(?=^#{1,6}\s|\Z)'
    body = re.sub(pattern, '', unscoped(body))
    # Also retire standalone fenced Specify invocations outside named sections.
    body = re.sub(r'(?is)```[^\n]*\n(?:(?!```).)*(?:\$speckit-specify|/speckit[.-]specify)(?:(?!```).)*```',
                  '*Previous Specify invocation retired; work on the scoped children.*', body)
    return body.rstrip()


def effort(dimensions):
    require(set(dimensions) == set(DIMENSIONS), 'Supply all five effort dimensions.')
    require(all(type(x) is int and 0 <= x <= 3 for x in dimensions.values()), 'Effort dimensions must be integers 0..3.')
    total = sum(dimensions.values())
    return next(score for limit, score in [(1, 1), (3, 2), (5, 3), (7, 5), (10, 8), (13, 13), (15, 21)] if total <= limit)


def fill_scores(node):
    """Give every tree node without a `score` the rubric score of its dimensions; a declared score is left to validation."""
    if not isinstance(node, dict):
        return
    if 'score' not in node:
        try:
            node['score'] = effort(node.get('dimensions') or {})
        except ScopeError:
            pass  # validation reports the invalid dimensions
    for child in node.get('children') or []:
        fill_scores(child)


def read_analysis(path):
    """An analysis file with missing node scores filled from the dimensions, so every hash sees one form."""
    analysis = read_json(Path(path))
    if isinstance(analysis, dict):
        fill_scores(analysis.get('tree'))
    return analysis


def slim_issue(issue):
    """The issue fields Scope reads back from a snapshot or journal (SC13); GitHub's other metadata is dropped."""
    kept = {k: issue.get(k) for k in ('number', 'id', 'node_id', 'title', 'body', 'state', 'state_reason', 'html_url')}
    kept['labels'] = [{'name': x['name'] if isinstance(x, dict) else x} for x in issue.get('labels') or []]
    kept['user'] = {'login': (issue.get('user') or {}).get('login')}
    return kept


def slim_comment(comment):
    kept = {k: comment.get(k) for k in ('id', 'author_association', 'created_at', 'updated_at', 'body', 'html_url')}
    kept['user'] = {k: (comment.get('user') or {}).get(k) for k in ('login', 'type')}
    return kept


def inspect_summary(result, output, skeleton_path):
    """What `inspect --output` prints: the snapshot itself is in the file (SC13)."""
    return {'issue': result['issue']['number'], 'title': result['issue']['title'], 'fingerprint': result['fingerprint'],
            'ready': result['ready'], 'blocked': result['blocked'],
            'prerequisites': [{k: d[k] for k in ('number', 'title', 'status')} for d in result['prerequisites']],
            'comments': len(result.get('comments', [])), 'images': len(result.get('images', [])),
            'output': str(output), 'skeleton': str(skeleton_path) if skeleton_path else None}


def skeleton(snapshot):
    """The analysis fields copied from an inspect snapshot; images start unviewed, so it cannot be published as is."""
    return {'issue': snapshot['issue']['number'], 'fingerprint': snapshot['fingerprint'],
            'images': [{'url': url, 'viewed': False, 'observations': ''} for url in snapshot.get('images', [])],
            'requirements': [], 'alignment': '', 'evidence': [],
            'tree': {'key': 'root', 'title': snapshot['issue']['title'], 'scope': '', 'out_of_scope': '',
                     'acceptance': [], 'covers': [], 'evidence': [], 'rationale': '',
                     'dimensions': dict.fromkeys(DIMENSIONS), 'specify_prompt': ''}}


def images(text):
    urls = re.findall(r'!\[[^\]]*\]\(<?([^\s)>]+)', text or '')
    urls += re.findall(r'<img\b[^>]*\bsrc=["\']([^"\']+)', text or '', re.I)
    urls += re.findall(r'https://[^\s<>"\)]+\.(?:png|jpe?g|webp|gif)(?:\?[^\s<>"\)]*)?', text or '', re.I)
    # Reference-style Markdown images.
    for ref in re.findall(r'!\[[^\]]*\]\[([^\]]+)\]', text or ''):
        urls += re.findall(r'^\[' + re.escape(ref) + r'\]:\s*<?([^\s>]+)', text, re.M)
    return sorted(set(urls))


def dependency_text(body):
    parts, active = [], False
    for line in unscoped(body).splitlines():
        heading = re.match(r'^(?:#{1,6}\s+|\*\*)(blocked by|depends on|dependencies|prerequisites|blocks)\b', line, re.I)
        if heading:
            active = heading[1].lower() != 'blocks'
            continue
        if re.match(r'^#{1,6}\s+', line):
            active = False
        if active and re.match(r'^\s*[-*]\s+', line):
            if not re.match(r'^\s*[-*]\s+(?:nothing|none|no prerequisites|no dependencies)\b', line, re.I):
                parts.append(line)
        inline = re.match(r'^(?:[-*]\s*)?(?:blocked by|depends on|prerequisites):\s*(.+)$', line, re.I)
        if inline:
            parts.append(inline[1])
    return '\n'.join(parts)


def rate_limited(text):
    """True when a GitHub message names a rate limit: "rate limit", "rate limited", "RATE_LIMIT", "rate-limit"."""
    return 'rate limit' in re.sub(r'[\s_\-]+', ' ', (text or '').lower())


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

    def command(self, args, payload=None, timeout=30):
        is_project = bool(args) and args[0] == 'project' and self.project_cfg is not None
        if is_project and time.time() < self._rest_until:
            return self._project_rest(args)
        p = subprocess.run(['gh', *args], input=json.dumps(payload) if payload is not None else None,
                           capture_output=True, text=True, encoding='utf-8', timeout=timeout)
        if p.returncode:
            if is_project and self.graphql_exhausted(p.stderr, args):
                return self._project_rest(args)
            raise ScopeError(f'GitHub request failed ({" ".join(args[:3])}): {p.stderr.strip()[:700]}')
        if is_project:
            if self._rest_until:
                self._rest_until = 0.0
                print('[scope] GraphQL budget recovered; Project operations use GraphQL again.', file=sys.stderr)
            self.transports.add('graphql')
        return json.loads(p.stdout) if p.stdout.strip() else None

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
        p = subprocess.run(['gh', 'api', 'graphql', '-f', 'query={rateLimit{remaining resetAt}}'],
                           capture_output=True, text=True, encoding='utf-8', timeout=30)
        reset = None
        if p.returncode:
            exhausted = explicit or rate_limited((p.stderr or '') + (p.stdout or ''))
        else:
            try:
                limit = json.loads(p.stdout)['data']['rateLimit']
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
        except ScopeError:
            return False
        direct = subprocess.run(['gh', 'api', 'graphql', '-f', 'query=query($login:String!){repositoryOwner(login:$login){login}}',
                                 '-f', f'login={cfg["owner"]}'], capture_output=True, text=True, encoding='utf-8', timeout=30)
        if direct.returncode and rate_limited((direct.stderr or '') + (direct.stdout or '')):
            return True
        try:
            self.verify_project()
        except ScopeError:
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
        data = self.command(args, payload, PAGE_TIMEOUT if pages else 30)
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
            except ScopeError as error:
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
                raise ScopeError('REST fallback supports single-select and text field edits only.')
            item_id = self.item_database_id(options.get('--id'))
            self.gh.api(f'{self.base}/items/{item_id}', 'PATCH', {'fields': [{'id': field['id'], 'value': value}]})
            return None
        raise ScopeError(f'REST fallback does not support `gh project {action}`; retry after the GraphQL rate limit resets.')

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


class Scope:
    def __init__(self, root, gh=None):
        self.root = Path(root).resolve()
        self.gh = gh or GitHub()
        self.cfg = read_json(self.root / '.specify/extensions/project/config.json')
        require(self.cfg and self.cfg.get('projectId'), 'Run /speckit-project-init first.')
        self.gh.project_cfg = self.cfg
        url = sanduq_remote.origin_url(self.root, resolve=True)
        require(url, 'A GitHub origin remote is required: no remote.origin.url is set (git remote add origin <url>).')
        self.repo = sanduq_remote.github_slug(url)
        require(self.repo, 'A GitHub origin remote is required: remote.origin.url does not name a github.com repository.')
        self.base = f'repos/{self.repo}/issues'
        self.artifact_directory, self.plan_file = workflow_policy.paths(self.root)
        self.catalog_path = self.artifact_directory / 'issues.json'
        self.map_path = self.artifact_directory / '.issue-map.json'
        self.catalog = read_json(self.catalog_path, {'issues': []})
        self.keymap = read_json(self.map_path, {})
        self._board = None
        self._board_cached = None  # None: not read yet in this process; True: read from the shared cache
        self.snapshot_reused = None
        # Per-process read caches (SC3): repository labels, Project fields, immutable issue database IDs.
        self._labels = None
        self._fields = None
        self._ids = {}
        self._listing = None

    def listing(self, fresh=False):
        """Every issue and pull request of the repository. A split publish lists once and its rewire and plan export
        reuse that listing (SC14); Scope's own writes keep it current through `remember`."""
        if self._listing is None or fresh:
            self._listing = self.gh.api(self.base + '?state=all&per_page=100', pages=True)
        return self._listing

    def remember(self, issue):
        """Put an issue returned by a read or write into this process's listing, in place."""
        if self._listing is None or not isinstance(issue, dict) or 'number' not in issue:
            return
        index = next((i for i, x in enumerate(self._listing) if x.get('number') == issue['number']), None)
        if index is None:
            self._listing.append(issue)
        else:
            self._listing[index] = issue

    def board_ttl(self):
        return float(workflow_policy.setting(self.root, 'scope', 'board_cache_seconds', 300))

    def cached_board(self):
        """The shared board items when they are for this repository and younger than the TTL, else None."""
        try:
            cache = read_json(self.root / BOARD_CACHE, {})
            age = time.time() - datetime.fromisoformat(cache['fetched_at']).timestamp()
        except (ValueError, KeyError, TypeError, OSError):
            return None
        fresh = sanduq_remote.same_github_repository(cache.get('repo'), self.repo) and 0 <= age < self.board_ttl() and isinstance(cache.get('items'), list)
        return cache['items'] if fresh else None

    def board(self, fresh=False):
        if self._board is None or fresh:
            # Only the first read in a process may come from the shared cache; any reload is live.
            items = None if fresh or self._board_cached is not None else self.cached_board()
            self._board_cached = items is not None
            if items is None:
                data = self.gh.command(['project', 'item-list', str(self.cfg['projectNumber']), '--owner', self.cfg['owner'], '--limit', '10000', '--format', 'json'])
                require(data['totalCount'] <= len(data['items']), 'Project exceeds collection limit; refusing a partial board snapshot.')
                items = [x for x in data['items'] if sanduq_remote.same_github_repository(x.get('content', {}).get('repository'), self.repo)
                         and x['content'].get('type') == 'Issue']
                if self.board_ttl() > 0:
                    write_json(self.root / BOARD_CACHE, {'fetched_at': datetime.now(timezone.utc).isoformat(),
                                                         'repo': self.repo, 'items': items})
            self._board = {x['content']['number']: x for x in items}
        return self._board

    def invalidate_board(self, memory=True):
        """Remove the shared cache (and, by default, this process's board) after a write to the board or an issue."""
        if memory:
            self._board = None
        (self.root / BOARD_CACHE).unlink(missing_ok=True)

    def drop_cached_board(self):
        """True when the board came from the shared cache and is now dropped: a gate refuses only on a live read."""
        if not self._board_cached:
            return False
        self._board, self._board_cached = None, False
        return True

    def load_snapshot(self, value, path=None, issue=None, evidence=True):
        """A saved `inspect --output` file when it is younger than the board cache TTL and its fingerprint matches
        one fresh fetch of the issue; otherwise an inspect (prerequisites only when `evidence` is False).
        Sets `snapshot_reused`."""
        self.snapshot_reused = False if path else None
        if path:
            issue = issue or self.resolve(value)
            try:
                saved = read_json(Path(path), {})
                young = time.time() - Path(path).stat().st_mtime < self.board_ttl()
            except (ValueError, OSError):
                saved, young = {}, False
            if (young and isinstance(saved, dict) and saved.get('schema_version') == 1 and saved.get('repo') == self.repo
                    and (saved.get('issue') or {}).get('number') == issue['number']
                    and saved.get('fingerprint') == fingerprint(issue)):
                self.snapshot_reused = True
                # The fingerprint ignores the managed block, so the receipt and labels come from the fresh issue.
                return dict(saved, issue=issue)
        return self.inspect(issue or value, evidence)

    def default_snapshot(self, value, path):
        """`path`, or the analyst's `.specify/scope/issue-<n>-snapshot.json` when it exists (SC4)."""
        if path or not re.fullmatch(r'#?[1-9]\d*', str(value or '').strip()):
            return path
        saved = self.root / '.specify/scope' / f'issue-{str(value).strip().lstrip("#")}-snapshot.json'
        return saved if saved.is_file() else None

    def issue(self, number):
        issue = self.gh.api(f'{self.base}/{number}')
        require('pull_request' not in issue, 'A pull request is not a scopeable issue.')
        self._ids[issue['number']] = issue['id']
        self.remember(issue)
        return issue

    def issue_id(self, number):
        """The issue's database ID; immutable, so read at most once per process."""
        return self._ids.get(number) or self.issue(number)['id']

    def resolve(self, value):
        if isinstance(value, dict):
            return value  # already fetched in this process
        value = (value or '').strip()
        require(value, 'SCOPE_ISSUE_REQUIRED: supply a GitHub issue number or exact title. Run /speckit-scope-run <issue>.')
        if re.fullmatch(r'#?[1-9]\d*', value):
            return self.issue(int(value.lstrip('#')))
        matches = [x for x in self.listing(fresh=True) if 'pull_request' not in x and x['title'].casefold() == value.casefold()]
        require(len(matches) == 1, f'SCOPE_ISSUE_AMBIGUOUS: exact title matched {len(matches)} issues; provide an issue number.')
        return matches[0]

    def status(self, issue):
        status = self.board().get(issue['number'], {}).get('status', 'Unknown (not on configured Project)')
        aliases = workflow_policy.statuses(self.root)
        status = next((logical for logical, actual in aliases.items() if actual == status), status)
        if issue.get('state_reason') == 'not_planned':
            return 'Closed (not planned)'
        if issue.get('state') == 'closed' and status != 'Done':
            return f'{status} (closed without Done status)'
        return status

    def refs(self, text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1:
            return set().union(*(self.refs(line) for line in lines))
        refs = set()
        for owner, repo, number in re.findall(r'https://github.com/([^/]+)/([^/]+)/issues/(\d+)', text):
            require(f'{owner}/{repo}'.casefold() == self.repo.casefold(), 'Cross-repository prerequisite requires explicit repository support; scope rejected.')
            refs.add(int(number))
        refs.update(int(x) for x in re.findall(r'(?<![\w/])#(\d+)\b', text))
        for key in re.findall(r'\b(?:BOOT-\d+|EPIC-[\w-]+|UC-[\w-]+|SCOPE-[\w-]+)\b', text):
            require(key in self.keymap, f'Unresolved prerequisite key: {key}')
            refs.add(int(self.keymap[key]))
        meaningful = re.sub(r'https://\S+|#[0-9]+|\b(?:BOOT|EPIC|UC|SCOPE)-[\w-]+', '', text)
        meaningful = re.sub(r'(?im)\b(?:none|n/a|no dependencies|no prerequisites)\b|[\s\-*,|`.;:()\[\]—]+', '', meaningful)
        require(not meaningful or refs, f'Unresolved prerequisite description: {text[:160]}')
        return refs

    def declared_dependencies(self, issue):
        """Prerequisites named outside native links: body text, scope receipt, board Blocked by, catalogue. No GitHub call."""
        refs = self.refs(dependency_text(issue.get('body', '')))
        refs |= set(metadata(issue.get('body')).get('dependencies', []))
        item = self.board().get(issue['number'], {})
        refs |= self.refs(str(item.get('blocked by', '') or ''))
        for entry in self.catalog['issues']:
            if self.keymap.get(entry['key']) == issue['number']:
                refs |= self.refs(', '.join(entry.get('blockedBy', [])))
        return refs

    def dependencies(self, issue):
        rows = self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by?per_page=100', pages=True)
        for row in rows:
            require(self.same_repository(row), 'Cross-repository prerequisite is unsupported; scope rejected.')
        refs = {x['number'] for x in rows} | self.declared_dependencies(issue)
        require(issue['number'] not in refs, 'Dependency cycle: issue depends on itself.')
        return sorted(refs)

    def rewire_candidates(self, parent, issues, keep=()):
        """`[(issue, dependencies)]` for the issues to move off `parent`: its native `dependencies/blocking` list
        (every issue when that list cannot be read, SC3), every issue whose declared dependencies name it, and `keep`.
        Publish reads these before any write (SC10). Dependency text that cannot be parsed fails closed on an issue
        tied to `parent` (native link, `keep`, or text naming it); any other issue is skipped with one stderr line."""
        try:
            rows = self.gh.api(f'{self.base}/{parent["number"]}/dependencies/blocking?per_page=100', pages=True)
            require(isinstance(rows, list) and all(isinstance(x, dict) and 'number' in x for x in rows), 'unexpected response')
            blocking = {x['number'] for x in rows}
        except ScopeError as error:
            print(f'[scope] dependencies/blocking unreadable ({str(error)[:200]}); checking every issue.', file=sys.stderr)
            blocking = None
        names = re.compile(rf'(?<![\w/])#{parent["number"]}\b'
                           + (rf'|{re.escape(parent["html_url"])}\b' if parent.get('html_url') else ''))
        found = []
        for issue in issues:
            tied = str(issue['number']) in keep or (blocking is not None and issue['number'] in blocking)
            try:
                if not tied and blocking is not None and parent['number'] not in self.declared_dependencies(issue):
                    continue
                deps = self.dependencies(issue)
            except ScopeError as error:
                if tied or names.search(issue.get('body') or '') or (blocking is None and parent['number'] in {
                        x['number'] for x in self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by?per_page=100', pages=True)}):
                    raise
                print(f'[scope] #{issue["number"]} not rewired: its dependencies do not parse ({str(error)[:160]}).', file=sys.stderr)
                continue
            if parent['number'] in deps or str(issue['number']) in keep:
                found.append((issue, deps))
        return found

    def prerequisite_report(self, issue, found=None):
        """Transitive prerequisites; `found` receives each visited issue's direct dependencies."""
        seen, stack, all_deps = set(), set(), {}
        found = {} if found is None else found

        def visit(current):
            n = current['number']
            require(n not in stack, f'Dependency cycle at #{n}.')
            if n in seen:
                return
            stack.add(n)
            found[n] = self.dependencies(current)
            for dep in found[n]:
                obj = self.issue(dep)
                all_deps[dep] = obj
                visit(obj)
            stack.remove(n)
            seen.add(n)
        visit(issue)
        return [{'number': n, 'title': x['title'], 'status': self.status(x), 'body': x.get('body'), 'html_url': x.get('html_url')}
                for n, x in sorted(all_deps.items())]

    def prerequisite_overrides(self, number):
        """Owner-approved exceptions to the readiness rule for one exact issue/prerequisite pair.

        Local and explicit: each entry names the scoped issue, the single prerequisite it
        excuses, the owner's reason and their approval. Nothing is inherited by other issues.
        """
        data = read_json(self.root / '.specify/scope/prerequisite-overrides.json', {})
        return {x['prerequisite']: x for x in data.get('overrides', [])
                if x.get('issue') == number and type(x.get('prerequisite')) is int and
                x.get('reason') and x.get('approved_by') and x.get('approval_text')}

    def inspect(self, value, evidence=True):
        """Prerequisites, then (with `evidence`) comments, images and prerequisite timelines."""
        issue = self.resolve(value)
        direct = {}
        deps = self.prerequisite_report(issue, direct)
        overrides = self.prerequisite_overrides(issue['number'])
        unready = [{k: d[k] for k in ('number', 'title', 'status')} for d in deps if d['status'] not in READY]
        blocked = [d for d in unready if d['number'] not in overrides]
        overridden = [dict(d, **{k: overrides[d['number']].get(k) for k in ('reason', 'approved_by', 'approval_text', 'approved_at')})
                      for d in unready if d['number'] in overrides]
        result = {'schema_version': 1, 'repo': self.repo, 'issue': slim_issue(issue),
                  'fingerprint': fingerprint(issue), 'dependencies': direct[issue['number']],
                  'prerequisites': deps, 'blocked': blocked, 'overridden': overridden, 'ready': not blocked}
        # Do not analyze implementation or images when prerequisites fail; gate and bind need no evidence.
        if blocked or not evidence:
            return result
        comments = self.gh.api(f'{self.base}/{issue["number"]}/comments?per_page=100', pages=True)
        result['comments'] = [slim_comment(x) for x in comments]
        result['images'] = images(issue.get('body', '') + '\n' + '\n'.join(x.get('body', '') for x in comments))
        result['implementation_evidence'] = []
        for dep in deps:
            timeline = self.gh.api(f'{self.base}/{dep["number"]}/timeline?per_page=100', pages=True)
            prs = []
            for event in timeline:
                source = event.get('source', {}).get('issue', {})
                if source.get('pull_request'):
                    prs.append({'url': source['html_url'], 'state': source['state'], 'title': source['title']})
            result['implementation_evidence'].append({'number': dep['number'], 'pull_requests': prs,
                                                     'note': 'Inspect PR files, merge state, code and tests; references alone do not prove implementation.'})
        return result

    def gate(self, value, required_status='Backlog', *, feature=None, token=None, session=None, analysis=None, analysis_path=None,
             snapshot_path=None, initial=None):
        require(re.fullmatch(r'#?[1-9]\d*', (value or '').strip()),
                'SCOPE_REQUIRED: Specify requires a GitHub issue number and current effort score. Run /speckit-scope-run <issue> first.')
        initial = initial or self.resolve(value)
        revalidation = workflow_policy.bound_claim(self.root, self.repo, initial['number'], {'scope', 'specify'})
        fresh = workflow_policy.fresh_claim(self.root, self.repo, initial['number'], feature, token, session) if any((feature, token, session)) else None

        def allowed():
            status = self.status(initial)
            fresh_continued = fresh and initial.get('state') == 'open' and status == 'Feature Specification'
            continued = revalidation and initial.get('state') == 'open' and status in {'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review'}
            return status == required_status or continued or fresh_continued
        ok = allowed() or (self.drop_cached_board() and allowed())
        for delay in BOARD_LAG_RETRY:
            # N1: right after publish, GitHub's Project listing can lag the item-add for a few seconds.
            if ok or initial['number'] in self.board():
                break
            time.sleep(delay)
            self.board(fresh=True)
            ok = allowed()
        require(ok, f'SPECIFY_STATE: Specify requires {required_status}; #{initial["number"]} is {self.status(initial)}.')
        # The fresh path validates the analysis against the issue's images, so only it needs the full evidence.
        snapshot = self.load_snapshot(value, self.default_snapshot(value, snapshot_path), initial, evidence=bool(fresh))
        issue = snapshot['issue']
        receipt = metadata(issue.get('body'))
        require(not receipt.get('children'), 'SCOPE_PARENT: do not specify this aggregate issue; select a scoped leaf sub-issue.')
        version, score = receipt.get('version'), receipt.get('score')
        require((version == 1 and score in (1, 2, 3, 5)) or (version == 2 and score in EFFORTS),
                'SCOPE_REQUIRED: missing approved scope score; run /speckit-scope-run first.')
        if version == 2:
            approved = receipt.get('approval', {})
            require(approved.get('approved_by') and approved.get('approved_at') and
                    re.fullmatch(r'[a-f0-9]{64}', approved.get('analysis_sha256', '')),
                    'SCOPE_REQUIRED: missing user approval provenance.')
        require(receipt.get('fingerprint') == fingerprint(issue), 'SCOPE_STALE: requirements changed; run /speckit-scope-run again.')
        require(receipt.get('dependencies') == snapshot['dependencies'], 'SCOPE_STALE: prerequisites changed; run /speckit-scope-run again.')
        pending = read_json(self.root / '.specify/scope/plan-pending.json', {})
        require(pending.get('operation') != receipt.get('operation'),
                'SCOPE_PLAN_PENDING: finish /speckit-scope-plan before specifying a newly decomposed issue.')
        labels = {x['name'] for x in issue.get('labels', [])}
        require(f'effort:{receipt["score"]}' in labels and 'scope:parent' not in labels, 'SCOPE_REQUIRED: effort label is missing or inconsistent; run /speckit-scope-run first.')
        require(not snapshot['blocked'], rejection(snapshot['blocked']))
        require(receipt.get('prompt'), 'SCOPE_REQUIRED: missing Specify prompt; run /speckit-scope-run first.')
        # `dependencies` (checked equal to the live prerequisites above) reaches scope-source.json through bind;
        # Workflow's PR lint and pr_publish read the prerequisites from there.
        result = {'issue': issue['number'], 'score': receipt['score'], 'prompt': receipt['prompt'],
                  'fingerprint': receipt['fingerprint'], 'dependencies': receipt['dependencies']}
        if fresh:
            require(initial.get('state') == 'open', 'SCOPE_FRESH_OPEN_ISSUE_REQUIRED')
            require(version == 2 and analysis is not None, 'SCOPE_FRESH_ANALYSIS_REQUIRED')
            nodes = self.validate_analysis(snapshot, analysis)
            require(len(nodes) == 1 and analysis['tree']['score'] == score,
                    'SCOPE_FRESH_APPROVED_LEAF_REQUIRED')
            require(not self.gh.api(f'{self.base}/{issue["number"]}/sub_issues?per_page=100', pages=True),
                    'SCOPE_PARENT: native children exist')
            parent = self.native_parent(issue['number'])
            parent_number = parent.get('number') if isinstance(parent, dict) else None
            # A root issue kept whole has no parent and no retained parent approval; a child that lost its parent does.
            require(parent_number or not receipt['approval'].get('child_count'), 'SCOPE_RETAINED_PARENT_APPROVAL_MISMATCH')
            if parent_number:
                parent_receipt = metadata(self.issue(parent_number).get('body'))
                require(issue['number'] in parent_receipt.get('children', [])
                        and parent_receipt.get('approval') == receipt['approval'],
                        'SCOPE_RETAINED_PARENT_APPROVAL_MISMATCH')
                children = self.gh.api(f'{self.base}/{parent_number}/sub_issues?per_page=100', pages=True)
                require(any(child.get('number') == issue['number'] for child in children), 'SCOPE_NATIVE_PARENT_MISMATCH')
            # A local replacement inherits owner resolutions only when the exact consumed
            # artifact was applied through Decisions and still matches its recorded bytes.
            # Publish prefixes the issue and effort, so the approved analysis's own prompt is unchanged too.
            local = analysis['tree']['specify_prompt']
            revised = receipt['prompt'] not in (local, leaf_prompt(issue['number'], score, local))
            artifact_sha = None
            if revised:
                require(analysis_path is not None, 'SCOPE_RESOLVED_ANALYSIS_EVIDENCE_REQUIRED')
                artifact = (self.root / analysis_path).resolve()
                require(artifact.is_relative_to((self.root / fresh['feature']).resolve())
                        and artifact.is_file() and read_analysis(artifact) == analysis,
                        'SCOPE_RESOLVED_ANALYSIS_EVIDENCE_MISMATCH')
                artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
                require(fresh['decision_evidence'].get(artifact.relative_to(self.root).as_posix()) == artifact_sha,
                        'SCOPE_RESOLVED_ANALYSIS_EVIDENCE_MISMATCH')
            result.update(feature=fresh['feature'], decision_sha256=fresh['decision_sha256'],
                          published_prompt=receipt['prompt'], prompt=analysis['tree']['specify_prompt'] if revised else receipt['prompt'],
                          analysis_role='applied-resolution' if revised else 'consulted',
                          applied_analysis_sha256=artifact_sha,
                          analysis_sha256=hashlib.sha256(json.dumps(analysis, sort_keys=True).encode()).hexdigest(),
                          approval=receipt['approval'], parent=parent_number, publication_required=False)
        return result

    def validate_analysis(self, snapshot, analysis):
        require(not snapshot['blocked'], rejection(snapshot['blocked']))
        require(analysis.get('issue') == snapshot['issue']['number'] and analysis.get('fingerprint') == snapshot['fingerprint'], 'Analysis does not match current issue requirements.')
        fill_scores(analysis.get('tree'))
        require(analysis.get('requirements') and all(isinstance(x, str) and x.strip() for x in analysis['requirements']), 'List the source requirements as stable coverage IDs.')
        require(analysis.get('alignment') and analysis.get('evidence'), 'Supply implementation alignment and source evidence.')
        observations = {x['url']: x for x in analysis.get('images', [])}
        for url in snapshot.get('images', []):
            require(observations.get(url, {}).get('viewed') is True and observations[url].get('observations'), f'Image must be visually inspected, not inferred from its URL: {url}')
        nodes, visiting = {}, set()

        def walk(node, depth=0):
            require(depth <= 7, 'Native sub-issue nesting limit exceeded; flatten the proposed breakdown.')
            key = node.get('key', '')
            require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', key) and key not in nodes, 'Node keys must be unique stable lowercase slugs.')
            nodes[key] = node
            for field in ('title', 'scope', 'out_of_scope', 'acceptance', 'rationale', 'evidence', 'covers'):
                require(node.get(field), f'{key}: missing {field}.')
            require(isinstance(node['acceptance'], list) and isinstance(node['covers'], list), f'{key}: acceptance and covers must be lists.')
            score = effort(node.get('dimensions', {}))
            require(node.get('score') == score, f'{key}: declared score does not match rubric ({score}).')
            children = node.get('children', [])
            if children:
                require(1 <= len(children) <= 100, f'{key}: parents support 1..100 direct children.')
                for child in children:
                    walk(child, depth + 1)
                covered = {r for child in children for r in child['covers']}
                require(set(node['covers']) <= covered, f'{key}: child scopes omit parent requirements.')
            else:
                require(node.get('specify_prompt'), f'{key}: missing complete Specify prompt.')
        walk(analysis['tree'])
        require(set(analysis['requirements']) <= set(analysis['tree']['covers']), 'Root omits source requirements.')
        done = set()

        def visit(key):
            require(key not in visiting, 'Cycle in proposed child dependencies.')
            if key in done:
                return
            visiting.add(key)
            for dep in nodes[key].get('depends_on', []):
                require(dep in nodes and not nodes[dep].get('children'), f'{key}: dependencies must reference proposed leaf keys.')
                require(not nodes[key].get('children'), 'Put sibling dependencies on executable leaves, not aggregate parents.')
                visit(dep)
            visiting.remove(key)
            done.add(key)
        for key in nodes:
            visit(key)
        return nodes

    def approval_path(self, analysis):
        return self.root / '.specify/scope/approvals' / f'{analysis["issue"]}-{analysis_hash(analysis)}.json'

    def baseline_path(self, issue_number):
        """The last decomposition the owner explicitly approved for this issue.

        Revisions diff against this, never against the previous revision, so the recorded
        difference always shows drift from what a human actually saw and accepted.
        """
        return self.root / '.specify/scope/approvals' / f'{issue_number}-baseline.json'

    def approve(self, snapshot, analysis, child_count, approved_by, approval_text):
        """Record explicit user approval locally; never mutate GitHub here."""
        nodes = self.validate_analysis(snapshot, analysis)
        require(type(child_count) is int and child_count >= 0 and child_count == len(nodes) - 1,
                'CHILD_COUNT: selected sub-issue count must match the complete proposal, including nested issues.')
        require(isinstance(approved_by, str) and approved_by.strip() and
                isinstance(approval_text, str) and approval_text.strip(),
                'APPROVAL_REQUIRED: record the actual approving user and their explicit approval statement.')
        approval = {'version': 1, 'repo': self.repo, 'issue': analysis['issue'],
                    'analysis_sha256': analysis_hash(analysis), 'fingerprint': snapshot['fingerprint'],
                    'dependencies': snapshot['dependencies'], 'child_count': child_count,
                    'approved_by': approved_by.strip(), 'approval_text': approval_text.strip(),
                    'approved_at': datetime.now(timezone.utc).isoformat()}
        write_json(self.approval_path(analysis), approval)
        # Record the approved baseline so later revisions can carry this approval forward
        # and diff against what the owner actually saw.
        write_json(self.baseline_path(analysis['issue']),
                   {'version': 1, 'approval': approval, 'analysis': analysis})
        return approval

    def receipt_matches(self, approval, snapshot, analysis, nodes):
        """True when a stored receipt describes exactly this proposal, source and prerequisites."""
        return (approval.get('version') == 1 and
                approval.get('repo') == self.repo and approval.get('issue') == analysis['issue'] and
                approval.get('analysis_sha256') == analysis_hash(analysis) and
                approval.get('fingerprint') == analysis['fingerprint'] and
                approval.get('dependencies') == snapshot['dependencies'] and
                type(approval.get('child_count')) is int and approval['child_count'] == len(nodes) - 1 and
                bool(approval.get('approved_by')) and bool(approval.get('approved_at')))

    def require_approval(self, snapshot, analysis, nodes):
        """Gate --apply on approval, carrying a prior approval across revisions.

        Constitution (Principle I): the INITIAL decomposition of an issue requires explicit
        owner approval. Once approved, a later revision of that same decomposition MUST run
        unattended -- it must not request approval, pause for feedback, or treat silence as
        blocking. The recorded difference against the approved baseline is the audit record
        that replaces the approval moment, so it is written to the receipt and returned for
        the run's reported output.
        """
        settled = workflow_policy.keep_together(self.root, analysis)
        if settled:
            require(len(nodes) == 1 and not analysis['tree'].get('children'),
                    'PROJECT_KEEP_TOGETHER: project preference forbids feature decomposition for this estimate.')
            return {'version': 1, 'repo': self.repo, 'issue': analysis['issue'],
                    'analysis_sha256': analysis_hash(analysis), 'fingerprint': snapshot['fingerprint'],
                    'dependencies': snapshot['dependencies'], 'child_count': 0,
                    'approved_by': 'project-policy', 'approved_at': datetime.now(timezone.utc).isoformat(),
                    'approval_text': 'Existing project keep-together preference; no new user decision.',
                    'policy_decision': settled}
        approval = read_json(self.approval_path(analysis), {})
        if self.receipt_matches(approval, snapshot, analysis, nodes):
            # Receipt recorded for exactly this proposal, source and prerequisite set.
            return approval

        # Anything else is a revision: the decomposition, the source fingerprint or the
        # prerequisite set has moved since approval. All of it carries forward unattended.
        baseline = read_json(self.baseline_path(analysis['issue']), {})
        base_approval = baseline.get('approval') or {}
        require(baseline.get('version') == 1 and base_approval.get('repo') == self.repo and
                base_approval.get('issue') == analysis['issue'] and base_approval.get('approved_by') and
                base_approval.get('approval_text') and base_approval.get('analysis_sha256'),
                'APPROVAL_REQUIRED: present findings, obtain the user-selected count and final proposal approval before --apply.')

        # A revision of an already-approved decomposition. Do not block; record and proceed.
        difference = analysis_difference(flatten_tree((baseline.get('analysis') or {}).get('tree')), nodes)
        if base_approval.get('dependencies') != snapshot['dependencies']:
            difference['dependencies'] = {'before': base_approval.get('dependencies'),
                                          'after': snapshot['dependencies']}
            difference['summary'].append('prerequisite set changed since approval')
        if base_approval.get('fingerprint') != snapshot['fingerprint']:
            difference['summary'].append('source issue content changed since approval')
        carried = {'version': 1, 'repo': self.repo, 'issue': analysis['issue'],
                   'analysis_sha256': analysis_hash(analysis), 'fingerprint': snapshot['fingerprint'],
                   'dependencies': snapshot['dependencies'], 'child_count': len(nodes) - 1,
                   'approved_by': base_approval['approved_by'],
                   'approval_text': base_approval.get('approval_text'),
                   'approved_at': base_approval.get('approved_at'),
                   'carried_forward': True,
                   'revision_of': base_approval['analysis_sha256'],
                   'baseline_approved_at': base_approval.get('approved_at'),
                   'difference': difference,
                   'recorded_at': datetime.now(timezone.utc).isoformat()}
        write_json(self.approval_path(analysis), carried)
        return carried

    def set_labels(self, issue, score, parent=False, current=None):
        """`current`: the issue's labels from a response read after the last write to it; reread when absent."""
        wanted = [f'effort:{score}', 'scope:parent' if parent else ('scope:small' if score <= 2 else 'scope:medium' if score <= 5 else 'scope:large')]
        if self._labels is None:
            self._labels = {x['name'] for x in self.gh.api(f'repos/{self.repo}/labels?per_page=100', pages=True)}
        for label in wanted:
            # gh label create --force would overwrite existing label metadata; use REST read/create.
            if label not in self._labels:
                self.gh.api(f'repos/{self.repo}/labels', 'POST', {'name': label, 'color': 'BFD4F2', 'description': 'Managed by Speckit Scope'})
                self._labels.add(label)
        if current is None:
            current = self.issue(issue['number']).get('labels', [])
        current = {x['name'] for x in current}
        for label in sorted(current):
            if (label.startswith('effort:') or label in {'scope:small', 'scope:medium', 'scope:large', 'scope:parent'}) and label not in wanted:
                from urllib.parse import quote
                self.gh.api(f'{self.base}/{issue["number"]}/labels/{quote(label, safe="")}', 'DELETE')
        self.gh.api(f'{self.base}/{issue["number"]}/labels', 'POST', {'labels': wanted})
        self.invalidate_board(memory=False)

    def add_to_board(self, issue):
        item = self.gh.command(['project', 'item-add', str(self.cfg['projectNumber']), '--owner', self.cfg['owner'], '--url', issue['html_url'], '--format', 'json'])['id']
        # Absent from a live read in this process: the new item has no field values, which is what item-list would
        # return, so record it instead of rereading the board. Otherwise (cached board, or the issue was there) reload.
        known = self._board is not None and not self._board_cached and issue['number'] not in self._board
        self.invalidate_board(memory=not known)
        if known:
            self._board[issue['number']] = {'id': item, 'content': {'number': issue['number'], 'repository': self.repo, 'type': 'Issue'}}
        return item

    def board_item(self, issue):
        """The issue's Project item ID; `item-add` only when the board has no item for it."""
        item = self.board().get(issue['number'])
        return item['id'] if item else self.add_to_board(issue)

    def edit_item(self, issue, field_id, key, value, option=None):
        """Set one Project field (single-select `option`, else text `value`) and mirror it in this process's board row."""
        item_id = self.board_item(issue)
        flag, raw = ('--single-select-option-id', option) if option else ('--text', value)
        self.gh.command(['project', 'item-edit', '--id', item_id, '--project-id', self.cfg['projectId'], '--field-id', field_id, flag, raw])
        self.invalidate_board(memory=False)
        row = (self._board or {}).get(issue['number'])
        if row is not None:
            if value:
                row[key] = value
            else:
                row.pop(key, None)  # item-list omits an empty field

    def project_fields(self):
        if self._fields is None:
            self._fields = self.gh.command(['project', 'field-list', str(self.cfg['projectNumber']), '--owner', self.cfg['owner'], '--format', 'json', '--limit', '100'])['fields']
        return self._fields

    def set_status(self, issue, status):
        status = self.actual_status(status)
        require(status in self.cfg['statusOptions'], f'Missing Project status: {status}')
        self.edit_item(issue, self.cfg['statusFieldId'], 'status', status, self.cfg['statusOptions'][status])

    def actual_status(self, status):
        return workflow_policy.statuses(self.root).get(status, status)

    def sync_dependency_fields(self, issue, deps):
        field = next((f for f in self.project_fields() if f['name'] == 'Blocked by'), None)
        if field:
            self.edit_item(issue, field['id'], 'blocked by', ', '.join(f'#{n}' for n in deps))

    def publish(self, snapshot, analysis, apply=False):
        root_issue = snapshot['issue']
        operation = analysis_hash(analysis)[:16]
        folder = self.root / '.specify/scope/runs' / f'{root_issue["number"]}-{operation}'
        journal_path = folder / 'journal.json'
        journal = read_json(journal_path, {'nodes': {}, 'before': {}, 'operation': operation})
        require(not journal.get('rolled_back'), 'SCOPE_ROLLED_BACK: this operation was cancelled; prepare a new reviewed analysis instead of resuming it.')
        if journal.get('nodes') and snapshot['fingerprint'] != analysis.get('fingerprint'):
            receipt = metadata(root_issue.get('body'))
            require(receipt.get('operation') == operation and receipt.get('fingerprint') == fingerprint(root_issue),
                    'Requirements changed during publication; reconcile the journal before retrying.')
            original = read_json(folder / 'snapshot.json')
            require(original, 'Missing original retry snapshot.')
            snapshot = dict(original, blocked=snapshot['blocked'])
        nodes = self.validate_analysis(snapshot, analysis)
        if not apply:
            # Report honestly whether this run still needs approval. A revision of an
            # already-approved decomposition does not, and previews its recorded difference.
            baseline = read_json(self.baseline_path(analysis['issue']), {})
            approved = self.receipt_matches(read_json(self.approval_path(analysis), {}), snapshot, analysis, nodes)
            is_revision = not approved and (baseline.get('approval') or {}).get('analysis_sha256') is not None
            preview = {'dry_run': True, 'issue': root_issue['number'], 'nodes': len(nodes),
                       'child_count': len(nodes) - 1, 'leaves': sum(not n.get('children') for n in nodes.values()),
                       'operation': operation, 'approval_required': not approved and not is_revision,
                       'findings': [{k: n.get(k) for k in ('key', 'title', 'scope', 'out_of_scope', 'score',
                                    'dimensions', 'rationale', 'acceptance', 'covers', 'depends_on')} for n in nodes.values()]}
            if is_revision:
                preview['revision'] = {'carried_forward': True,
                                       'approved_by': baseline['approval'].get('approved_by'),
                                       'revision_of': baseline['approval'].get('analysis_sha256'),
                                       'difference': analysis_difference(
                                           flatten_tree((baseline.get('analysis') or {}).get('tree')), nodes)}
            return preview
        approval = self.require_approval(snapshot, analysis, nodes)
        # Snapshot before any GitHub write. A resumed journal is explicit and durable.
        for name, value in [('snapshot.json', snapshot), ('analysis.json', analysis),
                            ('catalog-before.json', self.catalog), ('issue-map-before.json', self.keymap)]:
            if not (folder / name).exists():
                write_json(folder / name, value)
        existing = self.listing(fresh=True)
        candidates = None
        if analysis['tree'].get('children'):
            node_marker = f'<!-- speckit-scope:node {root_issue["number"]}:'
            candidates = self.rewire_candidates(root_issue, [
                x for x in existing if 'pull_request' not in x and x['number'] != root_issue['number']
                and x['number'] not in journal['nodes'].values() and node_marker not in (x.get('body') or '')],
                journal.get('dependencies_before', {}))
        journal['before'].setdefault(str(root_issue['number']), slim_issue(root_issue))
        write_json(journal_path, journal)
        inherited_images = snapshot.get('images', [])
        native_children = {}  # parent number -> its native sub-issue numbers, read once per parent

        def create(node, parent=None):
            marker = f'<!-- speckit-scope:node {root_issue["number"]}:{node["key"]} -->'
            if parent is None:
                issue = self.issue(root_issue['number'])
            else:
                matches = [x for x in existing if marker in (x.get('body') or '')]
                require(len(matches) <= 1, f'Duplicate operation node: {node["key"]}')
                issue = matches[0] if matches else None
                if issue:
                    previous = metadata(issue.get('body'))
                    require(not previous or previous.get('operation') == operation,
                            f'Existing child {node["key"]} belongs to another analysis; rescope the child explicitly.')
                if issue is None:
                    body = f'{marker}\n\n## Scope\n\n{node["scope"]}\n\n## Out of scope\n\n{node["out_of_scope"]}\n\n## Acceptance criteria\n\n' + '\n'.join('- ' + a for a in node['acceptance'])
                    body += '\n\n## Reference images\n\n' + '\n'.join(f'![Source issue reference]({u})' for u in inherited_images)
                    body += '\n\n## Source\n\n' + root_issue['html_url']
                    issue = self.gh.api(self.base, 'POST', {'title': node['title'], 'body': body})
                    self.remember(issue)
                if parent['number'] not in native_children:
                    native_children[parent['number']] = {x['number'] for x in self.gh.api(f'{self.base}/{parent["number"]}/sub_issues?per_page=100', pages=True)}
                if issue['number'] not in native_children[parent['number']]:
                    self.gh.api(f'{self.base}/{parent["number"]}/sub_issues', 'POST', {'sub_issue_id': issue['id']})
                    native_children[parent['number']].add(issue['number'])
            self._ids[issue['number']] = issue['id']
            journal['nodes'][node['key']] = issue['number']
            write_json(journal_path, journal)
            self.board_item(issue)
            if not self.board().get(issue['number'], {}).get('status'):
                self.set_status(issue, 'Backlog')
            if node.get('children'):
                current = self.gh.api(f'{self.base}/{issue["number"]}/sub_issues?per_page=100', pages=True)
                native_children[issue['number']] = {x['number'] for x in current}
                proposed_markers = {f'<!-- speckit-scope:node {root_issue["number"]}:{c["key"]} -->' for c in node['children']}
                new_count = sum(not any(mark in (x.get('body') or '') for x in current) for mark in proposed_markers)
                require(len(current) + new_count <= 100, 'Native parent would exceed GitHub\'s 100 direct sub-issue limit; restructure the proposed tree.')
            for child in node.get('children', []):
                create(child, issue)
        create(analysis['tree'])
        mapping = journal['nodes']
        for key, node in nodes.items():
            issue = self.issue(mapping[key])
            journal['before'].setdefault(str(issue['number']), slim_issue(issue))
            write_json(journal_path, journal)
            children = [mapping[n['key']] for n in node.get('children', [])]
            deps = [] if children else sorted(set(snapshot['dependencies'] + [mapping[x] for x in node.get('depends_on', [])]))
            native = {x['number'] for x in self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by?per_page=100', pages=True)} if deps else set()
            for dep in deps:
                if dep not in native:
                    self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by', 'POST', {'issue_id': self.issue_id(dep)})
            source_body = retire_prompts(issue.get('body', ''))
            changed = dict(issue, body=source_body)
            prompt = '' if children else leaf_prompt(issue['number'], node['score'], node['specify_prompt'])
            receipt = {'version': 2, 'score': node['score'], 'fingerprint': fingerprint(changed),
                       'dependencies': deps, 'children': children, 'prompt': prompt, 'operation': operation}
            receipt['approval'] = {k: approval.get(k) for k in ('analysis_sha256', 'child_count', 'approved_by', 'approved_at')}
            if approval.get('carried_forward'):
                # Attributability for an unattended revision: say whose approval was carried
                # and which approved analysis it came from.
                receipt['approval']['carried_forward'] = True
                receipt['approval']['revision_of'] = approval.get('revision_of')
            block = '## Scope analysis\n\n' + ('**Aggregate only. Do not start this issue as a separate work item. Use the sub-issues.**\n\n' if children else '')
            block += f'Effort: **{node["score"]}**\n\n{node["rationale"]}\n\n### Implementation alignment\n\n{analysis["alignment"]}\n\n### Evidence\n\n'
            block += '\n'.join('- ' + str(e) for e in node['evidence'])
            if children:
                block += '\n\n### Scoped sub-issues\n\n' + '\n'.join(f'- #{n}' for n in children)
            else:
                block += '\n\n### Speckit Specify prompt\n\n```text\n' + prompt + '\n```'
            block += '\n\n<!-- speckit-scope:metadata ' + json.dumps(receipt, ensure_ascii=True) + ' -->'
            updated = self.gh.api(f'{self.base}/{issue["number"]}', 'PATCH', {'body': replace_block(source_body, block)})
            self.remember(updated)
            labels = updated.get('labels') if isinstance(updated, dict) else None
            self.set_labels(issue, node['score'], bool(children), labels if isinstance(labels, list) else None)
            self.sync_dependency_fields(issue, deps)
        if analysis['tree'].get('children'):
            self.rewire(root_issue, [mapping[k] for k, n in nodes.items() if not n.get('children')], journal, journal_path, candidates)
            self.export_plan(journal, journal_path)
            write_json(self.root / '.specify/scope/plan-pending.json', {'operation': operation, 'issue': root_issue['number'], 'renderer': 'illustrate', 'required': 'Regenerate the dependency plan with Illustrate (/speckit-scope-plan), then run accept_plan.py.'})
        journal['published'] = True
        write_json(journal_path, journal)
        result = {'issue': root_issue['number'], 'nodes': mapping, 'journal': str(journal_path), 'plan_update_required': bool(analysis['tree'].get('children'))}
        if approval.get('carried_forward'):
            result['revision'] = {'carried_forward': True, 'approved_by': approval.get('approved_by'),
                                  'revision_of': approval.get('revision_of'),
                                  'difference': approval.get('difference')}
        return result

    def rewire(self, parent, leaves, journal, journal_path, candidates):
        """Move each candidate's dependency on `parent` to `leaves`; `candidates` come from `rewire_candidates`."""
        for issue, deps in candidates:
            journal['before'].setdefault(str(issue['number']), slim_issue(issue))
            journal.setdefault('dependencies_before', {}).setdefault(str(issue['number']), deps)
            write_json(journal_path, journal)
            replacement = sorted((set(deps) - {parent['number']}) | set(leaves))
            native = self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by?per_page=100', pages=True)
            # Add replacements before removing the original blocker, so interruption fails closed.
            for dep in replacement:
                if dep not in {x['number'] for x in native}:
                    self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by', 'POST', {'issue_id': self.issue_id(dep)})
            if parent['number'] in {x['number'] for x in native}:
                self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by/{parent["id"]}', 'DELETE')
            source = re.sub(r'(?ims)^#{1,6}\s+(?:blocked by|depends on|dependencies|prerequisites)\s*\n.*?(?=^#{1,6}\s|\Z)', '', unscoped(issue.get('body')))
            source = re.sub(r'(?im)^(?:[-*]\s*)?(?:blocked by|depends on|prerequisites):[^\n]*\n?', '', source)
            source += '\n\n### Blocked by\n\n' + '\n'.join(f'- #{n}' for n in replacement)
            # Dependency changes invalidate a previously scoped prompt; preserve it for history,
            # but fingerprint mismatch forces re-scope before Specify.
            original_block = MANAGED.search(issue.get('body') or '')
            if original_block:
                old_receipt = metadata(original_block.group())
                old_receipt['dependencies'] = replacement
                block = META.sub(lambda _: '<!-- speckit-scope:metadata ' + json.dumps(old_receipt) + ' -->', original_block.group())
                source += '\n\n' + block
            self.remember(self.gh.api(f'{self.base}/{issue["number"]}', 'PATCH', {'body': source}))
            self.sync_dependency_fields(issue, replacement)
            for entry in self.catalog['issues']:
                if self.keymap.get(entry['key']) == issue['number']:
                    entry['blockedBy'] = [f'#{n}' for n in replacement]
        write_json(self.catalog_path, self.catalog)

    def export_plan(self, journal=None, journal_path=None):
        standalone = journal is None  # inside publish, reuse the publish's listing
        if standalone:
            journal = {'before': {}}
            journal_path = self.root / '.specify/scope/runs' / f'plan-export-{time.time_ns()}' / 'journal.json'
            write_json(journal_path.parent / 'catalog-before.json', self.catalog)
            write_json(journal_path.parent / 'issue-map-before.json', self.keymap)
        rows = list(self.listing(fresh=standalone))
        entries = {self.keymap.get(x['key']): x for x in self.catalog['issues']}
        graph = []
        for issue in rows:
            if 'pull_request' in issue:
                continue
            receipt = metadata(issue.get('body'))
            if issue['number'] not in entries and not receipt:
                continue
            entry = entries.get(issue['number'])
            if entry is None:
                key = f'SCOPE-{issue["number"]}'
                entry = {'key': key, 'kind': 'scope', 'labels': [], 'blockedBy': []}
                self.keymap[key] = issue['number']
                self.catalog['issues'].append(entry)
            deps = self.dependencies(issue)
            entry.update(title=issue['title'], body=issue.get('body', ''), status=self.status(issue),
                         blockedBy=[f'#{n}' for n in deps], effort=receipt.get('score'),
                         scopeChildren=receipt.get('children', []), aggregate=bool(receipt.get('children')))
            graph.append({'number': issue['number'], 'kind': entry.get('kind'), 'title': issue['title'], 'url': issue['html_url'],
                          'status': self.status(issue), 'dependencies': deps, 'children': receipt.get('children', []), 'score': receipt.get('score')})
        reverse = {x['number']: [] for x in graph}
        for item in graph:
            for dep in item['dependencies']:
                reverse.setdefault(dep, []).append(item['number'])
        # Keep reverse catalogue and Project fields consistent with native blockers.
        blocks_field = next((f for f in self.project_fields() if f['name'] == 'Blocks'), None)
        for entry in self.catalog['issues']:
            number = self.keymap.get(entry['key'])
            blocks = sorted(reverse.get(number, []))
            entry['blocks'] = [f'#{n}' for n in blocks]
            item = self.board().get(number)
            value = ', '.join(f'#{n}' for n in blocks)
            if blocks_field and item and item.get('blocks', '') != value:
                self.edit_item({'number': number}, blocks_field['id'], 'blocks', value)
            issue = next((x for x in rows if x['number'] == number), None)
            if issue:
                body = issue.get('body') or ''
                reverse_text = '### Blocks\n\n' + ('\n'.join(f'- #{n}' for n in blocks) if blocks else '- None.') + '\n\n'
                # Place reverse references outside the managed analysis block.
                source = unscoped(body)
                updated_source = BLOCKS.sub(lambda _: reverse_text, source) if BLOCKS.search(source) else source.rstrip() + '\n\n' + reverse_text
                block = MANAGED.search(body)
                updated = updated_source.rstrip() + ('\n\n' + block.group() if block else '') + '\n'
                if updated.strip() != body.strip():
                    journal['before'].setdefault(str(number), slim_issue(issue))
                    write_json(journal_path, journal)
                    self.remember(self.gh.api(f'{self.base}/{number}', 'PATCH', {'body': updated}))
                entry['body'] = updated
        write_json(self.catalog_path, self.catalog)
        write_json(self.map_path, self.keymap)
        waves, critical_path, cyclic = plan_waves(graph)
        dependencies_path = self.artifact_directory / 'scope-dependencies.json'
        write_json(dependencies_path, {'repo': self.repo, 'issues': graph, 'waves': waves,
                                       'critical_path': critical_path, 'cyclic': cyclic})
        # Draft wave mapping for the plan diagram; accept_plan.py still checks it against the drawn HTML.
        write_json(self.artifact_directory / 'implementation-plan.mapping.json',
                   {'graph_sha256': hashlib.sha256(dependencies_path.read_bytes()).hexdigest(),
                    'issue_to_node': {str(n): wave['id'] for wave in waves for n in wave['issues']}})
        report = '# Implementation dependencies\n\nGenerated by Speckit Scope. Aggregate issues are tracking containers.\n\n| Issue | Title | Prerequisites |\n| --- | --- | --- |\n'
        report += '\n'.join(f'| #{x["number"]} | {x["title"].replace("|", "/")} | {", ".join("#" + str(n) for n in x["dependencies"]) or "None"} |' for x in graph)
        (self.artifact_directory / 'DEPENDENCIES.md').write_text(report + '\n', encoding='utf-8')
        self.invalidate_board(memory=False)
        return graph

    def render_spec(self, value, analysis_path, feature, apply=False, force=False):
        """spec.md rendered from the approved single-leaf analysis; a dry run returns the text and writes nothing."""
        target = (self.root / (feature or '')).resolve()
        require(feature and target.parent == (self.root / 'specs').resolve(),
                'SCOPE_RENDER_FEATURE_REQUIRED: pass --feature specs/<feature> inside this checkout.')
        require(analysis_path and Path(analysis_path).is_file(), '--analysis <analysis.json> is required.')
        raw = Path(analysis_path).read_bytes()
        analysis = read_analysis(analysis_path)
        tree = analysis.get('tree') or {}
        issue = self.resolve(value)
        require(analysis.get('issue') == issue['number'], 'SCOPE_RENDER_MISMATCH: the analysis is for another issue.')
        require((metadata(issue.get('body')).get('approval') or {}).get('analysis_sha256') == analysis_hash(analysis),
                'SCOPE_RENDER_UNAPPROVED: the issue\'s scope receipt does not approve this analysis; publish it with scope.py publish --apply first.')
        require(not tree.get('children'), 'SCOPE_RENDER_LEAF_REQUIRED: render a single-leaf analysis; specify each scoped sub-issue separately.')
        open_questions = []
        for key in ('uncertainty', 'open_questions'):
            items = analysis.get(key) or []
            require(isinstance(items, list), f'{key} must be a list.')
            for item in items:
                text = item.get('question') if isinstance(item, dict) else item
                require(isinstance(text, str) and text.strip(), f'Each {key} item needs question text.')
                open_questions.append(text.strip())
        block = lambda value: '\n'.join('- ' + x for x in value) if isinstance(value, list) else str(value).strip()
        sha = hashlib.sha256(raw).hexdigest()
        lines = [f'{RENDERED}{sha} -->', f'# Feature Specification: {issue["title"]}', '',
                 f'**Feature Branch**: `{target.name}`', '', '**Status**: Draft', '',
                 f'**Input**: GitHub issue #{issue["number"]} ({issue["html_url"]}), rendered from the approved Scope analysis', '',
                 '## Overview', '', block(analysis.get('alignment', '')), '', block(tree['scope']), '',
                 '## User Scenarios & Testing *(mandatory)*', '', f'### User Story 1 - {tree["title"]} (Priority: P1)', '',
                 tree['specify_prompt'].strip(), '', '## Requirements *(mandatory)*', '', '### Functional Requirements', '']
        lines += [f'- **FR-{i:03d}**: {text}' for i, text in enumerate(analysis['requirements'], 1)]
        lines += ['', '## Success Criteria *(mandatory)*', '', '### Measurable Outcomes', '']
        lines += [f'- **SC-{i:03d}**: {text}' for i, text in enumerate(tree['acceptance'], 1)]
        lines += ['', '## Out of Scope', '', block(tree['out_of_scope']), '', '## Open Questions', '']
        lines += [f'- [NEEDS CLARIFICATION: {text}]' for text in open_questions] or ['None.']
        text = '\n'.join(lines) + '\n'
        spec = target / 'spec.md'
        relative = spec.relative_to(self.root).as_posix()
        require(force or not spec.is_file() or spec.read_text(encoding='utf-8-sig').startswith(RENDERED),
                f'SCOPE_RENDER_EXISTS: {relative} was not rendered by Scope; pass --force to replace it.')
        result = {'issue': issue['number'], 'path': relative, 'analysis_sha256': sha, 'dry_run': not apply}
        if not apply:
            return dict(result, text=text)
        target.mkdir(parents=True, exist_ok=True)
        temporary = spec.with_suffix('.md.tmp')
        temporary.write_text(text, encoding='utf-8', newline='\n')
        temporary.replace(spec)
        return result

    def bind(self, value, apply=False, *, feature=None, token=None, session=None, analysis=None, analysis_path=None,
             snapshot_path=None):
        if any((feature, token, session)):
            # Refuse wrong phase before even decision reconciliation can write a ledger.
            workflow_policy.fresh_claim(self.root, self.repo, int(str(value).lstrip('#')),
                                        feature, token, session, stages=('specify',))
        selected = read_json(self.root / '.specify/feature.json', {}) if not feature else {}
        directory = feature or selected.get('feature_directory')
        require(directory, 'Specify has not created a feature directory.')
        path = (self.root / directory).resolve()
        require(path.is_relative_to(self.root / 'specs') and (path / 'spec.md').is_file(), 'Feature must contain specs/<slug>/spec.md inside this checkout.')
        existing_source = read_json(path / 'scope-source.json', {})
        initial = self.resolve(value)  # one read serves the resume check, the gate and the binding
        resuming = (existing_source.get('issue') == int(str(value).lstrip('#')) and
                    existing_source.get('repo') == self.repo and
                    self.status(initial) == 'Feature Specification')
        require(not existing_source or (existing_source.get('issue'), existing_source.get('repo')) == (int(str(value).lstrip('#')), self.repo), 'SCOPE_BINDING_MISMATCH')
        checked = self.gate(value, 'Feature Specification' if resuming else 'Backlog',
                            feature=feature, token=token, session=session, analysis=analysis, analysis_path=analysis_path,
                            snapshot_path=snapshot_path, initial=initial)
        issue = initial
        state_path = self.root / self.cfg['stateFile']
        state = read_json(state_path, {})
        slug = path.name
        current = state.get(slug, {})
        require(not current.get('issue') or current['issue'] == issue['number'], 'Feature already bound to a different issue.')
        if apply:
            item_id = self.board_item(issue)
            current.update(issue=issue['number'], issueNodeId=issue['node_id'], itemId=item_id, status=self.status(issue))
            current.setdefault('subIssues', {})
            state[slug] = current
            write_json(state_path, state)
            write_json(path / 'scope-source.json', dict(checked, repo=self.repo))
            revalidation = workflow_policy.bound_claim(self.root, self.repo, issue['number'], {'specify'})
            if not revalidation and self.status(issue) != 'Feature Specification':
                self.set_status(issue, 'Feature Specification')
            current['status'] = self.actual_status(self.status(issue)) if revalidation else self.actual_status('Feature Specification')
            write_json(state_path, state)
        return {'feature': slug, 'issue': checked['issue'], 'dry_run': not apply}

    def same_repository(self, issue):
        return sanduq_remote.same_github_repository(
            re.sub(r'^https://api\.github\.com/repos/', '', issue.get('repository_url') or ''), self.repo)

    def native_parent(self, number):
        """GitHub's native parent of the issue, or None when it has none (HTTP 404)."""
        try:
            return self.gh.api(f'{self.base}/{number}/parent')
        except ScopeError as error:
            if 'HTTP 404' in str(error) or 'Not Found' in str(error):
                return None
            raise

    def ancestors(self, number):
        """The issue's native parent chain in this repository, nearest first (SC15)."""
        chain, seen = [], {number}
        while True:
            parent = self.native_parent(number)
            if not isinstance(parent, dict) or not parent.get('number') or not self.same_repository(parent):
                return chain
            require(parent['number'] not in seen, 'Cycle in parent hierarchy.')
            seen.add(parent['number'])
            chain.append(parent)
            number = parent['number']

    def reconcile(self, apply=False, issue=None):
        """Roll child status up into Scope parents: every parent, or with `issue` only that issue's ancestors."""
        if issue is None:
            by_num = {x['number']: x for x in self.listing(fresh=True) if 'pull_request' not in x}
        else:
            require(re.fullmatch(r'#?[1-9]\d*', str(issue).strip()), 'reconcile takes a GitHub issue number.')
            by_num = {x['number']: x for x in self.ancestors(int(str(issue).strip().lstrip('#')))}
        parents = {n: metadata(x.get('body')) for n, x in by_num.items() if metadata(x.get('body')).get('children')}
        visited, active, result = set(), set(), []

        def visit(n):
            require(n not in active, 'Cycle in parent hierarchy.')
            if n in visited:
                return
            active.add(n)
            issue, receipt = by_num[n], parents[n]
            native = self.gh.api(f'{self.base}/{n}/sub_issues?per_page=100', pages=True)
            children = [x['number'] for x in native]
            for x in native:
                if self.same_repository(x):
                    by_num.setdefault(x['number'], x)
            require(set(receipt['children']) <= set(children), f'Parent #{n}: recorded child link missing; repair hierarchy before rollup.')
            for child in children:
                require(child in by_num, f'Inaccessible child #{child}; parent cannot complete.')
                if child in parents:
                    visit(child)
            states = {child: self.status(by_num[child]) for child in children}
            complete = bool(states) and all(s == 'Done' for s in states.values())
            target = 'Done' if complete else ('In review' if any(s in READY for s in states.values()) else 'In progress')
            table = '### Sub-issue progress\n\n| GitHub Issue Number | Title | Current status |\n| --- | --- | --- |\n'
            table += '\n'.join(f'| #{c} | {by_num[c]["title"].replace("|", "/")} | {s} |' for c, s in states.items())
            body = issue.get('body', '')
            block = MANAGED.search(body)
            require(block, f'Parent #{n}: missing managed scope block.')
            content = re.sub(r'(?s)\n### Sub-issue progress\n.*?(?=<!-- speckit-scope:metadata)', '\n', block.group())
            content = content.replace('<!-- speckit-scope:metadata', table + '\n\n<!-- speckit-scope:metadata')
            updated = body[:block.start()] + content + body[block.end():]
            if apply:
                written = None  # the last PATCH response is the parent as an ancestor must see it
                if updated != body:
                    written = self.gh.api(f'{self.base}/{n}', 'PATCH', {'body': updated})
                if self.status(issue) != target:
                    self.set_status(issue, target)
                if complete and issue['state'] != 'closed':
                    written = self.gh.api(f'{self.base}/{n}', 'PATCH', {'state': 'closed', 'state_reason': 'completed'})
                elif not complete and issue['state'] == 'closed':
                    written = self.gh.api(f'{self.base}/{n}', 'PATCH', {'state': 'open'})
                if written is not None:
                    by_num[n] = written if isinstance(written, dict) and written.get('number') == n else self.issue(n)
            result.append({'parent': n, 'status': target, 'children': states, 'dry_run': not apply})
            visited.add(n)
            active.remove(n)
        for n in parents:
            visit(n)
        if apply:
            self.invalidate_board(memory=False)
        return result


def plan_waves(graph):
    """Topological waves and the critical path over executable issues (no scope aggregates, no `kind: epic`).

    Returns `(waves, critical_path, cyclic)`: waves `[{id: "W1", issues: [...]}, ...]` where every dependency of an
    issue sits in an earlier wave; the longest dependency chain, first issue first; and the issues left unscheduled
    by a cycle. Dependencies on non-executable or unknown issues are ignored here; acceptance refuses them.
    """
    work = {x['number']: x for x in graph if not x.get('children') and x.get('kind') != 'epic'}
    deps = {n: sorted(d for d in set(x['dependencies']) if d in work and d != n) for n, x in work.items()}
    level, remaining = {}, set(work)
    while remaining:
        ready = sorted(n for n in remaining if all(d in level for d in deps[n]))
        if not ready:
            break
        for n in ready:
            level[n] = 1 + max((level[d] for d in deps[n]), default=-1)
        remaining -= set(ready)
    waves = [{'id': f'W{i + 1}', 'issues': sorted(n for n, lv in level.items() if lv == i)}
             for i in range(max(level.values(), default=-1) + 1)]
    path = []
    if level:
        current = min(n for n, lv in level.items() if lv == max(level.values()))
        while current is not None:
            path.append(current)
            current = min((d for d in deps[current] if level[d] == level[current] - 1), default=None)
    return waves, path[::-1], sorted(remaining)


def with_transport(result, gh):
    """Name the transport that served Project operations (stdout only; saved files are unchanged)."""
    transport = getattr(gh, 'project_transport', None)
    return {**result, 'transport': transport} if transport and isinstance(result, dict) else result


def rejection(blocked):
    text = 'SCOPE_PREREQUISITES_NOT_READY: prerequisites must be In review or Done.\n\n'
    text += '| GitHub Issue Number | Title | Current status |\n| --- | --- | --- |\n'
    return text + '\n'.join(f'| #{d["number"]} | {d["title"].replace("|", "/")} | {d["status"]} |' for d in blocked)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'gate', 'approve', 'publish', 'bind', 'reconcile', 'export-plan', 'render-spec'])
    parser.add_argument('issue', nargs='?')
    parser.add_argument('--root', default='.')
    parser.add_argument('--analysis', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--skeleton', type=Path, help='inspect: also write a new analysis JSON skeleton from the snapshot')
    parser.add_argument('--feature')
    parser.add_argument('--token')
    parser.add_argument('--session')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--child-count', type=int)
    parser.add_argument('--approved-by')
    parser.add_argument('--approval-text')
    parser.add_argument('--snapshot', type=Path, help='gate, approve, publish, bind: a saved inspect --output to reuse when still current')
    parser.add_argument('--force', action='store_true', help='render-spec: replace a spec.md that Scope did not render')
    args = parser.parse_args(argv)
    lock = None
    shown = None
    try:
        # Fail on missing identity before any GitHub/network access.
        if args.command in {'inspect', 'gate', 'approve', 'publish', 'bind', 'render-spec'}:
            require(args.issue and args.issue.strip(), 'SCOPE_ISSUE_REQUIRED: supply a GitHub issue number or exact title. Run /speckit-scope-run <issue> first.')
        app = Scope(args.root)
        if args.command == 'bind' and any((args.feature, args.token, args.session)):
            # Phase/ownership check precedes even the CLI's local mutation lock.
            workflow_policy.fresh_claim(app.root, app.repo, int(args.issue.lstrip('#')),
                                        args.feature, args.token, args.session, stages=('specify',))
        if args.apply:
            candidate = app.root / '.specify/scope/mutation.lock'
            candidate.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise ScopeError('A scope mutation is already running. Inspect mutation.lock and its process before retrying.')
            with os.fdopen(fd, 'w') as handle:
                handle.write(str(os.getpid()))
            lock = candidate
        if args.command == 'inspect':
            require(not (args.skeleton and args.skeleton.exists()),
                    f'SCOPE_SKELETON_EXISTS: {args.skeleton} exists; remove it or name a new file.')
            result = app.inspect(args.issue)
            if args.output:
                write_json(args.output, result)
            require(not result['blocked'], rejection(result['blocked']))
            if args.skeleton:
                write_json(args.skeleton, skeleton(result))
            if args.output:
                shown = inspect_summary(result, args.output, args.skeleton)
        elif args.command == 'gate':
            result = app.gate(args.issue, feature=args.feature, token=args.token, session=args.session,
                              analysis=read_analysis(args.analysis) if args.analysis else None, analysis_path=args.analysis,
                              snapshot_path=args.snapshot)
        elif args.command == 'approve':
            require(args.analysis and args.analysis.is_file(), '--analysis <analysis.json> is required.')
            result = app.approve(app.load_snapshot(args.issue, args.snapshot), read_analysis(args.analysis), args.child_count,
                                 args.approved_by, args.approval_text)
        elif args.command == 'publish':
            require(args.analysis and args.analysis.is_file(), '--analysis <analysis.json> is required.')
            result = app.publish(app.load_snapshot(args.issue, args.snapshot), read_analysis(args.analysis), args.apply)
        elif args.command == 'bind':
            result = app.bind(args.issue, args.apply, feature=args.feature, token=args.token, session=args.session,
                              analysis=read_analysis(args.analysis) if args.analysis else None, analysis_path=args.analysis,
                              snapshot_path=args.snapshot)
        elif args.command == 'reconcile':
            result = app.reconcile(args.apply, args.issue)
        elif args.command == 'render-spec':
            result = app.render_spec(args.issue, args.analysis, args.feature, args.apply, args.force)
        else:
            require(args.apply, 'export-plan requires --apply because it updates local plan data.')
            result = app.export_plan()
        if getattr(app, 'snapshot_reused', None) is not None and args.command in {'gate', 'approve', 'publish', 'bind'}:
            result = dict(result, snapshot_reused=bool(app.snapshot_reused))
        if args.output:
            write_json(args.output, result)
        print(json.dumps(with_transport(shown or result, app.gh), indent=2, ensure_ascii=True))
        return 0
    except (ScopeError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if lock:
            lock.unlink(missing_ok=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
