import importlib.util
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


class SkillInventoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.home = self.base / 'home'
        self.project = self.base / 'project'
        self.home.mkdir()
        self.project.mkdir()

    def inv(self, policy=None):
        return si.inventory(self.project, policy, home=self.home)

    # --- missing roots -------------------------------------------------

    def test_missing_roots_report_zero_and_do_not_exist(self):
        result = self.inv()
        for name in ('home', 'project_claude', 'project_agents'):
            root = result['roots'][name]
            self.assertFalse(root['exists'])
            self.assertEqual(root['skill_count'], 0)
            self.assertEqual(root['description_bytes'], 0)
            self.assertEqual(root['max_description_bytes'], 0)
            self.assertEqual(root['skill_md_bytes'], 0)
        self.assertEqual(result['combined']['skill_count'], 0)
        self.assertEqual(result['duplicates'], {})
        self.assertIsNone(si.warning(result))

    # --- below threshold -------------------------------------------------

    def test_counts_and_description_bytes_below_threshold(self):
        write_skill(self.home / '.claude/skills', 'alpha', description='Alpha skill')
        write_skill(self.project / '.claude/skills', 'beta', description='Beta skill')
        write_skill(self.project / '.agents/skills', 'gamma', description='Gamma skill')
        result = self.inv()
        self.assertEqual(result['roots']['home']['skill_count'], 1)
        self.assertEqual(result['roots']['project_claude']['skill_count'], 1)
        self.assertEqual(result['roots']['project_agents']['skill_count'], 1)
        self.assertEqual(result['combined']['skill_count'], 3)
        self.assertGreater(result['combined']['description_bytes'], 0)
        self.assertGreater(result['roots']['home']['skill_md_bytes'], 0)
        self.assertIsNone(si.warning(result))

    # --- above threshold (via policy override, so the test stays fast) ----

    def test_warns_when_combined_skill_count_exceeds_threshold(self):
        for i in range(3):
            write_skill(self.project / '.claude/skills', 'skill-%d' % i, description='d')
        policy = {'skills': {'inventory_thresholds': {'skill_count': 2}}}
        result = self.inv(policy)
        self.assertEqual(result['combined']['skill_count'], 3)
        self.assertEqual(result['thresholds']['skill_count'], 2)
        message = si.warning(result)
        self.assertIsNotNone(message)
        self.assertTrue(message.startswith('SKILL_INVENTORY_LARGE:'))

    def test_warns_when_combined_description_bytes_exceed_threshold(self):
        write_skill(self.project / '.claude/skills', 'big', description='x' * 100)
        policy = {'skills': {'inventory_thresholds': {'description_bytes': 10}}}
        result = self.inv(policy)
        self.assertGreater(result['combined']['description_bytes'], 10)
        self.assertIsNotNone(si.warning(result))

    def test_default_thresholds_do_not_warn_for_a_small_project(self):
        write_skill(self.project / '.claude/skills', 'only-one', description='short')
        result = self.inv()
        self.assertEqual(result['thresholds'], si.DEFAULT_THRESHOLDS)
        self.assertIsNone(si.warning(result))

    # --- malformed / missing frontmatter -----------------------------------

    def test_skill_without_frontmatter_counts_but_zero_description_bytes(self):
        write_skill(self.project / '.claude/skills', 'no-frontmatter', description=None, body='# Just a heading')
        result = self.inv()
        self.assertEqual(result['roots']['project_claude']['skill_count'], 1)
        self.assertEqual(result['roots']['project_claude']['description_bytes'], 0)

    def test_malformed_yaml_frontmatter_counts_but_zero_description_bytes(self):
        path = (self.project / '.claude/skills' / 'broken' / 'SKILL.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('---\ndescription: [unterminated\n---\nbody\n', encoding='utf-8')
        result = self.inv()
        self.assertEqual(result['roots']['project_claude']['skill_count'], 1)
        self.assertEqual(result['roots']['project_claude']['description_bytes'], 0)

    def test_non_string_description_counts_but_zero_description_bytes(self):
        write_skill(self.project / '.claude/skills', 'listy', description=None,
                    extra_frontmatter='description:\n  - one\n  - two')
        result = self.inv()
        self.assertEqual(result['roots']['project_claude']['skill_count'], 1)
        self.assertEqual(result['roots']['project_claude']['description_bytes'], 0)

    def test_unreadable_skill_md_is_skipped_not_raised(self):
        # A directory named SKILL.md (not a file) must not raise: is_file() is False.
        (self.project / '.claude/skills/oddity/SKILL.md').mkdir(parents=True)
        result = self.inv()
        self.assertEqual(result['roots']['project_claude']['skill_count'], 0)

    # --- duplicates ---------------------------------------------------------

    def test_duplicate_skill_name_across_roots_is_reported(self):
        write_skill(self.home / '.claude/skills', 'shared', description='home copy')
        write_skill(self.project / '.claude/skills', 'shared', description='project copy')
        write_skill(self.project / '.agents/skills', 'unique', description='only here')
        result = self.inv()
        self.assertEqual(result['duplicates'], {'shared': ['home', 'project_claude']})

    def test_no_duplicates_when_every_skill_name_is_unique(self):
        write_skill(self.home / '.claude/skills', 'alpha', description='a')
        write_skill(self.project / '.claude/skills', 'beta', description='b')
        result = self.inv()
        self.assertEqual(result['duplicates'], {})

    # --- symlinks -------------------------------------------------------

    def test_symlinked_skill_directory_is_counted_once(self):
        real = write_skill(self.project / '.claude/skills', 'real-skill', description='real').parent
        link = self.project / '.claude/skills' / 'aliased-skill'
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError as error:
            self.skipTest('Host does not support test symlinks: ' + str(error))
        result = self.inv()
        # Both directory entries resolve to the same real path, so they are
        # counted once, not twice.
        self.assertEqual(result['roots']['project_claude']['skill_count'], 1)

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
        self.assertEqual(result['roots']['project_claude']['skill_count'], 1)

    # --- policy override validation lives in workflow.py, exercised here on
    # the pure threshold-merge helper.

    def test_thresholds_merge_only_overridden_keys(self):
        merged = si.thresholds({'skills': {'inventory_thresholds': {'skill_count': 5}}})
        self.assertEqual(merged['skill_count'], 5)
        self.assertEqual(merged['description_bytes'], si.DEFAULT_THRESHOLDS['description_bytes'])

    def test_home_root_resolution_honors_sanduq_home_override(self):
        roots = si.resolve_roots(self.project, home=self.home)
        self.assertEqual(roots['home'], self.home / '.claude' / 'skills')

    def test_home_root_uses_env_override_when_no_explicit_home_given(self):
        import os
        old = os.environ.get('SANDUQ_HOME')
        os.environ['SANDUQ_HOME'] = str(self.home)
        try:
            self.assertEqual(si.home_root(), self.home)
        finally:
            if old is None:
                os.environ.pop('SANDUQ_HOME', None)
            else:
                os.environ['SANDUQ_HOME'] = old


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


class DoctorSkillInventoryIntegrationTests(unittest.TestCase):
    """`doctor()` always attaches the full inventory, and warns through the
    same non-blocking `warnings` list every other doctor check uses."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.home = self.root / 'fake-home'

    def test_doctor_result_carries_skill_inventory_and_it_never_blocks_by_itself(self):
        import os
        old = os.environ.get('SANDUQ_HOME')
        os.environ['SANDUQ_HOME'] = str(self.home)
        try:
            policy = w.default_policy(True, True)
            result = w.doctor(self.root, policy, check_delegation=False)
        finally:
            if old is None:
                os.environ.pop('SANDUQ_HOME', None)
            else:
                os.environ['SANDUQ_HOME'] = old
        self.assertIn('skill_inventory', result)
        self.assertEqual(result['skill_inventory']['combined']['skill_count'], 0)
        self.assertFalse(any(m.startswith('SKILL_INVENTORY_LARGE') for m in result['warnings']))

    def test_doctor_warns_skill_inventory_large_past_a_configured_threshold(self):
        import os
        for i in range(3):
            write_skill(self.root / '.claude/skills', 'skill-%d' % i, description='d')
        old = os.environ.get('SANDUQ_HOME')
        os.environ['SANDUQ_HOME'] = str(self.home)
        try:
            policy = w.default_policy(True, True)
            policy['skills'] = {'inventory_thresholds': {'skill_count': 2}}
            result = w.doctor(self.root, policy, check_delegation=False)
        finally:
            if old is None:
                os.environ.pop('SANDUQ_HOME', None)
            else:
                os.environ['SANDUQ_HOME'] = old
        self.assertTrue(any(m.startswith('SKILL_INVENTORY_LARGE') for m in result['warnings']))
        self.assertEqual(result['skill_inventory']['combined']['skill_count'], 3)


if __name__ == '__main__':
    unittest.main()
