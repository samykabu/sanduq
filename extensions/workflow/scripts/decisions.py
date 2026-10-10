#!/usr/bin/env python3
"""Stage-neutral decisions recorded in a bound GitHub issue discussion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

from workflow import WorkflowError, Run, digest, inside, load_policy, locked, read, require, write

MARKER = re.compile(r'\A<!-- sanduq-decision:question (\{[^\n]*\}) -->\n')
ANSWER = re.compile(r'^\s*(SD[1-9]\d*):\s*([A-Z])\s*$', re.I | re.M)
ANSWER_LIST = re.compile(r'^\s*(SD[1-9]\d*):\s*([A-Z](?:\s*,\s*[A-Z])*)\s*$', re.I | re.M)
CHOICES = re.compile(r'(?<=<!-- sanduq-decision:choices:start -->\n)(.*?)(?=\n<!-- sanduq-decision:choices:end -->)', re.S)
TICKED = re.compile(r'^- \[[xX]\] ')
LEGACY_TITLE = re.compile(r'\A\*\*(SD[1-9]\d*): (.+)\*\*\n')
MODES = ('single', 'multiple')


def scope_transport():
    path = Path(__file__).resolve().parents[2] / 'scope/scripts/scope.py'
    spec = importlib.util.spec_from_file_location('sanduq_scope_decision_transport', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GitHub:
    def __init__(self):
        self._project = None
        self.project_cfg = None

    @property
    def project_transport(self):
        return self._project.project_transport if self._project else None

    def api(self, endpoint, method='GET', payload=None, pages=False):
        args = ['gh', 'api', endpoint, '-H', 'Accept: application/vnd.github+json']
        if pages:
            args += ['--paginate', '--slurp']
        if method != 'GET':
            args += ['--method', method]
        if payload is not None:
            args += ['--input', '-']
        result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        require(result.returncode == 0, 'GITHUB_DECISION_API_FAILED: ' + result.stderr.strip()[:500])
        data = json.loads(result.stdout) if result.stdout.strip() else None
        return [item for page in data for item in page] if pages else data

    def command(self, args):
        if self._project is None:
            self._project = scope_transport().GitHub()
        self._project.project_cfg = self.project_cfg
        try:
            return self._project.command(args)
        except Exception as exc:
            raise WorkflowError('GITHUB_DECISION_PROJECT_FAILED: ' + str(exc)) from exc



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
    require(not (set(data) - {'version', 'id', 'options', 'body_digest', 'request_digest',
                             'choice_format', 'mode', 'recommended', 'upgraded_from'}),
            'DECISION_QUESTION_MARKER_INVALID')
    body = comment['body'].split('\n', 1)[1]
    if data.get('choice_format') == 1:
        require(data.get('mode') in MODES, 'DECISION_MODE_INVALID: ' + data['id'])
        recommended = data.get('recommended')
        require(recommended is None or (type(recommended) is int and 0 <= recommended < len(data['options'])),
                'DECISION_RECOMMENDATION_INVALID: ' + data['id'])
        checked = unticked(body)
        require(checked is not None and data.get('body_digest') == digest(checked),
                'DECISION_QUESTION_EDITED: ' + data['id'])
        title = LEGACY_TITLE.match(checked)
        require(title and title[1] == data['id'] and checked == render_body(
            data['id'], title[2], data['options'], data['mode'], recommended),
            'DECISION_QUESTION_EDITED: ' + data['id'])
        require(recommended is None or data['mode'] == 'single', 'DECISION_RECOMMENDATION_INVALID')
        return data
    require('choice_format' not in data, 'DECISION_QUESTION_MARKER_INVALID')
    require(data.get('body_digest') == digest(body), 'DECISION_QUESTION_EDITED: ' + data['id'])
    title = LEGACY_TITLE.match(body)
    choices = '\n'.join(f'- {letter(i)}. {option}' for i, option in enumerate(data['options']))
    require(title and title[1] == data['id'] and body.startswith(
        f'**{data["id"]}: {title[2]}**\n\n' + choices) and data.get('mode', 'single') == 'single'
        and data.get('recommended') is None, 'DECISION_QUESTION_EDITED: ' + data['id'])
    prefix = f'**{data["id"]}: {title[2]}**\n\n' + choices
    require(body[len(prefix):] == '' or body[len(prefix):].startswith('\n\n'),
            'DECISION_QUESTION_EDITED: ' + data['id'])
    return data


def letter(index):
    return chr(65 + index)


def render_body(qid, question, options, mode='single', recommended=None):
    """The canonical question body of a selectable decision: nothing is ticked."""
    hint = ('Tick exactly one option.' if mode == 'single'
            else 'Tick every option that applies (at least one).')
    lines = [f'- [ ] **{letter(i)}.** {option}' + (' **(Recommended)**' if i == recommended else '')
             for i, option in enumerate(options)]
    return (f'**{qid}: {question.strip()}**\n\n{hint} The recommendation is never pre-selected.\n\n'
            '<!-- sanduq-decision:choices:start -->\n' + '\n'.join(lines)
            + '\n<!-- sanduq-decision:choices:end -->\n\n'
            f'Prefer text? Reply in a new comment with `{qid}: A`'
            + (f' (or `{qid}: A, C`)' if mode == 'multiple' else '')
            + '. Decisions are reviewed in this issue.')


def unticked(body):
    """The body with every choice unticked, so a tick is the only edit that keeps its digest."""
    found = CHOICES.search(body)
    if not found:
        return None
    lines = [TICKED.sub('- [ ] ', line) for line in found[0].split('\n')]
    return body[:found.start()] + '\n'.join(lines) + body[found.end():]


def ticked(body, count):
    found = CHOICES.search(body)
    lines = found[0].split('\n') if found else []
    return [letter(i) for i, line in enumerate(lines[:count]) if TICKED.match(line)]


def resolve(answers, mode='single'):
    """Status and selected letters from recorded answers; one rule for reading and verifying."""
    if not answers:
        return 'pending', []
    groups = {}
    for reply in answers:
        key = 'checkbox' if reply.get('source') == 'checkbox' else reply.get('comment_id')
        groups.setdefault(key, set()).add(reply.get('option'))
    if mode == 'single':
        chosen = set().union(*groups.values())
        return ('conflict', []) if len(chosen) > 1 else ('answered', sorted(chosen))
    distinct = {frozenset(group) for group in groups.values()}
    return ('conflict', []) if len(distinct) > 1 else ('answered', sorted(next(iter(distinct))))


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
                                   'question_url': comment.get('html_url'), 'responses': [],
                                   'mode': record.get('mode', 'single')}
        if record.get('choice_format') == 1:
            # GitHub does not say who ticked a box, so this evidence names the question
            # comment and never an author.
            for option in ticked(comment['body'].split('\n', 1)[1], len(record['options'])):
                questions[record['id']]['responses'].append({
                    'option': option, 'source': 'checkbox', 'comment_id': comment['id'],
                    'author': None, 'body_digest': digest(['checkbox', record['id'], option]),
                    'url': comment.get('html_url')})
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
        for match in ANSWER_LIST.finditer('\n'.join(body)):
            qid = match[1].upper()
            if qid not in questions:
                continue
            letters = sorted(set(re.findall(r'[A-Z]', match[2].upper())))
            if questions[qid]['mode'] == 'single' and len(letters) > 1:
                continue  # a list of letters only answers a multiple-selection question
            for option in letters:
                require(ord(option) - 65 < len(questions[qid]['options']), 'DECISION_OPTION_INVALID: ' + qid)
                questions[qid]['responses'].append({'option': option, 'comment_id': comment['id'],
                     'updated_at': comment.get('updated_at'), 'author': comment['user']['login'],
                     'body_digest': digest(comment['body']), 'url': comment.get('html_url')})
    result = []
    for qid, question in questions.items():
        responses = question.pop('responses')
        status, selected = resolve(responses, question['mode'])
        result.append({**question, 'status': status, 'selected': selected,
                       'option': selected[0] if question['mode'] == 'single' and selected else None,
                       'answers': responses})
    return sorted(result, key=lambda item: int(item['id'][2:]))


LATER_STAGES = ('specify', 'clarify', 'plan', 'tasks', 'qa_analyze', 'manual_analyze', 'analyze',
                'taskstoissues', 'execute', 'verify', 'review', 'qa_document', 'manual_update',
                'ready', 'pr')


def bound_state(run, previous=None, claim_token=None, session_id=None):
    """Checkpoint state for a decision command, bound to its issue before and after Specify.

    Before Specify there is no scope-source.json (and none is invented): the checkpoint's
    issue is the binding. A paused or resumed run has no active claim and may sit on a
    different branch, so neither is required; a Specify receipt or later stage is.
    """
    # Read identity through Run, then grant branch relaxation only to paused pre-Specify work.
    state = run.load(allow_branch_change=True)
    active = state.get('active') or {}
    source_exists = (run.feature / 'scope-source.json').is_file()
    paused_pre_specify = (state.get('status') == 'paused' and not active and not source_exists
                          and not any(stage in state.get('receipts', {}) for stage in LATER_STAGES))
    if not paused_pre_specify:
        state = run.load()  # enforce the branch for active/bound/later work
    source = read(run.feature / 'scope-source.json', {})
    repo, number = state['issue'].split('#')
    if source:
        require((source.get('repo'), source.get('issue')) == (repo, int(number)),
                'DECISION_BINDING_MISMATCH')
    else:
        receipts = state.get('receipts', {})
        require(not any(stage in receipts for stage in LATER_STAGES)
                and (state.get('active') or {}).get('stage') in (None, 'scope', 'specify'),
                'DECISION_SOURCE_BINDING_REQUIRED')
    if active:
        require(active.get('token') and active.get('session_id') and
                active['token'] == (claim_token or os.environ.get('SANDUQ_WORKFLOW_CLAIM_TOKEN')) and
                active['session_id'] == (session_id or os.environ.get('SANDUQ_WORKFLOW_SESSION_ID')),
                'DECISION_ACTIVE_EXECUTOR_MISMATCH')
    if isinstance(previous, dict) and previous:
        require(not previous.get('feature') or previous['feature'] == getattr(run, 'relative', run.feature.relative_to(run.feature.parents[1]).as_posix()),
                'DECISION_BINDING_MISMATCH')
        require(not previous.get('issue') or previous['issue'] == state['issue'],
                'DECISION_BINDING_MISMATCH')
    return state


def reconcile(root, feature, gh=None, *, publish_field=False, claim_token=None, session_id=None):
    run = Run(root, feature)
    previous = read(run.feature / 'workflow/decisions.json', {})
    state = bound_state(run, previous, claim_token, session_id)
    repo, number = state['issue'].split('#')
    gh = gh or GitHub()
    issue = gh.api(f'repos/{repo}/issues/{number}')
    require(issue.get('number') == int(number), 'DECISION_ISSUE_MISMATCH')
    comments = gh.api(f'repos/{repo}/issues/{number}/comments?per_page=100', pages=True)
    current = answers(comments, issue, run.policy)
    path = run.feature / 'workflow/decisions.json'
    require(isinstance(previous, dict) and isinstance(previous.get('decisions', []), list),
            'DECISION_LEDGER_INVALID')
    prior = {item['id']: item for item in previous.get('decisions', [])}
    for item in current:
        old = prior.get(item['id'], {})
        if old:
            immutable = ('version', 'id', 'options', 'request_digest', 'question_comment_id')
            require(all(old.get(key) == item.get(key) for key in immutable),
                    'DECISION_QUESTION_EDITED: ' + item['id'])
            converted = (not old.get('choice_format') and item.get('choice_format') == 1
                         and item.get('upgraded_from') == old.get('body_digest')
                         and item.get('mode') == 'single' and item.get('recommended') is None)
            require(converted or all(old.get(key) == item.get(key) for key in
                    ('body_digest', 'choice_format', 'recommended', 'upgraded_from')),
                    'DECISION_QUESTION_EDITED: ' + item['id'])
            require(old.get('mode', 'single') == item.get('mode', 'single'),
                    'DECISION_QUESTION_EDITED: ' + item['id'])
        if old and converted:
            # Conversion may alter presentation only; recover the original title from the
            # new canonical body and check it against the recorded legacy digest.
            comment = next(c for c in comments if c['id'] == item['question_comment_id'])
            title = LEGACY_TITLE.match(comment['body'].split('\n', 1)[1])[2]
            legacy = f'**{item["id"]}: {title}**\n\n' + '\n'.join(
                f'- {letter(i)}. {value}' for i, value in enumerate(item['options']))
            suffix = f'\n\nReply with `{item["id"]}: A` (or another letter) in a new comment. Decisions are reviewed in this issue.'
            require(old['body_digest'] in (digest(legacy), digest(legacy + suffix)),
                    'DECISION_QUESTION_EDITED: ' + item['id'])
        answer_hash = digest(item['answers'])
        if (item['status'] == 'answered' and old.get('status') == 'applied'
                and old.get('answer_digest') == answer_hash):
            item['status'] = 'applied'
            item['application'] = old['application']
        item['answer_digest'] = answer_hash
    require(not (set(prior) - {item['id'] for item in current}), 'DECISION_QUESTION_REMOVED')
    ledger = {'version': 1, 'feature': feature, 'issue': state['issue'], 'decisions': current}
    if previous.get('lifecycle'):
        ledger['lifecycle'] = previous['lifecycle']
    if ledger != previous:
        write(path, ledger)
    if publish_field:
        sync_project_field(root, issue, ledger, gh, run.policy)
        lifecycle = sync_lifecycle(root, issue, ledger, gh, run.policy, ledger_path=path)
        if lifecycle != ledger.get('lifecycle', {}):
            ledger['lifecycle'] = lifecycle
            write(path, ledger)
        write(path, ledger)
    return ledger


def ask(root, feature, question, options, gh=None, mode='single', recommended=None):
    lock = Path(root) / '.specify/workflow/runtime' / ('decision-' + digest(feature) + '.lock')
    with locked(lock):
        return _ask(root, feature, question, options, gh, mode, recommended)


def _ask(root, feature, question, options, gh=None, mode='single', recommended=None):
    require(question.strip() and 2 <= len(options) <= 26
            and all(option.strip() and '\n' not in option for option in options),
            'DECISION_QUESTION_INVALID')
    require(mode in MODES, 'DECISION_MODE_INVALID')
    if isinstance(recommended, str):
        require(re.fullmatch(r'[A-Za-z]', recommended), 'DECISION_RECOMMENDATION_INVALID')
        recommended = ord(recommended.upper()) - 65
    require(recommended is None or (mode == 'single' and 0 <= recommended < len(options)),
            'DECISION_RECOMMENDATION_INVALID')
    ledger = reconcile(root, feature, gh)
    # Requests made without the new settings keep the digest they always had.
    request = {'question': question.strip(), 'options': options}
    if mode != 'single':
        request['mode'] = mode
    if recommended is not None:
        request['recommended'] = recommended
    request_digest = digest(request)
    existing = next((item for item in ledger['decisions']
                     if item.get('request_digest') == request_digest), None)
    if existing:
        return {'id': existing['id'], 'url': existing.get('question_url'),
                'status': existing['status'], 'reused': True}
    number = max((int(item['id'][2:]) for item in ledger['decisions']), default=0) + 1
    qid = f'SD{number}'
    body = render_body(qid, question, options, mode, recommended)
    marker = {'version': 1, 'id': qid, 'options': options, 'body_digest': digest(body),
              'request_digest': request_digest, 'choice_format': 1, 'mode': mode,
              'recommended': recommended}
    repo, issue = ledger['issue'].split('#')
    gh = gh or GitHub()
    posted = gh.api(f'repos/{repo}/issues/{issue}/comments', 'POST',
                    {'body': '<!-- sanduq-decision:question ' + json.dumps(marker, sort_keys=True) + ' -->\n' + body})
    require(posted.get('id'), 'DECISION_POST_NOT_CONFIRMED')
    ledger['decisions'].append({**marker, 'question_comment_id': posted['id'],
                                'question_url': posted.get('html_url'), 'status': 'pending',
                                'option': None, 'selected': [], 'answers': [],
                                'answer_digest': digest([])})
    write(Path(root) / feature / 'workflow/decisions.json', ledger)
    return {'id': qid, 'url': posted.get('html_url'), 'status': 'pending'}


def upgrade_questions(root, feature, gh=None):
    """Rewrite legacy question comments as selectable ones; idempotent and never ticks a box."""
    lock = Path(root) / '.specify/workflow/runtime' / ('decision-' + digest(feature) + '.lock')
    with locked(lock):
        return _upgrade_questions(root, feature, gh)


def _upgrade_questions(root, feature, gh=None):
    reconcile(root, feature, gh)  # validate trusted immutable evidence before any PATCH
    run = Run(root, feature)
    state = bound_state(run, read(run.feature / 'workflow/decisions.json', {}))
    repo, number = state['issue'].split('#')
    gh = gh or GitHub()
    issue = gh.api(f'repos/{repo}/issues/{number}')
    require(issue.get('number') == int(number), 'DECISION_ISSUE_MISMATCH')
    comments = gh.api(f'repos/{repo}/issues/{number}/comments?per_page=100', pages=True)
    upgraded, unchanged = [], []
    for comment in comments:
        if not authorized(comment, issue, run.policy):
            continue
        record = question_record(comment)  # an edited legacy question fails closed here
        if not record:
            continue
        if record.get('choice_format') == 1:
            unchanged.append(record['id'])
            continue
        title = LEGACY_TITLE.match(comment['body'].split('\n', 1)[1])
        require(title and title[1] == record['id'], 'DECISION_QUESTION_MARKER_INVALID: ' + record['id'])
        body = render_body(record['id'], title[2], record['options'])
        marker = {**record, 'body_digest': digest(body), 'choice_format': 1, 'mode': 'single',
                  'recommended': None, 'upgraded_from': record['body_digest']}
        text = '<!-- sanduq-decision:question ' + json.dumps(marker, sort_keys=True) + ' -->\n' + body
        patched = gh.api(f'repos/{repo}/issues/comments/{comment["id"]}', 'PATCH', {'body': text})
        require(patched and patched.get('id') == comment['id'] and patched.get('body') == text,
                'DECISION_UPGRADE_NOT_CONFIRMED: ' + record['id'])
        upgraded.append(record['id'])
    # The ledger keeps IDs, options and every real reply; only the question's digest moves.
    reconcile(root, feature, gh)
    return {'upgraded': upgraded, 'unchanged': unchanged}


def apply_answer(root, feature, qid, evidence, gh=None):
    lock = Path(root) / '.specify/workflow/runtime' / ('decision-' + digest(feature) + '.lock')
    with locked(lock):
        return _apply_answer(root, feature, qid, evidence, gh)


def _apply_answer(root, feature, qid, evidence, gh=None):
    root = Path(root).resolve()  # inside() resolves; an unresolved 8.3 root never matches
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
        mode = item.get('mode', 'single')
        status, selected = resolve(item['answers'], mode)
        require(status == 'answered' and item.get('selected', selected) == selected
                and (mode != 'single' or item.get('option') == selected[0]),
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


def project_item(gh, config, issue):
    gh.project_cfg = config
    base = ['--owner', config['owner'], '--format', 'json']
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
    return item


def sync_lifecycle(root, issue, ledger, gh, policy, ledger_path=None):
    """Park the issue in the mapped Need Clarifications status while a decision waits.

    Only mapped Backlog or Feature Specification issues are parked, and only a status this module parked is
    returned (to Feature Specification, and only when the clarification policy rereads
    answers). Any other status, advanced or set by someone else, is left alone.
    """
    previous = ledger.get('lifecycle') or {}
    if policy.get('decisions', {}).get('lifecycle_status', True) is False:
        return previous
    config = read(Path(root) / '.specify/extensions/project/config.json', {})
    require(config.get('projectId') and config.get('projectNumber') and config.get('owner')
            and config.get('statusFieldId'), 'DECISION_PROJECT_NOT_CONFIGURED')
    mapping = policy.get('scope', {}).get('statuses', {})
    backlog_status = mapping.get('Backlog', 'Backlog')
    feature_status = mapping.get('Feature Specification', 'Feature Specification')
    waiting_status = mapping.get('Need Clarifications', 'Need Clarifications')
    item = project_item(gh, config, issue)
    current = item.get('status')
    states = {value['status'] for value in ledger['decisions']}
    intent = previous.get('intent') or {}
    owned_intent = (intent.get('item') == item['id'] and intent.get('issue') == issue['number']
                    and intent.get('from') in (backlog_status, feature_status)
                    and intent.get('to') == waiting_status)
    parked = bool(previous.get('parked')) or (owned_intent and current == waiting_status)
    target = None
    if states & {'pending', 'conflict'}:
        if current in (backlog_status, feature_status):
            target, parked = waiting_status, True
    elif parked:
        if current == waiting_status and (
                policy.get('clarification', {}).get('resume_on_reinvoke') == 'reread-answers'):
            target, parked = feature_status, False
        elif current != waiting_status:
            parked = False  # someone moved it on; never move it back
    if target:
        option = config.get('statusOptions', {}).get(target)
        require(option, 'DECISION_STATUS_OPTION_MISSING: ' + target)
        # Persist intent before writing remotely; a lost response can be reconciled on retry.
        if target == waiting_status:
            ledger['lifecycle'] = {'intent': {'item': item['id'], 'issue': issue['number'],
                                             'from': current, 'to': target}}
            if ledger_path:
                write(ledger_path, ledger)
        gh.command(['project', 'item-edit', '--id', item['id'], '--project-id', config['projectId'],
                    '--field-id', config['statusFieldId'], '--single-select-option-id', option])
        verified = project_item(gh, config, issue)
        require(verified.get('status') == target, 'DECISION_STATUS_VERIFICATION_FAILED: ' + target)
        current = verified['status']
        cache = Path(root) / config['stateFile'] if config.get('stateFile') else None
        state = read(cache, {}) if cache else {}
        if state:
            for entry in state.values():
                if entry.get('issue') == issue['number']:
                    entry['status'] = target
            write(cache, state)
    return {'parked': True} if parked else {}


def sync_project_field(root, issue, ledger, gh, policy):
    """Only edit the dedicated Decision field; never move the lifecycle Status."""
    config = read(Path(root) / '.specify/extensions/project/config.json', {})
    require(config.get('projectId') and config.get('projectNumber') and config.get('owner'),
            'DECISION_PROJECT_NOT_CONFIGURED')
    field_name = policy.get('decisions', {}).get('project_field', 'Decision')
    gh.project_cfg = config
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
    item = project_item(gh, config, issue)
    states = {value['status'] for value in ledger['decisions']}
    summary = ('Needs review' if 'conflict' in states or 'answered' in states else
               'Waiting' if 'pending' in states else 'Applied' if states else 'None')
    option = next((value for value in field.get('options', []) if value['name'] == summary), None)
    require(option, 'DECISION_FIELD_OPTION_MISSING: ' + summary)
    gh.command(['project', 'item-edit', '--id', item['id'], '--project-id', config['projectId'],
                '--field-id', field['id'], '--single-select-option-id', option['id']])
    verified = project_item(gh, config, issue)
    require(verified.get(field_name[:1].lower() + field_name[1:], verified.get(field_name.lower())) == summary,
            'DECISION_FIELD_VERIFICATION_FAILED: ' + field_name)
    ledger['publication'] = {'decision': summary, 'transport': getattr(gh, 'project_transport', None)}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--feature', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    ask_command = sub.add_parser('ask')
    ask_command.add_argument('--question', required=True)
    ask_command.add_argument('--option', action='append', required=True)
    ask_command.add_argument('--mode', choices=MODES, default='single',
                             help='single: exactly one box; multiple: one or more boxes')
    ask_command.add_argument('--recommended', metavar='LETTER',
                             help='Letter of the recommended option, shown as a suffix and never pre-ticked')
    sub.add_parser('upgrade-questions', help='Make legacy question comments selectable; idempotent')
    sync = sub.add_parser('sync')
    sync.add_argument('--project-field', action='store_true')
    apply_command = sub.add_parser('apply')
    apply_command.add_argument('--id', required=True)
    apply_command.add_argument('--evidence', action='append', required=True)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if args.action == 'ask':
            result = ask(root, args.feature, args.question, args.option,
                         mode=args.mode, recommended=args.recommended)
        elif args.action == 'upgrade-questions':
            result = upgrade_questions(root, args.feature)
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
