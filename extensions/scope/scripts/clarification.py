#!/usr/bin/env python3
"""Shared unattended GitHub clarification rounds for Clarify and Superspec Brainstorm."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from urllib.parse import quote
from pathlib import Path

from scope import Scope, ScopeError, mutation_lock, require, read_json, write_json, with_transport

FEATURE, WAITING = 'Feature Specification', 'Need Clarifications'
RECORD = re.compile(r'\A<!-- speckit-clarification:(question|round|round-in-session) (\{[^\n]*\}) -->\n')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def record(comment):
    match = RECORD.match(comment.get('body', ''))
    if not match:
        return None
    value = json.loads(match[2])
    require(value.get('version') == 1, 'Unsupported clarification history version.')
    return dict(value, kind=match[1])


def plain_lines(text):
    """Controls/answers inside quotes or fences are not new user instructions."""
    result, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if not fenced and not line.lstrip().startswith('>'):
            result.append(line)
    return '\n'.join(result).strip()


def trusted(comment, creator):
    return comment.get('user', {}).get('type') != 'Bot' and (
        comment.get('user', {}).get('login', '').casefold() == creator.casefold()
        or comment.get('author_association') in {'OWNER', 'MEMBER', 'COLLABORATOR'})


def option_label(index):
    label = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return label


def host_image(root, repo, gh, path):
    """Return (url, None) for an Illustrate PNG that GitHub can show in an issue comment, else (None, reason).

    Same rule as the PR extension's image embedding: a commit-pinned github.com blob URL with
    ?raw=true, verified through the contents API at that commit. It loads for any reader who can
    see the repository, so private repositories work; raw.githubusercontent.com is never used.
    """
    root = Path(root).resolve()
    image = (root / path).resolve()
    if not image.is_relative_to(root) or image.suffix.lower() != '.png' or not image.is_file():
        return None, f'{path} is not an exported PNG inside the project'
    relative = image.relative_to(root).as_posix()
    git = lambda *a: subprocess.run(['git', '-C', str(root), *a], capture_output=True, text=True, check=True).stdout.strip()
    commit = 'HEAD'
    try:
        commit = git('rev-parse', 'HEAD')
        blob = git('hash-object', relative)
        remote = gh.api(f'repos/{repo}/contents/{quote(relative)}?ref={commit}')
    except (OSError, subprocess.CalledProcessError, ScopeError) as exc:
        detail = (getattr(exc, 'stderr', None) or str(exc)).strip()[:200]
        return None, f'{relative} is not on GitHub at commit {commit[:12]}; commit and push it, then rerun ({detail})'
    if not isinstance(remote, dict) or remote.get('sha') != blob:
        return None, f'{relative} at commit {commit[:12]} on GitHub differs from the local export; push the current file'
    return f'https://github.com/{repo}/blob/{commit}/{quote(relative)}?raw=true', None


def diagram_section(root, repo, gh, question):
    """Inline image when it can be hosted; otherwise the text version with the exact reason. Never blocks."""
    image = question['diagram_image']
    url, reason = host_image(root, repo, gh, image['path'])
    text = question['diagram_text'].strip()
    if url:
        return f'\n![{image["alt"]}]({url})\n\n{text}\n', None
    return f'\n_Diagram image not embedded: {reason}. Text version:_\n\n{text}\n', reason


def choice_lines(options, recommended):
    return [f'- [ ] **{option_label(i)}.** {text}' + (' **(Recommended)**' if i == recommended else '')
            for i, text in enumerate(options, 1)]


def selection(comment, item=None):
    """Read deliberate checkbox changes; recommendations are always initially unchecked."""
    item = item or record(comment) or {}
    result = {'state': 'unanswered', 'labels': [], 'options': []}
    if item.get('choice_format') != 1 or not item.get('options'):
        return result
    match = re.search(r'<!-- speckit-clarification:choices:start -->\n(.*?)\n<!-- speckit-clarification:choices:end -->', comment['body'], re.S)
    expected = choice_lines(item['options'], item['recommended_option'])
    lines = match[1].splitlines() if match else []
    if [re.sub(r'^- \[[xX]\]', '- [ ]', line) for line in lines] != expected:
        return dict(result, state='edited')
    chosen = [i for i, line in enumerate(lines) if re.match(r'^- \[[xX]\]', line)]
    return {'state': 'selected' if len(chosen) == 1 else ('ambiguous' if chosen else 'unanswered'),
            'labels': [option_label(i + 1) for i in chosen], 'options': [item['options'][i] for i in chosen]}


def managed_comment(kind, meta, content):
    meta = dict(meta, body_digest=digest(content))
    return '<!-- speckit-clarification:' + kind + ' ' + json.dumps(meta, ensure_ascii=True) + ' -->\n' + content


def pristine_batch_comment(comment, batch):
    item = record(comment)
    return item and item.get('batch') == batch and item.get('body_digest') == digest(comment['body'].split('\n', 1)[1])


def controls(comments, creator):
    policy = {'max_rounds': 7, 'closed': False, 'control_comment_ids': []}
    for comment in sorted(comments, key=lambda c: (c.get('updated_at', c.get('created_at', '')), c['id'])):
        if comment.get('user', {}).get('login', '').casefold() != creator.casefold() or comment.get('user', {}).get('type') == 'Bot' or record(comment):
            continue
        text = plain_lines(comment.get('body', ''))
        for line in text.splitlines():
            limit = re.fullmatch(r'\s*/clarification\s+max-rounds\s+([1-9]\d*)\s*', line, re.I)
            if not limit:
                limit = re.search(r'\b(?:max(?:imum)?\s+clarification\s+(?:rounds|iterations)|clarification\s+(?:round|iteration)\s+limit)\s*[:=]?\s*([1-9]\d*)\b', line, re.I)
            if limit:
                policy['max_rounds'] = int(limit[1])
                policy['control_comment_ids'].append(comment['id'])
            close = re.fullmatch(r'\s*(?:/clarification\s+close|(?:please\s+)?(?:close|stop|end)\s+(?:the\s+)?(?:clarification|brainstorm(?:ing)?)(?:\s+process)?|(?:please\s+)?(?:no more|stop asking)\s+(?:clarification\s+)?questions)[.!]?\s*', line, re.I)
            reopen = re.fullmatch(r'\s*/clarification\s+reopen\s*', line, re.I)
            if close or reopen:
                policy['closed'] = bool(close)
                policy['control_comment_ids'].append(comment['id'])
    policy['control_comment_ids'] = sorted(set(policy['control_comment_ids']))
    return policy


def history(comments, creator, own=frozenset()):
    questions, rounds = {}, []
    for comment in comments:
        item = record(comment)
        if not item:
            continue
        # Protocol records count only from the runtime's own comments (`own`) or a trusted human, so neither an
        # outside commenter nor another bot or app can forge a question or a round.
        if comment['id'] not in own and not trusted(comment, creator):
            continue
        item = dict(item, comment_id=comment['id'], comment_url=comment.get('html_url'))
        if item['kind'] == 'question':
            require(item['id'] not in questions, f'Duplicate clarification question ID {item["id"]}; reconcile history first.')
            questions[item['id']] = dict(item, selection=selection(comment, item))
        else:
            rounds.append(item)
    replies, unmatched = {qid: [] for qid in questions}, []
    for qid, question in questions.items():
        if question['selection']['state'] == 'selected':
            selected_comment = next(c for c in comments if c['id'] == question['comment_id'])
            replies[qid].append(selected_comment)
            # Only explicit earlier-round follow-ups can supply parent evidence.
            for parent in question.get('follows_up', []):
                if parent in questions and questions[parent].get('round', 0) < question.get('round', 0):
                    replies[parent].append(selected_comment)
    for comment in comments:
        if record(comment) or not trusted(comment, creator):
            continue
        body = comment.get('body', '')
        if not plain_lines(body):
            continue
        matches = [qid for qid, q in questions.items() if (
            re.search(r'(?<![A-Za-z0-9])' + re.escape(qid) + r'(?![A-Za-z0-9])', body, re.IGNORECASE)
            or f'#issuecomment-{q["comment_id"]}' in body
            or any(line.lstrip().startswith('>') and q['question'] in line for line in body.splitlines()))]
        for qid in matches:
            replies[qid].append(comment)
        if not matches:
            unmatched.append(comment)
    return {'questions': questions, 'rounds': rounds, 'reply_candidates': replies, 'unmatched_comments': unmatched}


def snapshot_digest(snapshot, exclude_batch=None, spec_override=None):
    comments = [c for c in snapshot['comments'] if not pristine_batch_comment(c, exclude_batch)] if exclude_batch else snapshot['comments']
    return digest({'issue': {k: snapshot['issue'].get(k) for k in ('number', 'title', 'body', 'state')},
                   'comments': [{k: c.get(k) for k in ('id', 'body', 'updated_at', 'user')} for c in comments],
                   'spec': snapshot['spec'] if spec_override is None else spec_override})


def apply_edits(spec, edits):
    for edit in edits:
        before, after = edit.get('before'), edit.get('after')
        require(isinstance(before, str) and before and isinstance(after, str) and after,
                'Spec edits require nonempty exact before/after text.')
        require(spec.count(before) == 1, 'Spec edit target is missing or ambiguous; reread the spec.')
        spec = spec.replace(before, after, 1)
    return spec


CLARIFICATIONS_FILE = 'workflow/clarifications.json'
ANSWER_LINE = r'^\s*{qid}\s*[:\-]\s*(.*)$'
VALUE_LIMIT = 500


def comment_url(repo, number, comment_id):
    return f'https://github.com/{repo}/issues/{number}#issuecomment-{comment_id}'


EVIDENCE_KINDS = ('comment', 'disposition', 'selection', 'closure', 'in-session')


def evidence_ref(kind, url=None, comment_id=None, explanation=None):
    """One evidence reference in the pinned shape: `{kind, url|null, comment_id|null, explanation|null}`."""
    assert kind in EVIDENCE_KINDS, kind
    return {'kind': kind, 'url': url, 'comment_id': comment_id, 'explanation': explanation}


def reply_text(body, qid):
    """The part of a human comment that answers `qid`: its own line, else the whole plain text."""
    plain = plain_lines(body)
    for line in plain.splitlines():
        found = re.match(ANSWER_LINE.format(qid=re.escape(qid)), line, re.I)
        if found and found[1].strip():
            return found[1].strip()
    return plain


def reply_answer(text, options):
    """`A`, `A, B` or `A - feedback` against the question's option letters; anything else is free text."""
    head = re.split(r'\s+[\u2014\u2013-]\s+', text, maxsplit=1)[0].strip()
    labels = [part.strip().upper() for part in re.split(r'\s*[,/&]\s*|\s+and\s+', head) if part.strip()]
    valid = {option_label(i) for i in range(1, len(options) + 1)}
    if labels and options and all(label in valid for label in labels):
        return ('single', labels[0]) if len(labels) == 1 else ('multiple', labels)
    return 'text', text[:VALUE_LIMIT]


def suggested_answers(prior):
    """`answered` dispositions the model may copy: one cleanly ticked option and no reply that could override it."""
    suggestions = []
    for qid, question in prior['questions'].items():
        candidates = prior['reply_candidates'].get(qid, [])
        if question['selection']['state'] == 'selected' and [c['id'] for c in candidates] == [question['comment_id']]:
            suggestions.append({'question_id': qid, 'disposition': 'answered', 'comment_ids': [question['comment_id']],
                                'option': question['selection']['labels'][0] + ' — ' + question['selection']['options'][0]})
    return suggestions


def answer_text(question, answer, comments):
    """The chosen answer for the spec's review log: the option letter and text, or the reply text."""
    chosen = answer_record(question, answer, comments)[0]
    if not chosen:
        return answer['disposition']
    if chosen['kind'] == 'text':
        return chosen['value']
    names = {option_label(i): text for i, text in enumerate(question.get('options') or [], 1)}
    labels = chosen['value'] if chosen['kind'] == 'multiple' else [chosen['value']]
    return ', '.join(f'{label} — {names[label]}' if label in names else label for label in labels)


def answer_record(question, answer, comments):
    """(answer, editor, answered_at, evidence) for one prior question, from recorded human evidence only.

    A checkbox selection has no recorded author or time (GitHub does not say who ticked it), so both stay null.
    """
    qid = question['id']
    options = question.get('options') or []
    evidence = []
    chosen = None
    for cid in answer.get('comment_ids', []):
        comment = comments.get(cid)
        if comment is None:
            continue
        if cid == question.get('comment_id'):
            evidence.append(evidence_ref('selection', question.get('comment_url'), cid))
            picked = question['selection']
            if picked.get('state') == 'selected':
                chosen = chosen or ({'kind': 'single', 'value': picked['labels'][0]}, None, None)
        else:
            evidence.append(evidence_ref('comment', comment.get('html_url'), cid))
            if chosen is None:
                kind, value = reply_answer(reply_text(comment.get('body', ''), qid), options)
                chosen = ({'kind': kind, 'value': value}, (comment.get('user') or {}).get('login'),
                          comment.get('created_at'))
    return (chosen or (None, None, None)) + (evidence,)


def clarification_items(snapshot, analysis, outcome, round_number, batch, repo, comment_ids, spec_path, observed_at,
                        in_session=None):
    """Normalized clarification records for one validated publication. Pure: no GitHub calls, no writes.

    `in_session` maps each question key to its session answer (`{answer, answered_by, answered_at}`); those
    questions are recorded as applied, with the single `round-in-session` comment (`comment_ids['summary']`)
    as their evidence."""
    number = snapshot['issue']['number']
    comments = {c['id']: c for c in snapshot['comments']}
    items = []
    by_question = {a['question_id']: a for a in analysis.get('answers', [])}
    for qid, prior in snapshot['history']['questions'].items():
        answer = by_question[qid]
        disposition = answer['disposition']
        value, editor, answered_at, evidence = answer_record(prior, answer, comments) \
            if disposition in ('answered', 'superseded') else (None, None, None, [])
        applied = None
        if disposition == 'answered':
            state = 'applied'
            applied = {'at': observed_at, 'evidence': [spec_path + '#speckit-clarification:spec ' + batch]}
        elif disposition == 'superseded':
            state = 'superseded'
        elif outcome == 'closed':
            state = 'waived'
            evidence = [evidence_ref('closure', comment_url(repo, number, cid), cid)
                        for cid in snapshot['policy'].get('control_comment_ids', [])]
        elif prior['selection'].get('state') in ('ambiguous', 'edited'):
            state = 'conflict'
            evidence = [evidence_ref('selection', prior.get('comment_url'), prior.get('comment_id'))]
        else:
            state = 'pending'
        items.append({'source_id': qid, 'question': prior['question'], 'options': list(prior.get('options') or []),
                      'answer': value, 'state': state,
                      'url': prior.get('comment_url') or comment_url(repo, number, prior.get('comment_id')),
                      'editor': editor, 'observed_at': observed_at, 'answered_at': answered_at, 'applied': applied,
                      'evidence': evidence + [evidence_ref(
                          'disposition', explanation=(disposition + ': ' + str(answer.get('explanation', '')))[:VALUE_LIMIT])],
                      'batch': batch})
    for index, question in enumerate(analysis['questions'] if in_session else [], 1):
        given = in_session[question['key']]
        url = comment_url(repo, number, comment_ids['summary'])
        items.append({'source_id': f'C{round_number}Q{index}', 'question': question['question'],
                      'options': list(question.get('options') or []), 'answer': given['answer'], 'state': 'applied',
                      'url': url, 'editor': given['answered_by'], 'observed_at': observed_at,
                      'answered_at': given['answered_at'],
                      'applied': {'at': observed_at, 'evidence': [spec_path + '#speckit-clarification:spec ' + batch]},
                      'evidence': [evidence_ref('in-session', url, comment_ids['summary'],
                                                'answered in session by ' + given['answered_by'])],
                      'batch': batch})
    if outcome == 'waiting' and not in_session:
        for index, question in enumerate(analysis['questions'], 1):
            qid = f'C{round_number}Q{index}'
            url = comment_url(repo, number, comment_ids[qid])
            items.append({'source_id': qid, 'question': question['question'],
                          'options': list(question.get('options') or []), 'answer': None, 'state': 'pending',
                          'url': url, 'editor': None, 'observed_at': observed_at, 'answered_at': None,
                          'applied': None,
                          'evidence': [evidence_ref('comment', url, comment_ids[qid])],
                          'batch': batch})
    return items


def substance(item):
    """What identifies a revision: everything except when it was observed and which batch re-observed it."""
    value = {k: v for k, v in item.items() if k not in ('observed_at', 'batch', 'revision')}
    if value.get('applied'):
        value['applied'] = {k: v for k, v in value['applied'].items() if k != 'at'}
    return value


def merge_items(existing, fresh, batch):
    """Add this batch's records to the kept ones. A record this batch already wrote is replaced (replay); an
    unchanged record keeps its revision; a changed one becomes the next revision. Earlier revisions stay."""
    items = [dict(item) for item in existing]
    for new in fresh:
        history = [i for i, item in enumerate(items) if item['source_id'] == new['source_id']]
        latest = items[history[-1]] if history else None
        if latest and latest.get('batch') == batch:
            items[history[-1]] = dict(new, revision=latest['revision'])
        elif latest and substance(latest) == substance(new):
            continue
        else:
            items.append(dict(new, revision=(latest['revision'] + 1) if latest else 1))
    return items


def _is_link(path):
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return os.path.islink(path) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def well_formed(items):
    """True when every kept item can be merged: an object with a text `source_id` and a positive integer `revision`."""
    return isinstance(items, list) and all(
        isinstance(item, dict) and isinstance(item.get('source_id'), str) and item['source_id']
        and type(item.get('revision')) is int and item['revision'] >= 1 for item in items)


def persist_clarifications(path, fresh, batch):
    """Write `workflow/clarifications.json` atomically, keeping prior revisions."""
    path = Path(path)
    for item in (path.parent, path):
        if _is_link(item):
            raise ScopeError('CLARIFICATIONS_UNSAFE: ' + str(item) + ' is a symbolic link or reparse point; remove it '
                             'so the clarification records are not written through it.')
    current = {}
    if path.exists():
        try:
            current = read_json(path)
        except (ValueError, OSError):
            current = None
        # An existing file that is empty, `{}`, `[]`, `""` or any other unsupported shape is not a record file.
        supported = isinstance(current, dict) and current.get('v') == 1 and well_formed(current.get('items'))
        if not supported:
            current = None
    if current is None:
        # The file cannot be merged. The spec and the board have already moved, so failing here would fail
        # every rerun at the same point: keep the bytes aside and write a fresh file.
        aside = path.with_name(path.name + '.unreadable-' + batch)
        if aside.exists():
            aside = path.with_name(aside.name + '-' + uuid.uuid4().hex[:8])
        path.replace(aside)
        sys.stderr.write(f'warning: CLARIFICATIONS_UNREADABLE: moved {path} to {aside.name} and wrote a new file\n')
        current = {}
    document = {'v': 1, 'items': merge_items(current.get('items', []), fresh, batch)}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with open(temp, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(document, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)
    return document


class Clarification:
    def __init__(self, app):
        self.app = app
        self.root, self.gh = app.root, app.gh

    def source(self, value=None):
        if value:
            require(re.fullmatch(r'#?[1-9]\d*', str(value)), 'Provide a GitHub issue number; resolve spec paths through scope-source.json.')
            return self.app.resolve(str(value))
        feature = read_json(self.root / '.specify/feature.json', {})
        directory = feature.get('feature_directory', '')
        path = (self.root / directory).resolve()
        require(directory and path.is_relative_to(self.root / 'specs'), 'No bound feature. Provide a GitHub issue number.')
        binding = read_json(path / 'scope-source.json', {})
        require(binding.get('repo') == self.app.repo and binding.get('issue'), 'No source issue binding. Run Specify for a scoped Backlog issue first.')
        return self.app.issue(binding['issue'])

    def gate(self, issue):
        status = self.app.status(issue)
        if not self.app.tracks(FEATURE):
            # The board mode never writes Feature Specification or Need Clarifications, so the clarification
            # records say whether a published question still waits for its answer.
            require(issue.get('state') == 'open', 'CLARIFICATION_CLOSED: do not reopen a closed issue implicitly.')
            waiting = self.unanswered(issue)
            if waiting:
                raise ScopeError(f'CLARIFICATION_WAITING: {", ".join(waiting)} has no answer yet; tick one option per question, '
                                 'or add a normal comment such as C1Q1: A with optional feedback. Then rerun. No new questions '
                                 'were posted and no state was changed.')
            return
        from workflow_policy import load
        policy = load(self.root)
        from workflow_policy import bound_claim
        revalidation = bound_claim(self.root, self.app.repo, issue['number'], {'clarify'})
        if revalidation and status in {'Ready', 'In progress', 'In review'}:
            require(issue.get('state') == 'open', 'CLARIFICATION_CLOSED: do not reopen a closed issue implicitly.')
            return
        if status == WAITING and policy and policy.get('clarification', {}).get('resume_on_reinvoke') == 'reread-answers':
            require(issue.get('state') == 'open', 'CLARIFICATION_CLOSED: do not reopen a closed issue implicitly.')
            return
        if status != FEATURE and self.app.drop_cached_board():
            return self.gate(issue)  # a cached board may let the gate pass, never refuse it
        if status == WAITING:
            raise ScopeError(f'CLARIFICATION_WAITING: tick one option per question, or add a normal comment such as C1Q1: A with optional feedback. Then move the issue back to {self.app.actual_status(FEATURE)} and rerun. No new questions were posted and no state was changed.')
        require(status == FEATURE, f'CLARIFICATION_STATE: only {self.app.actual_status(FEATURE)} issues can be processed; #{issue["number"]} is {self.app.actual_status(status)}.')

    def unanswered(self, issue):
        """Published question IDs with no answer: with the local transport, the `C<r>Q<n>` sections of the feature's
        clarifications.md without a reply; otherwise the questions whose latest record is pending and that have no
        selected box and no reply from a trusted commenter."""
        feature, state = self.checkpoint(issue)
        if state.get('clarification_transport') == 'local':
            from workflow_policy import _decisions_module
            path = self.root / feature / 'clarifications.md'
            sections = _decisions_module().local_sections(path.read_text(encoding='utf-8-sig') if path.is_file() else '')
            return [qid for qid, section in sections.items()
                    if qid.startswith('C') and not (section['ticked'] or section['answers'])]
        latest = {}
        for item in read_json(self.root / feature / CLARIFICATIONS_FILE, {}).get('items', []) if feature else []:
            latest[item['source_id']] = item
        pending = [qid for qid, item in latest.items() if item.get('state') == 'pending']
        if not pending:
            return []
        comments = self.gh.api(f'{self.app.base}/{issue["number"]}/comments?per_page=100', pages=True)
        prior = history(comments, issue['user']['login'], self.own_comment_ids(issue['number'], comments))
        return [qid for qid in pending if not (
            (prior['questions'].get(qid) or {}).get('selection', {}).get('state') == 'selected'
            or prior['reply_candidates'].get(qid))]

    def own_comment_ids(self, number, comments):
        """The comments this runtime posted on issue `number`: the ids its publication journals and the shared
        posted-comments log recorded, plus bot comments by the account gh is signed in as (asked only when a bot
        record is not logged). Another bot's or app's record is never the runtime's own."""
        import sanduq_gh
        own = set(sanduq_gh.posted_comment_ids(self.root))
        for journal in (self.root / '.specify/scope/clarifications').glob(f'{number}-*/journal.json'):
            own.update((read_json(journal, {}) or {}).get('comments', {}).values())
        unknown = [c for c in comments if record(c) and c['id'] not in own and c.get('user', {}).get('type') == 'Bot']
        if unknown:
            try:
                login = ((self.gh.api('user') or {}).get('login') or '').casefold()
            except ScopeError:
                login = ''  # an app token cannot read /user: only the logged ids count
            own.update(c['id'] for c in unknown if login and c.get('user', {}).get('login', '').casefold() == login)
        return own

    def spec_path(self, issue):
        matches = []
        for binding in (self.root / 'specs').glob('*/scope-source.json'):
            value = read_json(binding, {})
            if value.get('issue') == issue['number'] and value.get('repo') == self.app.repo:
                path = (binding.parent / 'spec.md').resolve()
                require(path.is_relative_to(self.root / 'specs') and path.is_file(), 'Bound specification is missing or outside specs/.')
                matches.append(path)
        require(len(matches) == 1, f'Expected one bound specification for #{issue["number"]}; found {len(matches)}. Run Specify or resolve duplicate bindings.')
        return matches[0]

    def checkpoint(self, issue):
        """(feature label, workflow checkpoint) of the feature bound to `issue`; ('', {}) when none is bound or the
        run is unmanaged. Never raises: the state gate decides what a missing binding means."""
        for binding in (self.root / 'specs').glob('*/scope-source.json'):
            value = read_json(binding, {})
            if value.get('issue') == issue['number'] and value.get('repo') == self.app.repo:
                return binding.parent.relative_to(self.root).as_posix(), read_json(binding.parent / 'workflow/checkpoint.json', {})
        return '', {}

    def refuse_local(self, issue):
        """REQ-21: a feature whose checkpoint froze `clarification_transport: local` never posts to GitHub."""
        feature, state = self.checkpoint(issue)
        if state.get('clarification_transport') == 'local':
            raise ScopeError(f'CLARIFICATION_TRANSPORT_LOCAL: #{issue["number"]} answers clarifications in '
                             f'{feature}/clarifications.md, not on GitHub. Ask the questions in the conversation and '
                             'record the user\'s replies in that file (github-clarification skill, references/local.md); '
                             'nothing is posted or synced.')

    def engine(self):
        registry = read_json(self.root / '.specify/extensions/.registry', {}).get('extensions', {})
        enabled = registry.get('superspec', {}).get('enabled') is True
        command = self.root / '.specify/extensions/superspec/commands/brainstorm.md'
        available = any((self.root / agent / 'skills/speckit-superspec-brainstorm/SKILL.md').is_file() for agent in ('.agents', '.claude'))
        return 'brainstorm' if enabled and command.is_file() and available else 'clarify'

    def dispatch(self, value=None):
        issue = self.source(value)
        self.gate(issue)
        engine = self.engine()
        return {'issue': issue['number'], 'engine': engine,
                'command': '/speckit-superspec-brainstorm' if engine == 'brainstorm' else '/speckit-clarify'}

    def inspect(self, value=None, gate=True):
        issue = self.source(value)
        self.refuse_local(issue)
        if gate:
            self.gate(issue)  # Must precede reading the spec or comment history.
        path = self.spec_path(issue)
        comments = self.gh.api(f'{self.app.base}/{issue["number"]}/comments?per_page=100', pages=True)
        creator = issue['user']['login']
        own = self.own_comment_ids(issue['number'], comments)
        for comment in comments:
            comment['trusted'] = comment['id'] in own or trusted(comment, creator)  # false: context, never an answer
        prior = history(comments, creator, own)
        policy = controls(comments, creator)
        used = max([q['round'] for q in prior['questions'].values()] + [0] +
                   [r.get('round', 1) for r in prior['rounds'] if r['kind'] == 'round-in-session'])
        result = {'version': 1, 'issue': issue, 'creator': creator, 'spec_path': str(path.relative_to(self.root)),
                  'spec': path.read_text(encoding='utf-8-sig'), 'comments': comments, 'history': prior,
                  'policy': policy, 'next_round': used + 1, 'limit_reached': used >= policy['max_rounds'],
                  'suggested_answers': suggested_answers(prior), 'own_comment_ids': sorted(own)}
        result['snapshot_digest'] = snapshot_digest(result)
        return result

    def validate(self, snapshot, analysis, in_session=False):
        require(analysis.get('version') == 1 and analysis.get('issue') == snapshot['issue']['number'], 'Analysis must identify the current issue.')
        require(analysis.get('snapshot_digest') == snapshot['snapshot_digest'], 'CLARIFICATION_STALE: issue, answers or specification changed; reread and reevaluate.')
        require(analysis.get('engine') in {'clarify', 'brainstorm'}, 'Choose clarify or brainstorm.')
        require(isinstance(analysis.get('coverage'), dict) and analysis['coverage'], 'Supply the complete ambiguity coverage assessment.')
        require(isinstance(analysis.get('questions'), list), 'Supply all remaining questions as a list (capped only by clarification.max_questions_per_round).')
        answers = analysis.get('answers', [])
        require(isinstance(answers, list), 'answers must be a list.')
        previous = snapshot['history']['questions']
        require(len(answers) == len(previous) and {a['question_id'] for a in answers} == set(previous),
                'Reevaluate every prior question; none may be silently dropped.')
        comments = {c['id']: c for c in snapshot['comments']}
        own = set(snapshot.get('own_comment_ids', []))
        unresolved = []
        for answer in answers:
            require(answer.get('disposition') in {'answered', 'superseded', 'unresolved'}, 'Unknown answer disposition.')
            require(answer.get('explanation'), 'Explain how each answer resolves or leaves the question open.')
            if answer['disposition'] in {'answered', 'superseded'}:
                ids = answer.get('comment_ids', [])
                def evidence(comment):
                    item = record(comment)
                    if item:
                        return (item['kind'] == 'question' and (item['id'] == answer['question_id'] or
                                (item['id'] in previous and answer['question_id'] in item.get('follows_up', [])
                                 and previous[answer['question_id']].get('round', 0) < item.get('round', 0)))
                                and selection(comment, item)['state'] == 'selected'
                                and (trusted(comment, snapshot['creator']) or comment['id'] in own))
                    return trusted(comment, snapshot['creator']) and plain_lines(comment['body'])
                require(ids and all(i in comments and evidence(comments[i]) for i in ids),
                        'An accepted answer needs actual human comment evidence, not an AI recommendation.')
                candidates = {c['id'] for c in snapshot['history']['reply_candidates'][answer['question_id']]}
                require(set(ids) <= candidates, 'Answer evidence must reference this question by ID, link or Quote reply; ask a follow-up for ambiguous replies.')
            if answer['disposition'] == 'unresolved':
                unresolved.append(answer['question_id'])
        keys = set()
        for question in analysis['questions']:
            require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', question.get('key', '')) and question['key'] not in keys, 'Question keys must be unique stable slugs.')
            keys.add(question['key'])
            for field in ('question', 'why', 'recommendation', 'justification', 'details'):
                require(isinstance(question.get(field), str) and question[field].strip(), f'Question missing {field}.')
            require(question['question'].rstrip().endswith('?'), 'Each question must be a complete interrogative ending with ?. ')
            require(isinstance(question.get('options', []), list), 'Question options must be a list.')
            require(set(question.get('follows_up', [])) <= set(previous), 'Unknown follow-up question ID.')
            require(all(isinstance(x, str) and x.strip() for x in question.get('options', [])), 'Each option needs a complete description.')
            if question.get('options'):
                recommended = question.get('recommended_option')
                require(type(recommended) is int and 1 <= recommended <= len(question['options']),
                        'Supply recommended_option as the 1-based index of the recommended choice.')
                require(all('\n' not in x and '\r' not in x and '**(Recommended)**' not in x for x in question['options']),
                        'Keep each option on one line; the runtime adds the Recommended suffix.')
            if question.get('diagram'):
                require('```' not in question['diagram'], 'Supply Mermaid source without code fences.')
            if 'diagram_image' in question:
                image = question['diagram_image']
                require(isinstance(image, dict) and all(isinstance(image.get(k), str) and image[k].strip() for k in ('path', 'alt')),
                        'diagram_image needs the project-relative path of an exported Illustrate PNG and its alt text.')
                require(isinstance(question.get('diagram_text'), str) and question['diagram_text'].strip(),
                        'diagram_image needs diagram_text: the text version (for example a dependency list) used when the image cannot be hosted.')
            if 'priority' in question:
                require(type(question['priority']) is int and question['priority'] >= 1,
                        'Question priority must be a positive integer; 1 is the most important.')
        from workflow_policy import setting
        cap = setting(self.root, 'clarification', 'max_questions_per_round')
        if cap is not None and len(analysis['questions']) > cap:
            # 1 is the most important; a question without a priority is the least important; ties defer the later one.
            ranked = sorted(enumerate(analysis['questions']), key=lambda q: (q[1].get('priority', float('inf')), q[0]))
            raise ScopeError(f'CLARIFICATION_TOO_MANY_QUESTIONS: {len(analysis["questions"])} > {cap}; defer '
                             + ', '.join(q['key'] for _, q in ranked[cap:]))
        followups = {qid for q in analysis['questions'] for qid in q.get('follows_up', [])}
        if unresolved and not snapshot['limit_reached'] and not snapshot['policy']['closed']:
            require(set(unresolved) <= followups, 'Every unresolved prior question needs a precise follow-up question.')
        # OMAR-12: every spec edit cites the questions whose trusted answers justify it. Answered and superseded
        # dispositions were checked above for human evidence; a creator closure vouches for the questions it waives;
        # in session, the answers file is the evidence (checked by publish_in_session) for this round's C1Q<n>.
        if in_session:
            citable = {f'C1Q{i}' for i in range(1, len(analysis['questions']) + 1)}
        else:
            citable = {a['question_id'] for a in answers if a['disposition'] in {'answered', 'superseded'}}
            if snapshot['policy']['closed']:
                citable |= set(previous)
        for index, edit in enumerate(analysis.get('spec_edits') or [], 1):
            cited = edit.get('question_ids') if isinstance(edit, dict) else None
            bad = sorted(set(cited) - citable) if isinstance(cited, list) and all(isinstance(q, str) for q in cited) else None
            if not cited or bad is None or bad:
                raise ScopeError(f'CLARIFICATION_EDIT_UNTRUSTED: spec edit {index} must cite question_ids whose answers are '
                                 "trusted (answered or superseded with a trusted human comment, or waived by the creator's "
                                 'closure)' + (f'; not trusted: {", ".join(bad)}' if bad else '; it cites none')
                                 + '. Untrusted comments are context only; ask a follow-up question instead.')
        if snapshot['policy']['closed']:
            outcome = 'closed'
        elif analysis['questions'] or unresolved:
            outcome = 'limit' if snapshot['limit_reached'] else 'waiting'
        else:
            outcome = 'ready'
        if outcome in {'ready', 'closed'}:
            require(analysis.get('summary'), 'Provide a completion summary and document any explicitly waived uncertainty.')
        return outcome

    def transition(self, issue, status):
        # Keep live board and local no-regress cache in step.
        self.app.set_status(issue, status)
        if self.app.board_mode == 'off':
            return  # no board, no Project Sync state
        path = self.root / self.app.cfg['stateFile']
        state = read_json(path, {})
        for item in state.values():
            if item.get('issue') == issue['number']:
                item['status'] = self.app.actual_status(status)
        if state:
            write_json(path, state)

    def finishing_transition(self, issue, folder, journal, batch):
        """True when an earlier run moved the board for this batch and stopped before it finished.

        The journal is validated first: it must belong to this batch, keep its snapshot and analysis, and
        match the spec on disk. Only then may the retry skip the new-publication status gate.
        """
        if not journal or journal.get('complete') or not journal.get('transitioning'):
            return False
        self.app._board = None
        if self.app.status(issue) != journal['transitioning']:
            return False  # the board never moved (or moved elsewhere): the normal path applies
        stored = read_json(folder / 'analysis.json')
        require(journal.get('batch') == batch and (folder / 'snapshot.json').is_file() and stored
                and digest(stored)[:20] == batch and isinstance(journal.get('comments'), dict)
                and 'summary' in journal['comments'],
                'CLARIFICATION_JOURNAL_INVALID: the unfinished publication ' + batch + ' cannot be verified; inspect ' + str(folder))
        require(self.spec_path(issue).read_text(encoding='utf-8-sig') == journal.get('expected_spec'),
                'CLARIFICATION_JOURNAL_INVALID: the specification no longer matches the unfinished publication ' + batch)
        return True

    def finish_publication(self, value, folder, journal, batch, analysis, apply):
        """Repair an unfinished publication: the comments are posted, the spec replaced and the board moved.

        Nothing is posted or moved, so the live thread is not compared with the baseline: a human reply that
        arrived after the crash must not block the repair. The records come from the stored snapshot and
        analysis plus the journaled comment ids; each journaled comment must still exist.
        """
        snapshot = read_json(folder / 'snapshot.json')
        number = snapshot['issue']['number']
        outcome = self.validate(snapshot, analysis)
        status = WAITING if outcome in {'waiting', 'limit'} else 'Ready'
        result = {'issue': number, 'outcome': outcome, 'round': snapshot['next_round'], 'status': status,
                  'dry_run': not apply, 'batch': batch, 'unfinished': True}
        if not apply:
            return dict(result, reason='An earlier publication of this batch is unfinished: the comments are posted and the board '
                        'moved, but the records are missing. Rerun with --apply to repair them; nothing is posted again.')
        existing = {c['id'] for c in self.gh.api(f'{self.app.base}/{number}/comments?per_page=100', pages=True)}
        missing = sorted(str(i) for i in journal['comments'].values() if i not in existing)
        require(not missing, 'CLARIFICATION_JOURNAL_INVALID: journaled comments no longer exist: ' + ', '.join(missing))
        persist_clarifications(self.root / Path(snapshot['spec_path']).parent / CLARIFICATIONS_FILE,
                               clarification_items(snapshot, analysis, outcome, snapshot['next_round'], batch, self.app.repo,
                                                   journal['comments'], Path(snapshot['spec_path']).as_posix(),
                                                   datetime.now(timezone.utc).isoformat()), batch)
        journal['complete'] = True
        write_json(folder / 'journal.json', journal)
        from workflow_policy import load
        managed = load(self.root)
        if managed and managed.get('clarification', {}).get('resume_on_reinvoke') == 'reread-answers' and status == WAITING:
            # The digest of the exact input this repair processed, in the live thread's order: the stored
            # snapshot's version of each comment it held and the journaled posts as published. A comment that
            # arrived after the crash is left out, and an edit to any processed comment changes the next digest.
            live = self.inspect(value, gate=False)
            stored = {c['id']: c for c in snapshot['comments']}
            published = {v['id']: v for v in journal.get('published', {}).values()}
            ours = set(journal['comments'].values())
            processed = dict(live, issue=snapshot['issue'], comments=[
                stored.get(c['id']) or (published.get(c['id']) or c) for c in live['comments']
                if c['id'] in stored or c['id'] in ours])
            write_json(self.root / '.specify/scope/clarifications' / f'{number}-observed.json',
                       {'waiting_digest': snapshot_digest(processed)})
        result = dict(result, comment_ids=journal['comments'], next_action=None)
        resolved = not analysis['questions'] and all(a['disposition'] != 'unresolved' for a in analysis.get('answers', []))
        if status == 'Ready' and resolved:
            self.app._board = None
            self.ready_gate(number)
            path = self.root / snapshot['spec_path']
            result['next_action'] = {'command': '/speckit-plan', 'issue': number, 'spec_path': str(path.resolve()),
                                     'feature_directory': str(path.parent.relative_to(self.root)),
                                     'feature_name': path.parent.name}
        return result

    def publish(self, value, analysis, apply=False, answers=None):
        if answers is not None:
            return self.publish_in_session(value, analysis, answers, apply)
        batch = digest(analysis)[:20]
        source = self.source(value)
        self.refuse_local(source)
        folder = self.root / '.specify/scope/clarifications' / f'{source["number"]}-{batch}'
        journal_path = folder / 'journal.json'
        journal = read_json(journal_path)
        finishing = self.finishing_transition(source, folder, journal, batch)
        if finishing:
            return self.finish_publication(value, folder, journal, batch, analysis, apply)
        snapshot = self.inspect(value)
        from workflow_policy import load
        managed_policy = load(self.root)
        automatic_resume = bool(managed_policy and managed_policy.get('clarification', {}).get('resume_on_reinvoke') == 'reread-answers')
        observed_path = self.root / '.specify/scope/clarifications' / f'{snapshot["issue"]["number"]}-observed.json'
        observed = read_json(observed_path, {})
        if automatic_resume and observed.get('waiting_digest') == snapshot['snapshot_digest']:
            return {'issue': snapshot['issue']['number'], 'outcome': 'waiting', 'questions': 0,
                    'unchanged': True, 'dry_run': not apply, 'next_action': None,
                    'reason': 'No new answers or material input changes; no comments posted.'}
        if journal:
            baseline = read_json(folder / 'snapshot.json')
            normalized_spec = baseline['spec'] if snapshot['spec'] == journal.get('expected_spec') else snapshot['spec']
            require(snapshot_digest(snapshot, batch, normalized_spec) == baseline['snapshot_digest'],
                    'CLARIFICATION_STALE: new human input arrived during publication; reread before resuming.')
            baseline['comments'] = [c for c in snapshot['comments'] if not (record(c) and record(c).get('batch') == batch)]
            snapshot = baseline
        outcome = self.validate(snapshot, analysis)
        number, creator = snapshot['issue']['number'], snapshot['creator']
        round_number = snapshot['next_round']
        questions = analysis['questions'] if outcome == 'waiting' else []
        prepared, image_fallbacks = [], {}
        for index, question in enumerate(questions, 1):
            qid = f'C{round_number}Q{index}'
            meta = {'version': 1, 'id': qid, 'key': question['key'], 'round': round_number, 'batch': batch,
                    'engine': analysis['engine'], 'question': question['question'], 'follows_up': question.get('follows_up', []),
                    'choice_format': 1, 'options': question.get('options', []), 'recommended_option': question.get('recommended_option')}
            body = f'### {qid}: {question["question"]}\n\n@{creator}\n\n**Why this matters:** {question["why"]}\n\n'
            if question.get('options'):
                body += '**Choose one:**\n\n<!-- speckit-clarification:choices:start -->\n'
                body += '\n'.join(choice_lines(question['options'], question['recommended_option']))
                body += '\n<!-- speckit-clarification:choices:end -->\n\n'
                label = option_label(question['recommended_option'])
                body += f'**AI recommendation: {label} — {question["recommendation"]}**\n\n'
                body += f'**Why I recommend it:** {question["justification"]}\n\n'
                body += f'**Answer:** Tick one checkbox above, or add a normal comment: `{qid}: {label}`. Nothing is selected for you.\n\n'
            else:
                body += f'**AI recommendation: {question["recommendation"]}**\n\n**Why I recommend it:** {question["justification"]}\n\n'
                body += f'**Answer:** Add a normal comment: `{qid}: your answer`.\n\n'
            body += f'**Optional feedback or another answer:** `{qid}: your choice — your feedback`. You can answer several questions in one comment, one question ID per line. No Quote reply is needed.\n\n'
            has_diagram = any(question.get(k) for k in ('diagram', 'diagram_image', 'diagram_markdown'))
            body += '<details>\n<summary>More context' + (' and diagram' if has_diagram else '') + '</summary>\n\n' + question['details'] + '\n'
            if question.get('diagram'):
                body += '\n```mermaid\n' + question['diagram'].strip() + '\n```\n'
            if question.get('diagram_image'):
                section, reason = diagram_section(self.root, self.app.repo, self.gh, question)
                body += section
                if reason:
                    image_fallbacks[qid] = reason
            if question.get('diagram_markdown'):
                # Pre-1.6.0 analyses: still rendered, but only with an https image that private readers can load.
                require(re.search(r'!\[[^\]]*\]\(https://[^\s)]+\)', question['diagram_markdown'])
                        and 'raw.githubusercontent.com' not in question['diagram_markdown'],
                        'INLINE_IMAGE_REQUIRED: diagram_markdown needs an https image that is not a raw.githubusercontent.com URL; prefer diagram_image.')
                body += '\n' + question['diagram_markdown'].strip() + '\n'
            body += '\n</details>\n\nAfter answering the questions, move this issue to **Feature Specification** and rerun Clarify or Brainstorm.\n'
            if automatic_resume:
                body = body.replace('move this issue to **Feature Specification** and rerun', 'rerun')
            body = managed_comment('question', meta, body)
            require(len(body) <= 65000, f'{qid} exceeds GitHub\'s comment size; simplify this question\'s supporting material.')
            prepared.append((qid, body))
        spec = apply_edits(snapshot['spec'], analysis.get('spec_edits', []))
        log = '\n\n<!-- speckit-clarification:spec ' + batch + ' -->\n'
        log += f'### GitHub clarification review {round_number}\n\n'
        thread = {c['id']: c for c in snapshot['comments']}
        for answer in analysis.get('answers', []):
            links = ', '.join(f'https://github.com/{self.app.repo}/issues/{number}#issuecomment-{i}' for i in answer.get('comment_ids', []))
            log += f'- {answer["question_id"]}: {answer["disposition"]}. {answer["explanation"]}' + (f' Evidence: {links}' if links else '') + '\n'
            asked = snapshot['history']['questions'][answer['question_id']]
            log += f'  Q: {asked["question"]} → A: {answer_text(asked, answer, thread)}\n'
            choice = asked.get('selection', {})
            if choice.get('state') == 'selected':
                log += f'  Checkbox selection observed: {choice["labels"][0]} — {choice["options"][0]}.\n'
        if outcome == 'closed':
            log += '- The issue creator explicitly closed clarification. Outstanding decisions below are waived, not answered.\n'
            log += analysis['summary'] + '\n'
        elif outcome == 'limit':
            log += '- The question-round limit was reached. Unresolved decisions remain open.\n'
        spec += log
        summary = {'version': 1, 'round': round_number if questions else max(round_number - 1, 0), 'batch': batch,
                   'engine': analysis['engine'], 'outcome': outcome, 'question_ids': [q[0] for q in prepared],
                   'answers': analysis.get('answers', []), 'policy': snapshot['policy']}
        from workflow_policy import setting
        if setting(self.root, 'clarification', 'max_questions_per_round') is not None:
            summary['max_questions_per_round'] = setting(self.root, 'clarification', 'max_questions_per_round')
        summary_body = f'### Clarification review: {outcome}\n\n' + analysis.get('summary', 'Questions need your answers before implementation can be planned.') + '\n\n'
        if outcome == 'waiting':
            summary_body += f'Posted {len(prepared)} separate questions in round {round_number}.' + (
                '' if 'max_questions_per_round' in summary else ' There is no question-count cap.') + '\n\n'
        if outcome in {'waiting', 'limit'}:
            summary_body += f'The question-round limit is {snapshot["policy"]["max_rounds"]}. The issue creator can post `/clarification max-rounds N` to change it, or `/clarification close` to close the process explicitly. Answer the questions, then move the issue to **Feature Specification** before rerunning.\n'
        if outcome == 'closed':
            summary_body += 'The creator closed clarification explicitly. Any unresolved decisions are recorded as waived, not answered.\n'
        if automatic_resume:
            summary_body = summary_body.replace('Answer the questions, then move the issue to **Feature Specification** before rerunning.', 'Answer the questions, then rerun Clarify or Brainstorm. The workflow rereads your answers without a manual board move.')
        summary_body = managed_comment('round', summary, summary_body)
        require(len(summary_body) <= 65000, 'Round audit exceeds comment size; shorten explanations while preserving the answer references.')
        result = {'issue': number, 'outcome': outcome, 'round': round_number, 'questions': len(prepared),
                  'status': WAITING if outcome in {'waiting', 'limit'} else 'Ready', 'dry_run': not apply, 'batch': batch}
        if image_fallbacks:
            result['image_fallbacks'] = image_fallbacks
        if not apply:
            return dict(result, comment_previews=[body for _, body in prepared], summary_preview=summary_body)
        if not journal:
            write_json(folder / 'snapshot.json', snapshot)
            write_json(folder / 'analysis.json', analysis)
            journal = {'batch': batch, 'expected_spec': spec, 'comments': {}}
            write_json(journal_path, journal)
        # Detect new answers before writes; own retry comments are excluded.
        fresh = self.inspect(value)
        normalized_spec = snapshot['spec'] if fresh['spec'] == journal['expected_spec'] else fresh['spec']
        require(snapshot_digest(fresh, batch, normalized_spec) == snapshot['snapshot_digest'], 'CLARIFICATION_STALE: discussion changed before posting.')
        for index, (qid, body) in enumerate(prepared + [('summary', summary_body)]):
            # Reread between writes for a recoverable lost HTTP response; the first post uses the thread just read.
            existing = fresh['comments'] if index == 0 else self.gh.api(f'{self.app.base}/{number}/comments?per_page=100', pages=True)
            current_thread = dict(snapshot, comments=existing)
            require(snapshot_digest(current_thread, batch) == snapshot['snapshot_digest'],
                    'CLARIFICATION_STALE: new human input arrived while posting. Reread and reevaluate before continuing.')
            matches = [c for c in existing if record(c) and record(c).get('batch') == batch and
                       ((qid == 'summary' and record(c)['kind'] == 'round') or record(c).get('id') == qid)]
            require(len(matches) <= 1, f'Duplicate published comment for {qid}; reconcile before proceeding.')
            posted = matches[0] if matches else self.gh.api(f'{self.app.base}/{number}/comments', 'POST', {'body': body})
            journal['comments'][qid] = posted['id']
            # The version published now, so a repair can digest what was processed, not what was edited later.
            journal.setdefault('published', {})[qid] = {k: posted.get(k) for k in ('id', 'body', 'updated_at', 'user')}
            write_json(journal_path, journal)
        path = self.root / snapshot['spec_path']
        self.app._board = None
        final_snapshot = self.inspect(value)
        normalized_spec = snapshot['spec'] if final_snapshot['spec'] == journal['expected_spec'] else final_snapshot['spec']
        require(snapshot_digest(final_snapshot, batch, normalized_spec) == snapshot['snapshot_digest'],
                'CLARIFICATION_STALE: issue, answers or spec changed while posting. Reevaluate before changing state.')
        current = path.read_text(encoding='utf-8-sig')
        require(current in {snapshot['spec'], journal['expected_spec']}, 'Specification changed while posting; retain the journal and reconcile before changing state.')
        if current != spec:
            temporary = path.with_suffix('.clarification.tmp')
            temporary.write_text(spec, encoding='utf-8')
            temporary.replace(path)
        # final_snapshot read the issue and the live board just now; only the local spec changed since.
        issue = final_snapshot['issue']
        self.gate(issue)
        # Recorded before the move, so a retry can tell an unfinished publication from a new one.
        journal['transitioning'] = result['status']
        write_json(journal_path, journal)
        self.transition(issue, result['status'])
        # Only now: the spec is replaced and the transition succeeded. Written before the journal is marked
        # complete, so an interrupted publication repairs the file when it is rerun.
        persist_clarifications(self.root / Path(snapshot['spec_path']).parent / CLARIFICATIONS_FILE,
                               clarification_items(snapshot, analysis, outcome, round_number, batch, self.app.repo,
                                                   journal['comments'], Path(snapshot['spec_path']).as_posix(),
                                                   datetime.now(timezone.utc).isoformat()), batch)
        journal['complete'] = True
        write_json(journal_path, journal)
        if automatic_resume and result['status'] == WAITING:
            write_json(observed_path, {'waiting_digest': self.inspect(value, gate=False)['snapshot_digest']})
        result = dict(result, comment_ids=journal['comments'], next_action=None)
        # Only a successfully published, fully resolved review hands off to Plan.
        # A creator waiver can close the process without resolving its uncertainty.
        resolved = not analysis['questions'] and all(a['disposition'] != 'unresolved' for a in analysis.get('answers', []))
        if result['status'] == 'Ready' and resolved:
            self.app._board = None
            self.ready_gate(number)
            result['next_action'] = {'command': '/speckit-plan', 'issue': number,
                                     'spec_path': str(path.resolve()),
                                     'feature_directory': str(path.parent.relative_to(self.root)),
                                     'feature_name': path.parent.name}
        return result

    def session_answers(self, analysis, answers, creator):
        """`{key: {answer, answered_by, answered_at, shown}}` for every question, from the creator signed in to gh."""
        questions = {q['key']: q for q in analysis['questions']}
        require(isinstance(answers, list) and all(isinstance(a, dict) for a in answers),
                'CLARIFICATION_ANSWERS_INVALID: answers must be a list of {key, option | answer, answered_by, answered_at}.')
        given = {}
        for item in answers:
            key = item.get('key')
            require(key in questions and key not in given, f'CLARIFICATION_ANSWERS_INVALID: unknown or repeated question key {key!r}.')
            options = questions[key].get('options') or []
            require(('option' in item) != ('answer' in item), f'CLARIFICATION_ANSWERS_INVALID: {key} needs exactly one of option or answer.')
            if 'option' in item:
                require(type(item['option']) is int and 1 <= item['option'] <= len(options),
                        f'CLARIFICATION_ANSWERS_INVALID: {key} option must be the 1-based index of one of its options.')
                answer = {'kind': 'single', 'value': option_label(item['option'])}
                shown = f'**{answer["value"]}.** {options[item["option"] - 1]}'
            else:
                require(isinstance(item['answer'], str) and item['answer'].strip() and len(item['answer']) <= VALUE_LIMIT,
                        f'CLARIFICATION_ANSWERS_INVALID: {key} answer must be nonempty text of at most {VALUE_LIMIT} characters.')
                answer = {'kind': 'text', 'value': item['answer'].strip()}
                shown = answer['value']
            try:
                datetime.fromisoformat(str(item.get('answered_at')).replace('Z', '+00:00'))
            except ValueError:
                raise ScopeError(f'CLARIFICATION_ANSWERS_INVALID: {key} answered_at must be an ISO 8601 time.')
            require(isinstance(item.get('answered_by'), str), f'CLARIFICATION_ANSWERS_INVALID: {key} needs answered_by.')
            given[key] = {'answer': answer, 'answered_by': item['answered_by'], 'answered_at': item['answered_at'], 'shown': shown}
        missing = [key for key in questions if key not in given]
        require(not missing, 'CLARIFICATION_IN_SESSION_UNANSWERED: every question needs an answer; missing ' + ', '.join(missing))
        viewer = (self.gh.api('user') or {}).get('login') or ''
        others = sorted({a['answered_by'] for a in given.values() if a['answered_by'].casefold() != creator.casefold()})
        require(not others and viewer.casefold() == creator.casefold(),
                f'CLARIFICATION_IN_SESSION_IDENTITY: answers must come from the issue creator @{creator}, signed in to gh '
                f'(answered_by: {", ".join(others) or creator}; gh user: {viewer or "unknown"}).')
        return given

    def publish_in_session(self, value, analysis, answers, apply=False):
        """Round 1 answered in the session: one `round-in-session` comment, the spec edits, applied records, Ready."""
        from workflow_policy import setting
        require(setting(self.root, 'clarification', 'in_session_first_round', False) is True,
                'CLARIFICATION_IN_SESSION_DISABLED: set clarification.in_session_first_round: true in .specify/workflow.yml '
                'to answer the first round in the session, or publish the questions without --answers.')
        batch = digest(analysis)[:20]
        live = self.inspect(value)
        number = live['issue']['number']
        folder = self.root / '.specify/scope/clarifications' / f'{number}-{batch}'
        # A rerun of an interrupted apply validates against the stored baseline, not the thread with our own comment.
        snapshot = read_json(folder / 'snapshot.json') or live
        require(snapshot['next_round'] == 1, f'CLARIFICATION_IN_SESSION_ROUND: only round 1 can be answered in the session; '
                f'#{number} is at round {snapshot["next_round"]}. Publish the questions without --answers.')
        outcome = self.validate(snapshot, analysis, in_session=True)
        require(outcome == 'waiting', f'CLARIFICATION_IN_SESSION_STATE: in-session answers need open questions and an open '
                f'clarification process (outcome {outcome}); publish without --answers.')
        creator = snapshot['creator']
        given = self.session_answers(analysis, answers, creator)
        ids = {q['key']: f'C1Q{i}' for i, q in enumerate(analysis['questions'], 1)}
        spec = apply_edits(snapshot['spec'], analysis.get('spec_edits', []))
        spec += f'\n\n<!-- speckit-clarification:spec {batch} -->\n### GitHub clarification review 1\n\n'
        content = (f'### Clarification round 1: answered in session\n\n{analysis.get("summary", "")}\n\n@{creator} answered '
                   'these questions in the session. The specification is updated and the issue moves to **Ready**.\n\n')
        for question in analysis['questions']:
            a, qid = given[question['key']], ids[question['key']]
            spec += f'- {qid} ({question["key"]}): {a["shown"]}\n  Answered in session by @{a["answered_by"]} at {a["answered_at"]}.\n'
            content += (f'#### {qid}: {question["question"]}\n\n**Answer:** {a["shown"]}\n\n'
                        f'**Answered by:** @{a["answered_by"]} at {a["answered_at"]}\n\n')
        for a in given.values():
            del a['shown']
        meta = {'version': 1, 'round': 1, 'batch': batch, 'engine': analysis['engine'], 'outcome': 'ready',
                'question_ids': list(ids.values()), 'answers': [dict(given[k], id=ids[k], key=k) for k in ids],
                'policy': snapshot['policy']}
        body = managed_comment('round-in-session', meta, content)
        require(len(body) <= 65000, 'The in-session round exceeds GitHub\'s comment size; shorten the summary or answers.')
        if snapshot is not live:
            current = snapshot['spec'] if live['spec'] == spec else live['spec']
            require(snapshot_digest(live, batch, current) == snapshot['snapshot_digest'],
                    'CLARIFICATION_STALE: issue, comments or specification changed since the interrupted publication; reread and reevaluate.')
        result = {'issue': number, 'outcome': 'ready', 'round': 1, 'questions': len(ids), 'status': 'Ready',
                  'dry_run': not apply, 'batch': batch, 'in_session': True}
        if not apply:
            return dict(result, comment_preview=body)
        if snapshot is live:
            write_json(folder / 'snapshot.json', snapshot)
        thread = self.gh.api(f'{self.app.base}/{number}/comments?per_page=100', pages=True)
        mine = [c for c in thread if (record(c) or {}).get('kind') == 'round-in-session' and record(c).get('batch') == batch]
        require(len(mine) <= 1, 'Duplicate in-session round comment; reconcile before proceeding.')
        posted = mine[0] if mine else self.gh.api(f'{self.app.base}/{number}/comments', 'POST', {'body': body})
        path = self.root / snapshot['spec_path']
        current = path.read_text(encoding='utf-8-sig')
        require(current in {snapshot['spec'], spec}, 'CLARIFICATION_STALE: the specification changed while publishing; reconcile it and rerun.')
        if current != spec:
            temporary = path.with_suffix('.clarification.tmp')
            temporary.write_text(spec, encoding='utf-8')
            temporary.replace(path)
        # Records before the move: a rerun after an interrupted move replaces them (same batch) and finishes.
        persist_clarifications(path.parent / CLARIFICATIONS_FILE,
                               clarification_items(snapshot, analysis, 'ready', 1, batch, self.app.repo, {'summary': posted['id']},
                                                   Path(snapshot['spec_path']).as_posix(), datetime.now(timezone.utc).isoformat(),
                                                   in_session=given), batch)
        self.app._board = None
        issue = self.app.issue(number)
        self.gate(issue)
        self.transition(issue, 'Ready')
        self.ready_gate(number)
        return dict(result, comment_ids={'summary': posted['id']},
                    next_action={'command': '/speckit-plan', 'issue': number, 'spec_path': str(path.resolve()),
                                 'feature_directory': str(path.parent.relative_to(self.root)), 'feature_name': path.parent.name})

    def ready_gate(self, number):
        """The plan gate right after the move to Ready; without a Ready column the later Clarify receipt is the gate."""
        if self.app.tracks('Ready'):
            self.plan_gate(str(number))

    def plan_gate(self, value=None):
        issue = self.source(value)
        feature, state = self.checkpoint(issue)
        if state.get('clarification_transport') == 'local' or not self.app.tracks('Ready'):
            # Nothing moved the board: the passed Clarify receipt (every question answered) is the gate.
            where = (('this feature records its questions and the user\'s replies in ' + feature +
                      '/clarifications.md (local transport)') if state.get('clarification_transport') == 'local' else
                     'project_sync.mode ' + self.app.board_mode + ' never moves the issue to Ready, so the Clarify '
                     'receipt is the record')
            require(state.get('receipts', {}).get('clarify', {}).get('outcome') == 'passed',
                    'CLARIFICATION_REQUIRED: planning needs a passed Clarify receipt; ' + where + '. '
                    'Complete the Clarify stage first.')
            return {'issue': issue['number'], 'status': self.app.actual_status(self.app.status(issue)), 'transport': 'local'}
        status = self.app.status(issue)
        from workflow_policy import bound_claim
        revalidation = bound_claim(self.root, self.app.repo, issue['number'], {'plan'})
        previous = (revalidation or {}).get('state', {}).get('receipts', {}).get('clarify', {})
        continued = revalidation and issue.get('state') == 'open' and status in {'In progress', 'In review'} and previous.get('outcome') == 'passed' and previous.get('unresolved') == 0 and previous.get('answers_applied') is True
        if not (status == 'Ready' or continued) and self.app.drop_cached_board():
            return self.plan_gate(value)
        require(status == 'Ready' or continued, 'CLARIFICATION_REQUIRED: planning requires Ready or a matching managed revalidation with resolved clarification. Finish GitHub clarification first.')
        return {'issue': issue['number'], 'status': self.app.actual_status(status), 'revalidation': bool(continued)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'dispatch', 'publish', 'plan-gate'])
    parser.add_argument('issue', nargs='?')
    parser.add_argument('--root', default='.')
    parser.add_argument('--analysis', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--answers', type=Path, help='publish only: the in-session answers for round 1')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    lock = ExitStack()
    try:
        app = Clarification(Scope(args.root))
        if args.apply:
            lock.enter_context(mutation_lock(app.root, 'Another Scope/clarification mutation is running'))
        if args.command == 'publish':
            require(args.analysis and args.analysis.is_file(), 'Provide --analysis <review.json>.')
            require(not args.answers or args.answers.is_file(), 'Provide --answers <answers.json>.')
            result = app.publish(args.issue, read_json(args.analysis), args.apply,
                                 read_json(args.answers) if args.answers else None)
        else:
            result = getattr(app, args.command.replace('-', '_'))(args.issue)
        if args.output:
            write_json(args.output, result)
            shown = {'output': str(args.output), 'issue': result.get('issue', {}).get('number') if isinstance(result.get('issue'), dict) else result.get('issue')}
            if args.command == 'inspect':
                # What the analysis copies or checks first, so a zero-question round needs no read of the snapshot.
                shown.update(snapshot_digest=result['snapshot_digest'], round=result['next_round'],
                             prior_questions=len(result['history']['questions']), comments=len(result['comments']),
                             suggested_answers=len(result['suggested_answers']),
                             # trusted comments that answer no recorded question: a requirement change may sit there
                             unmatched_comments=len(result['history']['unmatched_comments']))
            print(json.dumps(with_transport(shown, app.gh), ensure_ascii=True))
        else:
            print(json.dumps(with_transport(result, app.gh), indent=2, ensure_ascii=True))
        return 0
    except (ScopeError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        lock.close()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
