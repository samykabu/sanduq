"""W18: the advisory hash cache behind `package_digest(cached=True)` (claim only)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workflow as w  # noqa: E402

OLD = time.time() - 60


class HashCacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        self.labels = ['.specify/extensions/scope/scripts/scope.py', '.specify/extensions/scope/README.md',
                       '.specify/presets/workflow/preset.yml']
        for label in self.labels:
            self.put(label, 'content of ' + label + '\r\n')

    def put(self, label, text, when=OLD):
        path = self.root / label
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))
        os.utime(path, (when, when))

    def cache(self):
        return json.loads((self.root / w.HASH_CACHE).read_text(encoding='utf-8'))

    def hashed(self):
        """The labels `fingerprint_files` is asked to hash during one cached call."""
        calls, real = [], w.fingerprint_files

        def record(root, paths, *args, **kwargs):
            calls.extend(paths)
            return real(root, paths, *args, **kwargs)
        return calls, mock.patch.object(w, 'fingerprint_files', record)

    def test_a_hit_reads_nothing_and_equals_the_full_hash(self):
        first = w.cached_fingerprints(self.root, self.labels)
        self.assertEqual(first, w.fingerprint_files(self.root, self.labels))
        calls, recording = self.hashed()
        with recording:
            self.assertEqual(w.cached_fingerprints(self.root, self.labels), first)
        self.assertEqual(calls, [])
        self.assertEqual(w.package_digest(self.root, cached=True), w.package_digest(self.root))

    def test_a_size_or_mtime_change_is_hashed_again(self):
        w.cached_fingerprints(self.root, self.labels)
        self.put(self.labels[0], 'a longer edited content\n')
        self.put(self.labels[1], 'Content of ' + self.labels[1] + '\r\n', when=OLD + 5)  # same size, new mtime
        calls, recording = self.hashed()
        with recording:
            result = w.cached_fingerprints(self.root, self.labels)
        self.assertEqual(sorted(calls), sorted(self.labels[:2]))
        self.assertEqual(result, w.fingerprint_files(self.root, self.labels))

    def test_a_fresh_mtime_is_never_served_or_stored(self):
        self.put(self.labels[0], 'just written\n', when=time.time())
        w.cached_fingerprints(self.root, self.labels)
        self.assertNotIn(self.labels[0], self.cache())
        calls, recording = self.hashed()
        with recording:
            w.cached_fingerprints(self.root, self.labels)
        self.assertEqual(calls, [self.labels[0]])

    def test_a_changed_text_attribute_is_hashed_again(self):
        w.cached_fingerprints(self.root, self.labels)
        (self.root / '.gitattributes').write_text('*.md -text\n', encoding='utf-8')
        calls, recording = self.hashed()
        with recording:
            result = w.cached_fingerprints(self.root, self.labels)
        self.assertEqual(calls, [self.labels[1]])
        self.assertEqual(result, w.fingerprint_files(self.root, self.labels))  # CRLF now kept byte-exact

    def test_byte_sensitive_files_are_never_stored(self):
        self.put('.specify/extensions/scope/schema.sql', 'select 1;\r\n')
        self.put('.specify/extensions/scope/blob.md', 'a\0b')
        labels = ['.specify/extensions/scope/schema.sql', '.specify/extensions/scope/blob.md']
        w.cached_fingerprints(self.root, labels)
        self.assertFalse((self.root / w.HASH_CACHE).exists())

    def test_a_malformed_or_forged_cache_is_ignored_unless_its_key_matches(self):
        (self.root / w.HASH_CACHE).parent.mkdir(parents=True, exist_ok=True)
        (self.root / w.HASH_CACHE).write_text('{not json', encoding='utf-8')
        self.assertEqual(w.cached_fingerprints(self.root, self.labels), w.fingerprint_files(self.root, self.labels))
        entries = self.cache()
        entries[self.labels[0]] = [1, 2, None, 'f' * 64]  # wrong size and mtime
        entries[self.labels[1]] = 'not a list'
        (self.root / w.HASH_CACHE).write_text(json.dumps(entries), encoding='utf-8')
        self.assertEqual(w.cached_fingerprints(self.root, self.labels), w.fingerprint_files(self.root, self.labels))

    def test_full_hashing_never_reads_the_cache(self):
        w.cached_fingerprints(self.root, self.labels)
        entries = self.cache()
        entries[self.labels[0]][3] = 'f' * 64  # a stale or forged hash under a matching key
        (self.root / w.HASH_CACHE).write_text(json.dumps(entries), encoding='utf-8')
        self.assertNotEqual(w.package_digest(self.root), w.package_digest(self.root, cached=True))
        self.assertEqual(w.fingerprint_files(self.root, self.labels)[self.labels[0]],
                         w.fingerprint_files(self.root, [self.labels[0]])[self.labels[0]])
        self.assertNotEqual(w.fingerprint_files(self.root, self.labels)[self.labels[0]], 'f' * 64)

    def test_the_cache_keeps_only_the_last_calls_paths(self):
        w.cached_fingerprints(self.root, self.labels)
        w.cached_fingerprints(self.root, self.labels[:1])
        self.assertEqual(sorted(self.cache()), self.labels[:1])

    def test_a_missing_file_is_none_like_the_full_hash(self):
        labels = self.labels + ['.specify/extensions/scope/gone.py']
        self.assertEqual(w.cached_fingerprints(self.root, labels)[labels[-1]], None)


if __name__ == '__main__':
    unittest.main()
