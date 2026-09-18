import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import release as r

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        (self.root/'.gitignore').write_text('dist/\n')
        p=self.root/'extensions/example';p.mkdir(parents=True)
        (p/'extension.yml').write_text('schema_version: "1.0"\nextension:\n  id: example\n  name: Example\n  version: "1.1.0"\n  repository: https://github.com/samykabu/sanduq\n')
        (p/'README.md').write_text('Example')
        catalog={'extensions':{'example':{'version':'1.0.0'}}}
        r.write(self.root/'catalog.json',catalog);r.write(self.root/'extensions/catalog.json',catalog)
        r.write(self.root/'extensions/pending-releases.json',{'versions':{'example':'1.1.0'},'status':'ready'})
        for args in [('init','-q'),('config','user.name','Test'),('config','user.email','test@example.invalid'),('add','.'),('commit','-qm','Source')]:
            subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True)
        self.before=(self.root/'catalog.json').read_bytes()

    def verified(self, plan):
        r.write(self.root/'dist/release-verification.json',{'plan_sha256':r.sha(self.root/'dist/release-plan.json'),'assets':[{'tag':x['tag'],'sha256':x['sha256'],'verified':True} for x in plan['releases']]})

    def test_prepare_preserves_catalog_and_builds_repeatable_archive(self):
        a=r.prepare(self.root);b=r.prepare(self.root)
        self.assertEqual(a['releases'][0]['sha256'],b['releases'][0]['sha256'])
        self.assertEqual((self.root/'catalog.json').read_bytes(),self.before)
        self.assertTrue(a['publishable'])

    def test_dirty_preview_cannot_be_published(self):
        (self.root/'extensions/example/README.md').write_text('Uncommitted')
        with self.assertRaisesRegex(ValueError,'clean checkout'):r.prepare(self.root)
        plan=r.prepare(self.root,development=True);self.assertFalse(plan['publishable'])
        with self.assertRaisesRegex(ValueError,'cannot be published'):r.publish(self.root,apply=True)

    def test_verification_failure_leaves_both_catalogs_unchanged(self):
        plan=r.prepare(self.root);self.verified(plan)
        def fail(*args):raise ValueError('immutable asset mismatch')
        with self.assertRaisesRegex(ValueError,'asset mismatch'):r.promote(self.root,verifier=fail)
        self.assertEqual((self.root/'catalog.json').read_bytes(),self.before)
        self.assertEqual((self.root/'extensions/catalog.json').read_bytes(),self.before)

    def test_verification_receipt_must_match_exact_plan(self):
        plan=r.prepare(self.root);self.verified(plan)
        plan['source_commit']='changed';r.write(self.root/'dist/release-plan.json',plan)
        with self.assertRaisesRegex(ValueError,'Source commit changed|another plan'):r.promote(self.root,verifier=lambda *a:None)

    def test_promote_after_verification_updates_both_catalogs_and_pending(self):
        plan=r.prepare(self.root);self.verified(plan);calls=[]
        r.promote(self.root,verifier=lambda asset,root:calls.append(asset['tag']))
        self.assertEqual(calls,['example-v1.1.0'])
        self.assertEqual(r.read(self.root/'catalog.json'),r.read(self.root/'extensions/catalog.json'))
        self.assertEqual(r.read(self.root/'catalog.json')['extensions']['example']['version'],'1.1.0')
        self.assertEqual(r.read(self.root/'extensions/pending-releases.json')['versions'],{})

    def test_unready_pending_release_cannot_publish(self):
        pending=r.read(self.root/'extensions/pending-releases.json');pending['status']='implementation-in-progress';r.write(self.root/'extensions/pending-releases.json',pending)
        subprocess.run(['git','add','.'],cwd=self.root,check=True);subprocess.run(['git','commit','-qm','Unready'],cwd=self.root,check=True)
        with self.assertRaisesRegex(ValueError,'status ready'):r.prepare(self.root)
