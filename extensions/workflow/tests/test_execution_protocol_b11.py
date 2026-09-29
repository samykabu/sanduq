"""B11 (Sprint 4, Stream B): prove the execution-protocol rules from the retrospective
(F1, F2, F3, F11, T0, T7, T8, S6), the B7 sync-states cadence and quiet-output default,
and B12's now-final light-tier collection text are present in the *installed*
reference files, not just the working tree, so a future edit or a packaging
regression cannot silently drop them.

Follows test_skill_split.py's approach of checking exact marker phrases, but reads
them from the archive `extensions/scripts/package.py` builds (the same one `install.py`
and `upgrade.py` ship), the same way `test_execution_policy.py` verifies package
contents, rather than diffing against a pre-B11 git revision (there is none: B11 only
adds rules, it never moves or drops one, so there is nothing to diff).

B11 review fix (finding 6): the original marker list here was too loose to catch a
dropped table row, a dropped template field or a dropped F11 bullet, because several
markers were substrings that could survive the surrounding structure being deleted
(e.g. a phrase from a table's Notes cell staying true even if the row's leading
`| task_class |` cell were removed and the row de-tabled into prose). This version
adds structural checks: every table row's exact leading cell, every one of the ten
template field names read off the fenced block itself (not just counted), and every
one of the six F11 bullets, each checked as an exact, complete line/cell rather than
a fragment that could remain after the rest of its row/bullet/line is gone.
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
    'blocking rather than backgrounded',                                  # F1
    'ends its turn while it still owns background work that is running',  # F2
    'is never a valid final message from any agent in this protocol',      # F2
    'bounded foreground loop around `delegate_dispatch.py collect` until the '
    "run's status is terminal",                                           # F2 x delegate_dispatch.py
    'Where this fallback applies, the dispatcher',                        # F1 x nested-spawn fallback
    'forwards each T7 result once, unchanged',                            # F1 x nested-spawn fallback
    'Turn budgets bound how large',                                       # T0
    'it excludes cache reads, which are about 96% of a worker\'s total '
    'token volume',                                                       # T0 budget basis
    'the orchestration agent compares the task\'s recorded `progress.py '
    'usage` figure against its class budget',                             # T0 overrun mechanism
    'Budget overrun T###: <class> <figure>/<budget>: <reason>',           # T0 overrun log line
    'never Haiku (standing rule 5)',                                      # T0 x standing rule 5
    'the `[collect]` marker or an explicit override (B12), never by default',  # T0 x standing rule 5
    'roughly 150K tokens resident',                                       # T0 hand-off
    '`git stash` and `git add -A`/`git add .` are forbidden for a worker',  # S6
    'as are `delegate_dispatch.py accept`, `delegate_dispatch.py trust-reset` and '
    '`delegate_dispatch.py adopt`',                                       # B12: also forbidden for a worker
    '`accept`/`trust-reset`/`adopt` are ledger-trust decisions the '
    'orchestration agent alone makes',                                    # B12: why they are forbidden
    'Staging stays with the orchestration agent, which stages a '
    "worker's owned paths by explicit name",                              # S6 fix: no self-contradiction
    '--tasks specs/<feature>/tasks.md --output specs/<feature>/workflow/progress --summary',  # B7 --summary default
]

# Every row of the turn-budget table, as its exact leading two cells (`| class | figure`),
# so a row that survives only as de-tabled prose (no longer a real table row) is caught,
# not just the class name or a phrase from its Notes cell.
TABLE_ROWS = [
    '| implementation | ~120K',
    '| qa_author | ~300K',
    '| qa_collect | ~60K',
    '| documentation | ~180K',
    '| review | ~200K',
]

REPORT_MARKERS = [
    'A wake-up that carries no new information produces no message',   # F3
    'read its summary first',                                          # T8
    'only for a lane that failed',                                     # T8
    '## Light-tier collection results (B12)',                          # B12 heading
    'At every phase commit, the orchestration agent also records the '
    "dispatcher's own",                                                # dispatcher usage cadence
    'python .specify/extensions/workflow/scripts/progress.py usage --output '
    'specs/<feature>/workflow/progress --overhead dispatcher --agent '
    '<dispatcher-session-id> --collect claude --log '
    "<dispatcher's own session transcript> --summary",                 # exact dispatcher-usage command
    'Sync native task issues once per phase, not once per task',       # B7 cadence
    'the dispatcher owns this call',                                   # B11 review fix: named owner
    "`sync_states()` already walks",                                   # B7 cadence rationale
    'Never infer human-review completion from generated evidence',
    'Prefer `--summary`',                                              # B7 quiet-output default
    'skipped reason=<why>',                                            # B7 --summary skip form
    '--parent ... --apply --summary',                                  # --summary on the sync-states call
    '--collect claude --summary',                                      # --summary on a usage example
]

# The ten T7 result-template field names, in order, each as it must open its own line
# (`Diff:` replaced `Commit:` in the B11 review fix, since staging/committing moved to
# the orchestration agent and a worker never has a commit sha to report).
TEMPLATE_FIELDS = [
    'Task:', 'Status:', 'Files touched:', 'Tests:', 'Evidence:', 'Diff:',
    'Consumers checked:', 'Tokens:', 'Blockers:', 'Next:',
]

# The six F11 consumers-checklist bullets, each as its exact, complete line (minus the
# leading `- `), so a bullet cannot be dropped while some fragment of it lingers.
F11_BULLETS = [
    'End-to-end/integration specs that reference the changed name, route or contract.',
    "The lane registry (titles, counts) if a test's identity or count changed.",
    'QA capture specs and their generated sample output.',
    'Manual/User-Manual pages and sample copies describing the changed behavior.',
    "Contract docs, through the project's pending-artifact-updates convention where one exists.",
    'PR image pins, when a changed screenshot is embedded in the PR body.',
]

TASK_CLASSES = ('implementation', 'qa_author', 'qa_collect', 'documentation', 'review')

# B12 reached consensus; this is its exact text for the "Light-tier collection
# results" section, verbatim as the coordinator supplied it. The installed section
# body (everything after the heading, up to the next heading) must equal this,
# normalised, so no sentence of it can be silently dropped, reworded or reordered.
B12_TEXT = (
    'When delegation is enabled, `start` a light-tier or `qa_collect` task with '
    '`--owned <path>` (repeatable) — it is now required, never a silent '
    'whole-directory default. A light-tier `successful` result is never accepted '
    'on a bare claim: `collect` only trusts a produced-file list that is both '
    "inside the declared owned paths and among the driver's own measured changes "
    '— never counts from a worker\'s summary. Completing a delegated stage or '
    'checking off a delegated task is not enough either: `complete` and the Ready '
    "gate both require the dispatcher's own ledger — untampered, and for "
    '`complete`, started under the exact claim being completed — to show the '
    'attempt `successful`; any other status, including `unverified`, `running` or '
    'a hand-edited ledger, is refused. Resolve `unverified` with `reassign` to a '
    'standard tier, or `delegate_dispatch.py accept --run-id <id> --command '
    '"<check>" --expect counts|files [--owned <path>]`, which runs that check '
    'itself (never a `.bat`/`.cmd` shim on Windows — use the underlying '
    'executable) and records sha256/size evidence. `accept --owned` may only '
    'narrow the paths recorded at `start`. A note never accepts an `unverified` run.'
    ' Ledger trust is tri-state, not pass/fail: no local `.written` marker (a '
    'fresh checkout or CI runner) is a warning only, not a block — status is '
    'still enforced. A genuine tamper (a marker that disagrees) is sticky and '
    'survives a later legitimate write; resolve it with `delegate_dispatch.py '
    'trust-reset --feature <f> --reason "<text>"` only after reviewing exactly '
    'what changed — this catches accidental and local tampering only, never a '
    'forged commit, so CI integrity still rests on review. After upgrading to '
    'this release, re-delegate any stage claimed under an older checkpoint '
    "once, since its recorded attempt has no `claim_token` and can never "
    'satisfy `complete`. `trust-reset` is an orchestration-agent command, '
    "never a worker's."
    ' A checked task with no delegation attempt reaches Ready only through '
    '`delegate_dispatch.py adopt --feature <feature> --id <task> --command '
    '"<acceptance check>" --expect counts|files [--owned <path>]`. It refuses '
    '(`DELEGATION_ADOPT_HAS_ATTEMPT`) if any attempt already exists for that '
    'task, and otherwise runs the acceptance check with the same machinery as '
    '`accept` (no shell, `.bat`/`.cmd` shims refused, bounded timeout, output '
    'cap, owned-path containment, sha256 evidence), recording a successful '
    'attempt only when the check passes. There is no self-certification or '
    'exemption path: a project that enables delegation mid-feature adopts '
    'each already-checked task individually, with a real check.'
    " An adopted attempt is bound to the task's content: `adopt` records a "
    'sha256 of the task line (minus its checkbox state, whitespace '
    'normalised), and Ready re-checks that hash at completion time, refusing '
    'with `DELEGATION_ADOPT_TASK_CHANGED` if the task was edited or replaced '
    'under the same id since adoption. Since an adopted attempt has no '
    'dispatcher route to escalate, `reassign` refuses it with '
    '`DELEGATION_REASSIGN_ADOPTED_UNSUPPORTED`; the supported recovery is to '
    're-run `adopt` with a corrected acceptance check, or to `start` the task '
    'normally.'
)

# The dispatcher-operations.md marker list must include B12's new [Collect] marker
# alongside the four it already had.
DISPATCHER_OPS_MARKERS = [
    '`[Impl]` (or `[QA]`, `[Docs]`, `[Review]`, `[Collect]`) marker',
]


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
                cls.raw_assign = archive.read(
                    'workflow/skills/workflow/references/execution-assign.md').decode('utf-8')
                cls.raw_report = archive.read(
                    'workflow/skills/workflow/references/execution-report.md').decode('utf-8')
                cls.dispatcher_ops = normalize(archive.read(
                    'workflow/skills/workflow/references/dispatcher-operations.md').decode('utf-8'))
                cls.assign = normalize(cls.raw_assign)
                cls.report = normalize(cls.raw_report)
                reference_prefix = 'workflow/skills/workflow/references/'
                core_path = 'workflow/skills/workflow/SKILL.md'
                cls.all_reference_texts = {
                    name: archive.read(name).decode('utf-8')
                    for name in archive.namelist()
                    if name.startswith(reference_prefix) or name == core_path
                }

    def test_assign_carries_every_b11_marker(self):
        missing = [m for m in ASSIGN_MARKERS if normalize(m) not in self.assign]
        self.assertEqual(missing, [],
                          f'Missing from the installed execution-assign.md: {missing}')

    def test_report_carries_every_b11_marker(self):
        missing = [m for m in REPORT_MARKERS if normalize(m) not in self.report]
        self.assertEqual(missing, [],
                          f'Missing from the installed execution-report.md: {missing}')

    def test_turn_budget_table_has_every_row_as_a_real_table_row(self):
        missing = [row for row in TABLE_ROWS if row not in self.assign]
        self.assertEqual(missing, [],
                          f'Turn-budget table missing row(s) (as real `| cell | cell` rows, '
                          f'not just the class name in prose): {missing}')
        # Belt and braces: the class name itself must also appear (catches a row whose
        # class name was typo'd or removed while the rest of the row stayed).
        for task_class in TASK_CLASSES:
            self.assertIn(task_class, self.assign,
                          f'Turn-budget table missing task class {task_class!r}')

    def test_ten_line_result_template_has_all_ten_fields_in_order(self):
        start = self.raw_report.index('Task: <T### and title>')
        fence_end = self.raw_report.index('```', start)
        block = self.raw_report[start:fence_end]
        lines = [ln for ln in block.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 10,
                          f'Structured result template must be exactly 10 lines, got '
                          f'{len(lines)}: {lines}')
        for field, line in zip(TEMPLATE_FIELDS, lines):
            self.assertTrue(line.startswith(field),
                             f'Expected line to start with {field!r}, got {line!r}')
        # And each field name individually, so a template that kept ten lines but
        # silently renamed or dropped one field cannot pass by line count alone.
        for field in TEMPLATE_FIELDS:
            self.assertTrue(any(line.startswith(field) for line in lines),
                             f'Template field {field!r} missing from the ten-line block: {lines}')

    def test_consumers_checklist_has_all_six_bullets(self):
        start = self.raw_report.index('## Consumers checklist after a fix (F11)')
        end = self.raw_report.index('## Light-tier collection results (B12)', start)
        section = self.raw_report[start:end]
        bullets = [ln[2:].strip() for ln in section.splitlines() if ln.startswith('- ')]
        self.assertEqual(bullets, F11_BULLETS,
                          f'F11 consumers checklist bullets changed or incomplete: {bullets}')

    def test_b12_section_matches_the_consensus_text_exactly(self):
        heading = '## Light-tier collection results (B12)'
        start = self.raw_report.index(heading) + len(heading)
        end = self.raw_report.index('## Continue through delivery', start)
        body = normalize(self.raw_report[start:end])
        self.assertEqual(body, normalize(B12_TEXT),
                          'The B12 section no longer matches the consensus text exactly '
                          '(a word was dropped, reworded or reordered).')

    def test_b12_section_is_no_longer_a_placeholder(self):
        # Guards against a regression back to the pre-consensus placeholder wording.
        for stale in ('Placeholder.', 'still being revised upstream',
                      'the orchestrator will supply the final text'):
            self.assertNotIn(stale, self.report,
                              f'B12 placeholder text {stale!r} should have been replaced')

    def test_dispatcher_operations_names_the_collect_marker(self):
        missing = [m for m in DISPATCHER_OPS_MARKERS if normalize(m) not in self.dispatcher_ops]
        self.assertEqual(missing, [],
                          f'Missing from the installed dispatcher-operations.md: {missing}')

    def test_diff_field_uses_the_line_count_wording(self):
        self.assertIn('Diff: <+/- line counts per file, uncommitted>', self.raw_report)

    def test_no_reference_mentions_the_retired_exemption_terms(self):
        # B12 replaced its exemption path with the evidence-based `adopt` command;
        # neither of these terms named the old self-certification/exemption
        # mechanism may reappear in any installed reference or the core.
        stale_terms = ('orchestrator-executed', 'delegation_enabled_for_execute')
        offenders = {
            name: [term for term in stale_terms if term in text]
            for name, text in self.all_reference_texts.items()
        }
        offenders = {name: terms for name, terms in offenders.items() if terms}
        self.assertEqual(offenders, {},
                          f'Retired exemption term(s) found: {offenders}')


if __name__ == '__main__':
    unittest.main()
