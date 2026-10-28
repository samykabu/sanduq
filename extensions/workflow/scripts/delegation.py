#!/usr/bin/env python3
"""Policy, task metadata and skill discovery for opt-in workflow delegation."""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import yaml

from execution_tools import sha256_file

try:
    import sanduq_fs
except ModuleNotFoundError:  # the source tree; package.py copies it into scripts/
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_fs

# ``qa`` split in two (B12): ``qa_author`` is standard-tier authored QA work
# (writing tests, analysing coverage); ``qa_collect`` is the light-eligible
# route for running an existing, fixed check and reporting its result. Nothing
# routes to ``qa_collect`` by inference; see ``task_type`` and ``stage_work_type``.
TYPES = ('discovery', 'implementation', 'qa_author', 'qa_collect', 'documentation',
         'review', 'coordination')
# Discovery (Scope, Specify, Clarify, Plan, Tasks) is never light: standard by
# default, with Scope and Plan overridable to high by policy. qa_collect is the
# only route whose default is light; coordination defaults to high per standing
# rule 5 and C2 (coordination -> high): it claims and completes workflow
# stages and issues, review/coordination-grade work, never a cheap default.
DEFAULT_TIERS = {'discovery': 'standard', 'implementation': 'standard', 'qa_author': 'standard',
                 'qa_collect': 'light', 'documentation': 'documentation', 'review': 'review',
                 'coordination': 'high'}
MODEL_PROFILES = ('high', 'standard', 'light', 'documentation', 'review')
# Tiers a Sanduq role file pins (assets/roles): only these can run natively on the exact model.
ROLE_TIERS = ('standard', 'review')
STAGE_TYPES = {
    'scope': 'discovery', 'specify': 'discovery', 'clarify': 'discovery',
    'plan': 'discovery', 'tasks': 'discovery', 'qa_analyze': 'qa_author',
    'manual_analyze': 'documentation', 'analyze': 'review',
    'taskstoissues': 'coordination', 'execute': 'coordination',
    'verify': 'qa_author', 'review': 'review', 'qa_document': 'documentation',
    'manual_update': 'documentation', 'ready': 'coordination', 'pr': 'coordination',
}
# qa_collect is never inferred from a stage's identity: ``verify`` selects
# tests, handles lane gaps and reports blocking findings (SKILL.md), so it is
# not a fixed script by default and stays qa_author. A project may name an
# explicit stage -> command mapping in policy
# (``delegation.fixed_collection_commands``, empty by default); only when a
# stage's resolved command still matches that exact string does
# ``stage_work_type`` route it to the light-eligible qa_collect.
# The default route a fresh qa_collect gets: light-eligible, one fallback that
# lets the harness use its own default model. Used both for a brand-new policy
# and to complete a policy migrated from the pre-1.7 single ``qa`` route.
DEFAULT_QA_COLLECT_ROUTE = {'preferred': {'harness': 'selected', 'tier': 'light'},
                            'fallbacks': [{'harness': 'selected', 'model': None}]}
# The standard-tier route qa_author gets reset to when a pre-1.7 policy's
# ``qa`` route was itself the old light-tier default (or any light candidate):
# a legacy install must not keep sending authored QA work to Haiku (finding 5).
DEFAULT_QA_AUTHOR_ROUTE = {'preferred': {'harness': 'selected', 'tier': 'standard'},
                           'fallbacks': [{'harness': 'selected', 'model': None}]}
TASK_LINE = re.compile(r'^(\s*- \[([ xX])\]\s+(T\d{3,})\b.*)$')
MARKER = re.compile(r'^\s*<!-- sanduq-delegation (\{[^\n]+\}) -->\s*$')
INLINE_MARKER = re.compile(r'[ \t]*(<!-- sanduq-delegation \{[^\n]+\} -->)[ \t]*$')
OVERRIDE_KEY = re.compile(r'^specs/[^/]+/T\d{3,}$')


class DelegationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DelegationError(message)


def delegated_run_id():
    """`SANDUQ_DELEGATED_RUN`, or None. Set means a real delegated worker
    process tree exists underneath this one. Read through this one place
    so `delegate_dispatch.require_not_worker_context` and `workflow.py`'s
    `require_not_delegated_context` (round 1, finding 7) can never read a
    different answer for the same environment -- each still applies its
    own policy on top (the orchestrator role gets a narrow exception in
    one, none in the other), but the underlying fact they start from is
    shared, not duplicated.
    """
    return os.environ.get('SANDUQ_DELEGATED_RUN')


def delegated_role():
    """`SANDUQ_DELEGATED_ROLE`, or None. See `delegated_run_id`."""
    return os.environ.get('SANDUQ_DELEGATED_ROLE')


def task_line_content_sha256(line):
    """sha256 of a task line's content, minus its checkbox state and with
    whitespace normalised (round 8, finding 1): the binding an adopted
    attempt records at ``adopt`` time and the Ready gate checks at
    completion time. Re-checking, unchecking or reformatting the line does
    not itself change this digest, but editing its substantive text --
    including swapping in a different task under the same id -- does, so a
    stale adoption is caught rather than silently carried over to new work.
    """
    match = TASK_LINE.match(line)
    require(match is not None, 'DELEGATION_TASK_LINE_INVALID')
    content = re.sub(r'^\s*-\s*\[[ xX]\]\s*', '', match.group(1))
    # annotate_tasks relocates an inline "<!-- sanduq-delegation ... -->"
    # marker onto its own line on the very next run, even for an already
    # checked task (round 9, finding 3): stripping it here means that
    # relocation -- pure formatting, no substantive change to the task --
    # does not itself invalidate an adoption made while the marker was
    # still inline.
    content = INLINE_MARKER.sub('', content)
    return hashlib.sha256(re.sub(r'\s+', ' ', content).strip().encode('utf-8')).hexdigest()


def task_lines(text):
    """Map of task id -> its exact current line (stripped), read once for
    checking every adopted attempt's binding at Ready (round 8, finding 1)."""
    lines = {}
    for line in text.splitlines():
        match = TASK_LINE.match(line)
        if match:
            lines[match.group(3)] = match.group(1).strip()
    return lines


def feature_identity(root, feature):
    """Return the one POSIX ``specs/<name>`` identity for any --feature spelling."""
    root = Path(root).resolve()
    text = str(feature).strip().replace('\\', '/')
    require(text, 'DELEGATION_FEATURE_INVALID')
    if Path(text).is_absolute():
        resolved = Path(text).resolve()
        require(resolved.is_relative_to(root), 'DELEGATION_FEATURE_INVALID: ' + str(feature))
        text = resolved.relative_to(root).as_posix()
    require(not re.match(r'^[A-Za-z]:|^/', text), 'DELEGATION_FEATURE_INVALID: ' + str(feature))
    parts = [part for part in text.split('/') if part not in ('', '.')]
    require(len(parts) == 2 and parts[0] == 'specs' and parts[1] != '..' and
            ':' not in parts[1], 'DELEGATION_FEATURE_INVALID: ' + str(feature))
    return 'specs/' + parts[1]


# One lock implementation for every runtime (SAMY-01/09): these names stay importable from here.
from sanduq_fs import (LOCK_UNREADABLE_STALE_SECONDS, lock_held, lock_is_stale, lock_owner,  # noqa: E402,F401
                       process_alive, recover_stale_lock)


def release_owned_lock(path, token):
    sanduq_fs.release_owned_lock(path, token, DelegationError, 'DELEGATION_LOCK_RELEASE_BUSY')


def file_lock(path, timeout, busy):
    """Exclusive cross-process lock that recovers a dead owner's lock file (`sanduq_fs.file_lock`).

    Yields the owner token; callers that write shared state call lock_held()
    before their final write so a displaced owner never overwrites a newer one.
    """
    return sanduq_fs.file_lock(path, timeout, busy, DelegationError, 'DELEGATION_LOCK_RELEASE_BUSY')


# Upgrade and install hold these while they snapshot, change and may roll back
# the project's managed files, including every delegation ledger.
MAINTENANCE_LOCKS = ('upgrade.lock', 'install.lock')


def maintenance_in_progress(root, owners=()):
    """Name the upgrade or install lock held by a process other than ``owners``.

    A lock with no readable owner yet counts as held: its creator writes the
    owner immediately after the exclusive create.
    """
    runtime = Path(root) / '.specify/workflow/runtime'
    for name in MAINTENANCE_LOCKS:
        path = runtime / name
        if not path.exists():
            continue
        pid = (lock_owner(path) or {}).get('pid')
        if pid is not None and pid in owners:
            continue
        return name
    return None


def require_no_maintenance(root, owners=()):
    held = maintenance_in_progress(root, owners)
    if held is None:
        return
    # These locks are never recovered automatically: a crashed upgrade or
    # install leaves its lock behind, and waiting will not clear it.
    lock = '.specify/workflow/runtime/' + held
    owner = lock_owner(Path(root) / lock) or {}
    pid = owner.get('pid')
    who = ('pid ' + str(pid) + (' (created ' + str(owner['created']) + ')' if owner.get('created') else '')
           if pid is not None else 'a process that has not recorded its pid')
    check = ('check with "tasklist /FI \\"PID eq ' + str(pid) + '\\"" on Windows or "ps -p ' + str(pid) +
             '" elsewhere' if pid is not None else 'check for a running upgrade.py or install.py')
    raise DelegationError(
        'WORKFLOW_UPGRADE_IN_PROGRESS: ' + lock + ' is held by ' + who + '. If that process is '
        'still running, retry once it finishes. If it is not (' + check + '), the upgrade or '
        'install crashed and the lock is stale: delete ' + lock + ', then rerun the upgrade or '
        'install, because its rollback may not have completed')


def validate_candidate(candidate):
    require(isinstance(candidate, dict) and
            set(candidate) in ({'harness', 'tier'}, {'harness', 'model'}),
            'DELEGATION_CANDIDATE_INVALID')
    require(candidate['harness'] in ('selected', 'codex', 'claude'), 'DELEGATION_HARNESS_INVALID')
    if 'tier' in candidate:
        require(candidate['tier'] in MODEL_PROFILES, 'DELEGATION_TIER_INVALID')
    else:
        require(candidate['model'] is None or
                isinstance(candidate['model'], str) and candidate['model'].strip(), 'DELEGATION_MODEL_INVALID')


def validate_route(route, allow_light=True):
    # allow_default_model: the route may fall back to the CLI's default model, still only after the user
    # confirms the substitution (DEC-12 B); absent means the default model is never a substitute.
    require(isinstance(route, dict) and set(route) - {'allow_default_model'} == {'preferred', 'fallbacks'},
            'DELEGATION_ROUTE_INVALID: a route has exactly preferred, fallbacks and optionally allow_default_model')
    require(type(route.get('allow_default_model', False)) is bool,
            'DELEGATION_ROUTE_INVALID: allow_default_model must be true or false')
    validate_candidate(route['preferred'])
    require(isinstance(route['fallbacks'], list) and len(route['fallbacks']) <= 5,
            'DELEGATION_FALLBACKS_INVALID')
    for candidate in route['fallbacks']:
        validate_candidate(candidate)
    if not allow_light:
        require(all(candidate.get('tier') != 'light' for candidate in (route['preferred'], *route['fallbacks'])),
                'DELEGATION_DISCOVERY_LIGHT_FORBIDDEN')


def _route_has_light_candidate(route):
    if not isinstance(route, dict):
        return False
    candidates = [route.get('preferred')] + list(route.get('fallbacks') or ())
    return any(isinstance(c, dict) and c.get('tier') == 'light' for c in candidates)


def migrate_qa_route(config):
    """Map a pre-1.7 policy's single ``qa`` route onto ``qa_author``, in place.

    ``qa_collect`` is new: a project that never had it gets the same default
    shape every fresh policy gets, so it is always present and always
    light-eligible, never inherited from the old ``qa`` route (which may have
    pointed anywhere).

    The pre-1.7 default routed ``qa`` to the light tier (today's qa_collect
    default is exactly that old shape). A legacy policy that never customised
    it, or that customised it to some other light-tier route, would otherwise
    keep sending authored QA work to the light tier forever (finding 5): any
    light candidate in the legacy route resets qa_author to the new standard
    default instead of inheriting it. Returns a notice string when that reset
    happened, else ``None``, for the caller to surface (``doctor``).
    """
    if not isinstance(config, dict):
        return None
    routes = config.get('routes')
    if not isinstance(routes, dict) or 'qa' not in routes:
        return None
    legacy = routes.pop('qa')
    routes.setdefault('qa_collect', copy.deepcopy(DEFAULT_QA_COLLECT_ROUTE))
    if 'qa_author' in routes:
        return None
    if _route_has_light_candidate(legacy):
        routes['qa_author'] = copy.deepcopy(DEFAULT_QA_AUTHOR_ROUTE)
        return ('DELEGATION_LEGACY_QA_AUTHOR_RESET: the pre-1.7 delegation.routes.qa route sent '
                'authored QA work to the light tier; qa_author was reset in memory to the standard '
                'default. Review delegation.routes.qa_author and edit .specify/workflow.yml if a '
                'different route is wanted.')
    routes['qa_author'] = legacy
    return None


# The only key fixed_collection_commands may ever route (schema and
# validate_delegation enforce the same restriction on the policy itself;
# this is the second, load-bearing enforcement inside stage_work_type, so an
# unvalidated dict passed directly -- as a test, or any future caller, might
# -- can still never move a discovery stage, or any stage but verify, to
# qa_collect). A value naming a runtime pseudo-command ("workflow:...") or a
# skill invocation ("speckit....") is never a genuinely fixed external
# script and is rejected even when it is the stage's own real default
# command (finding 1, round 2: policy naming verify's actual default,
# "workflow:verification", must not silently restore the pre-fix behaviour).
FIXED_COLLECTION_ALLOWED_STAGE = 'verify'
FIXED_COLLECTION_REJECTED_PREFIXES = ('workflow:', 'speckit.')


def stage_work_type(commands, stage, fixed_collection_commands=None):
    """The delegation work type for one stage, given its resolved command map.

    ``commands`` is the checkpoint's resolved ``stage -> command`` map (the same
    one ``workflow.py`` persists at claim time), so a caller anywhere in the
    lifecycle classifies a stage identically. ``fixed_collection_commands`` is
    the optional ``delegation.fixed_collection_commands`` policy map; only
    ``verify``, named there with a resolved-command match that is not a
    ``workflow:`` or ``speckit.`` value, ever routes to qa_collect. Every
    other stage -- discovery above all -- always returns its STAGE_TYPES
    default, regardless of what the map contains for it.
    """
    require(stage in STAGE_TYPES, 'DELEGATION_STAGE_INVALID')
    if stage == FIXED_COLLECTION_ALLOWED_STAGE:
        fixed = (fixed_collection_commands or {}).get(FIXED_COLLECTION_ALLOWED_STAGE)
        if (fixed is not None and not fixed.startswith(FIXED_COLLECTION_REJECTED_PREFIXES) and
                (commands or {}).get(FIXED_COLLECTION_ALLOWED_STAGE) == fixed):
            require(STAGE_TYPES[stage] != 'discovery', 'DELEGATION_STAGE_INVALID')
            return 'qa_collect'
    return STAGE_TYPES[stage]


def light_tier_route_warnings(config):
    """Non-fatal advisories for a route defaulted to light where it should not be.

    qa_author (authored QA work: writing or analysing tests, finding 5) and
    coordination (claims and completes stages, finding 6/7) both default to a
    standard-or-above tier; a policy that still routes either to light is
    valid (nothing forbids it outside discovery) but is very likely a stale
    pre-1.7 default or an unintended edit, so ``doctor`` surfaces it.
    """
    warnings = []
    routes = (config or {}).get('routes') or {}
    for name, label in (('qa_author', 'authored QA work (writing or analysing tests)'),
                        ('coordination', 'stage claim/completion and issue coordination')):
        if _route_has_light_candidate(routes.get(name)):
            warnings.append(
                'DELEGATION_LIGHT_TIER_ROUTE: delegation.routes.' + name + ' has a light-tier '
                'candidate; ' + label + ' should not default to the light tier. Review '
                'delegation.routes.' + name + ' in .specify/workflow.yml.')
    return warnings


def validate_delegation(config):
    require(isinstance(config, dict) and set(config) - {'native_allowed'} ==
            {'enabled', 'install_scope', 'stronger_retry', 'models', 'routes', 'overrides',
             'fixed_collection_commands'},
            'DELEGATION_POLICY_INVALID')
    # Optional and never filled in, so an older policy keeps its digest: absent means native for every type.
    native = config.get('native_allowed', {})
    require(isinstance(native, dict) and set(native) <= set(TYPES) and
            all(type(value) is bool for value in native.values()),
            'DELEGATION_NATIVE_ALLOWED_INVALID: native_allowed maps a work type (' + ', '.join(TYPES) +
            ') to true or false')
    require(type(config['enabled']) is bool, 'DELEGATION_SELECTION_INVALID')
    require(config['install_scope'] in ('project', 'global'), 'DELEGATION_SCOPE_INVALID')
    require(type(config['stronger_retry']) is int and config['stronger_retry'] in (0, 1),
            'DELEGATION_RETRY_INVALID')
    models = config['models']
    require(isinstance(models, dict) and set(models) == {'codex', 'claude'},
            'DELEGATION_MODELS_INVALID')
    for harness in ('codex', 'claude'):
        require(isinstance(models[harness], dict) and
                set(models[harness]) == set(MODEL_PROFILES),
                'DELEGATION_MODELS_INVALID: ' + harness)
        require(all(isinstance(value, str) and value.strip() for value in models[harness].values()),
                'DELEGATION_MODEL_INVALID: ' + harness)
    routes = config['routes']
    require(isinstance(routes, dict) and set(routes) >= set(TYPES) and
            set(routes) <= set(TYPES) | {'qa'}, 'DELEGATION_ROUTES_INVALID')
    for name, route in routes.items():
        validate_route(route, allow_light=name != 'discovery')
    require(isinstance(config['overrides'], dict), 'DELEGATION_OVERRIDES_INVALID')
    for key, route in config['overrides'].items():
        require(isinstance(key, str) and OVERRIDE_KEY.fullmatch(key),
                'DELEGATION_OVERRIDE_KEY_INVALID: ' + str(key))
        validate_route(route)
    fixed = config['fixed_collection_commands']
    require(isinstance(fixed, dict) and set(fixed) <= {FIXED_COLLECTION_ALLOWED_STAGE} and
            all(isinstance(v, str) and v.strip() for v in fixed.values()),
            'DELEGATION_FIXED_COLLECTION_COMMANDS_INVALID: only "' +
            FIXED_COLLECTION_ALLOWED_STAGE + '" may be named')
    require(all(not v.startswith(FIXED_COLLECTION_REJECTED_PREFIXES) for v in fixed.values()),
            'DELEGATION_FIXED_COLLECTION_COMMANDS_INVALID: a workflow: or speckit. command is '
            'never a fixed external script')
    return config


TASK_PREFIX = re.compile(r'^\s*(?:- \[[ xX]\]\s+)?(?:T\d{3,}\b\s*)?(?:\[[^\]]*\]\s*)*', re.I)
TYPE_MARKERS = (('implementation', r'\[(?:impl|implement|implementation|code)\]'),
                ('qa_author', r'\[(?:qa|test|tests|tdd)\]'),
                ('documentation', r'\[(?:doc|docs|documentation|manual)\]'),
                ('review', r'\[review\]'))
# The only way a task ever routes to the light-eligible qa_collect: an
# explicit, unambiguous marker. It is checked separately from TYPE_MARKERS
# (never folded into the heuristic loop below) so it is never inferred from
# task text, and combining it with any other explicit marker is ambiguous and
# falls back to implementation (standard) rather than guessing which one wins.
COLLECT_MARKER = re.compile(r'\[collect\]')
# Nouns that turn a leading "test", "review", "audit" or "inspect" into the
# name of something being built: "Audit log retention", "Review queue API",
# "Test runner integration" are implementation work.
COMPOUND_HEADS = (r'(?:logs?|logging|trails?|queues?|apis?|endpoints?|services?|tables?|models?|'
                  r'pages?|screens?|ui|components?|records?|events?|history|workflows?|status|'
                  r'forms?|panels?|widgets?|features?|flows?|pipelines?|jobs?|tools?|tooling|'
                  r'modes?|dashboards?|views?|requests?|threads?|steps?|stages?|dialogs?|modals?|'
                  r'buttons?|links?|runners?|frameworks?|environments?|env|config|configuration|'
                  r'infrastructure|infra|containers?|databases?|db|servers?|accounts?|users?|'
                  r'reporters?|matrix|schema|state|store|entries|entry|trigger|hooks?)')
# A documentation file named as the direct object or destination: a README,
# changelog or contributing guide with or without its extension, a path under a
# top-level docs/ folder, or any Markdown, reStructuredText or AsciiDoc file. A
# code file under a nested docs folder ("src/docs/parser.py") is not one.
DOC_FILE = (r'(?:(?:readme|changelog|contributing)(?:\.(?:md|mdx|rst|txt|adoc))?|'
            r'docs?/[\w./-]*[\w-]|(?:[\w.-]+/)*[\w.-]+\.(?:md|mdx|rst|adoc))')
DOC_END = r'(?:\s+(?:for|with|to|in|on|about|of)\b|\s*[.:;]?$)'
# Only the task's leading action decides unmarked work, so a domain noun such
# as "audit logging" or "review queue" never reroutes an implementation task,
# whether it leads the description or not.
LEADING_ACTIONS = (
    ('qa_author', r'(?:run|execute)\s+(?:[\w/-]+\s+){0,4}?(?:tests?|test suites?|suites?|checks)\b|'
           r'(?:write|add|create)\s+(?:[\w/-]+\s+){0,3}?tests?(?:\s+(?:for|of|to|in|covering|that)\b|\s*[.:;]?$)|'
           r'smoke[- ]test\b|test\b(?!\s+(?:data|fixtures?|harness|helpers?|utils?|utilities|'
           r'factor(?:y|ies)|doubles?|mocks?|suites?|coverage|plans?|results?|' + COMPOUND_HEADS[3:-1] +
           r')\b)|capture\s+(?:[\w/-]+\s+){0,2}?screenshots?\b'),
    ('documentation', r'document\s+(?:the|how|why|all|each|every|our|a|an)\b|'
                      r'document\s+(?:[\w/-]+\s+){0,4}?(?:in|into|to|under)\s+' + DOC_FILE + DOC_END + '|'
                      r'(?:write|update|add|create|revise)\s+(?:the\s+)?' + DOC_FILE +
                      r'(?:\s+(?:section|page|entry))?' + DOC_END + '|'
                      r'(?:write|update|add|create|revise)\s+(?:[\w/-]+\s+){0,3}?'
                      r'(?:docs?|documentation|readme|user manual|manual|release notes|changelog|guide)'
                      r'(?:\s+(?:section|page|entry))?' + DOC_END),
    ('review', r'(?:review|audit|inspect)\b(?!\s+' + COMPOUND_HEADS + r'\b)'),
)
# A leading check that also asks for code changes ("Inspect the parser and fix
# the crash") is implementation work that happens to start with a check.
MIXED_IMPLEMENTATION = re.compile(
    r'(?:\band\b|\bthen\b|&|,|;)\s+(?:then\s+)?(?:fix|fixes|implement|build|refactor|remove|'
    r'migrate|wire|patch|resolve|rewrite|change|correct|repair)\b')


def task_type(description, lean=False):
    """Classify explicit task markers, then only an unambiguous leading action.

    Anything unclear stays implementation, the route every task can take.
    ``[Impl]`` (or ``[Implementation]``, ``[Code]``) forces implementation.
    ``[Collect]`` is the sole explicit route to qa_collect; combined with any
    other explicit marker it is ambiguous and falls back to implementation.
    """
    value = description.casefold()
    prefix = TASK_PREFIX.match(value)[0]
    matched = [work_type for work_type, marker in TYPE_MARKERS if re.search(marker, prefix)]
    if lean and '[artifact-analysis]' in prefix and not matched and not COLLECT_MARKER.search(prefix):
        return 'discovery'
    if COLLECT_MARKER.search(prefix):
        return 'implementation' if matched else 'qa_collect'
    if matched:
        return matched[0]
    action = value[len(prefix):].strip()
    for work_type, pattern in LEADING_ACTIONS:
        if re.match(pattern, action):
            return 'implementation' if MIXED_IMPLEMENTATION.search(action) else work_type
    return 'implementation'


# SEC-01 interim: every external run launches the agent CLI in permission-bypass mode with the whole parent
# environment, so review-kind work (the review work type, or a route on the review profile) is refused until
# the clean-environment launch planned in PH-02 exists.
REVIEW_ROUTE_UNSAFE = ('DELEGATION_REVIEW_ROUTE_UNSAFE: an external delegated run launches the agent CLI in '
                       'permission-bypass mode with the full environment, so review work is not delegated; run '
                       'the review natively in the selected host, or wait for the clean-environment launch '
                       'planned in PH-02')


def review_route_unsafe(work_type, route):
    """True for review-kind work: the review work type or any candidate on the review model profile."""
    return work_type == 'review' or any(c.get('tier') == 'review' for c in (route['preferred'], *route['fallbacks']))


def unsafe_review_routes(config):
    """The policy routes and overrides the SEC-01 interim refuses, for `doctor`."""
    return sorted([name for name, route in config['routes'].items() if review_route_unsafe(name, route)] +
                  [key for key, route in config['overrides'].items() if review_route_unsafe(None, route)])


def selected_route(config, work_type, selected_host, identity=None):
    validate_delegation(config)
    require(work_type in TYPES, 'DELEGATION_TASK_TYPE_INVALID')
    require(selected_host in ('codex', 'claude'), 'DELEGATION_SELECTED_HOST_INVALID')
    rule = 'default:' + work_type
    route = config['routes'][work_type]
    if identity and identity in config['overrides']:
        route = config['overrides'][identity]
        rule = 'override:' + identity
    elif route != {'preferred': {'harness': 'selected', 'tier': DEFAULT_TIERS[work_type]},
                   'fallbacks': [{'harness': 'selected', 'model': None}]}:
        rule = 'yaml:' + work_type
    require(not review_route_unsafe(work_type, route), REVIEW_ROUTE_UNSAFE)
    unsupported = native_unsupported(config, work_type, route['preferred'], selected_host)
    candidates = []
    if unsupported is None:
        # Native first: the host runs the work itself on the preferred tier's pinned model; the
        # configured candidates stay behind it as external fallbacks.
        tier = route['preferred']['tier']
        candidates.append({'harness': selected_host, 'requested_model': config['models'][selected_host][tier],
                           'tier': tier, 'rule': rule, 'choice': 'preferred',
                           'route_kind': 'native', 'route_reason': 'native-first'})
    for index, item in enumerate((route['preferred'], *route['fallbacks'])):
        harness = selected_host if item['harness'] == 'selected' else item['harness']
        model = config['models'][harness][item['tier']] if 'tier' in item else item['model']
        reason = ('external:cross-vendor' if harness != selected_host else
                  'native-failed:pending' if unsupported is None else 'native-unsupported:' + unsupported)
        candidates.append({'harness': harness, 'requested_model': model,
                           'tier': item.get('tier'), 'rule': rule,
                           'choice': 'preferred' if index == 0 else 'fallback:' + str(index),
                           'route_kind': 'external', 'route_reason': reason})
    return candidates


def native_unsupported(config, work_type, preferred, selected_host):
    """The capability that keeps a route off the native host, or None when the host can run it natively.

    Native needs delegation on (the role files then pin the tier's model), the work type allowed by
    ``native_allowed``, a preferred candidate on the selected host (a route naming the other vendor is a
    deliberate cross-vendor route and stays external) and a tier a role file pins, so the exact model is a
    configured one.
    """
    if not config['enabled']:
        return 'delegation-disabled'
    if not config.get('native_allowed', {}).get(work_type, True):
        return 'work-type-disabled'
    if preferred['harness'] not in ('selected', selected_host):
        return 'cross-vendor-route'
    if preferred.get('tier') not in ROLE_TIERS:
        return 'model-pin'
    return None


def external_candidates(candidates, attempts=()):
    """The external candidates of a route, each ``native-failed:pending`` reason resolved from the identity's
    latest native attempt (its failure category, else its status), or ``not-attempted`` when none exists."""
    native = [a for a in attempts if a.get('kind') == 'native']
    latest = max(native, key=lambda a: a.get('started_at') or '') if native else None
    category = (latest.get('failure_category') or latest.get('status') or 'unknown') if latest else 'not-attempted'
    return [{**c, 'route_reason': 'native-failed:' + category} if c.get('route_reason') == 'native-failed:pending'
            else c for c in candidates if c.get('route_kind') != 'native']


def stronger_candidate(config, prior, selected_host):
    """One escalation to a stronger configured tier, when one exists."""
    tier = prior.get('tier')
    stronger = {'light': 'standard', 'standard': 'high',
                'documentation': 'high', 'review': 'high'}.get(tier)
    if not stronger:
        return None
    harness = prior['harness'] if prior['harness'] in ('codex', 'claude') else selected_host
    if config['models'][harness][stronger] == prior['requested_model']:
        return None
    return {'harness': harness, 'requested_model': config['models'][harness][stronger],
            'tier': stronger, 'rule': 'stronger-retry:' + tier + '->' + stronger,
            'choice': 'reassignment', 'route_kind': 'external',
            'route_reason': prior.get('route_reason') or 'unknown'}


def read_policy(root):
    from workflow import load_policy
    return load_policy(root)


def active_host(root):
    from workflow import active_host as host
    return host(root)


def ledger_path(root, feature):
    path = (root / feature / 'workflow/delegations.json').resolve()
    require(path.is_relative_to(root.resolve() / 'specs') and
            path.parent.parent == (root / feature).resolve(), 'DELEGATION_FEATURE_INVALID')
    return path


def foreign_write_marker(root, feature):
    """Persisted, sticky record that a genuine ledger tamper was detected for
    this feature (round 3, finding 2). Distinct from the ordinary written
    marker: cleared only by an explicit ``delegate_dispatch.py trust-reset``,
    so a later legitimate dispatcher write (which rewrites the ordinary
    marker to match the file it just saved) can never quietly launder an
    earlier hand-edit back into looking trusted.
    """
    from workflow import digest
    return root / '.specify/workflow/runtime' / ('delegation-' + digest(feature) + '.tampered')


def trust_reset_log_path(root, feature):
    from workflow import digest
    return root / '.specify/workflow/runtime' / ('delegation-' + digest(feature) + '.trust-resets.json')


def record_foreign_write(root, feature):
    """Persist the sticky tamper flag once, keeping the first detection's own
    digest (round 3, finding 2). A no-op if already recorded, so a second
    detection before ``trust-reset`` does not overwrite the original evidence.
    """
    from datetime import datetime, timezone
    from workflow import write
    from delegate_dispatch import ledger_bytes_digest
    marker = foreign_write_marker(root, feature)
    if marker.is_file():
        return
    write(marker, {'detected_at': datetime.now(timezone.utc).isoformat(),
                   'digest_at_detection': ledger_bytes_digest(ledger_path(root, feature))})


def ledger_trust_state(root, feature):
    """Tri-state trust read for the delegation ledger (round 3, findings 1-2).

    ``'untrusted'``: a genuine tamper was detected and persisted
    (``foreign_write_marker``) and not yet cleared by ``trust-reset``, or the
    ordinary written marker exists but no longer matches the ledger's current
    bytes. Refused by ``complete`` and the Ready gate.

    ``'unverified-local'``: there is no ordinary written marker at all.
    Normal for a CI checkout or a fresh clone -- ``delegations.json`` is
    committed, but the marker lives in local-only runtime state -- and not
    itself suspicious; a warning, not a block. It resolves to ``'trusted'``
    on its own the first time a dispatcher operation writes the ledger on
    this checkout. This detects accidental and local tampering only: anyone
    who can commit the ledger file can also commit a fabricated one, so CI
    integrity ultimately rests on review, not on this check.

    ``'trusted'``: the marker exists and matches, and no unresolved tamper
    is on record.
    """
    from workflow import read
    from delegate_dispatch import ledger_bytes_digest, written_marker
    if foreign_write_marker(root, feature).is_file():
        return 'untrusted'
    recorded = read(written_marker(root, feature), {}).get('sha256')
    if recorded is None:
        return 'unverified-local'
    return 'trusted' if recorded == ledger_bytes_digest(ledger_path(root, feature)) else 'untrusted'


def latest_attempt(root, feature, identity):
    """The final attempt in the reassignment chain for one identity, else None.

    ``identity`` is the bare suffix after ``feature + '/'``: ``stage:<stage>``
    or a bare task id such as ``T001``. The newest ``started_at`` among
    same-identity attempts is the live thread's own start (an automatic
    stronger retry or a manual reassignment is a later, chained attempt), and
    following ``replacement_run_id`` from there reaches its terminal end. Used
    to enforce that a delegated stage or task was actually verified before
    ``complete`` or the Ready task gate accept it (finding 1).
    """
    path = ledger_path(root, feature)
    if not path.is_file():
        return None
    ledger = json.loads(path.read_text(encoding='utf-8'))
    full = feature + '/' + identity
    candidates = [a for a in ledger.get('attempts', []) if a.get('identity') == full and a.get('run_id')]
    if not candidates:
        return None
    current = max(candidates, key=lambda a: a.get('started_at') or '')
    seen = set()
    while current.get('replacement_run_id') and current['run_id'] not in seen:
        seen.add(current['run_id'])
        following = next((a for a in ledger['attempts']
                          if a.get('run_id') == current['replacement_run_id']), None)
        if following is None:
            break
        current = following
    return current


def ledger_attempts(root, feature):
    """Every attempt in a feature's ledger, or an empty list when it has none."""
    path = ledger_path(root, feature)
    return json.loads(path.read_text(encoding='utf-8')).get('attempts', []) if path.is_file() else []


# Work that checks other work: its author must not be the agent that wrote what it checks.
REVIEW_WORK_TYPES = ('review', 'qa_author', 'qa_collect')


def same_lineage_author(attempts, attempt):
    """The run id of a successful authoring attempt (any work type outside REVIEW_WORK_TYPES) of the same
    feature by the same agent as this review or QA attempt, else None."""
    # Same agent = same host agent id (the last lineage element); the optional parent id is ignored, so
    # supplying it on one recording and omitting it on the other cannot make the lineages differ.
    def agent(a):
        return (a.get('author_lineage') or [a.get('host_agent_id')])[-1]
    reviewer = agent(attempt)
    if attempt.get('task_type') not in REVIEW_WORK_TYPES or not reviewer:
        return None
    return next((a['run_id'] for a in attempts if a.get('run_id') != attempt.get('run_id') and
                 a.get('status') == 'successful' and a.get('task_type') not in REVIEW_WORK_TYPES and
                 agent(a) == reviewer), None)


def active_task_ids(root, feature):
    path = ledger_path(root, feature)
    active = set()
    if path.exists():
        ledger = json.loads(path.read_text(encoding='utf-8'))
        active.update(attempt['identity'].rsplit('/', 1)[-1]
                      for attempt in ledger.get('attempts', [])
                      if attempt.get('status') in ('starting', 'running'))
    progress = root / feature / 'workflow/progress/state.json'
    if progress.is_file():
        state = json.loads(progress.read_text(encoding='utf-8'))
        active.update(task['id'] for task in state.get('tasks', [])
                      if task.get('status') == 'running')
    return active


def annotate_tasks(root, feature, config, selected_host=None, lean=False):
    """Refresh pending task metadata without changing checkbox lines or active work."""
    validate_delegation(config)
    feature = feature_identity(root, feature)
    if not config['enabled']:
        return {'changed': False, 'annotated': 0, 'disabled': True}
    selected_host = selected_host or active_host(root)
    path = (root / feature / 'tasks.md').resolve()
    require(path.is_relative_to(root.resolve() / 'specs'), 'DELEGATION_FEATURE_INVALID')
    if not path.is_file():
        return {'changed': False, 'annotated': 0, 'missing_tasks': True}
    raw = path.read_bytes()
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    lines = raw.decode('utf-8-sig').splitlines(keepends=True)
    running = active_task_ids(root, feature)
    default_newline = '\r\n' if any(line.endswith('\r\n') for line in lines) else '\n'
    output = []
    annotated = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        body = line.rstrip('\r\n')
        ending = line[len(body):]
        joined = INLINE_MARKER.search(body) if TASK_LINE.match(body) else None
        if joined:
            # Repair a marker an earlier release appended to a final task line
            # that had no newline. That release also added the newline after the
            # marker, so at end of file the original unterminated ending returns.
            old_marker = '  ' + joined[1]
            marker_ending = ending if index < len(lines) else ''
            body, ending = body[:joined.start()], default_newline
        elif index < len(lines) and MARKER.match(lines[index].rstrip('\r\n')):
            old_marker = lines[index].rstrip('\r\n')
            marker_ending = lines[index][len(old_marker):]
            index += 1
        else:
            old_marker, marker_ending = None, ending
        match = TASK_LINE.match(body)
        if not match:
            output.append(line)
            continue
        task_id = match[3]
        if match[2].lower() == 'x' or task_id in running:
            output.append(body + ending)
            if old_marker is not None:
                output.append(old_marker + marker_ending)
            continue
        work_type = task_type(match[1], lean)
        try:
            route = selected_route(config, work_type, selected_host, feature + '/' + task_id)[0]
        except DelegationError as exc:
            if not str(exc).startswith('DELEGATION_REVIEW_ROUTE_UNSAFE'):
                raise
            # A refused review task still gets a marker, naming no harness: it runs in the selected host.
            route = {'harness': None, 'requested_model': None, 'rule': 'refused:DELEGATION_REVIEW_ROUTE_UNSAFE'}
        metadata = {'task_id': task_id, 'task_type': work_type,
                    'preferred_harness': route['harness'],
                    'preferred_model': route['requested_model'], 'rule': route['rule']}
        # A final task line without a newline gains one before its marker; the
        # marker then ends the file the same way the task line did.
        output.append(body + (ending or default_newline))
        output.append('  <!-- sanduq-delegation ' + json.dumps(metadata, sort_keys=True) + ' -->' +
                      marker_ending)
        annotated += 1
    content = ''.join(output)
    original = ''.join(lines)
    if content != original:
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_bytes(bom + content.encode('utf-8'))
        os.replace(temp, path)
    return {'changed': content != original, 'annotated': annotated, 'running_unchanged': sorted(running)}


SKILL_FILES = ('delegate.mjs', 'SKILL.md', 'contracts/result-schema-v2.md')
SKILL_ROOTS = ('.agents/skills', '.claude/skills', '.codex/skills')
# The driver contract this workflow depends on. A copy is reusable only when the
# driver itself reports these capabilities; files that merely exist prove nothing.
DRIVER_CONTRACT = 'delegate-task.driver.v1'
REQUIRED_CONTRACT = {
    'result_schema': 'delegate-task.result.v2',
    'commands': {'start', 'collect', 'doctor', 'contract'},
    'start_flags': {'--harness', '--task', '--cwd', '--model', '--sandbox', '--timeout', '--clean-env', '--keep-env',
                    '--constraint', '--allow-commit'},
    'collect_flags': {'--json'},
    'env': {'DELEGATE_RUNS_DIR'},
    'meta_fields': {'run_id', 'harness', 'model', 'constraint', 'permission', 'allow_commit'},
    'result_fields': {'run_id', 'harness', 'status', 'status_reason', 'status_provenance', 'summary',
                      'requested_model', 'actual_model', 'model_observed', 'tokens',
                      'dirty_paths_changed', 'head_changed', 'index_changed', 'coverage_complete',
                      'artifacts'},
}
INSTALL_LOCK_TIMEOUT = 180.0
# OMAR-07: what a managed project's copy of the vendored skill says about itself. The portable
# description ("have another agent do X") would let the model run the driver outside the ledger.
MANAGED_SKILL_DESCRIPTION = ('Driver that Sanduq delegate_dispatch.py runs for this workflow project; do not invoke it '
                             'directly here. To have another agent do a task, use the host\'s native subagents or '
                             'delegate_dispatch.py, which record the attempt in the ledger.')


def managed_skill_text(text):
    """The vendored SKILL.md as a project copy: the driver description and `disable-model-invocation: true`."""
    text = re.sub(r'^description:[^\r\n]*$', 'description: ' + MANAGED_SKILL_DESCRIPTION, text, count=1, flags=re.M)
    end = text.index('\n---', 1)  # the closing frontmatter fence
    return text[:end] + '\ndisable-model-invocation: true' + text[end:]


def local_skill_paths(root, host):
    agent = '.agents' if host == 'codex' else '.claude'
    return [root / agent / 'skills/delegate-task',
            global_root() / agent / 'skills/delegate-task',
            global_root() / ('.codex' if host == 'codex' else '.claude') / 'skills/delegate-task']


def global_root():
    return Path.home()


def is_junction(path):
    """True for a Windows directory junction, which ``is_symlink`` does not report.

    ``Path.is_junction`` only exists from Python 3.12; earlier versions read the
    reparse tag directly.
    """
    path = Path(path)
    if hasattr(path, 'is_junction'):
        return path.is_junction()
    if os.name != 'nt':
        return False
    try:
        return os.lstat(path).st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
    except (OSError, AttributeError):
        return False


def is_link(path):
    """A symlink or a Windows junction: an entry that points at a folder elsewhere."""
    return Path(path).is_symlink() or is_junction(path)


def driver_compatibility(node, driver):
    """Return None when the driver reports the required contract, else the reason."""
    try:
        result = subprocess.run([node, str(driver), 'contract'], capture_output=True, text=True,
                                encoding='utf-8', timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 'contract query failed: ' + str(exc)[:200]
    if result.returncode:
        return 'driver predates the contract command (exit ' + str(result.returncode) + ')'
    try:
        contract = json.loads(result.stdout)
    except ValueError:
        return 'contract output is not JSON'
    if not isinstance(contract, dict) or contract.get('contract') != DRIVER_CONTRACT:
        found = contract.get('contract') if isinstance(contract, dict) else None
        return 'contract ' + str(found) + ' is not ' + DRIVER_CONTRACT
    if contract.get('result_schema') != REQUIRED_CONTRACT['result_schema']:
        return ('result schema ' + str(contract.get('result_schema')) + ' is not ' +
                REQUIRED_CONTRACT['result_schema'])
    for key, required in REQUIRED_CONTRACT.items():
        if key == 'result_schema':
            continue
        missing = sorted(required - set(contract.get(key) or ()))
        if missing:
            return key + ' missing ' + ', '.join(missing)
    if (contract.get('exit_codes') or {}).get('collect_still_running') != 3:
        return 'collect does not report a running run with exit code 3'
    return None


def check_copy(folder, node):
    """Classify one installed copy as None (usable), 'broken' or an incompatibility reason."""
    driver = folder / 'delegate.mjs'
    if not all((folder / name).is_file() for name in SKILL_FILES):
        return 'broken', None
    if subprocess.run([node, '--check', str(driver)], capture_output=True).returncode:
        return 'broken', None
    reason = driver_compatibility(node, driver)
    return ('incompatible', reason) if reason else (None, None)


def inspect_skill(root, host):
    """Find the first usable project or global copy; report why others were rejected."""
    override = os.environ.get('SANDUQ_DELEGATE_DRIVER')
    candidates = ([Path(override).parent] if override else []) + local_skill_paths(root, host)
    plugin = os.environ.get('CLAUDE_PLUGIN_ROOT')
    if plugin:
        candidates.append(Path(plugin) / 'skills/delegate-task')
    broken, incompatible = [], []
    node = shutil.which('node')
    for folder in dict.fromkeys(candidates):
        if not folder.exists():
            continue
        if node is None:
            return {'ok': False, 'error': 'NODE_MISSING'}
        problem, reason = check_copy(folder, node)
        if problem == 'broken':
            broken.append(str(folder))
            continue
        if problem:
            incompatible.append({'path': str(folder), 'reason': reason})
            continue
        return {'ok': True, 'driver': str((folder / 'delegate.mjs').resolve()),
                'scope': 'project' if folder.is_relative_to(root) else 'global'}
    error = ('DELEGATE_SKILL_BROKEN' if broken else
             'DELEGATE_SKILL_INCOMPATIBLE' if incompatible else 'DELEGATE_SKILL_MISSING')
    return {'ok': False, 'error': error, 'broken': broken, 'incompatible': incompatible}


def bundled_skill():
    # Vendored from sanduq-skills (vendor.lock.json) in the source tree and shipped in the package.
    folder = Path(__file__).resolve().parents[1] / 'assets/delegate-task'
    return folder if folder.is_dir() else None


def backup_root(root, scope):
    """Backups live outside every skill discovery root, so no stale SKILL.md is found."""
    base = root if scope == 'project' else global_root()
    folder = (base / '.specify/workflow/backups/delegate-task' if scope == 'project' else
              base / '.sanduq/backups/delegate-task')
    resolved = folder.resolve()
    require(resolved.is_relative_to(base.resolve()) and
            not any(resolved.is_relative_to((base / skills).resolve()) for skills in SKILL_ROOTS),
            'DELEGATE_SKILL_BACKUP_PATH_INVALID')
    return folder


def move_aside(item, backups):
    """Move one directory entry, never its tree file by file, into a fresh backup slot."""
    backups.mkdir(parents=True, exist_ok=True)
    slot = backups / (item.name + '.' + uuid.uuid4().hex)
    try:
        item.rename(slot)
    except OSError as exc:
        # A single rename keeps every customised file together; never fall back
        # to a recursive copy-and-delete that could stop halfway.
        raise DelegationError('DELEGATE_SKILL_BACKUP_FAILED: ' + str(exc)) from exc
    return slot


def install_lock_path(root, scope):
    base = root / '.specify/workflow/runtime' if scope == 'project' else global_root() / '.sanduq/runtime'
    return base / 'delegate-skill-install.lock'


def legacy_backups(root):
    """Sibling backups earlier builds left inside skill discovery roots, by scope."""
    found = {'project': [], 'global': []}
    for scope, base in (('project', root), ('global', global_root())):
        for skills in SKILL_ROOTS:
            folder = base / skills
            if folder.is_dir():
                found[scope] += sorted(folder.glob('delegate-task.sanduq-backup-*'))
    return found


def move_legacy_backups(root, legacy):
    """Move each legacy backup to its own scope's backup root, never across scopes."""
    moved = []
    for scope, items in legacy.items():
        if not items:
            continue
        backups = backup_root(root, scope)
        if scope == 'project':
            from workflow import ensure_local_excludes
            ensure_local_excludes(root)
        for item in items:
            moved.append({'from': str(item), 'to': str(move_aside(item, backups))})
    return moved


def rejected_copies(status):
    """Normalise inspect_skill rejections to path/reason records."""
    return ([{'path': path, 'reason': 'broken: required files missing or driver fails node --check'}
             for path in status.get('broken') or []] + list(status.get('incompatible') or []))


def install_skill(root, host, scope, force_scope=False, upgrade_owner=None):
    """Reuse any usable copy; otherwise install the bundled skill at ``scope``.

    Installation, legacy backup moves and backup rollback run under a lock per
    scope, so concurrent dispatchers never interleave; a waiter re-inspects and
    reuses the copy the first one installed. ``force_scope`` refreshes the copy
    at ``scope`` even when a usable one exists. While an upgrade or install
    owns the project's managed files, only that upgrade or install may change a
    skill; everyone else is refused inside the project lock, which it drains.
    """
    require(scope in ('project', 'global'), 'DELEGATION_SCOPE_INVALID')
    legacy = legacy_backups(root)
    with contextlib.ExitStack() as stack:
        stack.enter_context(file_lock(install_lock_path(root, 'project'), INSTALL_LOCK_TIMEOUT,
                                      'DELEGATE_SKILL_INSTALL_BUSY'))
        require_no_maintenance(root, (os.getpid(), upgrade_owner))
        if scope == 'global' or legacy['global']:
            stack.enter_context(file_lock(install_lock_path(root, 'global'), INSTALL_LOCK_TIMEOUT,
                                          'DELEGATE_SKILL_INSTALL_BUSY'))
        return install_skill_locked(root, host, scope, force_scope)


def install_skill_locked(root, host, scope, force_scope):
    agent = '.agents' if host == 'codex' else '.claude'
    target_root = root if scope == 'project' else global_root()
    target = target_root / agent / 'skills/delegate-task'
    existing = inspect_skill(root, host)
    if existing.get('error') == 'NODE_MISSING':
        return existing
    # Earlier builds left sibling backups inside discovery roots; they leave
    # even when a usable copy is reused, so no stale SKILL.md stays visible.
    moved = move_legacy_backups(root, legacy_backups(root))
    notices = ['DELEGATE_SKILL_LEGACY_BACKUP_MOVED: ' + item['from'] + ' -> ' + item['to']
               for item in moved]
    if existing['ok'] and not force_scope:
        return {**existing, 'installed': False, 'legacy_backups_moved': moved, 'notices': notices}
    node = shutil.which('node')
    require(node is not None, 'NODE_MISSING')
    source = bundled_skill()
    require(source is not None and all((source / name).is_file() for name in SKILL_FILES),
            'DELEGATE_SKILL_PACKAGE_MISSING')
    target.parent.mkdir(parents=True, exist_ok=True)
    require(target.parent.resolve().is_relative_to(target_root.resolve()),
            'DELEGATE_SKILL_TARGET_OUTSIDE_SCOPE')
    if scope == 'project':
        from workflow import ensure_local_excludes
        ensure_local_excludes(root)
    backups = backup_root(root, scope)
    backups.mkdir(parents=True, exist_ok=True)
    # Build and verify the new copy outside the discovery root first, so a
    # failed or interrupted install never leaves a partial skill behind.
    staging = backups / ('.staging-' + uuid.uuid4().hex)
    try:
        # Runtime only (W7): the README images in assets/ and the READMEs stay in the package, not the skill folder.
        shutil.copytree(source, staging, ignore=shutil.ignore_patterns('test', 'runs', 'node_modules', 'assets', 'README*'))
        if scope == 'project':  # a global copy also serves standalone projects and keeps the portable text
            skill = staging / 'SKILL.md'
            skill.write_text(managed_skill_text(skill.read_text(encoding='utf-8')), encoding='utf-8')
        problem, reason = check_copy(staging, node)
        require(problem is None, 'DELEGATE_SKILL_INSTALL_FAILED: ' + str(reason or problem))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    rejected = {item['path']: item['reason'] for item in rejected_copies(existing)}
    # A dangling junction neither exists nor is a symlink, but it is still the
    # user's entry: move the link itself aside so a failure can put it back.
    dangling = is_link(target) and not target.exists()
    backup = move_aside(target, backups) if target.exists() or is_link(target) else None
    placed = False
    try:
        staging.rename(target)
        placed = True
        require(all((target / name).is_file() for name in SKILL_FILES), 'DELEGATE_SKILL_INSTALL_FAILED')
    except Exception:
        # Only the copy this call put in place is removed. Anything still at the
        # target after a failed rename belongs to someone else and stays.
        if placed and not is_link(target) and target.exists():
            require(target.resolve().is_relative_to(target_root.resolve()),
                    'DELEGATE_SKILL_ROLLBACK_OUTSIDE_SCOPE')
            shutil.rmtree(target)
        shutil.rmtree(staging, ignore_errors=True)
        if backup is not None and not os.path.lexists(target):
            backup.rename(target)
        raise
    replaced = None
    if backup is not None:
        replaced = [{'path': str(target), 'backup': str(backup),
                     'reason': rejected.get(str(target), 'dangling link' if dangling else
                                            'replaced at the configured scope')}]
        notices.append('DELEGATE_SKILL_REPLACED: ' + str(target) + ' (' + replaced[0]['reason'] +
                       ') was moved to ' + str(backup) + '; carry any local customisation '
                       'into the new copy by hand')
    return {'ok': True, 'driver': str((target / 'delegate.mjs').resolve()), 'scope': scope,
            'installed': True, 'backup': str(backup) if backup else None,
            'replaced': replaced, 'rejected': rejected_copies(existing) or None,
            'legacy_backups_moved': moved, 'notices': notices}


def owned_scope(root, host, driver):
    """The scope whose Sanduq install location holds ``driver``, else None.

    Only a real folder at the project or global location Sanduq installs to is
    Sanduq's to refresh. A driver override, a plugin copy, another discovery
    root or a symlinked or junctioned folder belongs to someone else.
    """
    agent = '.agents' if host == 'codex' else '.claude'
    folder = Path(driver).resolve().parent
    for scope, base in (('project', root), ('global', global_root())):
        location = base / agent / 'skills/delegate-task'
        if not is_link(location) and location.is_dir() and location.resolve() == folder:
            return scope
    return None


def health_error(status):
    """The failure code, with the failing copy and next action when doctor names them."""
    error = status.get('error', 'DELEGATE_SKILL_UNAVAILABLE')
    return error + ': ' + status['path'] + ': ' + status['action'] if status.get('action') else error


DOCTOR_TIMEOUT = 15  # seconds per node probe: claim and start run doctor under the dispatch lock (SAMY-02)
DOCTOR_RETRY = 'python .specify/extensions/workflow/scripts/delegation.py doctor'


class DoctorTimeout(DelegationError):
    pass


DOCTOR_NEXT = ('check that node and the delegate-task driver respond on this machine, then run "' +
               DOCTOR_RETRY + '"')


def doctor_probe(args, **kwargs):
    try:
        return sanduq_fs.run_bounded(args, timeout=DOCTOR_TIMEOUT, error_code='DELEGATE_DOCTOR_TIMEOUT',
                                     error=DoctorTimeout, next_step=DOCTOR_NEXT, capture_output=True, text=True,
                                     **kwargs)
    except DoctorTimeout as exc:
        exc.command = ' '.join(map(str, args))
        raise


def doctor(root, host, install=False, scope='project', upgrade_owner=None):
    try:
        return _doctor(root, host, install, scope, upgrade_owner)
    except DoctorTimeout as exc:
        return {'ok': False, 'error': 'DELEGATE_DOCTOR_TIMEOUT', 'path': exc.command, 'diagnostic': str(exc),
                'action': 'it did not finish within ' + str(DOCTOR_TIMEOUT) + ' s and was stopped; ' + DOCTOR_NEXT}


def _doctor(root, host, install, scope, upgrade_owner):
    node = shutil.which('node')
    if not node:
        return {'ok': False, 'error': 'NODE_MISSING'}
    probe = doctor_probe([node, '--version'])
    version = re.search(r'v?(\d+)', probe.stdout)
    if probe.returncode or not version or int(version[1]) < 18:
        return {'ok': False, 'error': 'NODE_18_REQUIRED'}
    status = (install_skill(root, host, scope, upgrade_owner=upgrade_owner) if install
              else inspect_skill(root, host))
    if not status['ok']:
        return status
    result = doctor_probe([node, status['driver'], 'doctor'], cwd=root, encoding='utf-8')
    refresh = owned_scope(root, host, status['driver'])
    if result.returncode and install and not status.get('installed') and refresh:
        # Refresh the copy that failed, where it is. Installing at the
        # configured scope instead would leave the failing copy first in the
        # search order, and every later dispatch would replace the other one.
        first = status
        status = install_skill(root, host, refresh, force_scope=True, upgrade_owner=upgrade_owner)
        status['notices'] = (first.get('notices') or []) + (status.get('notices') or [])
        result = doctor_probe([node, status['driver'], 'doctor'], cwd=root, encoding='utf-8')
    if result.returncode:
        owned = owned_scope(root, host, status['driver']) is not None
        action = ('the copy was refreshed from the bundle and still fails; inspect the diagnostic'
                  if status.get('installed') else
                  'run "python .specify/extensions/workflow/scripts/delegation.py install" to refresh it'
                  if owned else
                  'Sanduq does not own this copy (a driver override, plugin, symlinked folder or '
                  'another discovery root) and will not replace it; repair it, or remove it so a '
                  'Sanduq install is used')
        return {**status, 'ok': False, 'error': 'DELEGATE_SKILL_DOCTOR_FAILED',
                'path': str(Path(status['driver']).resolve().parent), 'owned': owned,
                'action': action, 'diagnostic': result.stderr.strip() or result.stdout.strip()}
    available = {}
    cli_errors = {}
    for harness in ('codex', 'claude'):
        line = next((line for line in result.stdout.splitlines()
                     if re.match(r'^' + harness + r'\s', line)), '')
        if not line or 'NOT FOUND on PATH' in line:
            cli_errors[harness] = 'AGENT_CLI_MISSING'
        elif 'UNDECODABLE SHIM' in line or 'BROKEN:' in line:
            cli_errors[harness] = 'AGENT_CLI_BROKEN'
        available[harness] = harness not in cli_errors
    return {**status, 'node': probe.stdout.strip(), 'harnesses': available,
            'cli_errors': cli_errors, 'diagnostic': result.stdout.strip()}


HEALTH_CACHE = '.specify/workflow/runtime/delegation-health.json'
HEALTH_TTL = 3600  # seconds; longer than one model stage, so consecutive claims reuse one probe


def health_key(root, host, scope, driver):
    """What a green probe is valid for: host, scope, overrides, the driver copy's bytes and the node/codex/claude
    executables (path, size, mtime). A CLI that loses its login inside the TTL is found at dispatch start."""
    files = {}
    for name in SKILL_FILES:
        path = Path(driver).parent / name if driver else None
        files[name] = sha256_file(path) if path and path.is_file() else None
    tools = {}
    for name in ('node', 'codex', 'claude'):
        found = shutil.which(name)
        try:
            info = os.stat(found) if found else None
        except OSError:
            info = None
        tools[name] = [found, info.st_size, info.st_mtime_ns] if info else [found]
    return {'host': host, 'scope': scope, 'driver': driver, 'files': files, 'tools': tools,
            'override': os.environ.get('SANDUQ_DELEGATE_DRIVER'), 'plugin': os.environ.get('CLAUDE_PLUGIN_ROOT')}


def forget_health(root):
    (Path(root) / HEALTH_CACHE).unlink(missing_ok=True)


def cached_health(root, host, scope):
    """`doctor(install=True)` for a claim (W6): a green result with an available CLI is kept for HEALTH_TTL and
    reused while its key holds. A miss, a red result or a driver start failure probes again; `doctor` always does."""
    path = Path(root) / HEALTH_CACHE
    try:
        cached = json.loads(path.read_text(encoding='utf-8'))
        driver = cached['result'].get('driver')
        if (0 <= time.time() - cached['at'] < HEALTH_TTL
                and cached['key'] == health_key(root, host, scope, driver)):
            return {**cached['result'], 'cached': True, 'notices': []}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    result = doctor(root, host, install=True, scope=scope)
    if result.get('ok') and any((result.get('harnesses') or {}).values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = {key: value for key, value in result.items() if key != 'notices'}
        path.write_text(json.dumps({'at': time.time(), 'key': health_key(root, host, scope, result.get('driver')),
                                    'result': stored}), encoding='utf-8')
    else:
        forget_health(root)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('doctor', 'install', 'annotate', 'route'):
        command = sub.add_parser(action)
        if action in ('annotate', 'route'):
            command.add_argument('--feature', required=True)
        if action == 'route':
            command.add_argument('--id', required=True)
            command.add_argument('--type', choices=TYPES, required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        policy = read_policy(root)
        config = policy['delegation']
        host = active_host(root)
        if args.action in ('doctor', 'install'):
            result = doctor(root, host, args.action == 'install', config['install_scope'])
        elif args.action == 'annotate':
            import lean_policy
            result = annotate_tasks(root, args.feature, config, host, lean_policy.enabled(
                policy, lean_policy.feature_tier(root, feature_identity(root, args.feature))))
        else:
            # The same specs/<name> identity the dispatcher and overrides use.
            require(re.fullmatch(r'T\d{3,}|stage:[a-z_]+', args.id), 'DELEGATION_IDENTITY_INVALID')
            identity = feature_identity(root, args.feature) + '/' + args.id
            result = {'enabled': config['enabled'], 'identity': identity, 'type': args.type,
                      'candidates': selected_route(config, args.type, host, identity) if config['enabled'] else []}
        print(json.dumps(result, indent=2))
        return 0 if result.get('ok', True) else 1
    except (DelegationError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
