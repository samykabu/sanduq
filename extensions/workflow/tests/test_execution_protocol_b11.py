"""B11 (Sprint 4, Stream B): prove the execution-protocol rules from the retrospective
(F1, F2, F3, F11, T0, T7, T8, S6), the B7 sync-states cadence and quiet-output default,
and the B12 placeholder are present in the *installed* reference files, not just the
working tree, so a future edit or a packaging regression cannot silently drop them.

Follows test_skill_split.py's approach of checking exact marker phrases, but reads
them from the archive `extensions/scripts/package.py` builds (the same one `install.py`
and `upgrade.py` ship), the same way `test_execution_policy.py` verifies package
contents, rather than diffing against a pre-B11 git revision (there is none: B11 only
adds rules, it never moves or drops one, so there is nothing to diff).
"""
import importlib.util
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('execution_package', ROOT / 'extensions/scripts/package.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)

# Marker phrases for the B11 rules; every one must be found, verbatim, in the
# installed reference file named alongside it.
ASSIGN_MARKERS = [
    "Never route a worker's result to the dispatcher for relay",           # F1
    'ends its turn while it still owns background work that is running',  # F2
    'is never a valid final message from any agent in this protocol',      # F2
    'Turn budgets bound how large',                                       # T0
    'never Haiku (standing rule 5)',                                      # T0 x standing rule 5
    'the `[collect]` marker or an explicit override (B12), never by default',  # T0 x standing rule 5
    'roughly 150K tokens resident',                                       # T0 hand-off
    '`git stash` and `git add -A`/`git add .` are forbidden for a worker',  # S6
    '--tasks specs/<feature>/tasks.md --output specs/<feature>/workflow/progress --summary',  # B7 --summary default
]

REPORT_MARKERS = [
    'A wake-up that carries no new information produces no message',   # F3
    'Task: <T### and title>',                                          # T7 template
    'Status: done | blocked | partial',
    'Files touched: <paths, or "none">',
    'Consumers checked: <which consumers were checked',
    'read its summary first',                                          # T8
    'only for a lane that failed',                                     # T8
    'End-to-end/integration specs that reference the changed name',    # F11
    'The lane registry (titles, counts)',                              # F11
    'QA capture specs and their generated sample output',              # F11
    '## Light-tier collection results (B12)',                          # B12 placeholder
    'the orchestrator will supply the final text',                     # B12 placeholder
    '--overhead dispatcher --agent <dispatcher-session-id>',           # dispatcher usage at phase commit
    'Sync native task issues once per phase, not once per task',       # B7 cadence
    "`sync_states()` already walks",                                   # B7 cadence rationale
    'Never infer human-review completion from generated evidence',
    'Prefer `--summary`',                                              # B7 quiet-output default
    'skipped reason=<why>',                                            # B7 --summary skip form
    "--parent ... --apply --summary",                                  # --summary on the sync-states call
    '--collect claude --summary',                                      # --summary on a usage example
]

TASK_CLASSES = ('implementation', 'qa_author', 'qa_collect', 'documentation', 'review')


def normalize(text):
    # Markdown hard-wraps a paragraph at ~80 columns, so a marker phrase this
    # test checks for can legitimately straddle a line break; collapse all
    # whitespace runs (including newlines) to a single space before matching,
    # the same way test_skill_split.py's normalize() does.
    return re.sub(r'\s+', ' ', text).strip()


class ExecutionProtocolB11Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            package = packager.package('workflow', output=Path(folder) / 'workflow.zip')
            with zipfile.ZipFile(package['archive']) as archive:
                cls.raw_report = archive.read(
                    'workflow/skills/workflow/references/execution-report.md').decode('utf-8')
                cls.assign = normalize(archive.read(
                    'workflow/skills/workflow/references/execution-assign.md').decode('utf-8'))
                cls.report = normalize(cls.raw_report)

    def test_assign_carries_every_b11_marker(self):
        missing = [m for m in ASSIGN_MARKERS if normalize(m) not in self.assign]
        self.assertEqual(missing, [],
                          f'Missing from the installed execution-assign.md: {missing}')

    def test_report_carries_every_b11_marker(self):
        missing = [m for m in REPORT_MARKERS if normalize(m) not in self.report]
        self.assertEqual(missing, [],
                          f'Missing from the installed execution-report.md: {missing}')

    def test_turn_budget_table_names_every_required_task_class(self):
        for task_class in TASK_CLASSES:
            self.assertIn(task_class, self.assign,
                          f'Turn-budget table missing task class {task_class!r}')

    def test_ten_line_result_template_has_exactly_ten_fields(self):
        start = self.raw_report.index('Task: <T### and title>')
        fence_end = self.raw_report.index('```', start)
        block = self.raw_report[start:fence_end]
        lines = [ln for ln in block.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 10,
                          f'Structured result template must be exactly 10 lines, got '
                          f'{len(lines)}: {lines}')


if __name__ == '__main__':
    unittest.main()
