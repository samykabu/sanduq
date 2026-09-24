#!/usr/bin/env python3
"""Verify one-off CI rule waivers approved in a GitHub PR discussion."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

from decisions import GitHub
from workflow import WorkflowError, github_repository, require
import sanduq_ci

MARKER = re.compile(r'\A<!-- sanduq-gate-waiver (\{[^\n]*\}) -->\nReason: ([^\n]+)\s*\Z')
RULE_ERRORS = {
    'receipts': ('POLICY_CHANGED', 'RECEIPT_MISSING', 'STALE_RECEIPT',
                 'CLARIFICATION_UNRESOLVED', 'BLOCKING_FINDINGS_REMAIN'),
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


def authorized(comment, pr, policy):
    user = comment.get('user') or {}
    login = str(user.get('login', '')).casefold()
    selected = {name.casefold() for name in policy.get('decisions', {}).get('authorized_users', [])}
    return bool(login) and user.get('type') != 'Bot' and login != pr['user']['login'].casefold() and (
        login in selected or comment.get('author_association') in ('OWNER', 'MEMBER', 'COLLABORATOR'))


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
    matches = []
    today = today or datetime.now(timezone.utc).date()
    for comment in comments:
        match = MARKER.match(comment.get('body', ''))
        if not match:
            continue
        import json
        try:
            item = json.loads(match[1])
        except ValueError:
            continue
        if not isinstance(item, dict) or (item.get('version'), item.get('pr'), item.get('feature'),
                                         item.get('rule'), item.get('head_sha')) != (
                1, int(pr_number), feature, rule, head):
            continue
        if item.get('reason') != match[2] or not item['reason'].strip():
            continue
        try:
            expires = date.fromisoformat(item['expires'])
        except (KeyError, TypeError, ValueError):
            continue
        if expires < today or not authorized(comment, pr, policy):
            continue
        matches.append({'rule': rule, 'feature': feature, 'pr': int(pr_number),
                        'head_sha': head, 'reason': item['reason'],
                        'expires': str(expires), 'reviewer': comment['user']['login'],
                        'url': comment.get('html_url')})
    require(len(matches) == 1, 'WAIVER_NOT_VERIFIED: require one current authorized PR comment for '
            + rule + ' on ' + feature)
    return matches[0]
