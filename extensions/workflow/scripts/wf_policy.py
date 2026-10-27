"""Workflow policy: defaults, validation, tiers, the stage order, side effects and policy cutoffs."""
from __future__ import annotations

import copy
import difflib
import re
import sanduq_ci
import skill_inventory
import lean_policy
import verification_plan
import yaml
from pathlib import Path
from wf_core import (SCHEMA, BASE_STAGES, RECEIPT_POLICY_KEYS, DEFAULT_PROFILES, LITE_SKIPPED, ARTIFACT_BUDGETS,
                     ARTIFACT_ENFORCE, PROJECT_SYNC_PHASES, PROJECT_SYNC_POINTS, DEFAULT_SYNC_STATE, TASK_ISSUE_MODES,
                     PROJECT_SYNC_MODES, MINIMAL_SYNC_PHASES, SIDE_EFFECTS, WORKFLOW_SCRIPT, WorkflowError, require,
                     portable_label)
from wf_fingerprints import sync_state_label


def default_policy(qa, manual):
    require(type(qa) is bool and type(manual) is bool, 'Select QA and User Manual explicitly.')
    from delegation import DEFAULT_TIERS
    return {'schema_version': SCHEMA, 'processes': {'qa': qa, 'user_manual': manual},
            'execution': {'engine': 'auto', 'checkpoints': 'required-only'},
            'providers': {'clarification': 'prefer-superspec', 'tasks': 'prefer-superspec'},
            'issue_sync': {'taskstoissues': 'required', 'parent_link': 'native-subissue'},
            'clarification': {'transport': 'github-comments', 'resume_on_reinvoke': 'reread-answers'},
            'decisions': {'transport': 'github-issue', 'authorized_users': [],
                          'project_field': 'Decision', 'lifecycle_status': True},
            'context': {'mode': 'measured-only', 'max_fraction': .60,
                        'checkpoint_fraction': .50, 'reserve_fraction': .10},
            'finalize': {'create_pr': True, 'merge': False}, 'updates': {'policy': 'reviewed'},
            'delegation': {
                'enabled': False, 'install_scope': 'project', 'stronger_retry': 1,
                'models': {
                    'codex': {'high': 'gpt-6-astra', 'standard': 'gpt-6-sol', 'light': 'gpt-6-terra',
                              'documentation': 'gpt-6-sol', 'review': 'gpt-6-sol'},
                    'claude': {'high': 'opus', 'standard': 'sonnet', 'light': 'haiku',
                               'documentation': 'opus', 'review': 'opus'},
                },
                'routes': {
                    name: {'preferred': {'harness': 'selected', 'tier': tier},
                           'fallbacks': [{'harness': 'selected', 'model': None}]}
                    for name, tier in DEFAULT_TIERS.items()
                },
                'overrides': {},
                'fixed_collection_commands': {},
            },
            'receipts': {'require_input_roles': False},
            'ci': sanduq_ci.default_ci()}


def select_gate(ci, mode=None, scope=None, rules=(), keys=None):
    """Apply explicit gate choices while preserving unmentioned project settings.

    `keys` sets optional gate keys (`affected_command`, `verification_check`,
    `verify_command`); None leaves one unchanged and "none" removes it.
    """
    keys = {name: value for name, value in (keys or {}).items() if value is not None}
    if mode is None and scope is None and not rules and not keys:
        return ci
    gate = copy.deepcopy(sanduq_ci.gate_config(ci))
    for name, value in keys.items():
        if value.strip().lower() == 'none':
            gate.pop(name, None)
        else:
            gate[name] = value
    if mode is not None:
        gate['mode'] = mode
    if scope is not None:
        gate['scope'] = scope
    for selection in rules:
        name, separator, value = selection.partition('=')
        require(separator and name in sanduq_ci.GATE_RULES and value in ('on', 'off'),
                'CI_GATE_RULE_SELECTION_INVALID: expected name=on|off')
        gate['rules'][name] = value == 'on'
    sanduq_ci.validate_gate(gate)
    ci['gate'] = gate
    return ci


# AHMED-03: the keys of `.specify/workflow.yml` (None: the top level) and of each fixed-schema section. A misspelt
# key would otherwise be ignored, or change a section and invalidate receipts. `delegation`, `ci` and
# `lean_execution` check their own keys; `receipts` and `skills.inventory_thresholds` already refuse unknown ones.
POLICY_KEYS = {
    None: ('schema_version', 'processes', 'execution', 'providers', 'issue_sync', 'clarification', 'decisions',
           'context', 'finalize', 'updates', 'delegation', 'receipts', 'ci', 'skills', 'progress', 'illustrate',
           'scope', 'profiles', 'artifacts', 'project_sync', 'lean_execution'),
    'processes': ('qa', 'user_manual'),
    'execution': ('engine', 'checkpoints'),
    'providers': ('clarification', 'tasks'),
    'issue_sync': ('taskstoissues', 'parent_link'),
    'clarification': ('transport', 'resume_on_reinvoke', 'max_questions_per_round', 'in_session_first_round'),
    'decisions': ('transport', 'authorized_users', 'project_field', 'lifecycle_status'),
    'context': ('mode', 'max_fraction', 'checkpoint_fraction', 'reserve_fraction'),
    'finalize': ('create_pr', 'merge'),
    'updates': ('policy',),
    'skills': ('inventory_thresholds',),
    'progress': ('hook_wiring', 'post_tool_matcher'),
    'illustrate': ('hooks',),
    'illustrate.hooks': ('self_check',),
    'scope': ('statuses', 'keep_together', 'board_cache_seconds', 'artifact_directory', 'plan_file'),
    'profiles': ('enabled', 'lite', 'standard'),
    'profiles.lite': ('max_score',),
    'profiles.standard': ('max_score',),
    'artifacts': ('budgets', 'enforce'),
    'artifacts.budgets': tuple(ARTIFACT_BUDGETS),
    'project_sync': ('points', 'mode'),
}


def unknown_policy_key(policy):
    """POLICY_KEY_UNKNOWN for the first key no fixed-schema section defines, with the closest known key."""
    for section, allowed in POLICY_KEYS.items():
        value = policy
        for part in (section.split('.') if section else ()):
            value = value.get(part) if isinstance(value, dict) else None
        if not isinstance(value, dict):
            continue  # an absent or malformed section is its own validator's error
        for key in value:
            if key in allowed:
                continue
            path = (section + '.' if section else '') + str(key)
            close = difflib.get_close_matches(str(key), allowed, n=1)
            raise WorkflowError(
                'POLICY_KEY_UNKNOWN: ' + path + '; ' + ('did you mean ' + (section + '.' if section else '') + close[0]
                                                        + '?' if close else 'no similar key exists.') +
                ' Allowed keys' + (' of ' + section if section else ' at the top level') + ': ' + ', '.join(allowed) +
                '. Fix .specify/workflow.yml; if the key comes from a newer Workflow release, upgrade this project '
                'with "python .specify/extensions/workflow/scripts/upgrade.py --version <that version> --apply"')


def validate_policy(policy, root=None):
    require(isinstance(policy, dict) and policy.get('schema_version') == SCHEMA, 'POLICY_SCHEMA_UNSUPPORTED')
    unknown_policy_key(policy)
    if 'lean_execution' in policy:
        try:
            lean_policy.validate(policy['lean_execution'])
            for key in ('verification_plan', 'preflight_manifest', 'scope_analysis'):
                if policy['lean_execution'].get(key):
                    verification_plan.file_path(Path(root) if root is not None else Path.cwd(), policy['lean_execution'][key])
        except ValueError as exc:
            raise WorkflowError(str(exc)) from exc
    for section in ('processes','execution','providers','issue_sync','clarification','context','finalize','updates'):
        require(isinstance(policy.get(section), dict), 'POLICY_SECTION_INVALID: ' + section)
    for key in ('qa', 'user_manual'):
        require(type(policy.get('processes', {}).get(key)) is bool, 'POLICY_SELECTION_REQUIRED: ' + key)
    require(policy.get('execution', {}).get('engine') in ('auto', 'speckit', 'superspec'), 'EXECUTOR_UNSUPPORTED')
    require(policy.get('execution', {}).get('checkpoints') in ('required-only', 'every-phase'), 'CHECKPOINT_POLICY_INVALID')
    for key in ('clarification', 'tasks'):
        require(policy.get('providers', {}).get(key) in ('prefer-superspec', 'core', 'superspec'), 'PROVIDER_POLICY_INVALID: ' + key)
    context = policy.get('context', {})
    require(context.get('mode') in ('strict', 'measured-only', 'measured-with-estimated-fallback'), 'CONTEXT_MODE_INVALID')
    cap, checkpoint, reserve = (context.get(k) for k in ('max_fraction', 'checkpoint_fraction', 'reserve_fraction'))
    require(all(type(v) in (int, float) for v in (cap, checkpoint, reserve)), 'CONTEXT_LIMIT_INVALID')
    require(0 < checkpoint < cap <= .60 and 0 < reserve < cap, 'CONTEXT_LIMIT_INVALID')
    issue_sync = policy.get('issue_sync', {})
    require(set(issue_sync) == {'taskstoissues', 'parent_link'} and issue_sync['taskstoissues'] in TASK_ISSUE_MODES
            and issue_sync['parent_link'] == 'native-subissue', 'TASK_ISSUES_REQUIRED')
    validate_front_half_policy(policy)
    require(policy.get('finalize') == {'create_pr': True, 'merge': False}, 'FINALIZE_POLICY_INVALID')
    require(policy.get('clarification', {}).get('resume_on_reinvoke') in ('reread-answers', 'manual-status'), 'CLARIFICATION_POLICY_INVALID')
    # Older consumer policies remain valid and opt out until the project selects delegation.
    if 'delegation' not in policy:
        policy['delegation'] = copy.deepcopy(default_policy(False, False)['delegation'])
    from delegation import migrate_qa_route, validate_delegation
    # Pre-1.7 policies predate fixed_collection_commands; empty means no stage
    # is ever inferred as qa_collect, matching today's behaviour exactly.
    policy['delegation'].setdefault('fixed_collection_commands', {})
    # Pre-1.7 policies routed everything QA-shaped through a single ``qa`` key;
    # read in place as qa_author, with a fresh light-eligible qa_collect added.
    migrate_qa_route(policy['delegation'])
    try:
        validate_delegation(policy['delegation'])
    except ValueError as exc:
        raise WorkflowError(str(exc)) from exc
    decisions = policy.get('decisions')
    if decisions is not None:
        require(isinstance(decisions, dict) and decisions.get('transport') == 'github-issue',
                'DECISION_POLICY_INVALID')
        users = decisions.get('authorized_users')
        require(isinstance(users, list) and all(isinstance(user, str) and user.strip() for user in users)
                and len({user.casefold() for user in users}) == len(users), 'DECISION_AUTHORITY_INVALID')
        require(isinstance(decisions.get('project_field'), str) and decisions['project_field'].strip(),
                'DECISION_FIELD_INVALID')
        require(type(decisions.get('lifecycle_status', True)) is bool, 'DECISION_LIFECYCLE_INVALID')
    # Optional and never filled in: an older policy keeps its digest.
    receipts = policy.get('receipts')
    if receipts is not None:
        require(isinstance(receipts, dict) and all(
            key in RECEIPT_POLICY_KEYS and type(value) is RECEIPT_POLICY_KEYS[key]
            for key, value in receipts.items()), 'RECEIPTS_POLICY_INVALID')
    skills = policy.get('skills')
    if skills is not None:
        require(isinstance(skills, dict), 'POLICY_SECTION_INVALID: skills')
        overrides = skills.get('inventory_thresholds')
        if overrides is not None:
            require(isinstance(overrides, dict) and overrides
                    and set(overrides) <= set(skill_inventory.DEFAULT_THRESHOLDS)
                    and all(type(value) is int and value > 0 for value in overrides.values()),
                    'SKILL_INVENTORY_THRESHOLDS_INVALID: expected positive integers for '
                    + ', '.join(sorted(skill_inventory.DEFAULT_THRESHOLDS)))
    # Read by the progress and illustrate extensions (PyYAML); absent keys keep today's behaviour.
    progress = policy.get('progress')
    if progress is not None:
        require(isinstance(progress, dict) and set(progress) <= {'hook_wiring', 'post_tool_matcher'}
                and progress.get('hook_wiring', 'speckit') in ('speckit', 'native')
                and isinstance(progress.get('post_tool_matcher', ''), str),
                'PROGRESS_POLICY_INVALID: hook_wiring is speckit or native; post_tool_matcher is a string')
    illustrate = policy.get('illustrate')
    if illustrate is not None:
        hooks = illustrate.get('hooks', {}) if isinstance(illustrate, dict) else None
        require(isinstance(illustrate, dict) and set(illustrate) <= {'hooks'} and isinstance(hooks, dict)
                and set(hooks) <= {'self_check'} and type(hooks.get('self_check', False)) is bool,
                'ILLUSTRATE_POLICY_INVALID: hooks.self_check is a boolean')
    scope = policy.get('scope', {})
    require(isinstance(scope, dict), 'POLICY_SECTION_INVALID: scope')
    status_names = scope.get('statuses', {})
    require(isinstance(status_names, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in status_names.items())
            and len(set(status_names.values())) == len(status_names), 'SCOPE_STATUS_MAPPING_INVALID')
    # A project written before CI selection existed keeps its current behaviour:
    # the shipped GitHub-hosted default is filled in rather than rejected.
    if 'ci' not in policy:
        legacy_ci = sanduq_ci.default_ci()
        legacy_ci.pop('gate')
        policy['ci'] = legacy_ci
    try:
        sanduq_ci.validate_ci(policy['ci'])
    except sanduq_ci.CIPolicyError as exc:
        raise WorkflowError(str(exc)) from exc
    band = scope.get('keep_together')
    if band:
        require(isinstance(band, dict), 'SCOPE_BAND_INVALID')
        require(type(band.get('target')) in (int, float) and type(band.get('tolerance')) in (int, float), 'SCOPE_BAND_INVALID')
        require(band['target'] >= 0 and band['tolerance'] >= 0 and bool(band.get('unit')), 'SCOPE_UNIT_REQUIRED')
        require(band.get('inclusive') is True, 'SCOPE_BAND_MUST_BE_INCLUSIVE')
    return policy


def _positive(value):
    return type(value) is int and value > 0


def validate_front_half_policy(policy):
    """Profiles, clarification caps, artifact budgets, Project Sync points and the board cache.

    Every key is optional; an absent one keeps the earlier behaviour."""
    profiles = policy.get('profiles')
    if profiles is not None:
        require(isinstance(profiles, dict) and set(profiles) <= {'enabled', 'lite', 'standard'}
                and type(profiles.get('enabled')) is bool, 'PROFILES_POLICY_INVALID: expected {enabled, lite, standard}')
        bands = {}
        for name in ('lite', 'standard'):
            band = profiles.get(name, DEFAULT_PROFILES[name])
            require(isinstance(band, dict) and set(band) == {'max_score'} and _positive(band['max_score']),
                    'PROFILES_POLICY_INVALID: ' + name + ' expects {max_score: positive integer}')
            bands[name] = band['max_score']
        require(bands['lite'] < bands['standard'], 'PROFILES_POLICY_INVALID: lite.max_score must be below standard.max_score')
    clarification = policy.get('clarification', {})
    if 'max_questions_per_round' in clarification:
        require(_positive(clarification['max_questions_per_round']), 'CLARIFICATION_POLICY_INVALID: max_questions_per_round')
    if 'in_session_first_round' in clarification:
        require(type(clarification['in_session_first_round']) is bool, 'CLARIFICATION_POLICY_INVALID: in_session_first_round')
    artifacts = policy.get('artifacts')
    if artifacts is not None:
        require(isinstance(artifacts, dict) and set(artifacts) <= {'budgets', 'enforce'}, 'ARTIFACTS_POLICY_INVALID')
        budgets = artifacts.get('budgets', {})
        require(isinstance(budgets, dict) and set(budgets) <= set(ARTIFACT_BUDGETS)
                and all(_positive(value) for value in budgets.values()),
                'ARTIFACTS_POLICY_INVALID: budgets expects positive integers for ' + ', '.join(ARTIFACT_BUDGETS))
        require(artifacts.get('enforce', 'lite-standard') in ARTIFACT_ENFORCE,
                'ARTIFACTS_POLICY_INVALID: enforce is one of ' + ', '.join(ARTIFACT_ENFORCE))
    project_sync = policy.get('project_sync')
    if project_sync is not None:
        require(isinstance(project_sync, dict) and set(project_sync) <= {'points', 'mode'}, 'PROJECT_SYNC_POLICY_INVALID')
        points = project_sync.get('points')
        require(points is None or (isinstance(points, list) and set(points) <= set(PROJECT_SYNC_POINTS)
                                   and len(set(points)) == len(points)),
                'PROJECT_SYNC_POLICY_INVALID: points is a list of ' + ', '.join(PROJECT_SYNC_POINTS))
        require(project_sync.get('mode', 'full') in PROJECT_SYNC_MODES,
                'PROJECT_SYNC_POLICY_INVALID: mode is one of ' + ', '.join(PROJECT_SYNC_MODES))
    scope = policy.get('scope')
    if isinstance(scope, dict) and 'board_cache_seconds' in scope:
        value = scope['board_cache_seconds']
        require(type(value) is int and value >= 0, 'SCOPE_BOARD_CACHE_INVALID: expected seconds >= 0 (0 disables)')


def tier(policy, score):
    """The profile tier for an effort score: `full` unless profiles are enabled and the score fits a band."""
    profiles = policy.get('profiles') or {}
    if not profiles.get('enabled') or score is None:
        return 'full'
    for name in ('lite', 'standard'):
        if score <= profiles.get(name, DEFAULT_PROFILES[name])['max_score']:
            return name
    return 'full'


def state_tier(state):
    """The tier frozen into a checkpoint at the first Plan claim, else None (the full stage list)."""
    return ((state or {}).get('profile') or {}).get('tier')


def feature_tier(root, feature):
    """The frozen tier read from a feature's checkpoint, for callers that hold no state."""
    return lean_policy.feature_tier(root, feature)


def skipped_stages(policy, tier_name):
    """Stages the tier or the board mode does not run, with the reason recorded in the checkpoint and the log."""
    skipped = {}
    if task_issue_mode(policy) == 'off':
        skipped['taskstoissues'] = 'issue_sync.taskstoissues: off'
    if tier_name in ('lite', 'standard'):
        skipped['tasks'] = 'merged into plan (' + tier_name + ' tier)'
    if tier_name == 'lite':
        skipped.update({stage: 'lite tier' for stage in LITE_SKIPPED if stage in stages(policy)})
    return skipped


def project_sync_mode(policy):
    return (policy.get('project_sync') or {}).get('mode', 'full')


def sync_phases(policy):
    """Stage -> Project Sync phase the board mode writes. Minimal keeps the tracked phases (`done` is post-merge)
    and, with Tasks-to-Issues off, writes `ready` after Analyze instead; off writes nothing."""
    mode = project_sync_mode(policy)
    if mode == 'off':
        return {}
    if mode == 'full':
        return dict(PROJECT_SYNC_PHASES)
    phases = {stage: phase for stage, phase in PROJECT_SYNC_PHASES.items() if phase in MINIMAL_SYNC_PHASES}
    if task_issue_mode(policy) == 'off':
        phases = {'analyze': 'ready', **{s: p for s, p in phases.items() if s != 'taskstoissues'}}
    return phases


def sync_phase_written(policy, phase):
    """Whether `project-sync --phase <phase>` writes the board under the mode (else it is recorded as skipped)."""
    mode = project_sync_mode(policy)
    return mode == 'full' or (mode == 'minimal' and phase in MINIMAL_SYNC_PHASES)


def board_mode_line(policy):
    """Doctor's one line naming the board mode."""
    mode = project_sync_mode(policy)
    what = {'full': 'every phase is written to the board',
            'minimal': 'only Ready, In progress, In review and Done are written',
            'off': 'no board; nothing is written'}[mode]
    tasks = task_issue_mode(policy)
    return (mode + ': ' + what + '; ' + ('no task sub-issues' if tasks == 'off' else 'task sub-issues ' + tasks) +
            ' (project_sync.mode ' + mode + ', issue_sync.taskstoissues ' + tasks + ')')


def project_sync(policy, stage, feature='<feature>'):
    """The claim's Project Sync field: `{phase, command}` at a `project_sync.points` stage the mode writes, else
    False."""
    phase = sync_phases(policy).get(stage)
    if not phase or stage not in (policy.get('project_sync') or {}).get('points', PROJECT_SYNC_POINTS):
        return False
    return {'phase': phase, 'command': WORKFLOW_SCRIPT + ' project-sync --feature ' + feature + ' --phase ' + phase}


def task_issue_mode(policy):
    return policy['issue_sync']['taskstoissues']


def side_effects(policy, feature, stage, root=None):
    """The concrete side-effect globs for a stage; phase-lazy issue sync lets Execute extend the mapping. With
    `root`, the Project Sync state is the configured file."""
    paths = [path.replace('<feature>', feature) for path in SIDE_EFFECTS.get(stage, [])]
    if root is not None:
        paths = [sync_state_label(root) if path == DEFAULT_SYNC_STATE else path for path in paths]
    if stage == 'execute' and task_issue_mode(policy) == 'phase-lazy':
        paths.append(feature + '/workflow/task-issues.json')
    return paths


def matches_side_effect(path, patterns):
    path = portable_label(path)
    return any(re.fullmatch(re.escape(pattern).replace(r'\*', '[^/]*'), path) for pattern in patterns)


class PolicyLoader(yaml.SafeLoader):
    """AHMED-04: a duplicated key (a README section pasted below an existing one) is refused with its line instead
    of silently replacing the first mapping."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            require(key not in seen, 'POLICY_DUPLICATE_KEY: ' + str(key) + ' at line ' + str(key_node.start_mark.line + 1)
                    + ' of .specify/workflow.yml repeats an earlier ' + str(key) + ' key; merge the two into the '
                    'existing section (the second would silently replace the first)')
            seen.add(key)
        return super().construct_mapping(node, deep)


def parse_policy(text):
    return yaml.load(text, Loader=PolicyLoader)


def load_policy(root):
    path = root / '.specify/workflow.yml'
    require(path.is_file(), 'WORKFLOW_INIT_REQUIRED')
    return validate_policy(parse_policy(path.read_text(encoding='utf-8-sig')), root)


def stages(policy, tier=None):
    """The selected stage order; a lite or standard tier merges Tasks into Plan, lite also drops QA/manual stages,
    and `issue_sync.taskstoissues: off` drops Tasks-to-Issues."""
    selected = [s for s in BASE_STAGES if not (s.startswith('qa_') and not policy['processes']['qa'])
                and not (s.startswith('manual_') and not policy['processes']['user_manual'])
                and not (s == 'taskstoissues' and (policy.get('issue_sync') or {}).get('taskstoissues') == 'off')]
    if tier in ('lite', 'standard'):
        selected = [s for s in selected if s != 'tasks' and not (tier == 'lite' and s in LITE_SKIPPED)]
    return selected


# Sub-keys that tune how future work runs (a cache TTL, a question cap, the board mode) and never change what
# finished evidence means; a change to them alone reaches no stage (AHMED-30: switching `issue_sync.taskstoissues`
# or `project_sync.mode` on a feature in flight invalidates nothing).
OPERATIONAL_SUBKEYS = {'scope': ('board_cache_seconds',),
                       'clarification': ('max_questions_per_round', 'in_session_first_round'),
                       'issue_sync': ('taskstoissues',)}


def policy_cutoff(previous, current):
    if not previous: return 0
    affected = []
    def section(policy, key):
        value = policy.get(key)
        if isinstance(value, dict) and key in OPERATIONAL_SUBKEYS:
            value = {k: v for k, v in value.items() if k not in OPERATIONAL_SUBKEYS[key]} or None
        return value
    # `project_sync` only places board updates, like `context`, so it reaches no stage.
    for key, stage in {'scope':'scope','clarification':'clarify','decisions':'clarify','providers':'clarify',
                       'profiles':'plan','processes':'tasks','artifacts':'analyze',
                       'issue_sync':'taskstoissues','execution':'execute',
                       'finalize':'ready', 'lean_execution':'execute'}.items():
        if section(previous, key) != section(current, key): affected.append(BASE_STAGES.index(stage))
    # Context, update scheduling and receipt-contract keys (`receipts`) do not
    # retroactively invalidate semantic work: requiring input roles applies to
    # receipts written after the change, never to completed ones.
    return min(affected, default=len(BASE_STAGES))
