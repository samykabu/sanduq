#!/usr/bin/env python3
"""Parent-scoped Tasks-to-Issues adapter. Dry-run by default; --apply mutates GitHub."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from workflow import WorkflowError, require, inside, git, read, write, locked, digest, github_repository

MARKER = re.compile(r'<!-- sanduq-task (\{[^\n]+\}) -->')

# GitHub rejects an issue title over this many characters.
TITLE_LIMIT = 256
TITLE_ELLIPSIS = '...'


def issue_title(task, description):
    """A deterministic GitHub-legal title: `task: description`, shortened to the
    headline when it would exceed GitHub's limit. The full description always
    stays in the issue body (see `sync`), so shortening never drops information,
    and the same input always shortens to the same title (idempotent re-sync)."""
    title = task + ': ' + description
    if len(title) <= TITLE_LIMIT:
        return title
    return title[:TITLE_LIMIT - len(TITLE_ELLIPSIS)].rstrip() + TITLE_ELLIPSIS


def parse_tasks(text):
    tasks = {}
    for line in text.splitlines():
        match = re.match(r'^\s*- \[([ xX])\]\s+(T\d{3,})\b\s*:?[ \t]*(.*)$', line)
        if not match:
            continue
        done, task, description = match.groups()
        require(task not in tasks, 'DUPLICATE_TASK_ID: ' + task)
        description = re.sub(r'^\s*(?:\[(?:P|US\d+|TDD|REVIEW|SUBAGENT)\]\s*)+', '', description)
        require(bool(description), 'EMPTY_TASK: ' + task)
        tasks[task] = {'description': description, 'done': done.lower() == 'x'}
    require(tasks, 'NO_TASKS_FOUND')
    return tasks


def dependency_order(tasks, dependencies):
    require(isinstance(dependencies, dict) and all(isinstance(v, list) for v in dependencies.values()), 'DEPENDENCIES_MUST_BE_A_MAPPING_OF_LISTS')
    require(set(dependencies) <= set(tasks), 'UNKNOWN_DEPENDENT_TASK')
    ordered, visiting = [], set()
    def visit(task):
        require(task in tasks, 'UNKNOWN_PREREQUISITE: ' + task)
        require(task not in visiting, 'TASK_DEPENDENCY_CYCLE')
        if task in ordered:
            return
        visiting.add(task)
        for parent in dependencies.get(task, []): visit(parent)
        visiting.remove(task)
        ordered.append(task)
    for task in tasks: visit(task)
    return ordered


def remote_repository(root):
    return github_repository(root)


class GitHub:
    def api(self, path, method='GET', payload=None, pages=False):
        args = ['gh', 'api', path, '-X', method, '-H', 'Accept: application/vnd.github+json']
        if pages: args += ['--paginate', '--slurp']
        if payload is not None: args += ['--input', '-']
        result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                                text=True, encoding='utf-8', capture_output=True)
        require(result.returncode == 0, 'GITHUB_API_FAILED: ' + result.stderr.strip())
        output = json.loads(result.stdout) if result.stdout.strip() else None
        return [item for page in output for item in page] if pages else output


def matching_issues(issues, repo, parent, feature):
    found = {}
    for issue in issues:
        if issue.get('pull_request'): continue
        for match in MARKER.finditer(issue.get('body') or ''):
            marker = json.loads(match[1])
            if (marker.get('repo'), marker.get('parent'), marker.get('feature')) != (repo, parent, feature):
                continue
            task = marker.get('task')
            require(task not in found, 'DUPLICATE_REMOTE_TASK: ' + str(task))
            found[task] = issue
    return found


def sync(root, feature, parent, dependencies, apply=False, github=None):
    root = root.resolve()
    directory = inside(root, feature)
    require(directory.is_relative_to(root / 'specs'), 'FEATURE_PATH_INVALID')
    repo = remote_repository(root)
    binding = read(directory / 'scope-source.json', {})
    require(binding.get('repo') == repo and binding.get('issue') == parent, 'TASK_PARENT_BINDING_MISMATCH')
    tasks = parse_tasks((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
    ordered = dependency_order(tasks, dependencies)
    gh = github or GitHub()
    base = f'repos/{repo}/issues'
    parent_issue = gh.api(f'{base}/{parent}')
    require(not parent_issue.get('pull_request') and parent_issue['state'] == 'open', 'PARENT_NOT_OPEN_ISSUE')
    with locked(root / '.specify/workflow/runtime' / (digest([repo, parent, feature]) + '.tasks.lock')):
        known = matching_issues(gh.api(base + '?state=all&per_page=100', pages=True), repo, parent, feature)
        children = gh.api(f'{base}/{parent}/sub_issues?per_page=100', pages=True)
        linked = {issue['number'] for issue in children}
        # Adopt only an explicit legacy Project mapping under this exact parent.
        # Unmapped existing task children require reconciliation, never duplication.
        config = read(root / '.specify/extensions/project/config.json', {})
        legacy = read(inside(root, config.get('stateFile', '.specify/project-sync-state.json')), {}).get(directory.name, {})
        if legacy:
            require(legacy.get('issue') == parent, 'LEGACY_PROJECT_PARENT_CONFLICT')
        for task, entry in legacy.get('subIssues', {}).items():
            if task not in tasks or task in known: continue
            number = entry.get('number', entry.get('issue')) if isinstance(entry, dict) else entry
            matches = [i for i in children if i['number'] == number]
            require(len(matches) == 1 and re.search(r'\b' + re.escape(task) + r'\b', matches[0].get('title', '')), 'LEGACY_TASK_LINK_UNVERIFIED: ' + task)
            known[task] = matches[0]
        for child in children:
            match = re.search(r'\bT\d{3,}\b', child.get('title', ''))
            if match and match[0] in tasks:
                require(match[0] in known and known[match[0]]['number'] == child['number'], 'UNMAPPED_EXISTING_TASK: reconcile native child before creating ' + match[0])
        journal_path = directory / 'workflow/task-issues.json'
        journal = read(journal_path, {'schema_version': 1, 'repo': repo, 'parent': parent, 'feature': feature, 'tasks': {}})
        require((journal['repo'], journal['parent'], journal['feature']) == (repo, parent, feature), 'TASK_JOURNAL_IDENTITY_MISMATCH')
        result = {'dry_run': not apply, 'repo': repo, 'parent': parent, 'feature': feature, 'tasks': {}}
        for task in ordered:
            marker = {'repo': repo, 'parent': parent, 'feature': feature, 'task': task}
            text = '<!-- sanduq-task ' + json.dumps(marker, sort_keys=True) + ' -->\n'
            text += f'Parent: #{parent}\n\nTask: `{task}` in `{feature}/tasks.md`\n\n' + tasks[task]['description'] + '\n'
            refs = [known[t]['number'] for t in dependencies.get(task, []) if t in known]
            if refs: text += '\nDepends on: ' + ', '.join('#' + str(n) for n in refs) + '\n'
            text += '<!-- /sanduq-task -->\n'
            title = issue_title(task, tasks[task]['description'])
            issue = known.get(task)
            action = 'reuse' if issue else 'create'
            if apply and issue is None:
                # Creation carries a stable marker. After a lost response a rerun
                # discovers the created issue before any new POST.
                issue = gh.api(base, 'POST', {'title': title, 'body': text})
                known[task] = issue
                journal['tasks'][task] = {'number': issue['number'], 'id': issue['id'], 'linked': False}
                write(journal_path, journal)
            if apply and issue:
                original = issue.get('body') or ''
                if '<!-- /sanduq-task -->' in original:
                    updated = re.sub(r'<!-- sanduq-task \{[^\n]+\} -->.*?<!-- /sanduq-task -->\n?', lambda _: text, original, count=1, flags=re.S)
                else:
                    updated = original.rstrip() + '\n\n' + text
                if updated != original or issue.get('title') != title:
                    gh.api(f'{base}/{issue["number"]}', 'PATCH', {'title': title, 'body': updated})
                if issue['number'] not in linked:
                    gh.api(f'{base}/{parent}/sub_issues', 'POST', {'sub_issue_id': issue['id']})
                actual = gh.api(f'{base}/{issue["number"]}/parent')
                require(actual['number'] == parent and actual.get('repository_url', '').rstrip('/') == f'https://api.github.com/repos/{repo}', 'NATIVE_PARENT_LINK_NOT_VERIFIED')
                journal['tasks'][task] = {'number': issue['number'], 'id': issue['id'], 'linked': True}
                write(journal_path, journal)
            result['tasks'][task] = {'action': action, 'number': issue['number'] if issue else None,
                                      'native_link_verified': bool(apply and issue), 'depends_on': dependencies.get(task, [])}
        result['native_links_verified'] = apply and all(t['native_link_verified'] for t in result['tasks'].values())
        if apply: write(directory / 'workflow/task-issues-result.json', result)
        return result


def sync_states(root, feature, parent, apply=False, github=None):
    root = root.resolve(); directory = inside(root, feature)
    repo = remote_repository(root); gh = github or GitHub()
    journal = read(directory / 'workflow/task-issues.json', {})
    require((journal.get('repo'), journal.get('parent'), journal.get('feature')) == (repo, parent, feature), 'TASK_JOURNAL_IDENTITY_MISMATCH')
    binding = read(directory / 'scope-source.json', {})
    require(binding.get('repo') == repo and binding.get('issue') == parent, 'TASK_PARENT_BINDING_MISMATCH')
    tasks = parse_tasks((directory / 'tasks.md').read_text(encoding='utf-8-sig'))
    changes = []
    for task, info in tasks.items():
        require(task in journal['tasks'], 'UNPUBLISHED_TASK: ' + task)
        number = journal['tasks'][task]['number']
        endpoint = f'repos/{repo}/issues/{number}'
        actual = gh.api(endpoint + '/parent')
        require(actual['number'] == parent and actual.get('repository_url') == 'https://api.github.com/repos/' + repo, 'TASK_PARENT_CHANGED')
        issue = gh.api(endpoint)
        require(task in matching_issues([issue], repo, parent, feature), 'TASK_IDENTITY_CHANGED')
        desired = 'closed' if info['done'] else 'open'
        if issue['state'] != desired:
            changes.append({'task': task, 'number': number, 'from': issue['state'], 'to': desired})
            if apply: gh.api(endpoint, 'PATCH', {'state': desired})
    result = {'dry_run': not apply, 'changes': changes}
    if apply: write(directory / 'workflow/task-state.json', result)
    return result


def sync_summary(result):
    """One line: `ok created=<n> reused=<n> total=<n> dry_run=0|1`, for `--summary`."""
    tasks = result['tasks'].values()
    created = sum(t['action'] == 'create' for t in tasks)
    reused = sum(t['action'] == 'reuse' for t in tasks)
    return f'ok created={created} reused={reused} total={len(tasks)} dry_run={int(result["dry_run"])}'


def sync_states_summary(result):
    """One line: `ok opened=<n> closed=<n> changed=<n> dry_run=0|1`, for `--summary`."""
    opened = sum(c['to'] == 'open' for c in result['changes'])
    closed = sum(c['to'] == 'closed' for c in result['changes'])
    return f'ok opened={opened} closed={closed} changed={len(result["changes"])} dry_run={int(result["dry_run"])}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    parser.add_argument('--parent', type=int, required=True)
    parser.add_argument('--dependencies', type=Path, help='JSON task-ID dependency mapping, explicitly {} if independent')
    parser.add_argument('--sync-states', action='store_true', help='Update already-linked issue states from completed tasks; never create issues')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--summary', action='store_true', help='Print one line (ok/error, counts) instead of the full JSON result')
    parser.add_argument('--json', action='store_true', help='Print the full JSON result (today\'s default output)')
    args = parser.parse_args()
    if args.summary and args.json:
        parser.error('--summary and --json cannot be combined')
    try:
        if args.sync_states:
            result = sync_states(args.root, args.feature, args.parent, args.apply)
            line = sync_states_summary(result)
        else:
            require(args.dependencies and args.dependencies.is_file(), 'DEPENDENCY_FILE_REQUIRED')
            result = sync(args.root, args.feature, args.parent, read(args.dependencies), args.apply)
            line = sync_summary(result)
        print(line if args.summary else json.dumps(result, indent=2))
        return 0
    except (WorkflowError, ValueError, KeyError) as exc:
        if args.summary:
            print('error ' + str(exc))
        else:
            print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1
    except Exception as exc:
        # Any other unhandled exception (a corrupt journal/state file, a
        # missing tasks.md, ...) still must not crash with a raw traceback
        # under --summary; default (no-flag)/--json behaviour is unchanged
        # and keeps today's traceback-and-nonzero-exit.
        if not args.summary:
            raise
        print(f'error {type(exc).__name__}: {exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
