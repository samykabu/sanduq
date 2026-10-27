"""A5, E4, E8: alias opt-in, hidden hook-only Scope skills, the guard hook and the role agents."""
import json
import shutil
import sys
import tomllib
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import delegate_dispatch as dispatch
import hosts
import install as installer
import reconcile
import workflow as w
import test_hosts

ROLES = Path(__file__).resolve().parents[1] / 'assets/roles'
OTHER_HOOK = {'matcher': 'Edit', 'hooks': [{'type': 'command', 'command': 'echo other'}]}


# test_hosts deletes its base class so unittest does not run it alone.
HostTests = test_hosts.InstallKeepsHostsTests.__bases__[0]


class HostFilesTests(HostTests):
    def setUp(self):
        super().setUp()
        shutil.copytree(Path(__file__).resolve().parents[1] / 'hooks', self.package / 'hooks')

    def fresh_project(self):
        """A project no earlier install gave aliases: no lock, no alias files."""
        (self.root / hosts.INSTALL_LOCK).unlink()
        for folder in hosts.HOST_SKILLS.values():
            for name in hosts.ALIASES:
                path = self.root / folder / name / 'SKILL.md'
                if path.exists():
                    path.unlink(); path.parent.rmdir()

    def scope_alias(self, folder='.claude/skills'):
        return self.root / folder / 'speckit-scope/SKILL.md'

    def test_aliases_are_opt_in_and_kept_until_removed(self):
        self.fresh_project()
        self.install()
        self.assertFalse(self.scope_alias().exists())
        self.assertIs(w.read(self.root / hosts.INSTALL_LOCK)['with_aliases'], False)
        with self.subTest('--with-aliases'):
            with test_hosts.patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
                installer.install(self.root, apply=True, package_root=self.package, runner=self.specify, with_aliases=True)
            self.assertTrue(self.scope_alias().is_file())
            self.assertTrue(self.scope_alias('.agents/skills').is_file())
        with self.subTest('a later install keeps them'):
            self.install()
            self.assertTrue(self.scope_alias().is_file())
            self.assertEqual(hosts.alias_errors(self.root, self.package), [])
        with self.subTest('--without-aliases'):
            with test_hosts.patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
                installer.install(self.root, apply=True, package_root=self.package, runner=self.specify, with_aliases=False)
            self.assertFalse(self.scope_alias().exists())
            # The registered upstream Bridge is an executor; Sanduq always replaces it.
            bridge = self.root / '.claude/skills/speckit-superpowers-bridge/SKILL.md'
            self.assertIn(b'sanduq-workflow-alias:v1', bridge.read_bytes())
            self.assertEqual(hosts.alias_errors(self.root, self.package), [])

    def test_older_install_with_aliases_keeps_them(self):
        self.assertTrue(hosts.aliases_enabled(self.root))  # setUp's lock lists aliases, as 1.12 wrote it
        self.install()
        self.assertTrue(self.scope_alias().is_file())

    def test_without_aliases_keeps_a_locally_edited_alias(self):
        alias = self.scope_alias()
        alias.write_bytes(alias.read_bytes() + b'\nmine\n')
        with test_hosts.patch.object(installer, 'doctor', return_value={'ok': True, 'errors': []}):
            installer.install(self.root, apply=True, package_root=self.package, runner=self.specify, with_aliases=False)
        self.assertIn(b'mine', alias.read_bytes())

    def test_hook_only_scope_skills_are_hidden_on_claude_only(self):
        register = self.specify.register

        def rendered(host, names):  # Spec Kit writes frontmatter; the fake writes a bare line
            register(host, names)
            for path in (self.specify.root / hosts.HOST_SKILLS[host]).glob('speckit-scope-*/SKILL.md'):
                path.write_text('---\nname: ' + path.parent.name + '\ndescription: x\n---\nbody\n', encoding='utf-8')
        self.specify.register = rendered
        self.install()
        claude = (self.root / '.claude/skills/speckit-scope-bind/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('user-invocable: false', claude)
        self.assertNotIn('user-invocable', (self.root / '.agents/skills/speckit-scope-bind/SKILL.md').read_text(encoding='utf-8'))
        self.assertNotIn('user-invocable', (self.root / '.claude/skills/speckit-scope-run/SKILL.md').read_text(encoding='utf-8'))
        self.assertEqual(hosts.skill_report(self.root)['missing'], {})

    def test_hidden_flag_is_idempotent_and_reapplied_by_reconcile(self):
        path = self.root / '.claude/skills/speckit-scope-guard/SKILL.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'---\r\nname: speckit-scope-guard\r\ndescription: Guard\r\n---\r\n\r\nBody\r\n')
        reconcile.reconcile(self.root, apply=True)
        once = path.read_bytes()
        self.assertEqual(once, b'---\r\nname: speckit-scope-guard\r\ndescription: Guard\r\nuser-invocable: false\r\n---\r\n\r\nBody\r\n')
        reconcile.reconcile(self.root, apply=True)
        self.assertEqual(path.read_bytes(), once)
        path.write_bytes(b'---\nname: speckit-scope-guard\nuser-invocable: true\n---\nBody\n')  # a Spec Kit re-render
        reconcile.reconcile(self.root, apply=True)
        self.assertEqual(path.read_bytes(), b'---\nname: speckit-scope-guard\nuser-invocable: false\n---\nBody\n')
        self.assertEqual(hosts.with_flag('no frontmatter'), 'no frontmatter')

    def test_guard_hook_is_merged_into_both_hosts_without_clobbering(self):
        settings = self.root / '.claude/settings.json'
        w.write(settings, {'permissions': {'allow': ['Bash(ls)']}, 'hooks': {'PreToolUse': [OTHER_HOOK]}})
        result = self.install()
        self.assertEqual(result['codex_hook_approval'], hosts.CODEX_HOOK_APPROVAL)
        for path in (settings, self.root / '.codex/hooks.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            groups = data['hooks']['PreToolUse']
            guards = [h for g in groups for h in g['hooks'] if hosts.GUARD_MARK in h['command']]
            self.assertEqual(len(guards), 1, path)
            self.assertEqual([g['matcher'] for g in groups if g['hooks'][0] in guards], ['Bash'])
        claude = json.loads(settings.read_text(encoding='utf-8'))
        self.assertEqual(claude['permissions'], {'allow': ['Bash(ls)']})
        self.assertIn(OTHER_HOOK, claude['hooks']['PreToolUse'])
        before = settings.read_bytes()
        reconcile.reconcile(self.root, apply=True)
        self.assertEqual(settings.read_bytes(), before)

    def test_guard_command_names_the_interpreter_each_platform_has(self):
        command = lambda os_name: hosts.guard_hooks(self.package, os_name)['PreToolUse'][0]['hooks'][0]['command']
        self.assertTrue(command('nt').startswith('python -c '))
        self.assertTrue(command('posix').startswith('python3 -c '))
        self.assertNotIn('{python}', command('nt') + command('posix'))
        self.install()
        for path in ('.claude/settings.json', '.codex/hooks.json'):
            hook = w.read(self.root / path)['hooks']['PreToolUse'][-1]['hooks'][0]
            self.assertTrue(hook['command'].startswith(hosts.python_name() + ' -c '), path)

    def test_invalid_hook_settings_are_refused_not_overwritten(self):
        settings = self.root / '.claude/settings.json'
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text('{not json', encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'HOOK_SETTINGS_INVALID'):
            self.install()
        self.assertEqual(settings.read_text(encoding='utf-8'), '{not json')

    def test_roles_render_for_each_host_and_leave_user_files_alone(self):
        own = self.root / '.codex/agents/sanduq-reviewer.toml'
        own.parent.mkdir(parents=True)
        own.write_text('name = "sanduq-reviewer"\n', encoding='utf-8')
        result = self.install()
        self.assertEqual(result['host_files']['roles_skipped'], ['.codex/agents/sanduq-reviewer.toml'])
        self.assertEqual(own.read_text(encoding='utf-8'), 'name = "sanduq-reviewer"\n')
        worker = yaml.safe_load((ROLES / 'worker.yml').read_text(encoding='utf-8'))
        text = (self.root / '.claude/agents/sanduq-worker.md').read_text(encoding='utf-8')
        head = yaml.safe_load(text.split('---')[1])
        self.assertEqual(head['name'], 'sanduq-worker')
        self.assertEqual(head['description'], worker['description'])
        self.assertEqual(head['tools'], ', '.join(worker['tools']))
        self.assertNotIn('model', head)  # delegation off: the role inherits the session model
        expected = worker['instructions'].strip().replace('{no_dispatcher_commands}', dispatch.NO_DISPATCHER_COMMANDS.strip())
        self.assertIn(expected, text)
        codex = tomllib.loads((self.root / '.codex/agents/sanduq-worker.toml').read_text(encoding='utf-8'))
        self.assertEqual(set(codex), {'name', 'description', 'developer_instructions'})
        self.assertEqual(codex['developer_instructions'].strip(), expected)

    def test_role_model_comes_from_enabled_delegation_tiers(self):
        role = yaml.safe_load((ROLES / 'reviewer.yml').read_text(encoding='utf-8'))
        policy = {'delegation': {'enabled': True, 'models': {'claude': {'review': 'opus'}, 'codex': {'review': 'gpt-x'}}}}
        written, _ = hosts.install_roles(self.root, 'codex', self.package, policy)
        self.assertIn('.codex/agents/sanduq-reviewer.toml', written)
        self.assertEqual(tomllib.loads((self.root / '.codex/agents/sanduq-reviewer.toml').read_text(encoding='utf-8'))['model'], 'gpt-x')
        self.assertIn('\nmodel: opus\n', hosts.render_role(role, 'claude', 'opus'))
        self.assertEqual(hosts.install_roles(self.root, 'codex', self.package, policy), ([], []))

    def test_role_definitions_carry_the_protocol_rules(self):
        for name in hosts.ROLES:
            role = yaml.safe_load((ROLES / (name + '.yml')).read_text(encoding='utf-8'))
            self.assertEqual(set(role), {'name', 'description', 'instructions', 'model_tier', 'tools'})
            self.assertEqual(role['name'], 'sanduq-' + name)
            self.assertIn(role['model_tier'], ('high', 'standard', 'light', 'documentation', 'review'))
            for text in ('git stash', 'git add -A', 'git add .', '{no_dispatcher_commands}'):
                self.assertIn(text, role['instructions'])
            self.assertNotIn('delegate_dispatch.py', role['instructions'])  # OMAR-19: one generated sentence
            for host in ('claude', 'codex'):
                rendered = hosts.render_role(role, host)
                self.assertIn(dispatch.NO_DISPATCHER_COMMANDS.strip(), rendered)
                self.assertNotIn('{no_dispatcher_commands}', rendered)
            for field in ('Task:', 'Status:', 'Files touched:', 'Tests:', 'Evidence:', 'Diff:',
                          'Consumers checked:', 'Tokens:', 'Model:', 'Blockers:', 'Next:'):
                self.assertIn('\n' + field, role['instructions'])

    def test_doctor_warns_when_claude_md_does_not_import_agents_md(self):
        warned = lambda: [x for x in w.doctor(self.root, self.policy)['warnings'] if x.startswith('INSTRUCTION_FILES_DUPLICATED')]
        (self.root / 'CLAUDE.md').write_text('# Rules\nUse tabs.\n', encoding='utf-8')
        self.assertEqual(warned(), [])  # only one standing file
        (self.root / 'AGENTS.md').write_text('# Rules\nUse tabs.\n', encoding='utf-8')
        self.assertEqual(len(warned()), 1)
        (self.root / 'CLAUDE.md').write_text('@AGENTS.md\n\nClaude-only note.\n', encoding='utf-8')
        self.assertEqual(warned(), [])

    def test_failed_install_rolls_back_host_files(self):
        with test_hosts.patch.object(installer, 'register_hosts', return_value=[]):
            with self.assertRaisesRegex(w.WorkflowError, 'INSTALL_ROLLED_BACK'):
                self.install()
        self.assertFalse((self.root / '.claude/settings.json').exists())
        self.assertFalse((self.root / '.codex/agents/sanduq-worker.toml').exists())


if __name__ == '__main__':
    unittest.main()
