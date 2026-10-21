"""PR command text: one description in the frontmatter and the manifest (D1), and the QA preflight
asks Assure's script for the gate instead of reading the config (AU21)."""
import re
import unittest
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
COMMAND = (PR / 'commands/speckit.pr.generate.md').read_text(encoding='utf-8')
MANIFEST = (PR / 'extension.yml').read_text(encoding='utf-8')


class CommandTextTests(unittest.TestCase):
    def test_generate_description_is_identical_everywhere_and_narrower_than_finalize(self):
        front = re.search(r'^description: (".*")$', COMMAND, re.M).group(1)
        self.assertIn("'write the PR description'", front)
        self.assertNotIn("'open the PR'", front)  # Workflow's finalize keeps that trigger
        self.assertEqual(MANIFEST.count('description: ' + front), 2)  # the command and its hook

    def test_qa_preflight_reads_the_gate_through_the_script(self):
        self.assertIn('assure_state.py status --kind document --gate --summary --feature', COMMAND)
        self.assertIn('skipped gate=off', COMMAND)
        self.assertNotIn('contains\n`require_document_before_pr: true`', COMMAND)
        self.assertNotIn('require_document_before_pr', COMMAND)


if __name__ == '__main__':
    unittest.main()
