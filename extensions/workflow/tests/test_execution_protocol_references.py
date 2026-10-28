"""The execution-protocol rules ship in the *installed* reference files, not just the working tree, so an
edit or a packaging regression cannot silently drop one.

Reads the archive `extensions/scripts/package.py` builds (the one `install.py` and `upgrade.py` ship). Each
rule is checked by what an agent acts on: a heading, a table row's leading cells, a template field, a command,
an error code or a key term. No check pins a prose sentence, so rewording a rule never fails here; dropping
the command, code or structure it names does.
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

# Key terms of the assign rules (spawn and wait, turn budgets, hand-off, staging, the ledger-trust verbs);
# every one must appear in the installed assign reference or the Execute parts it composes with.
ASSIGN_MARKERS = [
    'blocking rather than backgrounded',                                  # spawn: blocking, concurrent calls
    'is never a valid final message',                                     # wait: no turn ends owning background work
    '`delegate_dispatch.py collect`',                                     # wait: the collect loop command
    'Turn budgets',                                                       # turn-budget table
    'cache reads',                                                        # budget basis
    '`progress.py usage`',                                                # overrun figure source
    'Budget overrun T###: <class> <figure>/<budget>: <reason>',           # overrun log line format
    'never Haiku',                                                        # qa_author never on the light tier
    '`[collect]` marker',                                                 # light tier only by marker
    '150K tokens',                                                        # planned hand-off threshold
    '`git stash`', '`git add -A`',                                        # forbidden for a task worker
    'A task worker runs no `delegate_dispatch.py` command',               # worker scope
    'top-level dispatcher session',                                       # where ledger-trust verbs run
    'delegated Execute stage',                                            # the orchestrator-scope exception
    '`trust-reset` stays forbidden',
    'by explicit name',                                                   # staging owned paths
    '--tasks specs/<feature>/tasks.md --output specs/<feature>/workflow/progress --summary',
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
    '## Report only on state change',
    '## Read verification summaries before raw output',
    'only for a lane that failed',
    '## Light-tier collection results',
    'python .specify/extensions/workflow/scripts/progress.py usage --output '
    'specs/<feature>/workflow/progress --overhead dispatcher --agent '
    '<dispatcher-session-id> --collect claude --log '
    "<dispatcher's own session transcript> --summary",                 # exact dispatcher-usage command
    'once per phase',                                                  # task-issue sync cadence
    'the dispatcher owns this call',
    '`sync_states()`',
    'human-review completion',
    '`--summary`',
    'skipped reason=<why>',                                            # --summary skip form
    '--parent ... --apply --summary',
    '--collect claude --summary',
]

# The eleven result-template field names, in order, each as it must open its own line. A worker
# reports `Diff:`, never a commit: the orchestration agent stages and commits.
TEMPLATE_FIELDS = [
    'Task:', 'Status:', 'Files touched:', 'Tests:', 'Evidence:', 'Diff:',
    'Consumers checked:', 'Tokens:', 'Model:', 'Blockers:', 'Next:',
]

# The consumers checklist: six bullets, each naming the consumer it covers.
CHECKLIST_CONSUMERS = [
    'End-to-end/integration specs', 'lane registry', 'QA capture specs', 'Manual/User-Manual pages',
    'Contract docs', 'PR image pins',
]

TASK_CLASSES = ('implementation', 'qa_author', 'qa_collect', 'documentation', 'review')

# What the light-tier collection section must name: the commands and flags an agent runs, the ledger
# marker, and every refusal or warning code the dispatcher and the Ready gate emit for this flow.
LIGHT_TIER_TERMS = [
    '--owned <path>', '`collect`', '`complete`', '`unverified`', '`reassign`',
    'delegate_dispatch.py accept --run-id <id> --command "<check>" --expect counts|files',
    '--nonce <dispatcher_nonce>', '`.bat`/`.cmd`', 'sha256', '`.written`', '`claim_token`',
    'delegate_dispatch.py trust-reset --feature <f> --reason "approved by <user>: <why>"',
    "the user's explicit approval",
    'delegate_dispatch.py adopt --feature <feature> --id <task> --command',
    'DELEGATION_ADOPT_HAS_ATTEMPT', 'DELEGATION_ADOPT_TASK_CHANGED', 'DELEGATION_REASSIGN_ADOPTED_UNSUPPORTED',
    '`SANDUQ_DELEGATED_RUN`', 'DELEGATION_WORKER_CONTEXT', 'DELEGATION_TASK_ADOPTED', 'DELEGATION_TASK_ACCEPTED',
    '`SANDUQ_DELEGATED_ROLE=orchestrator`', '`SANDUQ_DELEGATED_FEATURE=<feature>`', 'DELEGATION_ORCHESTRATOR_SCOPE',
]

# dispatcher-operations.md lists every task-class marker, [Collect] included.
DISPATCHER_OPS_MARKERS = [
    '`[Impl]` (or `[QA]`, `[Docs]`, `[Review]`, `[Collect]`) marker',
]


def normalize(text):
    # Markdown hard-wraps a paragraph at ~80 columns, so a marker phrase this
    # test checks for can legitimately straddle a line break; collapse all
    # whitespace runs (including newlines) to a single space before matching,
    # the same way test_skill_split.py's normalize() does.
    return re.sub(r'\s+', ' ', text).strip()


class ExecutionProtocolReferenceTests(unittest.TestCase):
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
                reference_prefix = 'workflow/skills/workflow/references/'
                # The Execute claim composes these two with its mode's parts (references/execute/*.md and
                # reporting.md), so a rule may live in any of them; every rule must still ship.
                cls.parts = {name[len(reference_prefix):]: archive.read(name).decode('utf-8')
                             for name in archive.namelist()
                             if name.startswith(reference_prefix + 'execute/') or name == reference_prefix + 'reporting.md'}
                protocol = '\n'.join(cls.parts[name] for name in sorted(cls.parts))
                cls.assign = normalize(cls.raw_assign + '\n' + protocol)
                cls.report = normalize(cls.raw_report + '\n' + protocol)
                core_path = 'workflow/skills/workflow/SKILL.md'
                cls.all_reference_texts = {
                    name: archive.read(name).decode('utf-8')
                    for name in archive.namelist()
                    if name.startswith(reference_prefix) or name == core_path
                }

    def test_assign_carries_every_rule_term(self):
        missing = [m for m in ASSIGN_MARKERS if normalize(m) not in self.assign]
        self.assertEqual(missing, [],
                          f'Missing from the installed execution-assign.md: {missing}')

    def test_report_carries_every_rule_term(self):
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

    def test_eleven_line_result_template_has_all_fields_in_order(self):
        start = self.raw_report.index('Task: <T### and title>')
        fence_end = self.raw_report.index('```', start)
        block = self.raw_report[start:fence_end]
        lines = [ln for ln in block.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 11,
                          f'Structured result template must be exactly 11 lines, got '
                          f'{len(lines)}: {lines}')
        for field, line in zip(TEMPLATE_FIELDS, lines):
            self.assertTrue(line.startswith(field),
                             f'Expected line to start with {field!r}, got {line!r}')
        # And each field name individually, so a template that kept eleven lines but
        # silently renamed or dropped one field cannot pass by line count alone.
        for field in TEMPLATE_FIELDS:
            self.assertTrue(any(line.startswith(field) for line in lines),
                             f'Template field {field!r} missing from the eleven-line block: {lines}')

    def test_consumers_checklist_has_all_six_bullets(self):
        start = self.raw_report.index('## Consumers checklist after a fix')
        end = self.raw_report.find('\n## ', start + 1)
        section = self.raw_report[start:end if end > 0 else None]
        bullets = [ln[2:].strip() for ln in section.splitlines() if ln.startswith('- ')]
        self.assertEqual(len(bullets), len(CHECKLIST_CONSUMERS), bullets)
        for consumer, bullet in zip(CHECKLIST_CONSUMERS, bullets):
            self.assertIn(consumer, bullet)

    def test_light_tier_section_names_every_command_and_code(self):
        heading = '## Light-tier collection results'
        text = self.parts['execute/delegated-workers.md']
        start = text.index(heading) + len(heading)
        end = text.find('\n## ', start)
        body = normalize(text[start:end if end > 0 else None])
        missing = [term for term in LIGHT_TIER_TERMS if normalize(term) not in body]
        self.assertEqual(missing, [], f'The light-tier collection section no longer names: {missing}')

    def test_light_tier_section_is_no_longer_a_placeholder(self):
        for stale in ('Placeholder.', 'still being revised upstream',
                      'the orchestrator will supply the final text'):
            self.assertNotIn(stale, self.report,
                              f'Placeholder text {stale!r} should have been replaced')

    def test_dispatcher_operations_names_the_collect_marker(self):
        missing = [m for m in DISPATCHER_OPS_MARKERS if normalize(m) not in self.dispatcher_ops]
        self.assertEqual(missing, [],
                          f'Missing from the installed dispatcher-operations.md: {missing}')

    def test_diff_field_uses_the_line_count_wording(self):
        self.assertIn('Diff: <+/- line counts per file, uncommitted>', self.raw_report)

    def test_no_reference_mentions_the_retired_exemption_terms(self):
        # A checked task earns Ready only through an evidence-based command; neither
        # self-certification term may reappear in any installed reference or the core.
        stale_terms = ('orchestrator-executed', 'delegation_enabled_for_execute')
        offenders = {
            name: [term for term in stale_terms if term in text]
            for name, text in self.all_reference_texts.items()
        }
        offenders = {name: terms for name, terms in offenders.items() if terms}
        self.assertEqual(offenders, {},
                          f'Retired exemption term(s) found: {offenders}')


class RoleBoundaryTextTests(unittest.TestCase):
    """Ledger-trust verbs stay with the top-level dispatcher, and every composing overlay states that the
    claim's reference text wins over the upstream text."""
    REFERENCES = ROOT / 'extensions/workflow/skills/workflow/references'
    VERBS = r'(accept|adopt|reassign|trust-reset)'
    PRECEDENCE = ('`reference_text`', 'wins', 'upstream hook prompts are skipped')

    def text(self, path):
        return normalize(path.read_text(encoding='utf-8'))

    def test_no_reference_lets_a_host_subagent_run_a_ledger_trust_verb(self):
        claims = re.compile(r'(orchestration agent|orchestration-agent|subagent|the orchestrator)[^.]*?'
                            r'\b(runs?|calls?|makes?|command)\b[^.]*?`?' + self.VERBS + r'\b')
        offenders = []
        for path in self.REFERENCES.rglob('*.md'):
            for sentence in re.split(r'(?<=[.;:])\s', self.text(path)):
                if claims.search(sentence) and not re.search(r'\b(never|not|only in the top-level|refuses?)\b',
                                                              sentence):
                    offenders.append((path.name, sentence))
        self.assertEqual(offenders, [])
        for name in ('execution-assign.md', 'execute/orchestrator.md', 'execute/delegated-workers.md'):
            text = self.text(self.REFERENCES / name)
            with self.subTest(name=name):
                self.assertIn('top-level dispatcher session', text)
                self.assertIn('"needs accept/adopt for T###"', text)
        for name in ('execution-assign.md', 'execute/orchestrator.md', 'execute/delegated-workers.md'):
            with self.subTest(name=name):
                self.assertRegex(self.text(self.REFERENCES / name), r"trust-reset` (also )?needs the user's explicit approval")

    def test_every_composing_overlay_states_the_precedence_and_the_contract_orders_it(self):
        overlays = [path for path in sorted((ROOT / 'presets/workflow/commands').glob('*.md'))
                    if 'then continue with the upstream instructions below' in path.read_text(encoding='utf-8')]
        overlays.append(ROOT / 'presets/scope-gate/commands/specify-gate.md')
        self.assertGreaterEqual(len(overlays), 11)
        for path in overlays:
            with self.subTest(overlay=path.name):
                for term in self.PRECEDENCE:
                    self.assertIn(term, self.text(path))
        contract = self.text(self.REFERENCES / 'dispatcher-operations.md')
        self.assertIn('Precedence inside a claim', contract)
        order = ['runtime claim fields', "claim's `reference_text`", 'the managed overlay', 'the upstream Spec Kit text',
                 'skill prose']
        positions = [contract.index(item, contract.index('Precedence inside a claim')) for item in order]
        self.assertEqual(positions, sorted(positions))


if __name__ == '__main__':
    unittest.main()
