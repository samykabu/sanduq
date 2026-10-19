"""Instruction lint: reporting is decided in references/reporting.md and no reference asks for a reporting agent."""
import re
import unittest
from pathlib import Path

REFERENCES = Path(__file__).resolve().parents[1] / 'skills' / 'workflow' / 'references'
RULE = 'Never spawn, retain, message or poll an additional agent solely for reporting.'
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
        self.assertIn(RULE, text)
        self.assertEqual(text.count(RULE), 1)
        for mode in ('projection', 'refresh', 'legacy'):
            self.assertIn('`' + mode + '`', text)
        self.assertIn('progress_bridge.py mode', text)

    def test_stage_runs_never_get_progress_lane_calls(self):
        text = flat(REFERENCES / 'reporting.md')
        self.assertIn('Lifecycle stage runs', text)
        self.assertIn('recorded by the delegation ledger', text)
        self.assertIn('no `progress lane` for them', text)
        self.assertIn('once per Execute workstream', text)
        self.assertIn('never per run', text)
        self.assertIn("updates that lane's owner", text)
        for path in self.references():
            if path.name != 'reporting.md':
                self.assertNotRegex(flat(path), r'progress lane [^.]*(?:stage|scope-worker)', path.name)

    def test_codex_worktrees_without_approved_hooks_self_report_and_workstream_lanes_are_marked(self):
        text = flat(REFERENCES / 'reporting.md')
        self.assertIn('progress bind --host codex --model <m> --effort <e>', text)
        self.assertIn('Progress 1.2.0 or later', text)
        self.assertIn('labelled self-report', text)
        self.assertIn('never host-observed telemetry', text)
        self.assertIn('`semantics: "workstream"`', text)
        self.assertIn('--effort E --workstream`', text)  # the direct command marks the lane too
        self.assertIn('leave `--workstream` out for a Progress older than 1.2.0', text)
        self.assertIn('codex hooks not approved', text)
        self.assertEqual(text.count('progress bind'), 1)

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
        for expected in ('stage-execute.md', 'execution-assign.md', 'execution-report.md', 'dispatcher-operations.md'):
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

    def test_waiting_for_workers_stays_and_watching_the_report_is_forbidden(self):
        assign = flat(REFERENCES / 'execution-assign.md')
        self.assertIn('bounded foreground loop around `delegate_dispatch.py collect`', assign)
        self.assertIn('Watching the report itself, or checking that it refreshed, is never background work', assign)
        self.assertIn('Do not re-open or re-verify it in a loop', assign)

    def test_lean_and_delegated_modes_agree_that_no_agent_exists_for_reporting(self):
        self.assertIn('no agent exists solely for it', flat(REFERENCES / 'stage-execute.md'))
        self.assertIn('it has no reporting duty', flat(REFERENCES / 'execute/orchestrator.md'))
        self.assertIn('Do not create the additional orchestration agent', flat(REFERENCES / 'execute/lean.md'))

    def test_dispatcher_status_appends_the_one_line_and_makes_synthesis_optional(self):
        status = flat(REFERENCES / 'dispatcher-operations.md')
        self.assertIn('progress.py status', status)
        self.assertIn('narrative on top is optional explanation', status)


if __name__ == '__main__':
    unittest.main()
