import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import skill_inventory as si

SPEC = importlib.util.spec_from_file_location('sanduq_workflow_for_skill_inventory',
                                              Path(__file__).resolve().parents[1] / 'scripts/workflow.py')
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


def write_skill(root, name, description=None, extra_frontmatter='', body='body text'):
    """Write <root>/<name>/SKILL.md with an optional frontmatter description."""
    path = root / name / 'SKILL.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    if description is None and not extra_frontmatter:
        path.write_text(body, encoding='utf-8')
    else:
        lines = ['---']
        if description is not None:
            lines.append('description: ' + description)
        if extra_frontmatter:
            lines.append(extra_frontmatter)
        lines += ['---', body]
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


class EnvOverride:
    """Set an environment variable for the duration of a test, restoring it after."""

    def __init__(self, testcase, name, value):
        old = os.environ.get(name)
        os.environ[name] = value
        testcase.addCleanup(lambda: os.environ.pop(name, None) if old is None
                             else os.environ.__setitem__(name, old))


class SkillInventoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.home = self.base / 'home'
        self.project = self.base / 'project'
        self.codex_home = self.base / 'codex-home'
        self.home.mkdir()
        self.project.mkdir()
        self.codex_home.mkdir()

    def inv(self, policy=None):
        return si.inventory(self.project, policy, home=self.home, codex_home=self.codex_home)

    # --- missing roots -------------------------------------------------

    def test_missing_roots_report_zero_and_do_not_exist(self):
        result = self.inv()
        for name in ('claude_home', 'claude_project', 'agents_home', 'agents_project', 'codex_home'):
            root = result['roots'][name]
            self.assertFalse(root['exists'])
            self.assertEqual(root['skill_count'], 0)
            self.assertEqual(root['description_bytes'], 0)
            self.assertEqual(root['max_description_bytes'], 0)
            self.assertEqual(root['skill_md_bytes'], 0)
        # No installed_plugins.json under a bare home: not counted, not guessed at.
        self.assertFalse(result['roots']['claude_plugins']['counted'])
        self.assertIsNotNone(result['roots']['claude_plugins']['reason'])
        for host in ('claude', 'codex'):
            self.assertEqual(result['hosts'][host]['combined']['skill_count'], 0)
            self.assertEqual(result['hosts'][host]['duplicates'], {})
        self.assertEqual(result['mirrors'], {})
        self.assertEqual(si.warnings(result), [])

    # --- per-host combined totals, not a cross-host sum ---------------------

    def test_combined_is_per_host_not_summed_across_hosts(self):
        write_skill(self.home / '.claude/skills', 'home-claude-only', description='d')
        write_skill(self.home / '.agents/skills', 'home-agents-only', description='d')
        write_skill(self.project / '.claude/skills', 'shared', description='d')
        write_skill(self.project / '.agents/skills', 'shared', description='d')  # Sanduq's own mirror
        write_skill(self.codex_home / 'skills', 'codex-only', description='d')
        result = self.inv()
        self.assertEqual(result['hosts']['claude']['combined']['skill_count'], 2)  # home-claude-only + shared
        self.assertEqual(result['hosts']['codex']['combined']['skill_count'], 3)  # home-agents-only + shared + codex-only
        # The mirrored "shared" skill must not appear as a duplicate on either host.
        self.assertEqual(result['hosts']['claude']['duplicates'], {})
        self.assertEqual(result['hosts']['codex']['duplicates'], {})
        self.assertIn('shared', result['mirrors'])
        self.assertEqual(result['mirrors']['shared'], {'claude': ['claude_project'], 'codex': ['agents_project']})

    # --- above threshold (via policy override, so the test stays fast) ----

    def test_warns_per_host_when_that_hosts_own_combined_skill_count_exceeds_threshold(self):
        for i in range(3):
            write_skill(self.project / '.claude/skills', 'claude-skill-%d' % i, description='d')
        policy = {'skills': {'inventory_thresholds': {'skill_count': 2}}}
        result = self.inv(policy)
        self.assertEqual(result['hosts']['claude']['combined']['skill_count'], 3)
        self.assertEqual(result['hosts']['codex']['combined']['skill_count'], 0)
        messages = si.warnings(result)
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith('SKILL_INVENTORY_LARGE: claude host'))

    def test_warns_independently_for_each_host_over_threshold(self):
        for i in range(3):
            write_skill(self.project / '.claude/skills', 'c-%d' % i, description='d')
            write_skill(self.project / '.agents/skills', 'a-%d' % i, description='d')
        policy = {'skills': {'inventory_thresholds': {'skill_count': 2}}}
        messages = si.warnings(self.inv(policy))
        hosts_warned = {m.split()[1] for m in messages}
        self.assertEqual(hosts_warned, {'claude', 'codex'})

    def test_warns_when_a_hosts_own_description_bytes_exceed_threshold(self):
        write_skill(self.project / '.claude/skills', 'big', description='x' * 100)
        policy = {'skills': {'inventory_thresholds': {'description_bytes': 10}}}
        result = self.inv(policy)
        self.assertGreater(result['hosts']['claude']['combined']['description_bytes'], 10)
        self.assertEqual(len(si.warnings(result)), 1)

    def test_default_thresholds_do_not_warn_for_a_small_project(self):
        write_skill(self.project / '.claude/skills', 'only-one', description='short')
        write_skill(self.project / '.agents/skills', 'only-one', description='short')
        result = self.inv()
        self.assertEqual(result['thresholds'], si.DEFAULT_THRESHOLDS)
        self.assertEqual(si.warnings(result), [])

    # --- malformed / missing frontmatter -----------------------------------

    def test_skill_without_frontmatter_counts_but_zero_description_bytes(self):
        write_skill(self.project / '.claude/skills', 'no-frontmatter', description=None, body='# Just a heading')
        result = self.inv()
        self.assertEqual(result['roots']['claude_project']['skill_count'], 1)
        self.assertEqual(result['roots']['claude_project']['description_bytes'], 0)

    def test_malformed_yaml_frontmatter_counts_but_zero_description_bytes(self):
        path = (self.project / '.claude/skills' / 'broken' / 'SKILL.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('---\ndescription: [unterminated\n---\nbody\n', encoding='utf-8')
        result = self.inv()
        self.assertEqual(result['roots']['claude_project']['skill_count'], 1)
        self.assertEqual(result['roots']['claude_project']['description_bytes'], 0)

    def test_non_string_description_counts_but_zero_description_bytes(self):
        write_skill(self.project / '.claude/skills', 'listy', description=None,
                    extra_frontmatter='description:\n  - one\n  - two')
        result = self.inv()
        self.assertEqual(result['roots']['claude_project']['skill_count'], 1)
        self.assertEqual(result['roots']['claude_project']['description_bytes'], 0)

    def test_unreadable_skill_md_is_skipped_not_raised(self):
        # A directory named SKILL.md (not a file) must not raise: is_file() is False.
        (self.project / '.claude/skills/oddity/SKILL.md').mkdir(parents=True)
        result = self.inv()
        self.assertEqual(result['roots']['claude_project']['skill_count'], 0)

    # --- symlinks -------------------------------------------------------

    def test_symlinked_skill_directory_is_counted_once(self):
        real = write_skill(self.project / '.claude/skills', 'real-skill', description='real').parent
        link = self.project / '.claude/skills' / 'aliased-skill'
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError as error:
            self.skipTest('Host does not support test symlinks: ' + str(error))
        result = self.inv()
        self.assertEqual(result['roots']['claude_project']['skill_count'], 1)

    def test_self_referential_symlink_does_not_loop_or_crash(self):
        skills_root = self.project / '.claude/skills'
        skills_root.mkdir(parents=True)
        loop = skills_root / 'loop'
        try:
            loop.symlink_to(loop, target_is_directory=True)
        except OSError as error:
            self.skipTest('Host does not support test symlinks: ' + str(error))
        write_skill(skills_root, 'normal', description='fine')
        result = self.inv()  # must return promptly, not hang or raise
        self.assertEqual(result['roots']['claude_project']['skill_count'], 1)

    # --- thresholds / env resolution -----------------------------------

    def test_thresholds_merge_only_overridden_keys(self):
        merged = si.thresholds({'skills': {'inventory_thresholds': {'skill_count': 5}}})
        self.assertEqual(merged['skill_count'], 5)
        self.assertEqual(merged['description_bytes'], si.DEFAULT_THRESHOLDS['description_bytes'])

    def test_home_root_resolution_honors_explicit_home_argument(self):
        roots = si.resolve_roots(self.project, home=self.home, codex_home=self.codex_home)
        self.assertEqual(roots['claude_home'], self.home / '.claude' / 'skills')
        self.assertEqual(roots['agents_home'], self.home / '.agents' / 'skills')

    def test_home_root_uses_sanduq_skills_home_env_override(self):
        EnvOverride(self, 'SANDUQ_SKILLS_HOME', str(self.home))
        self.assertEqual(si.home_root(), self.home)

    def test_codex_home_defaults_to_dot_codex_under_home(self):
        self.assertEqual(si.codex_home_root(self.home), self.home / '.codex')

    def test_codex_home_env_override_wins_over_home_fallback(self):
        codex_dir = self.base / 'explicit-codex-home'
        EnvOverride(self, 'CODEX_HOME', str(codex_dir))
        self.assertEqual(si.codex_home_root(self.home), codex_dir)

    def test_explicit_codex_home_argument_is_used_for_the_scan(self):
        write_skill(self.codex_home / 'skills', 'codex-thing', description='d')
        result = self.inv()
        self.assertEqual(result['roots']['codex_home']['skill_count'], 1)
        self.assertEqual(result['roots']['codex_home']['path'],
                          str(self.codex_home / 'skills'))

    # --- claude plugin skills, read only from installed_plugins.json -------

    def write_installed_plugins(self, plugins):
        path = self.home / '.claude/plugins/installed_plugins.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'version': 2, 'plugins': plugins}), encoding='utf-8')

    def test_missing_manifest_reports_plugins_as_not_counted(self):
        result = self.inv()
        plugins = result['roots']['claude_plugins']
        self.assertFalse(plugins['counted'])
        self.assertEqual(plugins['skill_count'], 0)
        self.assertIn('not found', plugins['reason'])

    def test_malformed_manifest_json_reports_plugins_as_not_counted(self):
        path = self.home / '.claude/plugins/installed_plugins.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{not json', encoding='utf-8')
        plugins = self.inv()['roots']['claude_plugins']
        self.assertFalse(plugins['counted'])
        self.assertIn('JSON', plugins['reason'])

    def test_manifest_without_plugins_object_reports_not_counted(self):
        path = self.home / '.claude/plugins/installed_plugins.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'version': 2}), encoding='utf-8')
        plugins = self.inv()['roots']['claude_plugins']
        self.assertFalse(plugins['counted'])

    def plugin_cache_dir(self, *parts):
        """A plugin install path that lives inside ~/.claude/plugins, as N2 requires."""
        return self.home.joinpath('.claude', 'plugins', 'cache', *parts)

    def test_valid_manifest_is_scanned_through_its_install_path(self):
        install_dir = self.plugin_cache_dir('claude-plugins-official', 'figma', '2.2.120')
        write_skill(install_dir / 'skills', 'figma-use', description='Use figma')
        write_skill(install_dir / 'skills', 'figma-code-connect', description='Connect')
        self.write_installed_plugins({
            'figma@claude-plugins-official': [{'scope': 'user', 'installPath': str(install_dir)}],
        })
        plugins = self.inv()['roots']['claude_plugins']
        self.assertTrue(plugins['counted'])
        self.assertIsNone(plugins['reason'])
        self.assertEqual(plugins['skill_count'], 2)
        self.assertGreater(plugins['description_bytes'], 0)
        self.assertEqual(plugins['skipped_install_paths'], [])
        # The scan actually used the manifest's installPath, not a guess: the two
        # skill names it found only exist under install_dir.
        self.assertEqual((install_dir / 'skills' / 'figma-use' / 'SKILL.md').is_file(), True)

    def test_plugin_skills_count_toward_the_claude_host_only(self):
        install_dir = self.plugin_cache_dir('typesafe-ai', 'typesafe', '0.5.7')
        write_skill(install_dir / 'skills', 'typesafe-ai', description='d')
        self.write_installed_plugins({
            'typesafe@typesafe-ai': [{'scope': 'user', 'installPath': str(install_dir)}],
        })
        result = self.inv()
        self.assertEqual(result['hosts']['claude']['combined']['skill_count'], 1)
        self.assertEqual(result['hosts']['codex']['combined']['skill_count'], 0)

    def test_malformed_plugin_entry_is_skipped_others_still_scanned(self):
        install_dir = self.plugin_cache_dir('somewhere', 'good', '1.0.0')
        write_skill(install_dir / 'skills', 'good-skill', description='d')
        self.write_installed_plugins({
            'bad-plugin@nowhere': 'not-a-list',
            'also-bad@nowhere': [{'scope': 'user'}],  # no installPath
            'good@somewhere': [{'scope': 'user', 'installPath': str(install_dir)}],
        })
        plugins = self.inv()['roots']['claude_plugins']
        self.assertTrue(plugins['counted'])
        self.assertEqual(plugins['skill_count'], 1)

    def test_duplicate_install_path_across_plugin_entries_counted_once(self):
        install_dir = self.plugin_cache_dir('market', 'shared', '1.0.0')
        write_skill(install_dir / 'skills', 'shared-skill', description='d')
        self.write_installed_plugins({
            'a@market': [{'scope': 'user', 'installPath': str(install_dir)}],
            'b@market': [{'scope': 'user', 'installPath': str(install_dir)}],
        })
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 1)

    def test_plugin_skill_name_repeated_in_project_root_is_a_same_host_duplicate(self):
        install_dir = self.plugin_cache_dir('market', 'dup', '1.0.0')
        write_skill(install_dir / 'skills', 'dup-skill', description='d')
        self.write_installed_plugins({'dup@market': [{'scope': 'user', 'installPath': str(install_dir)}]})
        write_skill(self.project / '.claude/skills', 'dup-skill', description='d')
        result = self.inv()
        self.assertIn('dup-skill', result['hosts']['claude']['duplicates'])

    # --- N1: scope/projectPath and enabledPlugins ---------------------------

    def test_project_scoped_entry_for_this_project_is_included(self):
        install_dir = self.plugin_cache_dir('market', 'proj-match', '1.0.0')
        write_skill(install_dir / 'skills', 'proj-skill', description='d')
        self.write_installed_plugins({
            'proj@market': [{'scope': 'project', 'installPath': str(install_dir), 'projectPath': str(self.project)}],
        })
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 1)

    def test_project_scoped_entry_for_a_different_project_is_excluded(self):
        install_dir = self.plugin_cache_dir('market', 'proj-mismatch', '1.0.0')
        write_skill(install_dir / 'skills', 'proj-skill', description='d')
        other_project = self.base / 'a-different-project'
        self.write_installed_plugins({
            'proj@market': [{'scope': 'project', 'installPath': str(install_dir), 'projectPath': str(other_project)}],
        })
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 0)

    def test_local_scoped_entry_for_a_different_project_is_excluded(self):
        install_dir = self.plugin_cache_dir('market', 'local-mismatch', '1.0.0')
        write_skill(install_dir / 'skills', 'local-skill', description='d')
        self.write_installed_plugins({
            'proj@market': [{'scope': 'local', 'installPath': str(install_dir),
                             'projectPath': str(self.base / 'elsewhere')}],
        })
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 0)

    def test_project_scoped_entry_without_project_path_is_excluded(self):
        install_dir = self.plugin_cache_dir('market', 'no-project-path', '1.0.0')
        write_skill(install_dir / 'skills', 'x-skill', description='d')
        self.write_installed_plugins({
            'proj@market': [{'scope': 'project', 'installPath': str(install_dir)}],
        })
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 0)

    def write_settings(self, path, enabled_plugins):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'enabledPlugins': enabled_plugins}), encoding='utf-8')

    def test_plugin_disabled_in_user_settings_is_skipped(self):
        install_dir = self.plugin_cache_dir('market', 'off', '1.0.0')
        write_skill(install_dir / 'skills', 'off-skill', description='d')
        self.write_installed_plugins({'off@market': [{'scope': 'user', 'installPath': str(install_dir)}]})
        self.write_settings(self.home / '.claude/settings.json', {'off@market': False})
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 0)

    def test_project_settings_override_user_settings_for_enablement(self):
        install_dir = self.plugin_cache_dir('market', 'reenabled', '1.0.0')
        write_skill(install_dir / 'skills', 're-skill', description='d')
        self.write_installed_plugins({'re@market': [{'scope': 'user', 'installPath': str(install_dir)}]})
        self.write_settings(self.home / '.claude/settings.json', {'re@market': False})
        self.write_settings(self.project / '.claude/settings.json', {'re@market': True})
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 1)

    def test_project_local_settings_override_project_settings_for_enablement(self):
        install_dir = self.plugin_cache_dir('market', 'localoff', '1.0.0')
        write_skill(install_dir / 'skills', 'local-off-skill', description='d')
        self.write_installed_plugins({'lo@market': [{'scope': 'user', 'installPath': str(install_dir)}]})
        self.write_settings(self.project / '.claude/settings.json', {'lo@market': True})
        self.write_settings(self.project / '.claude/settings.local.json', {'lo@market': False})
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 0)

    def test_plugin_not_mentioned_in_any_settings_file_defaults_to_enabled(self):
        install_dir = self.plugin_cache_dir('market', 'unmentioned', '1.0.0')
        write_skill(install_dir / 'skills', 'unmentioned-skill', description='d')
        self.write_installed_plugins({'um@market': [{'scope': 'user', 'installPath': str(install_dir)}]})
        self.write_settings(self.home / '.claude/settings.json', {'someone-else@market': False})
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 1)

    # --- N2: installPath confinement and UNC rejection ----------------------

    def test_install_path_outside_claude_plugins_is_skipped_and_recorded(self):
        outside = self.base / 'somewhere-else' / 'not-under-plugins'
        write_skill(outside / 'skills', 'escaped-skill', description='d')
        self.write_installed_plugins({'esc@market': [{'scope': 'user', 'installPath': str(outside)}]})
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 0)
        self.assertEqual(len(plugins['skipped_install_paths']), 1)
        self.assertEqual(plugins['skipped_install_paths'][0]['installPath'], str(outside))
        self.assertIn('outside', plugins['skipped_install_paths'][0]['reason'])

    def test_unc_install_path_is_skipped_and_recorded_without_touching_the_filesystem(self):
        for unc in (r'\\evil-host\share\plugin', '//evil-host/share/plugin'):
            with self.subTest(unc=unc):
                self.write_installed_plugins({'unc@market': [{'scope': 'user', 'installPath': unc}]})
                plugins = self.inv()['roots']['claude_plugins']
                self.assertEqual(plugins['skill_count'], 0)
                self.assertEqual(len(plugins['skipped_install_paths']), 1)
                self.assertEqual(plugins['skipped_install_paths'][0]['installPath'], unc)
                self.assertIn('UNC', plugins['skipped_install_paths'][0]['reason'])

    def test_symlinked_install_path_staying_inside_claude_plugins_is_accepted(self):
        real_target = self.plugin_cache_dir('market', 'real-plugin-storage')
        write_skill(real_target / 'skills', 'linked-skill', description='d')
        link = self.plugin_cache_dir('market', 'linked-plugin')
        try:
            link.symlink_to(real_target, target_is_directory=True)
        except OSError as error:
            self.skipTest('Host does not support test symlinks: ' + str(error))
        self.write_installed_plugins({'linked@market': [{'scope': 'user', 'installPath': str(link)}]})
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 1)
        self.assertEqual(plugins['skipped_install_paths'], [])

    def test_symlinked_install_path_escaping_claude_plugins_is_skipped(self):
        # The confinement check resolves symlinks first (N2): a link that SITS
        # inside ~/.claude/plugins but points outside it must still be rejected.
        outside_target = self.base / 'real-plugin-storage-outside'
        write_skill(outside_target / 'skills', 'escaped-skill', description='d')
        link = self.plugin_cache_dir('market', 'escaping-plugin')
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(outside_target, target_is_directory=True)
        except OSError as error:
            self.skipTest('Host does not support test symlinks: ' + str(error))
        self.write_installed_plugins({'escaping@market': [{'scope': 'user', 'installPath': str(link)}]})
        plugins = self.inv()['roots']['claude_plugins']
        self.assertEqual(plugins['skill_count'], 0)
        self.assertEqual(len(plugins['skipped_install_paths']), 1)
        self.assertIn('outside', plugins['skipped_install_paths'][0]['reason'])


class SkillInventoryPolicySchemaTests(unittest.TestCase):
    """`workflow.validate_policy` accepts a documented `skills.inventory_thresholds`
    override and rejects anything else under that key."""

    def policy(self):
        return w.default_policy(True, True)

    def test_valid_override_is_accepted(self):
        policy = self.policy()
        policy['skills'] = {'inventory_thresholds': {'skill_count': 50, 'description_bytes': 4096}}
        validated = w.validate_policy(policy)
        self.assertEqual(validated['skills']['inventory_thresholds']['skill_count'], 50)

    def test_partial_override_is_accepted(self):
        policy = self.policy()
        policy['skills'] = {'inventory_thresholds': {'skill_count': 50}}
        w.validate_policy(policy)  # must not raise

    def test_missing_skills_section_is_accepted(self):
        w.validate_policy(self.policy())  # must not raise; the section is optional

    def test_non_integer_threshold_is_rejected(self):
        policy = self.policy()
        policy['skills'] = {'inventory_thresholds': {'skill_count': 1.5}}
        with self.assertRaisesRegex(w.WorkflowError, 'SKILL_INVENTORY_THRESHOLDS_INVALID'):
            w.validate_policy(policy)

    def test_zero_or_negative_threshold_is_rejected(self):
        for value in (0, -1):
            with self.subTest(value=value):
                policy = self.policy()
                policy['skills'] = {'inventory_thresholds': {'skill_count': value}}
                with self.assertRaisesRegex(w.WorkflowError, 'SKILL_INVENTORY_THRESHOLDS_INVALID'):
                    w.validate_policy(policy)

    def test_unknown_threshold_key_is_rejected(self):
        policy = self.policy()
        policy['skills'] = {'inventory_thresholds': {'not_a_real_key': 5}}
        with self.assertRaisesRegex(w.WorkflowError, 'SKILL_INVENTORY_THRESHOLDS_INVALID'):
            w.validate_policy(policy)

    def test_empty_overrides_map_is_rejected(self):
        policy = self.policy()
        policy['skills'] = {'inventory_thresholds': {}}
        with self.assertRaisesRegex(w.WorkflowError, 'SKILL_INVENTORY_THRESHOLDS_INVALID'):
            w.validate_policy(policy)

    def test_non_dict_skills_section_is_rejected(self):
        policy = self.policy()
        policy['skills'] = ['not', 'a', 'dict']
        with self.assertRaisesRegex(w.WorkflowError, 'POLICY_SECTION_INVALID: skills'):
            w.validate_policy(policy)


class SkillInventoryJSONSchemaTests(unittest.TestCase):
    """`policy-v1.schema.json` itself (not just workflow.validate_policy) accepts and
    rejects the same `skills.inventory_thresholds` shape."""

    @classmethod
    def setUpClass(cls):
        from jsonschema import Draft202012Validator
        cls.Draft202012Validator = Draft202012Validator
        schema_path = Path(__file__).resolve().parents[1] / 'schemas/policy-v1.schema.json'
        cls.schema = json.loads(schema_path.read_text(encoding='utf-8'))

    def validator(self):
        return self.Draft202012Validator(self.schema)

    def test_schema_is_itself_valid(self):
        self.Draft202012Validator.check_schema(self.schema)

    def test_schema_accepts_a_full_policy_without_a_skills_section(self):
        policy = json.loads(json.dumps(w.default_policy(True, True)))
        self.validator().validate(policy)  # must not raise

    def test_schema_accepts_valid_inventory_thresholds(self):
        policy = json.loads(json.dumps(w.default_policy(True, True)))
        policy['skills'] = {'inventory_thresholds': {'skill_count': 50, 'description_bytes': 4096}}
        self.validator().validate(policy)  # must not raise

    def test_schema_rejects_an_unknown_key_under_inventory_thresholds(self):
        policy = json.loads(json.dumps(w.default_policy(True, True)))
        policy['skills'] = {'inventory_thresholds': {'not_a_real_key': 5}}
        self.assertTrue(list(self.validator().iter_errors(policy)))

    def test_schema_rejects_an_unknown_key_under_skills(self):
        policy = json.loads(json.dumps(w.default_policy(True, True)))
        policy['skills'] = {'unexpected': True}
        self.assertTrue(list(self.validator().iter_errors(policy)))

    def test_schema_rejects_a_non_positive_threshold(self):
        policy = json.loads(json.dumps(w.default_policy(True, True)))
        policy['skills'] = {'inventory_thresholds': {'skill_count': 0}}
        self.assertTrue(list(self.validator().iter_errors(policy)))

    def test_schema_rejects_empty_inventory_thresholds(self):
        policy = json.loads(json.dumps(w.default_policy(True, True)))
        policy['skills'] = {'inventory_thresholds': {}}
        self.assertTrue(list(self.validator().iter_errors(policy)))


class DoctorSkillInventoryIntegrationTests(unittest.TestCase):
    """`doctor()` only scans on a --project run, never fails from a scan error, and
    warns through the same non-blocking `warnings` list every other doctor check uses."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.home = self.root / 'fake-home'
        EnvOverride(self, 'SANDUQ_SKILLS_HOME', str(self.home))
        EnvOverride(self, 'CODEX_HOME', str(self.root / 'fake-codex-home'))

    def test_plain_doctor_never_runs_the_scan(self):
        calls = []
        original = w.skill_inventory.inventory
        w.skill_inventory.inventory = lambda *a, **k: (calls.append(1) or original(*a, **k))
        try:
            result = w.doctor(self.root, w.default_policy(True, True), check_delegation=False)
        finally:
            w.skill_inventory.inventory = original
        self.assertEqual(calls, [])
        self.assertNotIn('skill_inventory', result)

    def test_project_doctor_carries_the_full_inventory_and_it_never_blocks_by_itself(self):
        result = w.doctor(self.root, w.default_policy(True, True), project=True, check_delegation=False)
        self.assertIn('skill_inventory', result)
        self.assertEqual(result['skill_inventory']['hosts']['claude']['combined']['skill_count'], 0)
        self.assertFalse(any(m.startswith('SKILL_INVENTORY_LARGE') for m in result['warnings']))

    def test_project_doctor_warns_past_a_configured_threshold(self):
        write_skill(self.root / '.claude/skills', 'skill-0', description='d')
        write_skill(self.root / '.claude/skills', 'skill-1', description='d')
        write_skill(self.root / '.claude/skills', 'skill-2', description='d')
        policy = w.default_policy(True, True)
        policy['skills'] = {'inventory_thresholds': {'skill_count': 2}}
        result = w.doctor(self.root, policy, project=True, check_delegation=False)
        self.assertTrue(any(m.startswith('SKILL_INVENTORY_LARGE: claude') for m in result['warnings']))
        self.assertEqual(result['skill_inventory']['hosts']['claude']['combined']['skill_count'], 3)

    def test_a_scan_failure_is_reported_as_a_warning_never_a_doctor_crash(self):
        def boom(*args, **kwargs):
            raise RuntimeError('disk exploded')
        original = w.skill_inventory.inventory
        w.skill_inventory.inventory = boom
        try:
            result = w.doctor(self.root, w.default_policy(True, True), project=True, check_delegation=False)
        finally:
            w.skill_inventory.inventory = original
        self.assertIsNone(result['skill_inventory'])
        self.assertTrue(any(m.startswith('SKILL_INVENTORY_UNAVAILABLE') for m in result['warnings']))
        # A skill-inventory scan failure is a warning, never a reason doctor itself fails;
        # whatever else the bare fixture project produces stays whatever it would without this change.
        self.assertNotIn('SKILL_INVENTORY_UNAVAILABLE', result['errors'])


if __name__ == '__main__':
    unittest.main()
