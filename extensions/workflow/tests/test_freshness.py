import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
import sanduq_freshness as f
import workflow as w

class FreshnessTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        for args in [('init','-q'),('config','user.name','Test'),('config','user.email','test@example.invalid')]:
            subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True)
        (self.root/'src.txt').write_text('old behavior')
        self.feature='specs/001-example';(self.root/self.feature).mkdir(parents=True)
        (self.root/self.feature/'spec.md').write_text('# Example')
        (self.root/self.feature/'tasks.md').write_text('- [ ] T001 Behavior')
        subprocess.run(['git','add','.'],cwd=self.root,check=True)
        subprocess.run(['git','commit','-qm','baseline'],cwd=self.root,check=True)
        self.base=f.git(self.root,'rev-parse','HEAD').strip()
        self.state='.specify/extensions/assure/state/001-example-document.json'
        self.output='docs/001-example/QA.md';(self.root/self.output).parent.mkdir(parents=True);(self.root/self.output).write_text('Evidence')

    def call(self, action='status'):
        return f.record_or_status(self.root,self.feature,'document',self.state,action,[self.output],self.base)

    def test_state_and_workflow_writes_do_not_invalidate(self):
        self.call('record')
        (self.root/self.feature/'workflow').mkdir();(self.root/self.feature/'workflow/checkpoint.json').write_text('{}')
        self.assertTrue(self.call()['current'])
        (self.root/self.feature/'tasks.md').write_text('- [x] T001 Behavior')
        self.assertTrue(self.call()['current'])

    def test_a_later_decision_does_not_stale_receipts_recorded_before_it(self):
        label = self.feature + '/workflow/decisions.json'
        ledger = {'version': 1, 'feature': self.feature, 'decisions': [{'id': 'SD1', 'status': 'applied'}]}
        (self.root / label).parent.mkdir()
        (self.root / label).write_text(json.dumps(ledger))
        stored = w.fingerprint_files(self.root, [label], feature=self.feature)
        self.assertTrue(stored[label].startswith('decision-records:v1:SD1:'))
        ledger['decisions'].append({'id': 'SD2', 'status': 'pending'})  # the late module-map decision
        (self.root / label).write_text(json.dumps(ledger))
        self.assertEqual(w.fingerprint_files(self.root, [label], feature=self.feature, like=stored), stored)
        self.assertIn('SD1,SD2:', w.fingerprint_files(self.root, [label], feature=self.feature)[label])
        ledger['decisions'][0]['status'] = 'answered'  # a consumed decision still counts
        (self.root / label).write_text(json.dumps(ledger))
        self.assertNotEqual(w.fingerprint_files(self.root, [label], feature=self.feature, like=stored), stored)
        legacy = {label: 'a' * 64}  # a receipt recorded before projections stays byte-exact
        self.assertNotIn(':', w.fingerprint_files(self.root, [label], feature=self.feature, like=legacy)[label])

    def test_generated_graph_is_not_an_implicit_doc_input(self):
        graph = self.root / 'graphify-out/graph.json'
        graph.parent.mkdir(); graph.write_text('old graph')
        self.call('record'); graph.write_text('post-commit graph')
        self.assertTrue(self.call()['current'])
        # Explicitly selected graph outputs still carry integrity checks.
        recorded = f.fingerprints(self.root, ['graphify-out/graph.json'])
        graph.write_text('changed again')
        self.assertNotEqual(recorded, f.fingerprints(self.root, recorded))

    def progress_reports(self):
        return [directory + '/' + name
                for directory in (self.feature + '/progress', '.specify/progress', 'specs/002-other/progress')
                for name in ('model.json', 'view.md', 'facts.json', 'cache/inputs.json')]

    def test_progress_reports_do_not_change_inputs_or_state(self):
        reports = self.progress_reports()
        for kind in ('analyze', 'document'):
            for tracked in (False, True):
                with self.subTest(kind=kind, tracked=tracked):
                    state = f'.specify/extensions/assure/state/{kind}-{tracked}.json'
                    call = lambda action: f.record_or_status(
                        self.root, self.feature, kind, state, action, [self.output], self.base)
                    before = f.inputs(self.root, self.feature, kind, self.base)
                    call('record')
                    for name in reports:
                        path = self.root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('initial report', encoding='utf-8')
                    if tracked:
                        f.git(self.root, 'add', '--', *reports)
                        f.git(self.root, 'commit', '-qm', 'tracked reports')
                    for phase in ('added', 'changed', 'removed'):
                        with self.subTest(phase=phase):
                            if phase == 'changed':
                                for name in reports:
                                    (self.root / name).write_text('regenerated report', encoding='utf-8')
                                if tracked:
                                    f.git(self.root, 'add', '--', reports[0])
                            elif phase == 'removed':
                                for name in reports:
                                    (self.root / name).unlink()
                            after = f.inputs(self.root, self.feature, kind, self.base)
                            self.assertTrue(set(reports).isdisjoint(after['files']), after['files'])
                            self.assertEqual(before, after)
                            self.assertTrue(call('status')['current'])
                    if tracked:
                        f.git(self.root, 'add', '--', *reports)
                        f.git(self.root, 'commit', '-qm', 'removed reports')

    def test_progress_report_state_is_portable_to_a_clean_checkout(self):
        reports = self.progress_reports()
        (self.root / '.gitignore').write_text('specs/*/progress/\n.specify/progress/\n', encoding='utf-8')
        f.git(self.root, 'add', '--', '.gitignore', self.output)
        f.git(self.root, 'commit', '-qm', 'portable outputs and report exclusions')
        for name in reports:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('local report cache', encoding='utf-8')
        states = {kind: f'.specify/extensions/assure/state/{kind}.json' for kind in ('analyze', 'document')}
        for kind, state in states.items():
            f.record_or_status(self.root, self.feature, kind, state, 'record', [self.output], self.base)
        f.git(self.root, 'add', '--', *states.values())
        f.git(self.root, 'commit', '-qm', 'portable freshness state')
        with tempfile.TemporaryDirectory() as folder:
            clone = Path(folder) / 'checkout'
            # `clone -c` persists autocrlf in the clone's config; a transient `git -c ... clone` only
            # affects checkout, so later status calls (Linux CI) would see CRLF files as modified.
            f.git(self.root, 'clone', '-q', '-c', 'core.autocrlf=true', str(self.root), str(clone))
            self.assertEqual(f.git(clone, 'status', '--porcelain'), '')
            self.assertFalse((clone / self.feature / 'progress').exists())
            self.assertFalse((clone / '.specify/progress').exists())
            self.assertFalse((clone / 'specs/002-other/progress').exists())
            for kind, state in states.items():
                with self.subTest(kind=kind):
                    self.assertEqual(f.inputs(self.root, self.feature, kind, self.base),
                                     f.inputs(clone, self.feature, kind, self.base))
                    # Status reuses the saved base; the clone has no local report tree.
                    self.assertTrue(f.record_or_status(clone, self.feature, kind, state,
                                                      'status', [self.output])['current'])

    def test_real_progress_paths_and_semantic_inputs_still_invalidate(self):
        feature_paths = [self.feature + '/' + name for name in
                         ('spec.md', 'tasks.md', 'progress.md', 'src/progress/product.py')]
        product_paths = ['src/progress/product.py', 'progress/README.md', '.specify/progress.md',
                         'specs/002-other/progress.md', 'specs/002-other/src/progress/product.py', 'src.txt']
        for name in feature_paths + product_paths:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('original requirement or source', encoding='utf-8')
        # Another feature's files reach this branch through the diff once committed (#113).
        subprocess.run(['git', 'add', 'specs/002-other'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'other feature'], cwd=self.root, check=True)
        for kind in ('analyze', 'document'):
            names = feature_paths + (product_paths if kind == 'document' else [])
            state = f'.specify/extensions/assure/state/{kind}.json'
            call = lambda action: f.record_or_status(
                self.root, self.feature, kind, state, action, [self.output], self.base)
            before = f.inputs(self.root, self.feature, kind, self.base)
            self.assertTrue(set(names).issubset(before['files']))
            self.assertEqual(before['base_commit'], self.base if kind == 'document' else None)
            call('record')
            for name in names:
                with self.subTest(kind=kind, path=name):
                    path = self.root / name
                    path.write_text('changed requirement or source', encoding='utf-8')
                    self.assertFalse(call('status')['current'])
                    path.unlink()
                    self.assertFalse(call('status')['current'])
                    path.write_text('original requirement or source', encoding='utf-8')
                    self.assertTrue(call('status')['current'])

    def test_explicit_progress_outputs_are_still_checked(self):
        for kind in ('analyze', 'document'):
            for output in (self.feature + '/progress/view.md', '.specify/progress/model.json',
                           'specs/002-other/progress/facts.json'):
                with self.subTest(kind=kind, output=output):
                    path = self.root / output
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('reviewed report', encoding='utf-8')
                    state = f'.specify/extensions/assure/state/{kind}.json'
                    call = lambda action: f.record_or_status(
                        self.root, self.feature, kind, state, action, [output], self.base)
                    call('record')
                    saved = json.loads((self.root / state).read_text(encoding='utf-8'))
                    self.assertNotIn(output, saved['inputs']['files'])
                    self.assertIn(output, saved['outputs'])
                    self.assertTrue(call('status')['current'])
                    path.write_text('changed report', encoding='utf-8')
                    self.assertFalse(call('status')['current'])
                    call('record')
                    path.unlink()
                    self.assertFalse(call('status')['current'])

    def test_portable_hashes_cover_build_scripts_and_extensionless_text(self):
        names = ['script.mjs', 'project.csproj', 'source.rs', 'build.props', 'script.ps1',
                 'script.sh', 'config.toml', 'requirements.lock', 'LICENSE', '.gitignore']
        for name in names:
            (self.root / name).write_bytes(b'one\r\ntwo\r\n')
        for fingerprint in (f.fingerprints, w.fingerprint_files):
            before = fingerprint(self.root, names)
            for name in names:
                (self.root / name).write_bytes(b'one\ntwo\n')
            self.assertEqual(before, fingerprint(self.root, names))
            for name in names:
                (self.root / name).write_bytes(b'one\r\ntwo\r\n')

    def test_sql_binary_attributes_and_lone_cr_stay_byte_sensitive(self):
        (self.root / '.gitattributes').write_text('literal.mjs -text\n')
        for name, value in [('policy.sql', b'a\r\nb'), ('literal.mjs', b'a\r\nb'),
                            ('image.bin', b'\0a\r\nb'), ('invalid.bin', b'\xff\r\n'),
                            ('script.mjs', b'a\rb')]:
            path = self.root / name
            for fingerprint in (f.fingerprints, w.fingerprint_files):
                path.write_bytes(value); before = fingerprint(self.root, [name])
                path.write_bytes(value.replace(b'\r', b''))
                self.assertNotEqual(before, fingerprint(self.root, [name]), name)

    def test_actual_crlf_checkout_matches_lf_receipts(self):
        names = ['build.mjs', 'project.props', 'LICENSE', 'policy.sql']
        (self.root / '.gitattributes').write_text('* text=auto\n*.sql -text\n')
        for name in names:
            (self.root / name).write_bytes(b'first\nsecond\n')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-qm', 'portable source'], cwd=self.root, check=True)
        with tempfile.TemporaryDirectory() as folder:
            clone = Path(folder) / 'checkout'
            subprocess.run(['git', '-c', 'core.autocrlf=true', 'clone', '-q', str(self.root), str(clone)],
                           check=True, capture_output=True)
            self.assertIn(b'\r\n', (clone / 'build.mjs').read_bytes())
            for fingerprint in (f.fingerprints, w.fingerprint_files):
                self.assertEqual(fingerprint(self.root, names), fingerprint(clone, names))
    def test_deletion_and_new_source_are_detected(self):
        (self.root/'src.txt').unlink();self.call('record');self.assertTrue(self.call()['current'])
        (self.root/'src.txt').write_text('restored');self.assertFalse(self.call()['current'])
        self.call('record');(self.root/'new-source.txt').write_text('new');self.assertFalse(self.call()['current'])

    def test_untracked_notes_of_another_feature_are_not_inputs(self):
        # Issue #113: another feature's untracked coordination note is worktree debris, not this feature's input.
        self.call('record'); before = f.inputs(self.root, self.feature, 'document', self.base, [self.output])
        note = self.root/'specs/002-other/scope/source-supplement.md'
        note.parent.mkdir(parents=True); note.write_text('unrelated')
        self.assertEqual(f.inputs(self.root, self.feature, 'document', self.base, [self.output]), before)
        self.assertTrue(self.call()['current'])
        # Untracked product source and this feature's own untracked files still invalidate.
        (self.root/'specs/README.md').write_text('shared'); self.assertFalse(self.call()['current'])
        self.call('record'); (self.root/self.feature/'scope').mkdir(); (self.root/self.feature/'scope/note.md').write_text('own')
        self.assertFalse(self.call()['current'])
        # A committed change to another feature stays a diff input of this branch.
        subprocess.run(['git','add','specs/002-other'],cwd=self.root,check=True)
        subprocess.run(['git','commit','-qm','other'],cwd=self.root,check=True)
        self.call('record'); note.write_text('now tracked'); self.assertFalse(self.call()['current'])

    def test_modified_and_deleted_outputs_invalidate(self):
        self.call('record');(self.root/self.output).write_text('changed');self.assertFalse(self.call()['current'])
        self.call('record');(self.root/self.output).unlink();self.assertFalse(self.call()['current'])

    def write(self, name, value='original'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value) if isinstance(value, bytes) else path.write_text(value, encoding='utf-8')

    def test_reports_and_regenerated_outputs_do_not_stale_document_state(self):
        # R5 (#99 F2): a declared output in the project qa/ tree is hashed as an output, not also as an input.
        guide = 'qa/features/001-example/index.html'
        semantic = ['src.txt', 'tests/test_behavior.py', self.feature + '/qa/acceptance-plan.md']
        for name in semantic[1:] + [guide]:
            self.write(name)
        call = lambda action: f.record_or_status(self.root, self.feature, 'document', self.state, action, [guide], self.base)
        call('record')
        saved = json.loads((self.root / self.state).read_text(encoding='utf-8'))
        self.assertNotIn(guide, saved['inputs']['files'])
        self.write(guide)
        self.write('.specify/extensions/assure/state/001-example/reports/status.log', 'record ok, status ok')
        self.assertTrue(call('status')['current'])
        self.write(guide, 'changed guide')
        status = call('status')
        self.assertEqual((status['current'], status['changed_inputs'], status['changed_outputs']), (False, [], [guide]))
        self.write(guide)
        # No blanket exclusion: a report written into the feature after record is a new input.
        self.write(self.feature + '/qa/freshness.log', 'late report')
        self.assertEqual(call('status')['changed_inputs'], [self.feature + '/qa/freshness.log'])
        (self.root / self.feature / 'qa/freshness.log').unlink()
        for name in semantic:
            with self.subTest(path=name):
                before = (self.root / name).read_bytes()
                self.write(name, 'changed meaning')
                self.assertEqual(call('status')['changed_inputs'], [name])
                self.write(name, before)
                self.assertTrue(call('status')['current'])

    def test_declared_outputs_keep_integrity_wherever_they_live(self):
        # R6: implicit-discovery exclusions never weaken output checks.
        outputs = {'qa/features/001-example/index.html': 'guide', 'docs/001-example/shot.png': b'\x89PNG\0image',
                   'User-Manual/guide.md': 'manual', self.feature + '/workflow/report.md': 'excluded'}
        for name, value in outputs.items():
            self.write(name, value)
        for name, value in outputs.items():
            with self.subTest(output=name):
                call = lambda action: f.record_or_status(self.root, self.feature, 'document', self.state, action,
                                                         list(outputs), self.base)
                call('record')
                self.write(name, b'\x89PNG\0corrupt' if isinstance(value, bytes) else 'modified')
                self.assertEqual(call('status')['changed_outputs'], [name])
                (self.root / name).unlink()
                self.assertFalse(call('status')['current'])
                with self.assertRaisesRegex(ValueError, 'missing'):
                    call('record')
                self.write(name, value)

    def test_bookkeeping_stays_current_and_semantic_qa_json_stales(self):
        # R7: checkbox, progress and graph churn stay current; requirements, task meaning and QA JSON do not.
        self.write(self.feature + '/qa/scenarios.json', '{"scenario": "refund"}')
        self.call('record')
        self.write(self.feature + '/tasks.md', '- [x] T001 Behavior')
        self.write(self.feature + '/progress/view.md', 'regenerated')
        self.write('graphify-out/graph.json', '{}')
        self.assertTrue(self.call()['current'])
        for name, value in [(self.feature + '/qa/scenarios.json', '{"scenario": "void"}'),
                            (self.feature + '/spec.md', '# Changed requirement'),
                            (self.feature + '/tasks.md', '- [x] T001 Different behavior'), ('src.txt', 'new behavior')]:
            with self.subTest(path=name):
                before = (self.root / name).read_bytes()
                self.write(name, value)
                self.assertEqual(self.call()['changed_inputs'], [name])
                self.write(name, before)
        self.assertTrue(self.call()['current'])

    def test_analyze_keeps_its_outputs_as_inputs(self):
        state = '.specify/extensions/assure/state/001-example-analyze.json'
        task = self.feature + '/tasks.md'
        f.record_or_status(self.root, self.feature, 'analyze', state, 'record', [task])
        saved = json.loads((self.root / state).read_text(encoding='utf-8'))
        self.assertIn(task, saved['inputs']['files'])
        self.assertNotIn('outputsNotInputs', saved)

    def test_state_recorded_by_1_15_0_stays_current(self):
        # R9: 1.15.0 hashed declared outputs as implicit inputs too and wrote no marker.
        guide = 'qa/features/001-example/index.html'
        self.write(guide)
        legacy = {'schemaVersion': 2, 'feature': self.feature, 'kind': 'document',
                  'inputs': f.inputs(self.root, self.feature, 'document', self.base),
                  'outputs': f.fingerprints(self.root, [guide]), 'gitHead': self.base}
        self.assertIn(guide, legacy['inputs']['files'])
        self.write(self.state, json.dumps(legacy))
        call = lambda: f.record_or_status(self.root, self.feature, 'document', self.state, 'status', [guide])
        self.assertTrue(call()['current'])
        self.write(guide, 'changed guide')
        self.assertEqual(call()['changed_outputs'], [guide])

    def test_analysis_ignores_implementation_but_tracks_semantic_tasks(self):
        state='.specify/extensions/assure/state/001-example-analyze.json'
        call=lambda a:f.record_or_status(self.root,self.feature,'analyze',state,a,[self.feature+'/tasks.md'])
        call('record');(self.root/'src.txt').write_text('new implementation');self.assertTrue(call('status')['current'])
        (self.root/self.feature/'tasks.md').write_text('- [ ] T001 Different requirement');self.assertFalse(call('status')['current'])

    def test_missing_base_outputs_and_escape_are_errors(self):
        with self.assertRaisesRegex(ValueError,'base-ref'):f.inputs(self.root,self.feature,'document')
        with self.assertRaises(ValueError):f.record_or_status(self.root,self.feature,'document',self.state,'record',[],self.base)
        with self.assertRaises(ValueError):f.fingerprints(self.root,['../escape'])

    def test_checkpoint_target_branch_reads_the_feature_checkpoint(self):
        # F16: assure_state.py/manual_state.py default --base-ref to this.
        feature_dir = self.root / self.feature
        self.assertIsNone(f.checkpoint_target_branch(feature_dir))
        checkpoint = feature_dir / 'workflow/checkpoint.json'
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({'target_branch': 'develop'}), encoding='utf-8')
        self.assertEqual(f.checkpoint_target_branch(feature_dir), 'develop')
        checkpoint.write_text(json.dumps({'target_branch': None}), encoding='utf-8')
        self.assertIsNone(f.checkpoint_target_branch(feature_dir))
        checkpoint.write_text('not json', encoding='utf-8')
        self.assertIsNone(f.checkpoint_target_branch(feature_dir))
