"""W25: the derived index behind the claim's foreign active-claim check."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workflow as w  # noqa: E402

OLD = time.time() - 60


def scan(root, own):
    """The claim's check before the index: read every other checkpoint."""
    for path in (root / 'specs').glob('*/workflow/checkpoint.json'):
        if path != own and w.read(path, {}).get('active'):
            return path
    return None


class ActiveIndexTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.own = self.checkpoint('001-own', {'stage': 'plan'})
        for name in ('002-a', '003-b', '004-c'):
            self.checkpoint(name, None)

    def checkpoint(self, name, active, when=OLD, text=None):
        path = self.root / 'specs' / name / 'workflow/checkpoint.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name('next.tmp')
        temp.write_text(text if text is not None else json.dumps({'feature': 'specs/' + name, 'active': active}),
                        encoding='utf-8')
        os.utime(temp, (when, when))
        os.replace(temp, path)
        return path

    def check(self):
        """The indexed answer, asserted equal to the unindexed scan, and the checkpoints it read."""
        reads, real = [], w.read

        def record(path, default=None):
            if Path(path).name == 'checkpoint.json':
                reads.append(Path(path).parent.parent.name)
            return real(path, default)
        expected = scan(self.root, self.own)
        with mock.patch.object(w, 'read', record):
            found = w.foreign_active_claim(self.root, self.own)
        self.assertEqual(found, expected)
        return found, reads

    def test_an_unchanged_inactive_checkpoint_is_not_read_again(self):
        self.assertEqual(self.check(), (None, ['002-a', '003-b', '004-c']))
        self.assertEqual(self.check(), (None, []))

    def test_a_new_checkpoint_is_discovered(self):
        self.check()
        path = self.checkpoint('005-new', {'stage': 'execute'})
        self.assertEqual(self.check(), (path, ['005-new']))

    def test_a_deleted_checkpoint_leaves_the_index(self):
        self.check()
        (self.root / 'specs/003-b/workflow/checkpoint.json').unlink()
        self.assertEqual(self.check(), (None, []))
        index = json.loads((self.root / w.ACTIVE_INDEX).read_text(encoding='utf-8'))
        self.assertEqual(sorted(index), ['specs/002-a/workflow/checkpoint.json', 'specs/004-c/workflow/checkpoint.json'])

    def test_a_replaced_checkpoint_is_read_again_even_with_the_same_size_and_mtime(self):
        self.check()
        before = (self.root / 'specs/003-b/workflow/checkpoint.json').stat().st_size
        text = json.dumps({'feature': 'specs/003-b', 'active': 1})
        text += ' ' * (before - len(text))
        path = self.checkpoint('003-b', None, text=text)
        self.assertEqual(path.stat().st_size, before)
        self.assertEqual(self.check(), (path, ['003-b']))

    def test_a_malformed_checkpoint_is_refused_as_before(self):
        self.check()
        self.checkpoint('003-b', None, text='{not json')
        with self.assertRaises(ValueError):
            scan(self.root, self.own)
        with self.assertRaises(ValueError):
            w.foreign_active_claim(self.root, self.own)

    def test_a_malformed_index_is_rebuilt(self):
        self.check()
        (self.root / w.ACTIVE_INDEX).write_text('[1, 2', encoding='utf-8')
        self.assertEqual(self.check(), (None, ['002-a', '003-b', '004-c']))

    def test_a_recent_checkpoint_is_never_trusted_as_inactive(self):
        self.checkpoint('003-b', None, when=time.time())
        self.check()
        self.assertEqual(self.check(), (None, ['003-b']))

    def test_an_active_checkpoint_is_never_indexed(self):
        path = self.checkpoint('003-b', {'stage': 'plan'})
        self.assertEqual(self.check()[0], path)
        self.assertEqual(self.check(), (path, ['002-a', '003-b']))

    def test_the_own_checkpoint_is_never_a_foreign_claim(self):
        self.assertIsNone(self.check()[0])


if __name__ == '__main__':
    unittest.main()
