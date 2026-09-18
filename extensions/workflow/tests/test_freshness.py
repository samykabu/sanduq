import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/shared'))
import sanduq_freshness as f

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
