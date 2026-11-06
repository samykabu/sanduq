"""Instruction lint: reporting is decided in references/reporting.md and no reference asks for a reporting agent.

The reporting rules' exact wording is pinned in fixtures/rules-inventory.json (test_skill_split); these are the
structural checks."""
import re
import unittest
from pathlib import Path

REFERENCES = Path(__file__).resolve().parents[1] / 'skills' / 'workflow' / 'references'
RULE = re.compile(r'Never spawn[^.]*agent solely for reporting')  # the rule's key terms, in one sentence
LEGACY_HEADING = '## Legacy reporter calls (mode legacy only)'
# Wording that made an agent responsible for keeping the report alive or current.
FORBIDDEN = (
    r'\b(?:keep|retain|spawn|create|start)\b[^.]*\bagent\b[^.]*\b(?:update|monitor|poll|maintain|refresh|watch)\b[^.]*\breport',
    r'\bagent\b[^.]*\bso it can (?:update|refresh|maintain)\b[^.]*\breport',
    r'\b(?:keep|keeps|keeping)\b[^.]*\b(?:html |todo |progress )*report\b[^.]*\bcurrent\b',
    r'\b(?:keep|keeps|keeping) it current\b',
    r'\bsole report writer\b',
    r'\bagent\b[^.]*\breport (?:writes|updates)\b',
    r'\b(?:poll|monitor)\b[^.]*\b(?:the |a )?(?:progress )?report\b[^.]*\b(?:until|every|loop)\b',
)
MENTIONS_REPORT = re.compile(r'progress report|todo report|progress\.py|workflow/progress|report writes', re.I)


def flat(path):
    return re.sub(r'\s+', ' ', path.read_text(encoding='utf-8'))


class ReportingInstructions(unittest.TestCase):
    def references(self):
        found = sorted(REFERENCES.rglob('*.md'))  # the Execute claim's parts live in references/execute/
        self.assertTrue(found)
        return found

    def test_the_rule_is_stated_once_in_the_decision_reference(self):
        text = flat(REFERENCES / 'reporting.md')
        self.assertEqual(len(RULE.findall(text)), 1)
        for mode in ('projection', 'refresh', 'legacy'):
            self.assertIn('`' + mode + '`', text)
        self.assertIn('progress_bridge.py mode', text)
        self.assertEqual(text.count('progress bind'), 1)

    def test_only_the_decision_reference_names_progress_lanes_for_stage_runs(self):
        for path in self.references():
            if path.name != 'reporting.md':
                self.assertNotRegex(flat(path), r'progress lane [^.]*(?:stage|scope-worker)', path.name)

    def test_decision_reference_stays_small(self):
        self.assertLess(len((REFERENCES / 'reporting.md').read_bytes()), 4600)

    def test_no_reference_asks_an_agent_to_keep_update_or_monitor_the_report(self):
        for path in self.references():
            text = flat(path)
            for pattern in FORBIDDEN:
                match = re.search(pattern, text, re.I)
                self.assertIsNone(match, f'{path.name}: {match.group(0) if match else ""}')

    def test_every_reference_that_mentions_the_report_links_to_the_decision_reference(self):
        mentioning = []
        for path in self.references():
            if path.name == 'reporting.md':
                continue
            text = path.read_text(encoding='utf-8')
            if MENTIONS_REPORT.search(text):
                mentioning.append(path.name)
                self.assertIn('reporting.md', text, f'{path.name} mentions the report without linking reporting.md')
        for expected in ('stage-execute.md', 'execution-assign.md', 'execution-report.md', 'utilities.md'):
            self.assertIn(expected, mentioning)

    def test_legacy_call_sequences_live_only_under_the_legacy_heading(self):
        legacy_call = re.compile(r'workflow/scripts/progress\.py (?:init|task|usage|sync|phase|pr|event)\b')
        for path in self.references():
            text = path.read_text(encoding='utf-8')
            hits = [m.start() for m in legacy_call.finditer(text)]
            if not hits:
                continue
            self.assertEqual(path.name, 'reporting-legacy.md', path.name + ' carries a legacy reporter call')
            self.assertIn(LEGACY_HEADING, text)
            self.assertGreater(min(hits), text.index(LEGACY_HEADING))

    def test_the_legacy_anchor_that_reporting_links_to_exists(self):
        anchor = '#legacy-reporter-calls-mode-legacy-only'
        self.assertIn('execute/reporting-legacy.md' + anchor, (REFERENCES / 'reporting.md').read_text(encoding='utf-8'))
        self.assertIn(LEGACY_HEADING, (REFERENCES / 'execute/reporting-legacy.md').read_text(encoding='utf-8'))



if __name__ == '__main__':
    unittest.main()
