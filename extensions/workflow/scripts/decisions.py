#!/usr/bin/env python3
"""Stage-neutral decisions recorded in a bound GitHub issue discussion."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from workflow import WorkflowError, Run, digest, inside, load_policy, locked, read, require, write

MARKER = re.compile(r'\A<!-- sanduq-decision:question (\{[^\n]*\}) -->\n')
ANSWER = re.compile(r'^\s*(SD[1-9]\d*):\s*([A-Z])\s*$', re.I | re.M)


class GitHub:
    def api(self, endpoint, method='GET', payload=None, pages=False):
        args = ['gh', 'api', endpoint, '-H', 'Accept: application/vnd.github+json']
        if pages:
            args += ['--paginate', '--slurp']
        if method != 'GET':
            args += ['--method', method]
        if payload is not None:
            args += ['--input', '-']
        result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                                capture_output=True, text=True, encoding='utf-8')
        require(result.returncode == 0, 'GITHUB_DECISION_API_FAILED: ' + result.stderr.strip()[:500])
        data = json.loads(result.stdout) if result.stdout.strip() else None
        return [item for page in data for item in page] if pages else data

    def command(self, args):
        result = subprocess.run(['gh', *args], capture_output=True, text=True, encoding='utf-8')
        require(result.returncode == 0, 'GITHUB_DECISION_PROJECT_FAILED: ' + result.stderr.strip()[:500])
        return json.loads(result.stdout) if result.stdout.strip() else None


def authorized(comment, issue, policy):
    user = comment.get('user') or {}
    if user.get('type') == 'Bot':
        return False
    login = str(user.get('login', '')).casefold()
    allowed = {name.casefold() for name in policy.get('decisions', {}).get('authorized_users', [])}
    return bool(login) and (login in allowed or login == issue['user']['login'].casefold()
                            or comment.get('author_association') in ('OWNER', 'MEMBER', 'COLLABORATOR'))


def question_record(comment):
    match = MARKER.match(comment.get('body', ''))
    if not match:
        return None
    try:
        data = json.loads(match[1])
    except ValueError as exc:
        raise WorkflowError('DECISION_QUESTION_MARKER_INVALID') from exc
    require(isinstance(data, dict) and data.get('version') == 1
            and re.fullmatch(r'SD[1-9]\d*', str(data.get('id', ''))),
            'DECISION_QUESTION_MARKER_INVALID')
    require(isinstance(data.get('options'), list) and 2 <= len(data['options']) <= 26
            and all(isinstance(option, str) and option.strip() for option in data['options']),
            'DECISION_OPTIONS_INVALID')
    require(data.get('body_digest') == digest(comment['body'].split('\n', 1)[1]),
            'DECISION_QUESTION_EDITED: ' + data['id'])
    return data


def answers(comments, issue, policy):
    questions = {}
    for comment in comments:
        if not authorized(comment, issue, policy):
            continue
        record = question_record(comment)
        if not record:
            continue
        require(record['id'] not in questions, 'DECISION_QUESTION_DUPLICATE: ' + record['id'])
        questions[record['id']] = {**record, 'question_comment_id': comment['id'],
                                   'question_url': comment.get('html_url'), 'responses': []}
    for comment in comments:
        if not authorized(comment, issue, policy) or MARKER.match(comment.get('body', '')):
            continue
        # Only standalone lines count. Quoted text and fenced examples are ignored.
        body, fenced = [], False
        for line in comment.get('body', '').splitlines():
            if line.lstrip().startswith(('```', '~~~')):
                fenced = not fenced
            elif not fenced and not line.lstrip().startswith('>'):
                body.append(line)
        for match in ANSWER.finditer('\n'.join(body)):
            qid, option = match[1].upper(), match[2].upper()
            if qid in questions:
                require(ord(option) - 65 < len(questions[qid]['options']), 'DECISION_OPTION_INVALID: ' + qid)
                questions[qid]['responses'].append({'option': option, 'comment_id': comment['id'],
                     'updated_at': comment.get('updated_at'), 'author': comment['user']['login'],
                     'body_digest': digest(comment['body']), 'url': comment.get('html_url')})
    result = []
    for qid, question in questions.items():
        responses = question.pop('responses')
        choices = {reply['option'] for reply in responses}
        status = 'conflict' if len(choices) > 1 else ('answered' if choices else 'pending')
        result.append({**question, 'status': status, 'option': next(iter(choices)) if len(choices) == 1 else None,
                       'answers': responses})
    return sorted(result, key=lambda item: int(item['id'][2:]))


def reconcile(root, feature, gh=None, *, publish_field=False):
    run = Run(root, feature)
    state = run.load()
    source = read(run.feature / 'scope-source.json', {})
    repo, number = state['issue'].split('#')
    if source:
        require((source.get('repo'), source.get('issue')) == (repo, int(number)),
                'DECISION_BINDING_MISMATCH')
    else:
        require(not state.get('receipts', {}).get('specify') and
                (state.get('active') or {}).get('stage') in ('scope', 'specify'),
                'DECISION_SOURCE_BINDING_REQUIRED')
    gh = gh or GitHub()
    issue = gh.api(f'repos/{repo}/issues/{number}')
    require(issue.get('number') == int(number), 'DECISION_ISSUE_MISMATCH')
    comments = gh.api(f'repos/{repo}/issues/{number}/comments?per_page=100', pages=True)
    current = answers(comments, issue, run.policy)
    path = run.feature / 'workflow/decisions.json'
    previous = read(path, {})
    require(isinstance(previous, dict) and isinstance(previous.get('decisions', []), list),
            'DECISION_LEDGER_INVALID')
    prior = {item['id']: item for item in previous.get('decisions', [])}
    for item in current:
        old = prior.get(item['id'], {})
        answer_hash = digest(item['answers'])
        if (item['status'] == 'answered' and old.get('status') == 'applied'
                and old.get('answer_digest') == answer_hash):
            item['status'] = 'applied'
            item['application'] = old['application']
        item['answer_digest'] = answer_hash
    require(not (set(prior) - {item['id'] for item in current}), 'DECISION_QUESTION_REMOVED')
    ledger = {'version': 1, 'feature': feature, 'issue': state['issue'], 'decisions': current}
    if ledger != previous:
        write(path, ledger)
    if publish_field:
        sync_project_field(root, issue, ledger, gh, run.policy)
    return ledger


def ask(root, feature, question, options, gh=None):
    lock = Path(root) / '.specify/workflow/runtime' / ('decision-' + digest(feature) + '.lock')
    with locked(lock):
        return _ask(root, feature, question, options, gh)


def _ask(root, feature, question, options, gh=None):
    require(question.strip() and 2 <= len(options) <= 26 and all(option.strip() for option in options),
            'DECISION_QUESTION_INVALID')
    ledger = reconcile(root, feature, gh)
    request_digest = digest({'question': question.strip(), 'options': options})
    existing = next((item for item in ledger['decisions']
                     if item.get('request_digest') == request_digest), None)
    if existing:
        return {'id': existing['id'], 'url': existing.get('question_url'),
                'status': existing['status'], 'reused': True}
    number = max((int(item['id'][2:]) for item in ledger['decisions']), default=0) + 1
    qid = f'SD{number}'
    body = f'**{qid}: {question.strip()}**\n\n' + '\n'.join(f'- {chr(65+i)}. {option}' for i, option in enumerate(options))
    body += f'\n\nReply with `{qid}: A` (or another letter) in a new comment. Decisions are reviewed in this issue.'
    marker = {'version': 1, 'id': qid, 'options': options, 'body_digest': digest(body),
              'request_digest': request_digest}
    repo, issue = ledger['issue'].split('#')
    gh = gh or GitHub()
    posted = gh.api(f'repos/{repo}/issues/{issue}/comments', 'POST',
                    {'body': '<!-- sanduq-decision:question ' + json.dumps(marker, sort_keys=True) + ' -->\n' + body})
    require(posted.get('id'), 'DECISION_POST_NOT_CONFIRMED')
    ledger['decisions'].append({**marker, 'question_comment_id': posted['id'],
                                'question_url': posted.get('html_url'), 'status': 'pending',
                                'option': None, 'answers': [], 'answer_digest': digest([])})
    write(Path(root) / feature / 'workflow/decisions.json', ledger)
    return {'id': qid, 'url': posted.get('html_url'), 'status': 'pending'}


def apply_answer(root, feature, qid, evidence, gh=None):
    lock = Path(root) / '.specify/workflow/runtime' / ('decision-' + digest(feature) + '.lock')
    with locked(lock):
        return _apply_answer(root, feature, qid, evidence, gh)


def _apply_answer(root, feature, qid, evidence, gh=None):
    ledger = reconcile(root, feature, gh)
    item = next((item for item in ledger['decisions'] if item['id'] == qid), None)
    require(item and item['status'] in ('answered', 'applied'), 'DECISION_NOT_ANSWERED: ' + qid)
    files = [str(inside(root, value).relative_to(root).as_posix()) for value in evidence]
    require(files and all((root / value).is_file() for value in files), 'DECISION_APPLICATION_EVIDENCE_REQUIRED')
    item['status'] = 'applied'
    item['application'] = {'evidence': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files},
                           'answer_digest': item['answer_digest']}
    write(Path(root) / feature / 'workflow/decisions.json', ledger)
    return item


def verify_ledger(root, feature, ledger):
    require(isinstance(ledger, dict) and ledger.get('version') == 1
            and ledger.get('feature') == feature, 'DECISION_LEDGER_INVALID')
    require(isinstance(ledger.get('decisions'), list), 'DECISION_LEDGER_INVALID')
    for item in ledger.get('decisions', []):
        require(isinstance(item, dict) and isinstance(item.get('answers'), list)
                and all(isinstance(reply, dict) for reply in item['answers']),
                'DECISION_LEDGER_INVALID')
        require(item.get('status') == 'applied', 'DECISION_UNRESOLVED: ' + item.get('id', '?'))
        chosen = {reply.get('option') for reply in item.get('answers', [])}
        require(len(chosen) == 1 and item.get('option') == next(iter(chosen)),
                'DECISION_CHOICE_MISMATCH: ' + item.get('id', '?'))
        require(item.get('answers') and item.get('answer_digest') == digest(item['answers']),
                'DECISION_ANSWER_CHANGED: ' + item.get('id', '?'))
        application = item.get('application', {})
        require(isinstance(application, dict) and isinstance(application.get('evidence'), dict)
                and application['evidence'], 'DECISION_APPLICATION_EVIDENCE_REQUIRED')
        require(application.get('answer_digest') == item['answer_digest'], 'DECISION_APPLICATION_STALE')
        for name, expected in application.get('evidence', {}).items():
            path = inside(root, name)
            require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                    'DECISION_APPLICATION_STALE: ' + name)


def sync_project_field(root, issue, ledger, gh, policy):
    """Only edit the dedicated Decision field; never move the lifecycle Status."""
    config = read(Path(root) / '.specify/extensions/project/config.json', {})
    require(config.get('projectId') and config.get('projectNumber') and config.get('owner'),
            'DECISION_PROJECT_NOT_CONFIGURED')
    field_name = policy.get('decisions', {}).get('project_field', 'Decision')
    base = ['--owner', config['owner'], '--format', 'json']
    field_list = gh.command(['project', 'field-list', str(config['projectNumber']), *base, '--limit', '1000'])
    require(field_list.get('totalCount', len(field_list['fields'])) <= len(field_list['fields']),
            'DECISION_PROJECT_FIELDS_PARTIAL')
    fields = field_list['fields']
    field = next((value for value in fields if value['name'] == field_name), None)
    if field is None:
        gh.command(['project', 'field-create', str(config['projectNumber']), '--owner', config['owner'],
                    '--name', field_name, '--data-type', 'SINGLE_SELECT',
                    '--single-select-options', 'None,Waiting,Needs review,Applied', '--format', 'json'])
        fields = gh.command(['project', 'field-list', str(config['projectNumber']), *base, '--limit', '1000'])['fields']
        field = next((value for value in fields if value['name'] == field_name), None)
    require(field and field.get('type') == 'ProjectV2SingleSelectField',
            'DECISION_SINGLE_SELECT_FIELD_REQUIRED: ' + field_name)
    item_list = gh.command(['project', 'item-list', str(config['projectNumber']), *base, '--limit', '10000'])
    require(item_list.get('totalCount', len(item_list['items'])) <= len(item_list['items']),
            'DECISION_PROJECT_ITEMS_PARTIAL')
    items = item_list['items']
    repo = issue.get('repository_url', '').removeprefix('https://api.github.com/repos/')
    item = next((value for value in items if value.get('content', {}).get('type') == 'Issue'
                 and value['content'].get('number') == issue['number']
                 and value['content'].get('repository') == repo), None)
    if item is None:
        item = next((value for value in items if value.get('content', {}).get('url') == issue.get('html_url')), None)
    require(item, 'DECISION_PROJECT_ITEM_MISSING')
    states = {value['status'] for value in ledger['decisions']}
    summary = ('Needs review' if 'conflict' in states or 'answered' in states else
               'Waiting' if 'pending' in states else 'Applied' if states else 'None')
    option = next((value for value in field.get('options', []) if value['name'] == summary), None)
    require(option, 'DECISION_FIELD_OPTION_MISSING: ' + summary)
    gh.command(['project', 'item-edit', '--id', item['id'], '--project-id', config['projectId'],
                '--field-id', field['id'], '--single-select-option-id', option['id']])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    ask_command = sub.add_parser('ask')
    ask_command.add_argument('--question', required=True)
    ask_command.add_argument('--option', action='append', required=True)
    sync = sub.add_parser('sync')
    sync.add_argument('--project-field', action='store_true')
    apply_command = sub.add_parser('apply')
    apply_command.add_argument('--id', required=True)
    apply_command.add_argument('--evidence', action='append', required=True)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if args.action == 'ask':
            result = ask(root, args.feature, args.question, args.option)
        elif args.action == 'sync':
            result = reconcile(root, args.feature, publish_field=args.project_field)
        else:
            result = apply_answer(root, args.feature, args.id.upper(), args.evidence)
        if args.action in ('ask', 'apply'):
            reconcile(root, args.feature, publish_field=True)
        print(json.dumps(result, indent=2))
        return 0
    except (WorkflowError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
