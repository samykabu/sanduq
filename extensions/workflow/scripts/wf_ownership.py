"""Administrative ownership release; product receipts are never changed here."""
from __future__ import annotations

import re


def recovery_command(run, active):
    return ('python .specify/extensions/workflow/scripts/workflow.py recover --feature ' + run.relative +
            ' --token ' + str(active.get('token', '<recorded-token>')) + ' --reason <inspected-owner-stopped-reason>')


def writer_evidence(w, run, state, automatic=False):
    """Called under the delegation lock, also held until release is durable."""
    import delegate_dispatch as dispatch
    import delegation
    ledger = dispatch.load_ledger(run.root, run.relative)
    attempts = ledger['attempts']
    w.require(delegation.ledger_trust_state(run.root, run.relative) != 'untrusted',
              'OWNERSHIP_UNVERIFIABLE: delegation ledger is untrusted; inspect and trust-reset it first')
    live = [a for a in attempts if a.get('status') in dispatch.ACTIVE]
    w.require(not live, 'OWNERSHIP_EXECUTOR_ACTIVE: collect or recover delegated starting/running work first')
    terminal = dispatch.TERMINAL_STATUSES + dispatch.INACTIVE_INTENTS
    w.require(all(a.get('status') in terminal for a in attempts),
              'OWNERSHIP_UNVERIFIABLE: delegation contains an unknown writer state')
    w.require(not delegation.active_task_ids(run.root, run.relative),
              'OWNERSHIP_EXECUTOR_ACTIVE: inspect running task progress before recovery')
    active = state['active']
    bound = [a for a in attempts if a.get('claim_token') == active['token']]
    if automatic:
        w.require(active.get('delegation') and bound and
                  delegation.ledger_trust_state(run.root, run.relative) == 'trusted',
                  'OWNERSHIP_UNVERIFIABLE: native or legacy ownership has no trusted terminal writer evidence; ' +
                  recovery_command(run, active))
    return {'writer': 'terminal-delegation' if bound else 'owner-confirmed',
            'attempts': [{k: a.get(k) for k in ('run_id', 'intent_id', 'status', 'claim_id')} for a in attempts]}


def merged_delivery(w, run, state, report=None):
    """Read GitHub REST; a caller's verified flag is never terminal evidence."""
    from task_issues import GitHub
    repo = w.github_repository(run.root)
    bound_repo, number = state['issue'].split('#')
    w.require(w.same_github_repository(repo, bound_repo), 'OWNERSHIP_DELIVERY_REPOSITORY_MISMATCH')
    target = state.get('target_branch')
    w.require(isinstance(target, str) and target, 'OWNERSHIP_DELIVERY_TARGET_UNKNOWN')
    gh = GitHub()
    issue = gh.api(f'repos/{repo}/issues/{number}')
    w.require(issue.get('number') == int(number) and
              issue.get('html_url', '').lower() == f'https://github.com/{repo}/issues/{number}'.lower(),
              'OWNERSHIP_DELIVERY_ISSUE_MISMATCH')
    w.require(issue.get('state') == 'closed' and issue.get('state_reason') == 'completed',
              'OWNERSHIP_DELIVERY_NOT_COMPLETED: issue must be closed as completed')
    pr_url = (state.get('receipts', {}).get('pr') or {}).get('pr_url')
    if report is not None:
        w.require(isinstance(report, dict) and report.get('feature') == run.relative and
                  w.same_github_repository(report.get('repository'), repo) and
                  report.get('target_branch') == target and report.get('verified') is True and
                  report.get('report_only') is not True and
                  (not pr_url or report.get('pr_url') == pr_url), 'OWNERSHIP_DELIVERY_REPORT_MISMATCH')
        pr_url = report.get('pr_url')
    w.require(isinstance(pr_url, str) and
              re.fullmatch(r'https://github\.com/' + re.escape(repo) + r'/pull/[1-9]\d*', pr_url, re.I),
              'OWNERSHIP_DELIVERY_PR_REQUIRED: supply the exact feature PR in the postmerge report')
    pr = gh.api(f'repos/{repo}/pulls/{pr_url.rsplit("/", 1)[-1]}')
    head, base = pr.get('head') or {}, pr.get('base') or {}
    w.require(pr.get('html_url', '').lower() == pr_url.lower() and pr.get('merged') is True and
              pr.get('state') == 'closed' and pr.get('merged_at') and
              head.get('ref') == state['branch'] and base.get('ref') == target and
              all(w.same_github_repository((ref.get('repo') or {}).get('full_name'), repo) for ref in (head, base)) and
              all(re.fullmatch('[a-f0-9]{40}', str(sha or '')) for sha in (head.get('sha'), pr.get('merge_commit_sha'))),
              'OWNERSHIP_DELIVERY_PR_MISMATCH: require the merged feature branch in its bound repository and target')
    closing = (r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:#|' + re.escape(repo) +
               r'#|https://github\.com/' + re.escape(repo) + r'/issues/)' + re.escape(number) + r'\b')
    w.require(re.search(closing, pr.get('body') or '', re.I),
              'OWNERSHIP_DELIVERY_ISSUE_LINK_MISSING: the PR must explicitly close the bound issue')
    binding = {'feature': run.relative, 'repository': repo, 'issue': state['issue'], 'pr_url': pr_url,
               'target_branch': target, 'head_sha': head['sha'], 'merge_sha': pr['merge_commit_sha'],
               'merged_at': pr['merged_at'], 'issue_state_reason': issue['state_reason'], 'transport': 'github-rest'}
    if report is not None:
        w.require(all(report.get(k) == binding[k] for k in ('head_sha', 'merge_sha')),
                  'OWNERSHIP_DELIVERY_REPORT_MISMATCH')
    return binding
