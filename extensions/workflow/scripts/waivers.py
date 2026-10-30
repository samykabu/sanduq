#!/usr/bin/env python3
"""Verify one-off CI rule waivers approved in a GitHub PR discussion."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

from decisions import GitHub
from workflow import WorkflowError, github_repository, require
import sanduq_ci

MARKER = re.compile(r'\A<!-- sanduq-gate-waiver (\{[^\n]*\}) -->\nReason: ([^\n]+)\s*\Z')
RULE_ERRORS = {
    'receipts': ('POLICY_CHANGED', 'RECEIPT_MISSING', 'STALE_RECEIPT',
                 'CLARIFICATION_UNRESOLVED', 'BLOCKING_FINDINGS_REMAIN', 'RECEIPT_LOG_INVALID',
                 'RECEIPT_LOG_MISSING', 'RECEIPT_LOG_REWRITTEN', 'RECEIPT_EDITED_OUTSIDE_DISPATCHER'),
    'decisions': ('DECISION_LEDGER_INVALID', 'DECISION_FEATURE_MISMATCH',
                  'DECISION_ISSUE_MISMATCH', 'DECISION_UNRESOLVED',
                  'DECISION_ANSWER_CHANGED', 'DECISION_CHOICE_MISMATCH',
                  'DECISION_APPLICATION_STALE',
                  'DECISION_APPLICATION_EVIDENCE_REQUIRED'),
    'tasks': ('INCOMPLETE_TASKS',),
    'task_links': ('TASK_MAPPING_IDENTITY_MISMATCH', 'TASK_MAPPING_INCOMPLETE'),
    'documentation': ('SELECTED_PROCESS_MISSING', 'DOCUMENTATION_GATE_FAILED',
                      'DOCUMENTATION_NOT_CURRENT'),
    'portability': ('EVIDENCE_NOT_PORTABLE',),
    'candidate_merge': ('CANDIDATE_MERGE_REF_REQUIRED',
                        'CANDIDATE_MERGE_PARENTS_MISMATCH'),
    'live_answers': ('DECISION_LIVE_ANSWERS_CHANGED', 'DECISION_LIVE_UNRESOLVED',
                     'GITHUB_DECISION_API_FAILED'),
}


def error_rule(error):
    code = str(error).split(':', 1)[0]
    return next((rule for rule, codes in RULE_ERRORS.items() if code in codes), None)


def refusal(comment, pr, policy):
    """Why this commenter may not waive, or None when they may.

    A PR author may waive only when the base branch policy lists them under
    `decisions.self_waivers` (a one-person setup; see delivery-policy.md)."""
    user = comment.get('user') or {}
    login = str(user.get('login', '')).casefold()
    decisions = policy.get('decisions', {})
    selected = {name.casefold() for name in decisions.get('authorized_users', [])}
    if not login:
        return 'the comment has no author'
    if user.get('type') == 'Bot':
        return 'written by a bot'
    if login == pr['user']['login'].casefold():
        if login in {name.casefold() for name in decisions.get('self_waivers', [])}:
            return None
        return ('written by the PR author; ask another authorized user, or in a one-person setup list '
                'this login under decisions.self_waivers on the target branch')
    if login in selected or comment.get('author_association') in ('OWNER', 'MEMBER', 'COLLABORATOR'):
        return None
    return 'not a decisions.authorized_users entry, or a repository owner, member or collaborator'


def verify(root, pr_number, feature, rule, policy, gh=None, *, today=None):
    require(rule in sanduq_ci.GATE_RULES, 'WAIVER_RULE_INVALID')
    require(re.fullmatch(r'[1-9]\d*', str(pr_number)), 'WAIVER_PR_NUMBER_INVALID')
    gh = gh or GitHub()
    repo = github_repository(root)
    pr = gh.api(f'repos/{repo}/pulls/{pr_number}')
    require(pr.get('number') == int(pr_number), 'WAIVER_PR_MISMATCH')
    head = pr.get('head', {}).get('sha')
    require(re.fullmatch(r'[0-9a-f]{40}', str(head)), 'WAIVER_PR_HEAD_INVALID')
    comments = gh.api(f'repos/{repo}/issues/{pr_number}/comments?per_page=100', pages=True)
    matches, rejected = [], []
    today = today or datetime.now(timezone.utc).date()
    for comment in comments:
        body = comment.get('body', '')
        where = str(comment.get('html_url') or 'a PR comment')
        match = MARKER.match(body)
        if not match:
            if 'sanduq-gate-waiver' in body:
                rejected.append(where + ': not the two-line waiver format')
            continue
        try:
            item = json.loads(match[1])
        except ValueError:
            rejected.append(where + ': the marker is not valid JSON')
            continue
        if not isinstance(item, dict) or (item.get('version'), item.get('pr')) != (1, int(pr_number)):
            rejected.append(where + ': not a version 1 waiver for PR ' + str(pr_number))
            continue
        if (item.get('feature'), item.get('rule')) != (feature, rule):
            continue  # a waiver for another feature or rule
        if item.get('head_sha') != head:
            rejected.append(where + ': waiver is for head ' + str(item.get('head_sha')) + ', the PR head is now '
                            + head + '; ask for a new waiver')
            continue
        if item.get('reason') != match[2] or not item['reason'].strip():
            rejected.append(where + ': the JSON reason differs from the Reason line, or is empty')
            continue
        try:
            expires = date.fromisoformat(item['expires'])
        except (KeyError, TypeError, ValueError):
            rejected.append(where + ': expires is not a YYYY-MM-DD date')
            continue
        if expires < today:
            rejected.append(where + ': expired on ' + str(expires))
            continue
        why = refusal(comment, pr, policy)
        if why:
            rejected.append(where + ': ' + str((comment.get('user') or {}).get('login')) + ' may not waive: ' + why)
            continue
        matches.append({'rule': rule, 'feature': feature, 'pr': int(pr_number),
                        'head_sha': head, 'reason': item['reason'],
                        'expires': str(expires), 'reviewer': comment['user']['login'],
                        'url': comment.get('html_url')})
    require(len(matches) == 1, 'WAIVER_NOT_VERIFIED: require one current authorized PR comment for '
            + rule + ' on ' + feature + (' (found ' + str(len(matches)) + ')' if matches else '')
            + ('; rejected: ' + '; '.join(rejected) if rejected else ''))
    return matches[0]
