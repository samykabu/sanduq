#!/usr/bin/env python3
"""Project-selected continuous integration policy and workflow asset rendering.

Sanduq ships CI workflow assets, but it does not decide where a consumer project
runs them. The project records that decision once in `.specify/workflow.yml`
under `ci:`, and every shipped asset is rendered from that decision instead of
being copied with a hard-coded runner.

The module carries no third-party dependency so that `workflow`, `assure` and
`user-manual` can all vendor it.
"""
from __future__ import annotations

import re

PROVIDERS = ('github-actions', 'none')
RUNNER_POLICIES = ('hosted-allowed', 'self-hosted-required')
PYTHON_PROVISIONING = ('setup-action', 'preinstalled')
SYSTEM_PACKAGES = ('sudo-apt', 'preinstalled')
PLATFORMS = ('linux', 'windows', 'macos')

# GitHub-hosted label families. A runner set is hosted when every label is one.
HOSTED = re.compile(r'^(ubuntu|windows|macos)-([0-9.]+|latest)(-\w+)*$')

DEFAULT = {
    'provider': 'github-actions',
    'policy': 'hosted-allowed',
    'runners': {'linux': ['ubuntu-latest'], 'windows': ['windows-latest']},
    'capabilities': {'system_packages': 'sudo-apt', 'python': 'setup-action', 'python_version': '3.13'},
    'exceptions': [],
}

DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
VERSION = re.compile(r'^\d+\.\d+(\.\d+)?$')


class CIPolicyError(ValueError):
    """A project CI selection that cannot be rendered into a workflow."""


def _require(condition, message):
    if not condition:
        raise CIPolicyError(message)


def default_ci():
    """A fresh copy of the shipped default: GitHub-hosted, no exception needed."""
    return {'provider': DEFAULT['provider'], 'policy': DEFAULT['policy'],
            'runners': {name: list(labels) for name, labels in DEFAULT['runners'].items()},
            'capabilities': dict(DEFAULT['capabilities']), 'exceptions': []}


def hosted(labels):
    """True when every label in this runner set is a GitHub-hosted label."""
    return bool(labels) and all(HOSTED.match(label) for label in labels)


def validate_ci(ci):
    """Validate the `ci:` policy section. Returns it unchanged, or raises."""
    _require(isinstance(ci, dict), 'CI_POLICY_INVALID: ci must be a mapping')
    _require(ci.get('provider') in PROVIDERS, 'CI_PROVIDER_UNSUPPORTED: ' + repr(ci.get('provider')))
    _require(ci.get('policy') in RUNNER_POLICIES, 'CI_RUNNER_POLICY_INVALID: ' + repr(ci.get('policy')))

    runners = ci.get('runners')
    _require(isinstance(runners, dict) and runners, 'CI_RUNNERS_REQUIRED')
    for platform, labels in runners.items():
        _require(platform in PLATFORMS, 'CI_RUNNER_PLATFORM_UNKNOWN: ' + str(platform))
        _require(isinstance(labels, list) and labels
                 and all(isinstance(label, str) and label.strip() for label in labels),
                 'CI_RUNNER_LABELS_INVALID: ' + platform)
    _require('linux' in runners, 'CI_RUNNER_LINUX_REQUIRED')

    capabilities = ci.get('capabilities')
    _require(isinstance(capabilities, dict), 'CI_CAPABILITIES_REQUIRED')
    _require(capabilities.get('system_packages') in SYSTEM_PACKAGES,
             'CI_SYSTEM_PACKAGES_INVALID: ' + repr(capabilities.get('system_packages')))
    _require(capabilities.get('python') in PYTHON_PROVISIONING,
             'CI_PYTHON_PROVISIONING_INVALID: ' + repr(capabilities.get('python')))
    version = capabilities.get('python_version')
    _require(isinstance(version, str) and VERSION.match(version), 'CI_PYTHON_VERSION_INVALID: ' + repr(version))

    exceptions = ci.get('exceptions', [])
    _require(isinstance(exceptions, list), 'CI_EXCEPTIONS_INVALID')
    for entry in exceptions:
        _require(isinstance(entry, dict), 'CI_EXCEPTION_INVALID')
        for key in ('workflow', 'platform', 'reason', 'removed_by', 'decided'):
            value = entry.get(key)
            _require(isinstance(value, str) and value.strip(), 'CI_EXCEPTION_FIELD_REQUIRED: ' + key)
        _require(entry['platform'] in PLATFORMS, 'CI_EXCEPTION_PLATFORM_UNKNOWN: ' + entry['platform'])
        _require(DATE.match(entry['decided']), 'CI_EXCEPTION_DECIDED_INVALID: ' + entry['decided'])
    return ci


def exception_errors(ci, workflows=()):
    """Deviations from the project's own runner policy that lack a documented reason.

    Under `self-hosted-required` a GitHub-hosted runner set is a deviation, and
    every named workflow that runs on it needs its own dated exception entry
    saying why the self-hosted runner cannot serve it and what would remove the
    exception. Under `hosted-allowed` nothing is a deviation.
    """
    if ci.get('policy') != 'self-hosted-required':
        return []
    documented = {(entry['workflow'], entry['platform']) for entry in ci.get('exceptions', [])}
    errors = []
    for platform, labels in sorted(ci.get('runners', {}).items()):
        if not hosted(labels):
            continue
        for workflow in sorted(workflows) or ['*']:
            if (workflow, platform) not in documented and ('*', platform) not in documented:
                errors.append('CI_HOSTED_RUNNER_UNDOCUMENTED: ' + workflow + ' runs ' + platform
                              + ' on ' + ', '.join(labels)
                              + '; record why the self-hosted runner cannot serve it under ci.exceptions')
    return errors


# --- Asset rendering -------------------------------------------------------
#
# A shipped asset stays a valid, lintable workflow file on disk. Tokens are
# plain scalars -- `@` is a YAML reserved indicator and would break the parse --
# and optional steps are wrapped in comment markers, so a template parses as
# YAML both before and after rendering:
#
#     runs-on: __sanduq_runs_on_linux__
#     # sanduq:if system_packages_apt
#     - run: sudo apt-get install -y age
#     # sanduq:endif
#
TOKEN = re.compile(r'__sanduq_([a-z0-9_]+)__')
IF = re.compile(r'^(\s*)#\s*sanduq:if\s+(not\s+)?([a-z0-9_]+)\s*$')
ENDIF = re.compile(r'^\s*#\s*sanduq:endif\s*$')


def flags(ci):
    """The named booleans a template may branch on."""
    capabilities = ci['capabilities']
    return {'system_packages_apt': capabilities['system_packages'] == 'sudo-apt',
            'python_setup_action': capabilities['python'] == 'setup-action'}


def runs_on(labels):
    """YAML for a `runs-on:` value: a scalar for one label, a flow sequence otherwise."""
    if len(labels) == 1:
        return labels[0]
    return '[' + ', '.join(labels) + ']'


def tokens(ci):
    values = {'python_version': ci['capabilities']['python_version']}
    for platform, labels in ci.get('runners', {}).items():
        values['runs_on_' + platform] = runs_on(labels)
    return values


def render(template, ci):
    """Render a shipped workflow asset for this project's CI selection.

    `template` and the return value are both bytes so that callers keep control
    of the checkout line ending they write.
    """
    validate_ci(ci)
    text = template.decode('utf-8-sig')
    newline = '\r\n' if '\r\n' in text else '\n'
    known = flags(ci)
    values = tokens(ci)

    kept, stack = [], []
    for number, line in enumerate(text.replace('\r\n', '\n').split('\n'), start=1):
        opened = IF.match(line)
        if opened:
            name = opened.group(3)
            _require(name in known, 'CI_TEMPLATE_FLAG_UNKNOWN: ' + name + ' (line ' + str(number) + ')')
            keep = known[name] != bool(opened.group(2))
            stack.append(keep and all(stack))
            continue
        if ENDIF.match(line):
            _require(stack, 'CI_TEMPLATE_UNBALANCED: endif without if (line ' + str(number) + ')')
            stack.pop()
            continue
        if all(stack):
            kept.append(line)
    _require(not stack, 'CI_TEMPLATE_UNBALANCED: unclosed if')

    def substitute(match):
        _require(match.group(1) in values, 'CI_TEMPLATE_TOKEN_UNKNOWN: ' + match.group(1)
                 + '; the project declares no runner for this platform')
        return values[match.group(1)]

    return newline.join(TOKEN.sub(substitute, line) for line in kept).encode('utf-8')


def load_ci(root):
    """This project's recorded CI selection, or the shipped default.

    Assure and User Manual can be installed without the workflow extension, so a
    missing or CI-less policy is normal and yields the default rather than an error.
    """
    from pathlib import Path
    path = Path(root) / '.specify/workflow.yml'
    if not path.is_file():
        return default_ci()
    try:
        import yaml
    except ImportError:  # the consumer has not installed the workflow toolchain
        return default_ci()
    policy = yaml.safe_load(path.read_text(encoding='utf-8-sig')) or {}
    ci = policy.get('ci') if isinstance(policy, dict) else None
    return validate_ci(ci) if ci else default_ci()
