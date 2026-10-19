"""The instruction benchmark counts alternative references once (the largest) and keeps conditional ones apart."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import benchmark_instructions as bench  # noqa: E402

COMMAND = """---
description: 'Imports a diagram. Use when asked to "import this".'
---

1. Read `.specify/extensions/demo/references/always.md`.
2. Route by source and read the matching reference:
   - `.a`, `.a.json` →
     `.specify/extensions/demo/references/import-a.md`
   - `.b` → `.specify/extensions/demo/references/import-b.md`
   - `.c` → `.specify/extensions/demo/references/import-c.md`
   - anything else → stop.
3. Resolve the theme with `scripts/theme.py --root . resolve`; initialize it per
   `references/theme-init.md` if it is missing.
"""


class BenchmarkInstructionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / 'extensions' / 'demo'
        (root / 'commands').mkdir(parents=True)
        (root / 'references').mkdir()
        (root / 'extension.yml').write_text(
            "extension: {id: demo, version: 1.0.0}\nprovides:\n  commands:\n"
            "    - {name: speckit.demo.import, file: commands/import.md, description: 'Imports a diagram. Use when "
            "asked to \"import this\".'}\n", encoding='utf-8')
        (root / 'commands' / 'import.md').write_text(COMMAND, encoding='utf-8')
        self.sizes = {'always.md': 100, 'import-a.md': 300, 'import-b.md': 700, 'import-c.md': 500, 'theme-init.md': 900}
        for name, size in self.sizes.items():
            (root / 'references' / name).write_text('x' * size, encoding='utf-8')
        self.command_bytes = (root / 'commands' / 'import.md').stat().st_size
        self.result = bench.measure(self.tmp.name, ['demo'])['extensions']['demo']

    def test_alternatives_count_once_as_the_largest(self):
        c = self.result['commands']['speckit.demo.import']
        [group] = c['alternatives']
        self.assertEqual(group['chosen'], 'extensions/demo/references/import-b.md')
        self.assertEqual(sorted(group['options'].values()), [300, 500, 700])
        self.assertEqual(c['instruction_bytes'], self.command_bytes + 100 + 700)
        self.assertNotIn('extensions/demo/references/import-a.md', c['linked'])

    def test_conditional_references_are_reported_apart(self):
        c = self.result['commands']['speckit.demo.import']
        self.assertEqual(c['conditional'], {'extensions/demo/references/theme-init.md': 900})
        self.assertEqual(c['conditional_bytes'], 900)
        totals = self.result['totals']
        self.assertEqual(totals['instruction_bytes'], self.command_bytes + 100 + 700)
        self.assertEqual(totals['conditional_bytes'], 300 + 500 + 900)
        self.assertEqual(totals['command_bytes'], c['instruction_bytes'])

    def test_a_plain_mention_wins_over_a_conditional_one(self):
        plain, cond, groups = bench.classify('Read `references/a.md` when asked.\n\nThen read `references/a.md`.\n')
        self.assertEqual((plain, cond, groups), ({'references/a.md'}, set(), []))


if __name__ == '__main__':
    unittest.main()
