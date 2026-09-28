"""Installs, upgrades and host switches keep every installed integration complete."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hosts
import install as installer
import upgrade
import workflow as w
import test_install
import test_workflow as fixture

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
SANDUQ = 'https://github.com/samykabu/sanduq'
UPSTREAM_BRIDGE = (b'---\nname: speckit-superpowers-bridge\ndescription: Execute tasks\nmetadata:\n'
                   b'  author: github-spec-kit\n'
                   b'  source: speckit-superpowers-bridge:commands/speckit.speckit-superpowers-bridge.execute.md\n'
                   b'---\nUpstream Bridge executor: run every task now.\n')
# The commands each fake managed package provides.
PROVIDES = {'scope': ['speckit.scope.run', 'speckit.scope.bind'], 'project': ['speckit.project.sync'],
            'pr': ['speckit.pr.generate'], 'illustrate': ['speckit.illustrate.generate'],
            'assure': ['speckit.assure.analyze', 'speckit.assure.document'],
            'user-manual': ['speckit.user-manual.analyze', 'speckit.user-manual.update'],
            'workflow': ['speckit.workflow.continue', 'speckit.workflow.doctor']}


class FakeSpecify:
    """Spec Kit 1.0.13 as observed: extension skills exist only for the default integration.

    ``extension add --force`` removes the extension's skills from every host and
    registers them for the default one. ``integration use`` makes a host the
    default and re-registers every enabled extension for it from upstream
    sources, which overwrites the managed Bridge alias.
    """

    def __init__(self, test):
        self.test = test
        self.calls = []

    @property
    def root(self):
        return self.test.root

    def __call__(self, root, args, log):
        self.calls.append(list(args))
        log.append({'args': list(args), 'exit_code': 0, 'stdout': '', 'stderr': ''})
        if args[0] == sys.executable:
            owner = int(args[args.index('--upgrade-owner') + 1])
            installer.install(root, apply=True, package_root=self.test.package, runner=self, upgrade_owner=owner)
        elif args[1:3] == ['extension', 'add']:
            self.extension_add(args)
        elif args[1:3] == ['integration', 'use']:
            self.use(args[3])

    def extension_add(self, args):
        if '--dev' in args:
            source = Path(args[args.index('--dev') + 1])
            name = source.name
            version = str(yaml.safe_load((source / 'extension.yml').read_text(encoding='utf-8'))['extension']['version'])
        else:
            name = args[3]
            version = re.search(r'-v([\d.]+)/', args[args.index('--from') + 1])[1]
        write_manifest(self.root, name, version)
        registered = w.registry(self.root)
        registered[name] = {'version': version, 'enabled': True}
        w.write(self.root / '.specify/extensions/.registry', {'extensions': registered})
        for host in hosts.HOST_SKILLS:
            for command in PROVIDES.get(name, []):
                shutil.rmtree(hosts.skill_path(self.root, host, command).parent, ignore_errors=True)
        self.register(w.active_host(self.root), [name])

    def use(self, host):
        state = w.read(self.root / '.specify/integration.json')
        assert host in state['installed_integrations'], host
        state.update(integration=host, default_integration=host)
        w.write(self.root / '.specify/integration.json', state)
        options = w.read(self.root / '.specify/init-options.json')
        options.update(ai=host, integration=host)
        w.write(self.root / '.specify/init-options.json', options)
        for command in w.COMMANDS.values():
            if not command.startswith('workflow:'):
                path = hosts.skill_path(self.root, host, command)
                if not path.is_file():
                    path.parent.mkdir(parents=True, exist_ok=True); path.write_text('core command', encoding='utf-8')
        self.register(host, [name for name, entry in w.registry(self.root).items() if entry.get('enabled')])

    def register(self, host, names):
        for name in names:
            for command in PROVIDES.get(name, []):
                path = hosts.skill_path(self.root, host, command)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('registered ' + command, encoding='utf-8')
            if name == 'speckit-superpowers-bridge':
                path = self.root / hosts.HOST_SKILLS[host] / 'speckit-superpowers-bridge/SKILL.md'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(UPSTREAM_BRIDGE)


def write_manifest(root, name, version, repository=SANDUQ):
    path = root / '.specify/extensions' / name / 'extension.yml'
    path.parent.mkdir(parents=True, exist_ok=True)
    commands = [{'name': c, 'file': 'x.md'} for c in PROVIDES.get(name, [])]
    if name == 'speckit-superpowers-bridge':
        commands = [{'name': 'speckit.speckit-superpowers-bridge.execute', 'file': 'x.md',
                     'aliases': ['speckit.superpowers-bridge']}]
    path.write_text(yaml.safe_dump({'extension': {'id': name, 'version': version, 'repository': repository},
                                    'provides': {'commands': commands}}), encoding='utf-8')


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.git' not in p.relative_to(root).parts}


class HostTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure

    def setUp(self, default='codex'):
        test_install.InstallTests.setUp(self)
        registered = w.registry(self.root)
        registered['speckit-superpowers-bridge'] = {'version': '1.2.0', 'enabled': True}
        registered['workflow'] = {'version': '1.1.0', 'enabled': True}
        w.write(self.root / '.specify/extensions/.registry', {'extensions': registered})
        write_manifest(self.root, 'speckit-superpowers-bridge', '1.2.0', 'https://github.com/example/bridge')
        for name, entry in registered.items():
            if name != 'speckit-superpowers-bridge':
                write_manifest(self.root, name, entry['version'])
        self.default(default)
        shutil.copytree(self.root / '.agents/skills', self.root / '.claude/skills')
        for host in hosts.HOST_SKILLS:
            FakeSpecify(self).register(host, list(PROVIDES))
        # Both hosts start with the managed aliases, as a previous install left them.
        w.write(self.root / '.specify/workflow/install-lock.json',
                {'host': default, 'aliases': installer.install_aliases(self.root, self.package)})
        self.specify = FakeSpecify(self)

    def default(self, host):
        w.write(self.root / '.specify/integration.json', {
            'installed_integrations': ['codex', 'claude'], 'integration': host, 'default_integration': host,
            'integration_settings': {'codex': {'script': 'ps'}, 'claude': {'script': 'ps'}}})
        w.write(self.root / '.specify/init-options.json', {'ai': host, 'integration': host, 'ai_skills': True})

    def assert_complete(self):
        report = hosts.skill_report(self.root)
        self.assertEqual(report['hosts'][1:] and sorted(report['hosts']), ['claude', 'codex'])
        self.assertEqual(report['missing'], {})
        self.assertEqual(hosts.alias_errors(self.root, self.package), [])
        source = (self.package / 'skills/speckit-superpowers-bridge/SKILL.md').read_bytes()
        for folder in hosts.HOST_SKILLS.values():
            self.assertEqual((self.root / folder / 'speckit-superpowers-bridge/SKILL.md').read_bytes(), source)
            for commands in PROVIDES.values():
                for command in commands:
                    self.assertTrue((self.root / folder / hosts.skill_name(command) / 'SKILL.md').is_file(), command)

    def install(self):
        with patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            return installer.install(self.root, apply=True, package_root=self.package, runner=self.specify)


class InstallKeepsHostsTests(HostTests):
    def test_install_with_default_codex_keeps_claude_skills(self):
        integration = (self.root / '.specify/integration.json').read_bytes()
        result = self.install()
        self.assertEqual(result['hosts']['re_registered'], ['claude'])
        self.assertEqual(self.specify.calls[-2:], [['specify', 'integration', 'use', 'claude'],
                                                  ['specify', 'integration', 'use', 'codex']])
        self.assertEqual((self.root / '.specify/integration.json').read_bytes(), integration)
        self.assertEqual(w.active_host(self.root), 'codex')
        self.assert_complete()

    def test_install_with_default_claude_keeps_codex_skills(self):
        self.default('claude')
        result = self.install()
        self.assertEqual(result['hosts']['re_registered'], ['codex'])
        self.assertEqual(w.active_host(self.root), 'claude')
        self.assert_complete()

    def test_single_host_install_runs_no_integration_commands(self):
        w.write(self.root / '.specify/integration.json', {'installed_integrations': ['codex'],
                                                          'default_integration': 'codex'})
        self.install()
        self.assertFalse([c for c in self.specify.calls if c[1:3] == ['integration', 'use']])

    def test_lost_host_skills_are_caught_and_rolled_back(self):
        before = tree(self.root / '.claude')
        with patch.object(installer, 'register_hosts', return_value=[]):
            with self.assertRaisesRegex(w.WorkflowError, 'INSTALL_ROLLED_BACK.*HOST_SKILLS_MISSING: claude'):
                self.install()
        self.assertEqual(tree(self.root / '.claude'), before)

    def test_bridge_alias_edited_before_install_is_still_refused(self):
        alias = self.root / '.claude/skills/speckit-superpowers-bridge/SKILL.md'
        alias.write_bytes(alias.read_bytes() + b'\nLocal edit\n')
        with self.assertRaisesRegex(w.WorkflowError, 'ALIAS_HAS_LOCAL_EDITS'):
            self.install()
        self.assertIn(b'Local edit', alias.read_bytes())

    def test_upgrade_with_default_codex_keeps_claude_skills(self):
        self.upgrade()

    def test_upgrade_with_default_claude_keeps_codex_skills(self):
        self.default('claude')
        self.upgrade()

    def upgrade(self):
        default = w.active_host(self.root)
        packages = self.package / 'packages'
        (packages / 'workflow').mkdir(parents=True)
        (packages / 'workflow/extension.yml').write_text(yaml.safe_dump({'extension': {
            'id': 'workflow', 'version': '1.1.1', 'repository': SANDUQ}}), encoding='utf-8')
        with patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            upgrade.upgrade(self.root, '1.1.1', apply=True, packages=packages, runner=self.specify)
        self.assertEqual(w.registry(self.root)['workflow']['version'], '1.1.1')
        self.assertEqual(w.active_host(self.root), default)
        self.assert_complete()


class SwitchTests(HostTests):
    def checkpoint(self):
        path = self.root / 'specs/001-example/workflow/checkpoint.json'
        w.write(path, {'dependency_digest': w.package_digest(self.root), 'branch': 'main', 'active': None})

    def test_switch_restores_managed_bridge_alias_over_upstream_content(self):
        self.checkpoint()
        digest = w.package_digest(self.root)
        result = hosts.switch(self.root, 'claude', runner=self.specify, package_root=self.package)
        self.assertTrue(result['applied'])
        self.assertEqual(w.active_host(self.root), 'claude')
        self.assertEqual(self.specify.calls, [['specify', 'integration', 'use', 'claude']])
        self.assert_complete()  # the upstream Bridge content Spec Kit wrote is gone from both folders
        self.assertIn('.claude/skills/speckit-superpowers-bridge/SKILL.md', result['aliases_restored'])
        self.assertTrue(result['doctor']['ok'], result['doctor'])
        self.assertTrue(w.doctor(self.root, self.policy)['ok'])
        self.assertEqual(result['dependency_digest']['before'], digest)
        self.assertTrue(result['dependency_digest']['changed'])
        [entry] = result['checkpoints_to_migrate']
        self.assertEqual(entry['feature'], 'specs/001-example')
        self.assertFalse(entry['already_stale'])
        self.assertIn('.specify/extensions/workflow/scripts/workflow.py migrate --feature specs/001-example --reason '
                      '"Host switched from codex to claude"', entry['commands'][-1])
        self.assertEqual(w.read(self.root / '.specify/workflow/install-lock.json')['host'], 'claude')
        # A later install accepts what the switch left behind.
        self.install()
        self.assert_complete()

    def test_switch_back_and_forth_keeps_both_hosts(self):
        hosts.switch(self.root, 'claude', runner=self.specify, package_root=self.package)
        hosts.switch(self.root, 'codex', runner=self.specify, package_root=self.package)
        self.assertEqual(w.active_host(self.root), 'codex')
        self.assert_complete()
        self.assertTrue(w.doctor(self.root, self.policy)['ok'])

    def test_switch_re_registers_a_host_an_older_upgrade_emptied(self):
        shutil.rmtree(self.root / '.agents/skills/speckit-assure-analyze')
        plan = hosts.switch(self.root, 'claude', preview=True, package_root=self.package)
        self.assertEqual(plan['skills_before']['missing'], {'codex': ['speckit-assure-analyze']})
        self.assertEqual(plan['commands'], [['specify', 'integration', 'use', h] for h in ('claude', 'codex', 'claude')])
        result = hosts.switch(self.root, 'claude', runner=self.specify, package_root=self.package)
        self.assertEqual(result['re_registered_hosts'], ['codex'])
        self.assertEqual(w.active_host(self.root), 'claude')
        self.assert_complete()

    def test_preview_changes_nothing(self):
        self.checkpoint()
        before = tree(self.root)
        plan = hosts.switch(self.root, 'claude', preview=True, runner=self.specify, package_root=self.package)
        self.assertEqual(tree(self.root), before)
        self.assertEqual(self.specify.calls, [])
        self.assertTrue(plan['can_apply'], plan['blockers'])
        self.assertEqual(plan['commands'], [['specify', 'integration', 'use', 'claude']])
        self.assertTrue(plan['dependency_digest']['will_change'])
        self.assertEqual([e['feature'] for e in plan['checkpoints_to_migrate']], ['specs/001-example'])
        self.assertFalse(plan['checkpoints_to_migrate'][0]['already_stale'])

    def test_preview_through_the_cli_changes_nothing(self):
        before = tree(self.root)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'workflow.py'), '--root', str(self.root),
                                 'host', '--use', 'claude', '--preview'], capture_output=True, text=True,
                                encoding='utf-8', env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual((plan['from'], plan['to'], plan['preview']), ('codex', 'claude', True))
        self.assertEqual(tree(self.root), before)
        status = subprocess.run([sys.executable, str(SCRIPTS / 'workflow.py'), '--root', str(self.root), 'host'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(json.loads(status.stdout)['installed_hosts'], ['codex', 'claude'])

    def test_switch_to_host_with_missing_delegation_tiers_is_reported_and_refused(self):
        self.policy['delegation']['enabled'] = True
        del self.policy['delegation']['models']['claude']['review']
        self.policy['delegation']['routes']['review']['fallbacks'] = [{'harness': 'codex', 'model': None}]
        (self.root / '.specify/workflow.yml').write_text(yaml.safe_dump(self.policy), encoding='utf-8')
        before = tree(self.root)
        plan = hosts.switch(self.root, 'claude', preview=True, runner=self.specify, package_root=self.package)
        self.assertFalse(plan['can_apply'])
        self.assertIn('delegation.models.claude.review is missing: set the claude model for the review tier',
                      plan['delegation']['required_changes'])
        self.assertTrue(any('delegation.routes.review.fallbacks[0] pins harness codex' in note
                            for note in plan['delegation']['notes']))
        with self.assertRaisesRegex(w.WorkflowError, 'HOST_SWITCH_BLOCKED: .*delegation.models.claude.review'):
            hosts.switch(self.root, 'claude', runner=self.specify, package_root=self.package)
        self.assertEqual(self.specify.calls, [])
        self.assertEqual(tree(self.root), before)

    def test_switch_reports_a_model_of_the_other_host(self):
        self.policy['delegation']['enabled'] = True
        self.policy['delegation']['models']['claude']['high'] = 'gpt-6-astra'
        self.configure()
        plan = hosts.switch(self.root, 'claude', preview=True, package_root=self.package)
        self.assertIn('delegation.models.claude.high is "gpt-6-astra", a codex model: set a claude model',
                      plan['delegation']['required_changes'])
        self.assertFalse(plan['can_apply'])

    def test_disabled_delegation_only_advises(self):
        self.policy['delegation']['models']['claude']['high'] = 'gpt-6-astra'
        self.configure()
        plan = hosts.switch(self.root, 'claude', preview=True, package_root=self.package)
        self.assertEqual(plan['delegation']['required_changes'], [])
        self.assertTrue(plan['delegation']['advisories'])

    def test_switch_to_a_host_that_is_not_installed_is_refused(self):
        w.write(self.root / '.specify/integration.json', {'installed_integrations': ['codex'],
                                                          'default_integration': 'codex'})
        plan = hosts.switch(self.root, 'claude', preview=True, package_root=self.package)
        self.assertIn('HOST_NOT_INSTALLED', ' '.join(plan['blockers']))

    def test_upstream_bridge_left_by_a_bare_integration_use_is_replaced(self):
        # A user ran `specify integration use claude` directly before this release.
        self.specify.use('claude')
        self.specify.calls.clear()
        alias = self.root / '.claude/skills/speckit-superpowers-bridge/SKILL.md'
        self.assertEqual(alias.read_bytes(), UPSTREAM_BRIDGE)
        self.assertIn('ALIAS_NOT_RESTORED: .claude/skills/speckit-superpowers-bridge/SKILL.md',
                      hosts.status(self.root, self.package)['aliases_not_restored'])
        plan = hosts.switch(self.root, 'claude', preview=True, package_root=self.package)
        self.assertTrue(plan['can_apply'], plan['blockers'])
        hosts.switch(self.root, 'claude', runner=self.specify, package_root=self.package)
        self.assert_complete()

    def test_hand_edited_upstream_bridge_is_still_a_local_edit(self):
        alias = self.root / '.claude/skills/speckit-superpowers-bridge/SKILL.md'
        alias.write_bytes(UPSTREAM_BRIDGE.replace(b'source: speckit-superpowers-bridge:', b'source: mine:'))
        plan = hosts.switch(self.root, 'claude', preview=True, package_root=self.package)
        self.assertIn('ALIAS_HAS_LOCAL_EDITS: .claude/skills/speckit-superpowers-bridge/SKILL.md', ' '.join(plan['blockers']))

    def test_edited_alias_blocks_switch_before_anything_changes(self):
        alias = self.root / '.agents/skills/speckit-scope/SKILL.md'
        alias.write_bytes(alias.read_bytes() + b'\nLocal edit\n')
        before = tree(self.root)
        with self.assertRaisesRegex(w.WorkflowError, 'ALIAS_HAS_LOCAL_EDITS'):
            hosts.switch(self.root, 'claude', runner=self.specify, package_root=self.package)
        self.assertEqual(tree(self.root), before)

    def test_failed_switch_rolls_back_the_default(self):
        integration = (self.root / '.specify/integration.json').read_bytes()

        def failing(root, args, log):
            self.specify(root, args, log)
            raise w.WorkflowError('simulated')
        with self.assertRaisesRegex(w.WorkflowError, 'HOST_SWITCH_ROLLED_BACK'):
            hosts.switch(self.root, 'claude', runner=failing, package_root=self.package)
        self.assertEqual((self.root / '.specify/integration.json').read_bytes(), integration)
        self.assertEqual(w.active_host(self.root), 'codex')
        self.assert_complete()

    def test_doctor_warns_when_another_host_lost_skills(self):
        shutil.rmtree(self.root / '.claude/skills/speckit-pr-generate')
        health = w.doctor(self.root, self.policy)
        self.assertTrue(health['ok'])
        self.assertTrue(any(warning.startswith('HOST_SKILLS_MISSING: claude') and 'host --use codex' in warning
                            for warning in health['warnings']), health['warnings'])


del HostTests

if __name__ == '__main__':
    unittest.main()
