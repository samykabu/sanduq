import json
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sanduq_ci as ci
import workflow as w
import test_workflow as fixture

EXTENSIONS = Path(__file__).resolve().parents[2]
ASSETS = {
    'workflow-gates.yml': EXTENSIONS / 'workflow/assets/github/workflow-gates.yml',
    'documentation-gates.yml': EXTENSIONS / 'assure/assets/github/documentation-gates.yml',
    'user-manual-preview.yml': EXTENSIONS / 'user-manual/assets/github/user-manual-preview.yml',
    'user-manual-release.yml': EXTENSIONS / 'user-manual/assets/github/user-manual-release.yml',
}


def self_hosted():
    selection = ci.default_ci()
    selection['policy'] = 'self-hosted-required'
    selection['runners'] = {'linux': ['self-hosted', 'homek8-general'], 'windows': ['self-hosted', 'windows']}
    selection['capabilities'] = {'system_packages': 'preinstalled', 'python': 'preinstalled',
                                 'python_version': '3.13'}
    return selection


class RenderTests(unittest.TestCase):
    def test_every_shipped_asset_renders_to_valid_yaml_under_both_selections(self):
        for name, path in ASSETS.items():
            for label, selection in (('hosted', ci.default_ci()), ('self-hosted', self_hosted())):
                with self.subTest(asset=name, selection=label):
                    body = ci.render(path.read_bytes(), selection).decode()
                    self.assertNotIn('__sanduq_', body, 'unsubstituted token')
                    self.assertNotIn('sanduq:if', body, 'marker leaked into the rendered file')
                    self.assertNotIn('sanduq:endif', body)
                    self.assertTrue(yaml.safe_load(body).get('jobs'), name)

    def test_declared_runner_labels_reach_every_job(self):
        for name, path in ASSETS.items():
            with self.subTest(asset=name):
                body = ci.render(path.read_bytes(), self_hosted()).decode()
                self.assertIn('runs-on: [self-hosted, homek8-general]', body)
                self.assertNotIn('ubuntu-latest', body)

    def test_a_single_label_renders_as_a_scalar_not_a_sequence(self):
        selection = ci.default_ci()
        selection['runners']['linux'] = ['homek8-general']
        # The renderer preserves the template's own line ending, so this must not
        # depend on how the checkout landed.
        body = ci.render(ASSETS['workflow-gates.yml'].read_bytes(), selection).decode().replace('\r\n', '\n')
        self.assertIn('runs-on: homek8-general\n', body)
        document = yaml.safe_load(body)
        self.assertEqual(list(document['jobs'].values())[0]['runs-on'], 'homek8-general')

    def test_preinstalled_capabilities_remove_steps_a_self_hosted_runner_cannot_execute(self):
        for name in ('user-manual-preview.yml', 'user-manual-release.yml'):
            with self.subTest(asset=name):
                body = ci.render(ASSETS[name].read_bytes(), self_hosted()).decode()
                self.assertNotIn('sudo', body, 'an apt step survived a runner with no sudo')
                self.assertNotIn('actions/setup-python', body)

    def test_the_shipped_default_still_produces_github_hosted_workflows(self):
        # Adopting this release must not change CI for a project that never
        # records a selection of its own.
        for name, path in ASSETS.items():
            with self.subTest(asset=name):
                body = ci.render(path.read_bytes(), ci.default_ci()).decode()
                self.assertIn('runs-on: ubuntu-latest', body)
        preview = ci.render(ASSETS['user-manual-preview.yml'].read_bytes(), ci.default_ci()).decode()
        self.assertIn('sudo apt-get install -y age', preview)
        self.assertIn('actions/setup-python', preview)
        gates = ci.render(ASSETS['workflow-gates.yml'].read_bytes(), ci.default_ci()).decode()
        self.assertIn('actions/setup-python', gates)
        self.assertIn('ci_gate.py', gates)

    def test_every_template_is_itself_valid_yaml_before_rendering(self):
        # A token must be a plain scalar. '@' is a YAML reserved indicator, so a
        # token spelled with it makes the shipped file unparseable for the lint
        # job and for editor tooling, even though it renders correctly.
        for name, path in ASSETS.items():
            with self.subTest(asset=name):
                document = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
                self.assertTrue(document.get('jobs'), name)

    def test_multiple_labels_render_as_a_yaml_sequence_not_a_string(self):
        for name, path in ASSETS.items():
            with self.subTest(asset=name):
                document = yaml.safe_load(ci.render(path.read_bytes(), self_hosted()).decode())
                for job in document['jobs'].values():
                    self.assertEqual(job['runs-on'], ['self-hosted', 'homek8-general'])

    def test_line_endings_follow_the_template(self):
        template = ASSETS['workflow-gates.yml'].read_bytes().replace(b'\r\n', b'\n')
        self.assertNotIn(b'\r\n', ci.render(template, ci.default_ci()))
        self.assertIn(b'\r\n', ci.render(template.replace(b'\n', b'\r\n'), ci.default_ci()))

    def test_unknown_flag_or_token_is_refused_rather_than_silently_emitted(self):
        cases = (
            (b'# sanduq:if invented\nx\n# sanduq:endif\n', 'CI_TEMPLATE_FLAG_UNKNOWN'),
            (b'runs-on: __sanduq_runs_on_solaris__\n', 'CI_TEMPLATE_TOKEN_UNKNOWN'),
            (b'# sanduq:if python_setup_action\nx\n', 'CI_TEMPLATE_UNBALANCED'),
            (b'# sanduq:endif\n', 'CI_TEMPLATE_UNBALANCED'),
        )
        for template, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ci.CIPolicyError, message):
                    ci.render(template, ci.default_ci())

    def test_a_platform_the_project_never_declared_fails_loudly(self):
        selection = ci.default_ci()
        selection['runners'].pop('windows')
        with self.assertRaisesRegex(ci.CIPolicyError, 'CI_TEMPLATE_TOKEN_UNKNOWN'):
            ci.render(b'runs-on: __sanduq_runs_on_windows__\n', selection)

    def test_a_dropped_block_takes_its_nested_content_with_it(self):
        template = (b'# sanduq:if system_packages_apt\n'
                    b'outer\n'
                    b'# sanduq:if python_setup_action\n'
                    b'inner\n'
                    b'# sanduq:endif\n'
                    b'# sanduq:endif\n'
                    b'always\n')
        selection = ci.default_ci()
        selection['capabilities']['system_packages'] = 'preinstalled'
        self.assertEqual(ci.render(template, selection), b'always\n')
        self.assertEqual(ci.render(template, ci.default_ci()), b'outer\ninner\nalways\n')


class ValidationTests(unittest.TestCase):
    def test_the_shipped_default_is_valid(self):
        self.assertEqual(ci.validate_ci(ci.default_ci()), ci.default_ci())

    def test_each_malformed_selection_is_named_precisely(self):
        dated = {'workflow': 'w', 'platform': 'linux', 'reason': 'r', 'removed_by': 'x', 'decided': 'yesterday'}
        cases = {
            'CI_PROVIDER_UNSUPPORTED': lambda s: s.update(provider='jenkins'),
            'CI_RUNNER_POLICY_INVALID': lambda s: s.update(policy='whatever'),
            'CI_RUNNER_LINUX_REQUIRED': lambda s: s.update(runners={'windows': ['x']}),
            'CI_RUNNER_LABELS_INVALID': lambda s: s['runners'].update(linux=[]),
            'CI_RUNNER_PLATFORM_UNKNOWN': lambda s: s['runners'].update(solaris=['x']),
            'CI_SYSTEM_PACKAGES_INVALID': lambda s: s['capabilities'].update(system_packages='yum'),
            'CI_PYTHON_PROVISIONING_INVALID': lambda s: s['capabilities'].update(python='maybe'),
            'CI_PYTHON_VERSION_INVALID': lambda s: s['capabilities'].update(python_version='three'),
            'CI_EXCEPTION_FIELD_REQUIRED': lambda s: s.update(exceptions=[{'workflow': 'w'}]),
            'CI_EXCEPTION_DECIDED_INVALID': lambda s: s.update(exceptions=[dated]),
        }
        for message, mutate in cases.items():
            with self.subTest(message=message):
                selection = ci.default_ci()
                mutate(selection)
                with self.assertRaisesRegex(ci.CIPolicyError, message):
                    ci.validate_ci(selection)

    def test_hosted_label_families_are_recognized(self):
        for labels in (['ubuntu-latest'], ['windows-2022'], ['macos-14-xlarge']):
            self.assertTrue(ci.hosted(labels), labels)
        for labels in (['self-hosted', 'homek8-general'], ['homek8-general'], ['self-hosted', 'ubuntu-latest']):
            self.assertFalse(ci.hosted(labels), labels)

    def test_the_shipped_schema_matches_the_shipped_default(self):
        schema = json.loads((EXTENSIONS / 'workflow/schemas/policy-v1.schema.json').read_text(encoding='utf-8'))
        section = schema['properties']['ci']
        selection = ci.default_ci()
        # Gate is optional in the schema so pre-selection consumer policies stay valid.
        self.assertEqual(sorted(section['required']), sorted(k for k in selection if k not in ('exceptions', 'gate')))
        gate = section['properties']['gate']
        self.assertEqual(sorted(gate['properties']['mode']['enum']), sorted(ci.GATE_MODES))
        self.assertEqual(sorted(gate['properties']['scope']['enum']), sorted(ci.GATE_SCOPES))
        self.assertEqual(sorted(gate['properties']['rules']['properties']), sorted(ci.GATE_RULES))
        self.assertEqual(sorted(section['properties']['provider']['enum']), sorted(ci.PROVIDERS))
        self.assertEqual(sorted(section['properties']['policy']['enum']), sorted(ci.RUNNER_POLICIES))
        capabilities = section['properties']['capabilities']['properties']
        self.assertEqual(sorted(capabilities['system_packages']['enum']), sorted(ci.SYSTEM_PACKAGES))
        self.assertEqual(sorted(capabilities['python']['enum']), sorted(ci.PYTHON_PROVISIONING))
        self.assertEqual(sorted(section['properties']['runners']['properties']), sorted(ci.PLATFORMS))

    def test_gate_modes_rules_and_legacy_selection(self):
        selection = ci.default_ci()
        self.assertEqual(ci.gate_config(selection)['mode'], 'advisory')
        self.assertEqual(ci.gate_config(selection)['scope'], 'managed-only')
        legacy = dict(selection); legacy.pop('gate')
        self.assertEqual(ci.gate_config(legacy)['mode'], 'required')
        self.assertEqual(ci.gate_config(legacy)['scope'], 'all-prs')
        for rule, dependency in (('live_answers', 'decisions'), ('candidate_merge', 'receipts'),
                                 ('portability', 'receipts'), ('task_links', 'tasks')):
            with self.subTest(rule=rule):
                gate = ci.gate_config(selection).copy()
                gate['rules'] = dict(gate['rules'], **{rule: True, dependency: False})
                with self.assertRaisesRegex(ci.CIPolicyError, 'CI_GATE_RULE_DEPENDENCY'):
                    ci.validate_gate(gate)


class MergeCandidateTemplateTests(unittest.TestCase):
    def test_selected_candidate_uses_pr_merge_ref(self):
        source = ASSETS['workflow-gates.yml'].read_bytes()
        selection = ci.default_ci()
        head = ci.render(source, selection).decode()
        self.assertIn('ref: ${{ github.event.pull_request.head.sha }}', head)
        selection['gate']['rules']['candidate_merge'] = True
        merged = ci.render(source, selection).decode()
        self.assertNotIn('ref: ${{ github.event.pull_request.head.sha }}', merged)
        self.assertIn('fetch-depth: 0', merged)


class ExceptionTests(unittest.TestCase):
    def test_hosted_allowed_never_demands_a_reason(self):
        self.assertEqual(ci.exception_errors(ci.default_ci(), ['a.yml', 'b.yml']), [])

    def test_self_hosted_required_names_each_undocumented_workflow_and_platform(self):
        selection = ci.default_ci()
        selection['policy'] = 'self-hosted-required'
        errors = ci.exception_errors(selection, ['gates.yml'])
        self.assertEqual(len(errors), 2)  # linux and windows are both hosted
        self.assertTrue(all('CI_HOSTED_RUNNER_UNDOCUMENTED' in e and 'gates.yml' in e for e in errors))

    def test_a_dated_exception_clears_exactly_its_own_workflow_and_platform(self):
        selection = ci.default_ci()
        selection['policy'] = 'self-hosted-required'
        selection['runners'] = {'linux': ['self-hosted', 'homek8-general'], 'windows': ['windows-latest']}
        selection['exceptions'] = [{'workflow': 'gates.yml', 'platform': 'windows',
                                    'reason': 'no self-hosted Windows runner is registered',
                                    'removed_by': 'register a Windows scale set', 'decided': '2026-09-22'}]
        self.assertEqual(ci.exception_errors(selection, ['gates.yml']), [])
        # A second workflow on the same hosted runner is a separate decision.
        self.assertEqual(len(ci.exception_errors(selection, ['gates.yml', 'release.yml'])), 1)


class PolicyIntegrationTests(unittest.TestCase):
    configure = fixture.WorkflowTests.configure
    setUp = fixture.WorkflowTests.setUp

    def install_asset(self, name='workflow-gates.yml', extension='workflow'):
        asset = self.root / '.specify/extensions' / extension / 'assets/github' / name
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(ASSETS[name].read_bytes())
        return asset

    def test_a_policy_written_before_ci_selection_existed_keeps_its_behaviour(self):
        legacy = {k: v for k, v in w.default_policy(True, True).items() if k != 'ci'}
        (self.root / '.specify/workflow.yml').write_text(yaml.safe_dump(legacy), encoding='utf-8')
        self.assertEqual(ci.gate_config(w.load_policy(self.root)['ci'])['mode'], 'required')

    def test_a_malformed_ci_selection_stops_the_workflow(self):
        policy = w.default_policy(True, True)
        policy['ci']['runners']['linux'] = []
        (self.root / '.specify/workflow.yml').write_text(yaml.safe_dump(policy), encoding='utf-8')
        with self.assertRaisesRegex(w.WorkflowError, 'CI_RUNNER_LABELS_INVALID'):
            w.load_policy(self.root)

    def test_doctor_reports_a_workflow_file_left_behind_by_a_changed_selection(self):
        asset = self.install_asset()
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        policy = w.load_policy(self.root)
        target.write_bytes(ci.render(asset.read_bytes(), policy['ci']))
        self.assertEqual(w.ci_errors(self.root, policy), [])

        policy['ci']['runners']['linux'] = ['self-hosted', 'homek8-general']
        self.assertTrue(any('CI_WORKFLOW_STALE' in e for e in w.ci_errors(self.root, policy)))

    def test_a_file_kept_by_preserve_ci_is_the_projects_own_business(self):
        self.install_asset()
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'name: Local policy\njobs: {}\n')
        policy = w.load_policy(self.root)
        self.assertTrue(any('CI_WORKFLOW_STALE' in e for e in w.ci_errors(self.root, policy)))
        w.write(self.root / '.specify/workflow/install-receipt.json',
                {'preserved_ci': {'path': '.github/workflows/sanduq-workflow-gates.yml'}})
        self.assertEqual(w.ci_errors(self.root, policy), [])

    def test_a_preserved_file_recorded_in_the_tracked_lock_needs_no_receipt(self):
        self.install_asset()
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'name: Local policy\njobs: {}\n')
        policy = w.load_policy(self.root)
        self.assertTrue(any('CI_WORKFLOW_STALE' in e for e in w.ci_errors(self.root, policy)))
        self.assertEqual(w.ci_errors(self.root, policy, '.github/workflows/sanduq-workflow-gates.yml'), [])
        w.write(self.root / '.specify/workflow/install-lock.json',
                {'preserved_ci': {'path': '.github/workflows/sanduq-workflow-gates.yml'}})
        self.assertFalse((self.root / '.specify/workflow/install-receipt.json').exists())
        self.assertEqual(w.ci_errors(self.root, policy), [])

    def test_doctor_demands_a_reason_for_a_hosted_runner_the_project_forbade(self):
        self.install_asset()
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        policy = w.load_policy(self.root)
        policy['ci']['policy'] = 'self-hosted-required'
        target.write_bytes(ci.render(self.install_asset().read_bytes(), policy['ci']))
        errors = w.ci_errors(self.root, policy)
        self.assertTrue(any('CI_HOSTED_RUNNER_UNDOCUMENTED' in e for e in errors), errors)
        self.assertTrue(any('sanduq-workflow-gates.yml' in e for e in errors), errors)

    def test_provider_none_manages_no_workflow_files_at_all(self):
        policy = w.load_policy(self.root)
        policy['ci']['provider'] = 'none'
        policy['ci']['policy'] = 'self-hosted-required'
        target = self.root / '.github/workflows/sanduq-workflow-gates.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'anything\n')
        self.assertTrue(any('CI_PROVIDER_NONE_FILE_PRESENT' in error
                            for error in w.ci_errors(self.root, policy)))
        target.unlink()
        self.assertEqual(w.ci_errors(self.root, policy), [])

    def test_the_cli_records_a_selection_once_and_persists_it(self):
        script = EXTENSIONS / 'workflow/scripts/workflow.py'
        result = subprocess.run([sys.executable, str(script), '--root', str(self.root), 'ci',
                                 '--policy', 'self-hosted-required',
                                 '--linux', 'self-hosted,homek8-general',
                                 '--system-packages', 'preinstalled', '--python', 'preinstalled'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        saved = json.loads(result.stdout)['ci']
        self.assertEqual(saved['runners']['linux'], ['self-hosted', 'homek8-general'])
        reloaded = w.load_policy(self.root)['ci']
        self.assertEqual(reloaded['policy'], 'self-hosted-required')
        self.assertEqual(reloaded['capabilities']['python'], 'preinstalled')

    def test_the_cli_refuses_a_selection_it_could_not_render(self):
        script = EXTENSIONS / 'workflow/scripts/workflow.py'
        result = subprocess.run([sys.executable, str(script), '--root', str(self.root), 'ci', '--linux', 'none'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('CI_RUNNER_LINUX_REQUIRED', result.stdout + result.stderr)
        # The rejected selection must not have reached the policy file.
        self.assertEqual(w.load_policy(self.root)['ci']['runners']['linux'], ['ubuntu-latest'])

    def test_the_runtime_works_from_a_copied_scripts_directory(self):
        # project-init.sh runs workflow.py out of
        # .specify/extensions/workflow/scripts/, a plain copy of this directory
        # with no package layout around it. A shared module reachable only from
        # the source tree makes that invocation die on import, which no
        # source-tree test would notice.
        import shutil
        import tempfile
        copy = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, copy, True)
        scripts = copy / '.specify/extensions/workflow/scripts'
        shutil.copytree(EXTENSIONS / 'workflow/scripts', scripts,
                        ignore=shutil.ignore_patterns('__pycache__'))
        subprocess.run(['git', 'init', '-q'], cwd=copy, check=True, capture_output=True)
        (copy / '.specify/workflow.yml').write_text(
            yaml.safe_dump(w.default_policy(False, False)), encoding='utf-8')
        for action in (['project-defaults'], ['ci', '--show']):
            with self.subTest(action=action[0]):
                result = subprocess.run([sys.executable, str(scripts / 'workflow.py'), *action],
                                        cwd=copy, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(json.loads(result.stdout))

    def test_changing_ci_never_invalidates_completed_semantic_work(self):
        before = w.default_policy(True, True)
        after = w.default_policy(True, True)
        after['ci']['runners']['linux'] = ['self-hosted']
        self.assertEqual(w.policy_cutoff(before, after), len(w.BASE_STAGES))


if __name__ == '__main__':
    unittest.main()
