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

BEGIN, END = '<!-- speckit-scope:start -->', '<!-- speckit-scope:end -->'
META = re.compile(r'<!-- speckit-scope:metadata (.*?) -->', re.S)
MANAGED = re.compile(re.escape(BEGIN) + r'.*?' + re.escape(END), re.S)
BLOCKS = re.compile(r'(?im)^(?:#{1,6}\s+Blocks\b[^\n]*|\*\*Blocks\*\*[^\n]*)\n(?:[ \t]*\n|[ \t]*[-*]\s+[^\n]*(?:\n|$))*')
READY = {'In review', 'Done'}
DIMENSIONS = ('breadth', 'integration', 'data_security', 'verification', 'uncertainty')
EFFORTS = (1, 2, 3, 5, 8, 13, 21)


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

    @property
    def project_transport(self):
        """Transport that served this process's Project operations, or None if there were none."""
        if not self.transports:
            return None
        return '+'.join(sorted(self.transports, key=('graphql', 'rest').index))

    def command(self, args, payload=None):
        is_project = bool(args) and args[0] == 'project' and self.project_cfg is not None
        if is_project and time.time() < self._rest_until:
            return self._project_rest(args)
        p = subprocess.run(['gh', *args], input=json.dumps(payload) if payload is not None else None,
                           capture_output=True, text=True, encoding='utf-8')
        if p.returncode:
            if is_project and self.graphql_exhausted(p.stderr):
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
        self.transports.add('rest')
        return self._rest.run(args)

    def graphql_exhausted(self, stderr=''):
        """True when GraphQL is rate-limited. `gh project` can report this as an unrelated error
        (for example "unknown owner type"), so the real budget is always checked."""
        p = subprocess.run(['gh', 'api', 'graphql', '-f', 'query={rateLimit{remaining resetAt}}'],
                           capture_output=True, text=True, encoding='utf-8')
        reset = None
        if p.returncode:
            exhausted = 'rate limit' in ((p.stderr or '') + (p.stdout or '') + (stderr or '')).lower()
        else:
            try:
                limit = json.loads(p.stdout)['data']['rateLimit']
                exhausted = limit['remaining'] <= 0
                reset = datetime.fromisoformat(limit['resetAt'].replace('Z', '+00:00')).timestamp()
            except (ValueError, KeyError, TypeError, AttributeError):
                exhausted = False
        if exhausted:
            # Unknown reset: re-check GraphQL after a minute rather than before every operation.
            self._rest_until = max(reset or 0, time.time() + 60)
            when = datetime.fromtimestamp(reset, timezone.utc).strftime('%H:%M UTC') if reset else 'unknown'
            print(f'[scope] GraphQL rate-limited (resets {when}); using the REST Projects API for Project operations.',
                  file=sys.stderr)
        return exhausted

    def api(self, endpoint, method='GET', payload=None, pages=False):
        args = ['api', endpoint, '-H', 'Accept: application/vnd.github+json']
        if pages:
            args += ['--paginate', '--slurp']
        if method != 'GET':
            args += ['--method', method]
        if payload is not None:
            args += ['--input', '-']
        data = self.command(args, payload)
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
        self.gh = gh
        owner_path = 'orgs' if cfg.get('ownerType', 'user') == 'org' else 'users'
        self.base = f'{owner_path}/{cfg["owner"]}/projectsV2/{cfg["projectNumber"]}'
        self._fields = None
        self._item_ids = None

    def run(self, args):
        options = {args[i]: args[i + 1] for i in range(2, len(args) - 1) if args[i].startswith('--')}
        action = args[1] if len(args) > 1 else ''
        if action == 'field-list':
            fields = [self.field_row(f) for f in self.fields()]
            return {'fields': fields, 'totalCount': len(fields)}
        if action == 'item-list':
            items = [self.item_row(raw) for raw in self.raw_items()]
            return {'items': items, 'totalCount': len(items)}
        if action == 'item-add':
            match = re.search(r'github\.com/([^/]+/[^/]+)/issues/(\d+)', options.get('--url', ''))
            require(match, f'REST fallback: item-add needs an issue URL, got {options.get("--url")!r}.')
            issue = self.gh.api(f'repos/{match[1]}/issues/{match[2]}')
            item = self.gh.api(f'{self.base}/items', 'POST', {'type': 'Issue', 'id': issue['id']})
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
        self.repo = subprocess.check_output(['git', '-C', str(self.root), 'remote', 'get-url', 'origin'], text=True).strip()
        match = re.search(r'github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$', self.repo)
        require(match, 'A GitHub origin remote is required.')
        self.repo = match[1]
        self.base = f'repos/{self.repo}/issues'
        self.artifact_directory, self.plan_file = workflow_policy.paths(self.root)
        self.catalog_path = self.artifact_directory / 'issues.json'
        self.map_path = self.artifact_directory / '.issue-map.json'
        self.catalog = read_json(self.catalog_path, {'issues': []})
        self.keymap = read_json(self.map_path, {})
        self._board = None

    def board(self, fresh=False):
        if self._board is None or fresh:
            data = self.gh.command(['project', 'item-list', str(self.cfg['projectNumber']), '--owner', self.cfg['owner'], '--limit', '10000', '--format', 'json'])
            require(data['totalCount'] <= len(data['items']), 'Project exceeds collection limit; refusing a partial board snapshot.')
            self._board = {x['content']['number']: x for x in data['items']
                           if x.get('content', {}).get('repository') == self.repo and x['content'].get('type') == 'Issue'}
        return self._board

    def issue(self, number):
        issue = self.gh.api(f'{self.base}/{number}')
        require('pull_request' not in issue, 'A pull request is not a scopeable issue.')
        return issue

    def resolve(self, value):
        value = (value or '').strip()
        require(value, 'SCOPE_ISSUE_REQUIRED: supply a GitHub issue number or exact title. Run /speckit-scope <issue>.')
        if re.fullmatch(r'#?[1-9]\d*', value):
            return self.issue(int(value.lstrip('#')))
        rows = self.gh.api(self.base + '?state=all&per_page=100', pages=True)
        matches = [x for x in rows if 'pull_request' not in x and x['title'].casefold() == value.casefold()]
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

    def dependencies(self, issue):
        rows = self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by?per_page=100', pages=True)
        for row in rows:
            require(row['repository_url'].endswith('/' + self.repo), 'Cross-repository prerequisite is unsupported; scope rejected.')
        refs = {x['number'] for x in rows}
        refs |= self.refs(dependency_text(issue.get('body', '')))
        refs |= set(metadata(issue.get('body')).get('dependencies', []))
        item = self.board().get(issue['number'], {})
        refs |= self.refs(str(item.get('blocked by', '') or ''))
        for entry in self.catalog['issues']:
            if self.keymap.get(entry['key']) == issue['number']:
                refs |= self.refs(', '.join(entry.get('blockedBy', [])))
        require(issue['number'] not in refs, 'Dependency cycle: issue depends on itself.')
        return sorted(refs)

    def prerequisite_report(self, issue):
        seen, stack, all_deps = set(), set(), {}

        def visit(current):
            n = current['number']
            require(n not in stack, f'Dependency cycle at #{n}.')
            if n in seen:
                return
            stack.add(n)
            for dep in self.dependencies(current):
                obj = self.issue(dep)
                all_deps[dep] = obj
                visit(obj)
            stack.remove(n)
            seen.add(n)
        visit(issue)
        return [{'number': n, 'title': x['title'], 'status': self.status(x), 'issue': x}
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

    def inspect(self, value):
        issue = self.resolve(value)
        deps = self.prerequisite_report(issue)
        overrides = self.prerequisite_overrides(issue['number'])
        unready = [{k: d[k] for k in ('number', 'title', 'status')} for d in deps if d['status'] not in READY]
        blocked = [d for d in unready if d['number'] not in overrides]
        overridden = [dict(d, **{k: overrides[d['number']].get(k) for k in ('reason', 'approved_by', 'approval_text', 'approved_at')})
                      for d in unready if d['number'] in overrides]
        result = {'schema_version': 1, 'repo': self.repo, 'issue': issue,
                  'fingerprint': fingerprint(issue), 'dependencies': self.dependencies(issue),
                  'prerequisites': deps, 'blocked': blocked, 'overridden': overridden, 'ready': not blocked}
        # Do not analyze implementation or images when prerequisites fail.
        if blocked:
            return result
        comments = self.gh.api(f'{self.base}/{issue["number"]}/comments?per_page=100', pages=True)
        result['comments'] = comments
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

    def gate(self, value, required_status='Backlog'):
        require(re.fullmatch(r'#?[1-9]\d*', (value or '').strip()),
                'SCOPE_REQUIRED: Specify requires a GitHub issue number and current effort score. Run /speckit-scope <issue> first.')
        initial = self.resolve(value)
        revalidation = workflow_policy.bound_claim(self.root, self.repo, initial['number'], {'scope', 'specify'})
        continued = revalidation and initial.get('state') == 'open' and self.status(initial) in {'Feature Specification', 'Need Clarifications', 'Ready', 'In progress', 'In review'}
        require(self.status(initial) == required_status or continued,
                f'SPECIFY_STATE: Specify requires {required_status}; #{initial["number"]} is {self.status(initial)}.')
        snapshot = self.inspect(value)
        issue = snapshot['issue']
        receipt = metadata(issue.get('body'))
        require(not receipt.get('children'), 'SCOPE_PARENT: do not specify this aggregate issue; select a scoped leaf sub-issue.')
        version, score = receipt.get('version'), receipt.get('score')
        require((version == 1 and score in (1, 2, 3, 5)) or (version == 2 and score in EFFORTS),
                'SCOPE_REQUIRED: missing approved scope score; run /speckit-scope first.')
        if version == 2:
            approved = receipt.get('approval', {})
            require(approved.get('approved_by') and approved.get('approved_at') and
                    re.fullmatch(r'[a-f0-9]{64}', approved.get('analysis_sha256', '')),
                    'SCOPE_REQUIRED: missing user approval provenance.')
        require(receipt.get('fingerprint') == fingerprint(issue), 'SCOPE_STALE: requirements changed; run /speckit-scope again.')
        require(receipt.get('dependencies') == snapshot['dependencies'], 'SCOPE_STALE: prerequisites changed; run /speckit-scope again.')
        pending = read_json(self.root / '.specify/scope/plan-pending.json', {})
        require(pending.get('operation') != receipt.get('operation'),
                'SCOPE_PLAN_PENDING: finish /speckit-scope-plan before specifying a newly decomposed issue.')
        labels = {x['name'] for x in issue.get('labels', [])}
        require(f'effort:{receipt["score"]}' in labels and 'scope:parent' not in labels, 'SCOPE_REQUIRED: effort label is missing or inconsistent; run /speckit-scope first.')
        require(not snapshot['blocked'], rejection(snapshot['blocked']))
        require(receipt.get('prompt'), 'SCOPE_REQUIRED: missing Specify prompt; run /speckit-scope first.')
        return {'issue': issue['number'], 'score': receipt['score'], 'prompt': receipt['prompt'], 'fingerprint': receipt['fingerprint']}

    def validate_analysis(self, snapshot, analysis):
        require(not snapshot['blocked'], rejection(snapshot['blocked']))
        require(analysis.get('issue') == snapshot['issue']['number'] and analysis.get('fingerprint') == snapshot['fingerprint'], 'Analysis does not match current issue requirements.')
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

    def set_labels(self, issue, score, parent=False):
        wanted = [f'effort:{score}', 'scope:parent' if parent else ('scope:small' if score <= 2 else 'scope:medium' if score <= 5 else 'scope:large')]
        for label in wanted:
            # gh label create --force would overwrite existing label metadata; use REST read/create.
            existing = self.gh.api(f'repos/{self.repo}/labels?per_page=100', pages=True)
            if label not in {x['name'] for x in existing}:
                self.gh.api(f'repos/{self.repo}/labels', 'POST', {'name': label, 'color': 'BFD4F2', 'description': 'Managed by Speckit Scope'})
        current = {x['name'] for x in self.issue(issue['number']).get('labels', [])}
        for label in sorted(current):
            if (label.startswith('effort:') or label in {'scope:small', 'scope:medium', 'scope:large', 'scope:parent'}) and label not in wanted:
                from urllib.parse import quote
                self.gh.api(f'{self.base}/{issue["number"]}/labels/{quote(label, safe="")}', 'DELETE')
        self.gh.api(f'{self.base}/{issue["number"]}/labels', 'POST', {'labels': wanted})

    def add_to_board(self, issue):
        return self.gh.command(['project', 'item-add', str(self.cfg['projectNumber']), '--owner', self.cfg['owner'], '--url', issue['html_url'], '--format', 'json'])['id']

    def set_status(self, issue, status):
        status = self.actual_status(status)
        require(status in self.cfg['statusOptions'], f'Missing Project status: {status}')
        item = self.board().get(issue['number'])
        item_id = item['id'] if item else self.add_to_board(issue)
        self.gh.command(['project', 'item-edit', '--id', item_id, '--project-id', self.cfg['projectId'], '--field-id', self.cfg['statusFieldId'], '--single-select-option-id', self.cfg['statusOptions'][status]])
        self._board = None

    def actual_status(self, status):
        return workflow_policy.statuses(self.root).get(status, status)

    def sync_dependency_fields(self, issue, deps):
        fields = self.gh.command(['project', 'field-list', str(self.cfg['projectNumber']), '--owner', self.cfg['owner'], '--format', 'json', '--limit', '100'])['fields']
        field = next((f for f in fields if f['name'] == 'Blocked by'), None)
        if field:
            item = self.board().get(issue['number'])
            item_id = item['id'] if item else self.add_to_board(issue)
            self.gh.command(['project', 'item-edit', '--id', item_id, '--project-id', self.cfg['projectId'], '--field-id', field['id'], '--text', ', '.join(f'#{n}' for n in deps)])
            self._board = None

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
        journal['before'].setdefault(str(root_issue['number']), root_issue)
        write_json(journal_path, journal)
        existing = self.gh.api(self.base + '?state=all&per_page=100', pages=True)
        inherited_images = snapshot.get('images', [])

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
                    existing.append(issue)
                current_children = self.gh.api(f'{self.base}/{parent["number"]}/sub_issues?per_page=100', pages=True)
                if issue['number'] not in {x['number'] for x in current_children}:
                    self.gh.api(f'{self.base}/{parent["number"]}/sub_issues', 'POST', {'sub_issue_id': issue['id']})
            journal['nodes'][node['key']] = issue['number']
            write_json(journal_path, journal)
            self.add_to_board(issue)
            self._board = None
            if not self.board().get(issue['number'], {}).get('status'):
                self.set_status(issue, 'Backlog')
            if node.get('children'):
                native_children = self.gh.api(f'{self.base}/{issue["number"]}/sub_issues?per_page=100', pages=True)
                proposed_markers = {f'<!-- speckit-scope:node {root_issue["number"]}:{c["key"]} -->' for c in node['children']}
                new_count = sum(not any(mark in (x.get('body') or '') for x in native_children) for mark in proposed_markers)
                require(len(native_children) + new_count <= 100, 'Native parent would exceed GitHub\'s 100 direct sub-issue limit; restructure the proposed tree.')
            for child in node.get('children', []):
                create(child, issue)
        create(analysis['tree'])
        mapping = journal['nodes']
        for key, node in nodes.items():
            issue = self.issue(mapping[key])
            journal['before'].setdefault(str(issue['number']), issue)
            write_json(journal_path, journal)
            children = [mapping[n['key']] for n in node.get('children', [])]
            deps = [] if children else sorted(set(snapshot['dependencies'] + [mapping[x] for x in node.get('depends_on', [])]))
            for dep in deps:
                native = self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by?per_page=100', pages=True)
                if dep not in {x['number'] for x in native}:
                    self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by', 'POST', {'issue_id': self.issue(dep)['id']})
            source_body = retire_prompts(issue.get('body', ''))
            changed = dict(issue, body=source_body)
            prompt = '' if children else f'GitHub issue #{issue["number"]}\nEffort: {node["score"]}\n\n{node["specify_prompt"]}'
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
            self.gh.api(f'{self.base}/{issue["number"]}', 'PATCH', {'body': replace_block(source_body, block)})
            self.set_labels(issue, node['score'], bool(children))
            self.sync_dependency_fields(issue, deps)
        if analysis['tree'].get('children'):
            self.rewire(root_issue, [mapping[k] for k, n in nodes.items() if not n.get('children')], journal, journal_path)
            self.export_plan(journal, journal_path)
            write_json(self.root / '.specify/scope/plan-pending.json', {'operation': operation, 'issue': root_issue['number'], 'required': 'Run Archify and plan-accept after reviewing the updated dependency graph.'})
        journal['published'] = True
        write_json(journal_path, journal)
        result = {'issue': root_issue['number'], 'nodes': mapping, 'journal': str(journal_path), 'plan_update_required': bool(analysis['tree'].get('children'))}
        if approval.get('carried_forward'):
            result['revision'] = {'carried_forward': True, 'approved_by': approval.get('approved_by'),
                                  'revision_of': approval.get('revision_of'),
                                  'difference': approval.get('difference')}
        return result

    def rewire(self, parent, leaves, journal, journal_path):
        all_issues = self.gh.api(self.base + '?state=all&per_page=100', pages=True)
        for issue in all_issues:
            if 'pull_request' in issue or issue['number'] in journal['nodes'].values():
                continue
            deps = self.dependencies(issue)
            if parent['number'] not in deps and str(issue['number']) not in journal.get('dependencies_before', {}):
                continue
            journal['before'].setdefault(str(issue['number']), issue)
            journal.setdefault('dependencies_before', {}).setdefault(str(issue['number']), deps)
            write_json(journal_path, journal)
            replacement = sorted((set(deps) - {parent['number']}) | set(leaves))
            native = self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by?per_page=100', pages=True)
            # Add replacements before removing the original blocker, so interruption fails closed.
            for dep in replacement:
                if dep not in {x['number'] for x in native}:
                    self.gh.api(f'{self.base}/{issue["number"]}/dependencies/blocked_by', 'POST', {'issue_id': self.issue(dep)['id']})
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
            self.gh.api(f'{self.base}/{issue["number"]}', 'PATCH', {'body': source})
            self.sync_dependency_fields(issue, replacement)
            for entry in self.catalog['issues']:
                if self.keymap.get(entry['key']) == issue['number']:
                    entry['blockedBy'] = [f'#{n}' for n in replacement]
        write_json(self.catalog_path, self.catalog)

    def export_plan(self, journal=None, journal_path=None):
        if journal is None:
            journal = {'before': {}}
            journal_path = self.root / '.specify/scope/runs' / f'plan-export-{time.time_ns()}' / 'journal.json'
            write_json(journal_path.parent / 'catalog-before.json', self.catalog)
            write_json(journal_path.parent / 'issue-map-before.json', self.keymap)
        rows = self.gh.api(self.base + '?state=all&per_page=100', pages=True)
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
        fields = self.gh.command(['project', 'field-list', str(self.cfg['projectNumber']), '--owner', self.cfg['owner'], '--format', 'json', '--limit', '100'])['fields']
        blocks_field = next((f for f in fields if f['name'] == 'Blocks'), None)
        for entry in self.catalog['issues']:
            number = self.keymap.get(entry['key'])
            blocks = sorted(reverse.get(number, []))
            entry['blocks'] = [f'#{n}' for n in blocks]
            item = self.board().get(number)
            value = ', '.join(f'#{n}' for n in blocks)
            if blocks_field and item and item.get('blocks', '') != value:
                self.gh.command(['project', 'item-edit', '--id', item['id'], '--project-id', self.cfg['projectId'], '--field-id', blocks_field['id'], '--text', value])
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
                    journal['before'].setdefault(str(number), issue)
                    write_json(journal_path, journal)
                    self.gh.api(f'{self.base}/{number}', 'PATCH', {'body': updated})
                entry['body'] = updated
        write_json(self.catalog_path, self.catalog)
        write_json(self.map_path, self.keymap)
        write_json(self.artifact_directory / 'scope-dependencies.json', {'repo': self.repo, 'issues': graph})
        report = '# Implementation dependencies\n\nGenerated by Speckit Scope. Aggregate issues are tracking containers.\n\n| Issue | Title | Prerequisites |\n| --- | --- | --- |\n'
        report += '\n'.join(f'| #{x["number"]} | {x["title"].replace("|", "/")} | {", ".join("#" + str(n) for n in x["dependencies"]) or "None"} |' for x in graph)
        (self.artifact_directory / 'DEPENDENCIES.md').write_text(report + '\n', encoding='utf-8')
        return graph

    def bind(self, value, apply=False):
        feature = read_json(self.root / '.specify/feature.json', {})
        directory = feature.get('feature_directory')
        require(directory, 'Specify has not created a feature directory.')
        path = (self.root / directory).resolve()
        require(path.is_relative_to(self.root / 'specs') and (path / 'spec.md').is_file(), 'Feature must contain specs/<slug>/spec.md inside this checkout.')
        existing_source = read_json(path / 'scope-source.json', {})
        resuming = (existing_source.get('issue') == int(str(value).lstrip('#')) and
                    existing_source.get('repo') == self.repo and
                    self.status(self.resolve(value)) == 'Feature Specification')
        checked = self.gate(value, 'Feature Specification' if resuming else 'Backlog')
        issue = self.issue(checked['issue'])
        state_path = self.root / self.cfg['stateFile']
        state = read_json(state_path, {})
        slug = path.name
        current = state.get(slug, {})
        require(not current.get('issue') or current['issue'] == issue['number'], 'Feature already bound to a different issue.')
        if apply:
            item_id = self.add_to_board(issue)
            current.update(issue=issue['number'], issueNodeId=issue['node_id'], itemId=item_id, status=self.status(issue))
            current.setdefault('subIssues', {})
            state[slug] = current
            write_json(state_path, state)
            write_json(path / 'scope-source.json', dict(checked, repo=self.repo))
            revalidation = workflow_policy.bound_claim(self.root, self.repo, issue['number'], {'specify'})
            if not revalidation:
                self.set_status(issue, 'Feature Specification')
            current['status'] = self.actual_status(self.status(issue)) if revalidation else self.actual_status('Feature Specification')
            write_json(state_path, state)
        return {'feature': slug, 'issue': checked['issue'], 'dry_run': not apply}

    def reconcile(self, apply=False):
        rows = self.gh.api(self.base + '?state=all&per_page=100', pages=True)
        by_num = {x['number']: x for x in rows if 'pull_request' not in x}
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
                if updated != body:
                    self.gh.api(f'{self.base}/{n}', 'PATCH', {'body': updated})
                if self.status(issue) != target:
                    self.set_status(issue, target)
                if complete and issue['state'] != 'closed':
                    self.gh.api(f'{self.base}/{n}', 'PATCH', {'state': 'closed', 'state_reason': 'completed'})
                elif not complete and issue['state'] == 'closed':
                    self.gh.api(f'{self.base}/{n}', 'PATCH', {'state': 'open'})
                by_num[n] = self.issue(n)
            result.append({'parent': n, 'status': target, 'children': states, 'dry_run': not apply})
            visited.add(n)
            active.remove(n)
        for n in parents:
            visit(n)
        return result


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
    parser.add_argument('command', choices=['inspect', 'gate', 'approve', 'publish', 'bind', 'reconcile', 'export-plan'])
    parser.add_argument('issue', nargs='?')
    parser.add_argument('--root', default='.')
    parser.add_argument('--analysis', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--child-count', type=int)
    parser.add_argument('--approved-by')
    parser.add_argument('--approval-text')
    args = parser.parse_args(argv)
    lock = None
    try:
        # Fail on missing identity before any GitHub/network access.
        if args.command in {'inspect', 'gate', 'approve', 'publish', 'bind'}:
            require(args.issue and args.issue.strip(), 'SCOPE_ISSUE_REQUIRED: supply a GitHub issue number or exact title. Run /speckit-scope <issue> first.')
        app = Scope(args.root)
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
            result = app.inspect(args.issue)
            if args.output:
                write_json(args.output, result)
            require(not result['blocked'], rejection(result['blocked']))
        elif args.command == 'gate':
            result = app.gate(args.issue)
        elif args.command == 'approve':
            require(args.analysis and args.analysis.is_file(), '--analysis <analysis.json> is required.')
            result = app.approve(app.inspect(args.issue), read_json(args.analysis), args.child_count,
                                 args.approved_by, args.approval_text)
        elif args.command == 'publish':
            require(args.analysis and args.analysis.is_file(), '--analysis <analysis.json> is required.')
            result = app.publish(app.inspect(args.issue), read_json(args.analysis), args.apply)
        elif args.command == 'bind':
            result = app.bind(args.issue, args.apply)
        elif args.command == 'reconcile':
            result = app.reconcile(args.apply)
        else:
            require(args.apply, 'export-plan requires --apply because it updates local plan data.')
            result = app.export_plan()
        if args.output:
            write_json(args.output, result)
        print(json.dumps(with_transport(result, app.gh), indent=2, ensure_ascii=True))
        return 0
    except (ScopeError, OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if lock:
            lock.unlink(missing_ok=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
