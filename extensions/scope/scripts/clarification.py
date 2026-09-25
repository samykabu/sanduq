#!/usr/bin/env python3
"""Shared unattended GitHub clarification rounds for Clarify and Superspec Brainstorm."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from scope import Scope, ScopeError, require, read_json, write_json, with_transport

FEATURE, WAITING = 'Feature Specification', 'Need Clarifications'
RECORD = re.compile(r'\A<!-- speckit-clarification:(question|round) (\{[^\n]*\}) -->\n')


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


def history(comments, creator):
    questions, rounds = {}, []
    for comment in comments:
        item = record(comment)
        if not item:
            continue
        # Bot round records are accepted; human protocol comments need repository
        # association or creator identity, so outside commenters cannot forge history.
        if comment.get('user', {}).get('type') != 'Bot' and not trusted(comment, creator):
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
        if status == WAITING:
            raise ScopeError(f'CLARIFICATION_WAITING: tick one option per question, or add a normal comment such as C1Q1: A with optional feedback. Then move the issue back to {self.app.actual_status(FEATURE)} and rerun. No new questions were posted and no state was changed.')
        require(status == FEATURE, f'CLARIFICATION_STATE: only {self.app.actual_status(FEATURE)} issues can be processed; #{issue["number"]} is {self.app.actual_status(status)}.')

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

    def inspect(self, value=None):
        issue = self.source(value)
        self.gate(issue)  # Must precede reading the spec or comment history.
        path = self.spec_path(issue)
        comments = self.gh.api(f'{self.app.base}/{issue["number"]}/comments?per_page=100', pages=True)
        creator = issue['user']['login']
        prior = history(comments, creator)
        policy = controls(comments, creator)
        used = max([q['round'] for q in prior['questions'].values()] + [0])
        result = {'version': 1, 'issue': issue, 'creator': creator, 'spec_path': str(path.relative_to(self.root)),
                  'spec': path.read_text(encoding='utf-8-sig'), 'comments': comments, 'history': prior,
                  'policy': policy, 'next_round': used + 1, 'limit_reached': used >= policy['max_rounds']}
        result['snapshot_digest'] = snapshot_digest(result)
        return result

    def validate(self, snapshot, analysis):
        require(analysis.get('version') == 1 and analysis.get('issue') == snapshot['issue']['number'], 'Analysis must identify the current issue.')
        require(analysis.get('snapshot_digest') == snapshot['snapshot_digest'], 'CLARIFICATION_STALE: issue, answers or specification changed; reread and reevaluate.')
        require(analysis.get('engine') in {'clarify', 'brainstorm'}, 'Choose clarify or brainstorm.')
        require(isinstance(analysis.get('coverage'), dict) and analysis['coverage'], 'Supply the complete ambiguity coverage assessment.')
        require(isinstance(analysis.get('questions'), list), 'Supply all remaining questions as a list (no numeric cap).')
        answers = analysis.get('answers', [])
        require(isinstance(answers, list), 'answers must be a list.')
        previous = snapshot['history']['questions']
        require(len(answers) == len(previous) and {a['question_id'] for a in answers} == set(previous),
                'Reevaluate every prior question; none may be silently dropped.')
        comments = {c['id']: c for c in snapshot['comments']}
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
                                and (trusted(comment, snapshot['creator']) or comment.get('user', {}).get('type') == 'Bot'))
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
        followups = {qid for q in analysis['questions'] for qid in q.get('follows_up', [])}
        if unresolved and not snapshot['limit_reached'] and not snapshot['policy']['closed']:
            require(set(unresolved) <= followups, 'Every unresolved prior question needs a precise follow-up question.')
        require(not analysis.get('spec_edits') or any(a['disposition'] in {'answered', 'superseded'} for a in answers) or snapshot['policy']['closed'],
                'Do not change requirements without answer evidence or explicit creator closure.')
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
        path = self.root / self.app.cfg['stateFile']
        state = read_json(path, {})
        for item in state.values():
            if item.get('issue') == issue['number']:
                item['status'] = self.app.actual_status(status)
        if state:
            write_json(path, state)

    def publish(self, value, analysis, apply=False):
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
        batch = digest(analysis)[:20]
        folder = self.root / '.specify/scope/clarifications' / f'{snapshot["issue"]["number"]}-{batch}'
        journal_path = folder / 'journal.json'
        journal = read_json(journal_path)
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
        prepared = []
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
            body += '<details>\n<summary>More context' + (' and diagram' if question.get('diagram') else '') + '</summary>\n\n' + question['details'] + '\n'
            if question.get('diagram'):
                require(not automatic_resume, 'ARCHIFY_REQUIRED: managed questions use diagram_markdown with verified inline Archify image URLs.')
                body += '\n```mermaid\n' + question['diagram'].strip() + '\n```\n'
            if question.get('diagram_markdown'):
                require(re.search(r'!\[[^\]]*\]\(https://[^\s)]+\)', question['diagram_markdown']), 'INLINE_ARCHIFY_IMAGE_REQUIRED')
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
        for answer in analysis.get('answers', []):
            links = ', '.join(f'https://github.com/{self.app.repo}/issues/{number}#issuecomment-{i}' for i in answer.get('comment_ids', []))
            log += f'- {answer["question_id"]}: {answer["disposition"]}. {answer["explanation"]}' + (f' Evidence: {links}' if links else '') + '\n'
            choice = snapshot['history']['questions'][answer['question_id']].get('selection', {})
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
        summary_body = f'### Clarification review: {outcome}\n\n' + analysis.get('summary', 'Questions need your answers before implementation can be planned.') + '\n\n'
        if outcome == 'waiting':
            summary_body += f'Posted {len(prepared)} separate questions in round {round_number}. There is no question-count cap.\n\n'
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
        for qid, body in prepared + [('summary', summary_body)]:
            # Reread between writes for a recoverable lost HTTP response.
            existing = self.gh.api(f'{self.app.base}/{number}/comments?per_page=100', pages=True)
            current_thread = dict(snapshot, comments=existing)
            require(snapshot_digest(current_thread, batch) == snapshot['snapshot_digest'],
                    'CLARIFICATION_STALE: new human input arrived while posting. Reread and reevaluate before continuing.')
            matches = [c for c in existing if record(c) and record(c).get('batch') == batch and
                       ((qid == 'summary' and record(c)['kind'] == 'round') or record(c).get('id') == qid)]
            require(len(matches) <= 1, f'Duplicate published comment for {qid}; reconcile before proceeding.')
            posted = matches[0] if matches else self.gh.api(f'{self.app.base}/{number}/comments', 'POST', {'body': body})
            journal['comments'][qid] = posted['id']
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
        self.app._board = None
        self.gate(self.app.issue(number))
        self.transition(self.app.issue(number), result['status'])
        journal['complete'] = True
        write_json(journal_path, journal)
        if automatic_resume and result['status'] == WAITING:
            write_json(observed_path, {'waiting_digest': self.inspect(value)['snapshot_digest']})
        result = dict(result, comment_ids=journal['comments'], next_action=None)
        # Only a successfully published, fully resolved review hands off to Plan.
        # A creator waiver can close the process without resolving its uncertainty.
        resolved = not analysis['questions'] and all(a['disposition'] != 'unresolved' for a in analysis.get('answers', []))
        if result['status'] == 'Ready' and resolved:
            self.app._board = None
            self.plan_gate(str(number))
            result['next_action'] = {'command': '/speckit-plan', 'issue': number,
                                     'spec_path': str(path.resolve()),
                                     'feature_directory': str(path.parent.relative_to(self.root)),
                                     'feature_name': path.parent.name}
        return result

    def plan_gate(self, value=None):
        issue = self.source(value)
        status = self.app.status(issue)
        from workflow_policy import bound_claim
        revalidation = bound_claim(self.root, self.app.repo, issue['number'], {'plan'})
        previous = (revalidation or {}).get('state', {}).get('receipts', {}).get('clarify', {})
        continued = revalidation and issue.get('state') == 'open' and status in {'In progress', 'In review'} and previous.get('outcome') == 'passed' and previous.get('unresolved') == 0 and previous.get('answers_applied') is True
        require(status == 'Ready' or continued, 'CLARIFICATION_REQUIRED: planning requires Ready or a matching managed revalidation with resolved clarification. Finish GitHub clarification first.')
        return {'issue': issue['number'], 'status': self.app.actual_status(status), 'revalidation': bool(continued)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'dispatch', 'publish', 'plan-gate'])
    parser.add_argument('issue', nargs='?')
    parser.add_argument('--root', default='.')
    parser.add_argument('--analysis', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    lock = None
    try:
        app = Clarification(Scope(args.root))
        if args.apply:
            candidate = app.root / '.specify/scope/mutation.lock'
            candidate.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise ScopeError('Another Scope/clarification mutation is running. Inspect mutation.lock before retrying.')
            with os.fdopen(fd, 'w') as handle:
                handle.write(str(os.getpid()))
            lock = candidate
        if args.command == 'publish':
            require(args.analysis and args.analysis.is_file(), 'Provide --analysis <review.json>.')
            result = app.publish(args.issue, read_json(args.analysis), args.apply)
        else:
            result = getattr(app, args.command.replace('-', '_'))(args.issue)
        if args.output:
            write_json(args.output, result)
            print(json.dumps(with_transport({'output': str(args.output), 'issue': result.get('issue', {}).get('number') if isinstance(result.get('issue'), dict) else result.get('issue')}, app.gh), ensure_ascii=True))
        else:
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
