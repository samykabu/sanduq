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

    def test_modified_and_deleted_outputs_invalidate(self):
        self.call('record');(self.root/self.output).write_text('changed');self.assertFalse(self.call()['current'])
        self.call('record');(self.root/self.output).unlink();self.assertFalse(self.call()['current'])

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
