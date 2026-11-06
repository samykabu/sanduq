# SPDX-License-Identifier: MIT
"""The PR closing-reference lint shared by Workflow and PR (round 4, PM21).

Stdlib only: PR loads it without Workflow. Moved from `execution_tools.py` without behaviour
change; `execution_tools` re-exports the names.
"""
import hashlib
import re

PR_LINT_SCHEMA = 'sanduq.execution.pr-lint.v1'
CLOSE_REF = re.compile(
    r'\b(?P<kw>close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+'
    r'(?:https?://github\.com/(?P<urepo>[\w.-]+/[\w.-]+)/issues/(?P<unum>\d+)|(?P<repo>[\w.-]+/[\w.-]+)?#(?P<num>\d+))',
    re.I)
FENCE = re.compile(r'```.*?```|~~~.*?~~~|`[^`\n]*`', re.S)


def pr_lint(body, repo, issue, prerequisites=()):
    repo_key = repo.lower()
    prereqs = {int(p) for p in prerequisites}
    text = FENCE.sub('', body)
    closes, violations = [], []
    for match in CLOSE_REF.finditer(text):
        ref_repo = (match.group('urepo') or match.group('repo') or repo).lower()
        number = int(match.group('unum') or match.group('num'))
        closes.append({'keyword': match.group('kw').lower(), 'repo': ref_repo, 'issue': number})
        if ref_repo != repo_key:
            code = 'FOREIGN_REPO_CLOSE'
        elif number in prereqs:
            code = 'PREREQUISITE_CLOSE'
        elif number != int(issue):
            code = 'UNBOUND_ISSUE_CLOSE'
        else:
            continue
        violations.append({'code': code, 'repo': ref_repo, 'issue': number})
    # a body that never closes its bound issue would leave the issue open after merge (1.24.1, N1)
    if not any(c['repo'] == repo_key and c['issue'] == int(issue) for c in closes):
        violations.append({'code': 'BOUND_ISSUE_NOT_CLOSED', 'repo': repo_key, 'issue': int(issue)})
    return {'schema': PR_LINT_SCHEMA, 'ok': not violations,
            'body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(), 'bound': {'repo': repo_key, 'issue': int(issue)},
            'closes': closes, 'violations': violations}
