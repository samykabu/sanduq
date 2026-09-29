"""B8 (Sprint 4, Stream B): prove the SKILL.md/execution.md/preset-overlay split moved
every rule instead of dropping any of them.

Compares the pre-split originals (read from git history at BASE_COMMIT, the commit the
`feat/b8-dispatcher-core` branch forked from) against the current core SKILL.md and
`references/*.md`. Every whitespace-normalised sentence-ish unit from an original file
must appear verbatim somewhere in the new file set, unless it is explicitly listed in
REWORD_EXCEPTIONS with a reason (all of those are pointer text whose target moved, never
a dropped rule).
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# origin/main HEAD when the feat/b8-dispatcher-core worktree was created, i.e. the last
# commit before this package's SKILL.md/execution.md/preset-overlay split.
BASE_COMMIT = '5c96254'

ORIGINAL_PATHS = [
    'extensions/workflow/skills/workflow/SKILL.md',
    'extensions/workflow/skills/workflow/references/execution.md',
    'presets/workflow/commands/speckit.scope.run.md',
    'presets/workflow/commands/speckit.specify.md',
    'presets/workflow/commands/speckit.clarify.md',
    'presets/workflow/commands/speckit.plan.md',
    'presets/workflow/commands/speckit.tasks.md',
    'presets/workflow/commands/speckit.analyze.md',
    'presets/workflow/commands/speckit.taskstoissues.md',
    'presets/workflow/commands/speckit.implement.md',
    'presets/workflow/commands/speckit.superspec.brainstorm.md',
    'presets/workflow/commands/speckit.superspec.tasks.md',
    'presets/workflow/commands/speckit.superspec.execute.md',
    'presets/workflow/commands/speckit.superspec.review.md',
    'presets/workflow/commands/speckit.speckit-superpowers-bridge.execute.md',
    'presets/workflow/commands/speckit.speckit-superpowers-bridge.guard.md',
    'presets/workflow/commands/speckit.speckit-superpowers-bridge.handoff.md',
]

# Every entry here is a sentence (or bullet) from an original file that the new file set
# does NOT reproduce verbatim, because it was a navigation pointer whose target moved.
# The substance each one points at is preserved elsewhere (checked by other assertions in
# this suite and in test_workflow.py); only the pointer wording changed.
REWORD_EXCEPTIONS = [
    ("Run the stage loop below.",
     "the stage loop moved from this entry-point bullet into core SKILL.md; "
     "references/stage-scope.md now says 'Run the stage loop in the core skill.'"),
    ("If the bound PR is already merged, use the post-merge verification protocol below; "
     "do not create a replacement PR or claim the old readiness receipt verifies new source.",
     "the post-merge verification section now precedes this sentence inside "
     "references/stage-pr.md (both moved into the same file), so the pointer reads "
     "'...protocol above;' there."),
    ("Read [the execution protocol](references/execution.md).",
     "references/execution.md was split into execution-assign.md and execution-report.md "
     "(B8); the Execute row in references/stage-execute.md now names both halves."),
    ("Both managed executors use [the same execution protocol](references/execution.md).",
     "same split as above; references/stage-execute.md's Execution ownership section "
     "now names both halves."),
    ("Before executing a task, read\n"
     "`.specify/extensions/workflow/skills/workflow/references/execution.md`.",
     "same split; both speckit.implement.md's and speckit.superspec.execute.md's "
     "Core Implement provider text (moved to references/stage-execute.md) now points at "
     "`references/stage-execute.md`, which forwards to the two halves."),
    ("Add the stage-specific fields below.",
     "the Stage contracts table moved out of SKILL.md into per-stage references; "
     "references/receipt-rules.md now says 'Add the stage-specific fields in this "
     "stage's own reference.'"),
    ("Inside a matching claim, execute the domain work below once, then return control to "
     "the dispatcher.",
     "the managed-overlay boilerplate is now centralised in "
     "references/dispatcher-operations.md, decoupled from the per-command body it used "
     "to immediately precede in each preset file; 'below' was dropped ('execute the "
     "domain work once')."),
    ("Update the report from the actual merge result and complete post-merge verification below.",
     "post-merge verification is now a section of references/stage-pr.md rather than "
     "later in the same SKILL.md file; references/stage-execute.md points at it by path "
     "('...complete post-merge verification in `references/stage-pr.md`.')."),
    ("Stage contracts",
     "the old 'Stage contracts' table (SKILL.md) is now the 'Stage reference map' table "
     "plus one 'Required work and evidence' heading per stage-<name>.md; every cell's "
     "actual text is still checked verbatim."),
    ("Recovery after source drift (G6).",
     "the bold lead-in '**Recovery after source drift (G6).**' became the markdown "
     "heading '## Recovery after source drift (G6)' in references/receipt-rules.md; "
     "headings carry no trailing period, so the punctuation differs by one character."),
    ("STOP this invocation before the upstream legacy instructions below.",
     "B8 follow-up (three low notes, consensus): each speckit-superpowers-bridge overlay "
     "now merges its legacy-guard.md pointer and this STOP into one sentence, 'If "
     "`.specify/workflow.yml` exists, follow legacy-guard.md and STOP before the upstream "
     "legacy instructions below; otherwise continue with them unchanged.'; the words are "
     "the same but no longer form this exact original sentence."),
    ("Sync native task issues through the dispatcher after accepted batches.",
     "cadence changed to once per phase (plan package B7); owner stated in "
     "dispatcher-operations.md."),
    ("After completed execution batches and documentation tasks, run "
     "`task_issues.py --sync-states --feature ... --parent ... --apply` to "
     "close/reopen the correct native task issues.",
     "same B7 cadence change as above, applied to this original SKILL.md sentence "
     "(moved verbatim into references/dispatcher-operations.md by B8): it now reads "
     "'Once per phase boundary, ... the dispatcher runs `task_issues.py "
     "--sync-states ... --apply --summary` ...', naming the dispatcher as the "
     "owner and adding the B7 `--summary` flag, per the B11 review fix."),
    ("The checkpoint must be supplemented with concrete pending task IDs, test "
     "results, decisions, GitHub URLs, background process handles and unresolved "
     "approvals in handoff.md.",
     "B11 review fix (finding 4): references/dispatcher-operations.md's handoff-"
     "contents list now also names the dispatcher's own session ID and session "
     "transcript path, since execution-report.md's dispatcher-usage recording "
     "reads that path from the handoff; the surrounding items are unchanged."),
    ('```text python .specify/extensions/workflow/scripts/progress.py init --tasks '
     'specs/<feature>/tasks.md --output specs/<feature>/workflow/progress ```',
     "B11 (Sprint 4) added the B7 '--summary' flag to every routine progress.py/"
     "task_issues.py example call once B7 shipped it in the same release; the "
     "command in references/execution-assign.md is the same 'progress.py init "
     "--tasks ... --output ...' call with ' --summary' appended, so the sentence "
     "unit (the whole fenced block, one unit because it has no sentence-ending "
     "punctuation) no longer matches byte-for-byte."),
    ('```text python .specify/extensions/workflow/scripts/progress.py task --output '
     'specs/<feature>/workflow/progress --id T001 --status running --agent <worker-id> '
     '--note "Own src/example.py; depends on T000" python .specify/extensions/workflow/'
     'scripts/progress.py task --output specs/<feature>/workflow/progress --id T001 '
     '--status done --agent <worker-id> --note "Acceptance check passed; evidence: '
     'evidence/T001.txt" python .specify/extensions/workflow/scripts/progress.py event '
     '--output specs/<feature>/workflow/progress --message "Phase 1 tests passed; '
     'preparing phase commit" python .specify/extensions/workflow/scripts/progress.py '
     'phase --output specs/<feature>/workflow/progress --name "Phase 1" --status '
     'complete --commit <sha> ```',
     "same B7 '--summary' addition as above, applied to the task/event/phase example "
     "block in references/execution-report.md; every command is unchanged apart from "
     "the appended ' --summary'."),
    ('```text python .specify/extensions/workflow/scripts/progress.py usage --output '
     'specs/<feature>/workflow/progress --id T001 --agent <worker-id> --collect claude '
     'python .specify/extensions/workflow/scripts/progress.py usage --output '
     'specs/<feature>/workflow/progress --id T002 --agent <worker-id> --collect codex '
     'python .specify/extensions/workflow/scripts/progress.py usage --output '
     'specs/<feature>/workflow/progress --id T003 --agent <run-id> --collect delegate '
     '--log .delegate/runs/<run-id>/result.json python .specify/extensions/workflow/'
     'scripts/progress.py usage --output specs/<feature>/workflow/progress --overhead '
     'orchestrator --agent <orchestrator-id> --collect claude python .specify/'
     'extensions/workflow/scripts/progress.py sync --output specs/<feature>/workflow/'
     'progress ```',
     "same B7 '--summary' addition as above, applied to the usage/sync example block "
     "in references/execution-report.md; every command is unchanged apart from the "
     "appended ' --summary'."),
    ('```text python .specify/extensions/workflow/scripts/progress.py pr --output '
     'specs/<feature>/workflow/progress --url <pr-url> --status open python .specify/'
     'extensions/workflow/scripts/progress.py event --output specs/<feature>/workflow/'
     'progress --message "CI failure: <check>; fix assigned to <worker-id>" python '
     '.specify/extensions/workflow/scripts/progress.py pr --output specs/<feature>/'
     'workflow/progress --url <pr-url> --status merged ```',
     "same B7 '--summary' addition as above, applied to the PR-status example block "
     "in references/execution-report.md; every command is unchanged apart from the "
     "appended ' --summary'."),
]


def normalize(text):
    # `**bold lead-ins.**` in the originals became `## real headings` in the split files
    # (and vice versa is never done); strip both emphasis/heading markup so that a pure
    # style change never counts as dropped content.
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = text.replace('**', '')
    return re.sub(r'\s+', ' ', text).strip()


FRONTMATTER = re.compile(r'\A---\n.*?\n---\n', re.DOTALL)
HTML_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)
TABLE_ROW = re.compile(r'^\|(.+)\|\s*$')
SEPARATOR_ROW = re.compile(r'^\|[\s:|-]+\|\s*$')
LIST_MARKER = re.compile(r'^(?:\d+\.|-)\s+')
SENTENCE_SPLIT = re.compile(r'(?<=[.:;])\s+(?=[A-Z`(0-9])')


def strip_noise(text):
    # Frontmatter (schema-required installer metadata, unchanged verbatim in every new
    # overlay pointer file too) and the `<!-- sanduq-workflow-*:v1 -->` version markers
    # (also kept verbatim in every new overlay) are not prose rules; stripping them here
    # avoids false failures from how the sentence splitter chunks around them.
    text = FRONTMATTER.sub('', text)
    text = HTML_COMMENT.sub('', text)
    return text


def strip_tables(text):
    """Turn `| Stage | Cell text. |` rows into plain `Cell text.` lines so table
    markup cannot glue onto (and hide) the actual rule text during comparison."""
    out = []
    for line in text.split('\n'):
        if SEPARATOR_ROW.match(line):
            continue
        match = TABLE_ROW.match(line)
        if match:
            cells = [c.strip() for c in match.group(1).split('|')]
            out.append(' '.join(cells[1:]) if len(cells) > 1 else cells[0])
        else:
            out.append(line)
    return '\n'.join(out)


def split_paragraphs(text):
    # Force a paragraph break at every top-level list marker: the source files pack
    # entry-point bullets, stage-loop steps and recovery bullets with no blank line
    # between items, which would otherwise glue two originally-adjacent-but-now-
    # relocated bullets into one incomparable unit.
    text = re.sub(r'\n(?=\d+\.\s|-\s)', '\n\n', text)
    for para in text.split('\n\n'):
        para = LIST_MARKER.sub('', para.strip())
        if para:
            yield para


def sentences(text):
    for para in split_paragraphs(strip_tables(strip_noise(text))):
        blob = normalize(para)
        if not blob:
            continue
        for piece in SENTENCE_SPLIT.split(blob):
            piece = piece.strip()
            if len(piece) >= 12:
                yield piece


def git_show(path):
    result = subprocess.run(['git', 'show', f'{BASE_COMMIT}:{path}'], cwd=ROOT,
                             capture_output=True, text=True, encoding='utf-8', check=True)
    return result.stdout


class SkillSplitCompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core = ROOT / 'extensions/workflow/skills/workflow/SKILL.md'
        references = sorted((ROOT / 'extensions/workflow/skills/workflow/references').glob('*.md'))
        # The current (post-split) overlay pointer files are also searched: a few of them
        # inline a short, verbatim-preserved original sentence (e.g. the legacy guard's
        # STOP line) rather than only pointing elsewhere, and that counts as moved, not
        # dropped, even though the overlay body is otherwise new pointer text.
        overlays = sorted((ROOT / 'presets/workflow/commands').glob('*.md'))
        cls.new_files = [core] + references + overlays
        cls.new_corpus = normalize('\n\n'.join(p.read_text(encoding='utf-8') for p in cls.new_files))
        cls.exceptions = {normalize(text) for text, _reason in REWORD_EXCEPTIONS}

    def covered(self, unit):
        if unit in self.new_corpus:
            return True
        # An exception covers a unit only on an exact match after normalisation, never a
        # substring in either direction: a short exception phrase must not silently swallow
        # a longer, unrelated dropped sentence that happens to contain it (or vice versa).
        return unit in self.exceptions

    def test_every_original_sentence_is_moved_not_dropped(self):
        missing = []
        for path in ORIGINAL_PATHS:
            original = git_show(path)
            for unit in sentences(original):
                if not self.covered(unit):
                    missing.append((path, unit))
        detail = '\n'.join(f'- {path}: {unit[:200]}' for path, unit in missing[:40])
        self.assertEqual(missing, [],
                          f'{len(missing)} sentence(s)/bullet(s) from the pre-B8 files are not '
                          f'present (verbatim, whitespace-normalised) anywhere in the new core '
                          f'SKILL.md + references/*.md, and are not in REWORD_EXCEPTIONS:\n{detail}')

    def test_reword_exceptions_document_a_reason(self):
        for text, reason in REWORD_EXCEPTIONS:
            self.assertTrue(text.strip())
            self.assertGreaterEqual(len(reason), 20, f'Reason too thin for: {text!r}')

    def test_new_reference_files_are_all_reachable_from_core_or_each_other(self):
        # Every reference file must be named at least once by core SKILL.md or by another
        # reference file, so nothing under references/ is an orphan the dispatcher would
        # never be told to load.
        core = ROOT / 'extensions/workflow/skills/workflow/SKILL.md'
        reference_dir = ROOT / 'extensions/workflow/skills/workflow/references'
        files = {core: core.read_text(encoding='utf-8')}
        files.update({p: p.read_text(encoding='utf-8') for p in reference_dir.glob('*.md')})
        unreachable = []
        for target in reference_dir.glob('*.md'):
            mentions_elsewhere = sum(text.count(target.name) for path, text in files.items() if path != target)
            if mentions_elsewhere < 1:
                unreachable.append(target.name)
        self.assertEqual(unreachable, [], f'Orphaned reference file(s) never named: {unreachable}')

    def read_reference(self, name):
        return (ROOT / 'extensions/workflow/skills/workflow/references' / name).read_text(encoding='utf-8')

    def test_core_reads_receipt_rules_before_every_receipt(self):
        # Review finding 3: core step 5 must load receipt-rules.md unconditionally (not
        # only on drift/STALE_RECEIPT), because the passed-receipt rules (no pass on
        # failed/skipped/pending work, pending decisions block, decision ledger in inputs,
        # no checkpoint files in the manifest) live only in that reference.
        core = (ROOT / 'extensions/workflow/skills/workflow/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('Before writing any receipt, read', core)
        self.assertIn('receipt-rules.md', core)
        rules = normalize(self.read_reference('receipt-rules.md'))
        for rule in ('cannot receive a passed receipt', 'blocks a passed receipt',
                     'Reread the', 'checkpoint files in input manifests'):
            self.assertIn(rule, rules)

    def test_verify_review_ready_point_at_the_publication_preflight(self):
        # Review finding 4: the preflight in stage-pr.md must run before the last
        # Verify/Review/Ready pass, so each of those three stage references names it.
        anchor = 'stage-pr.md#publication-preflight-and-post-merge-verification'
        for name in ('stage-verify.md', 'stage-review.md', 'stage-ready.md'):
            self.assertIn(anchor, self.read_reference(name), name)

    def test_handoff_and_github_rules_are_linked_from_their_consumers(self):
        # Review finding 5: dispatcher-operations.md's handoff/GitHub-discussion/task-
        # dedup rules must be reachable from core step 3 and from the two stages whose
        # work is GitHub discussions (clarify) and GitHub issue/task identity
        # (taskstoissues), not just sitting unlinked in dispatcher-operations.md.
        anchor = 'dispatcher-operations.md#interruption-and-github-behavior'
        core = (ROOT / 'extensions/workflow/skills/workflow/SKILL.md').read_text(encoding='utf-8')
        self.assertIn(anchor, core)
        for name in ('stage-clarify.md', 'stage-taskstoissues.md'):
            self.assertIn(anchor, self.read_reference(name), name)

    def test_every_overlay_inlines_stop_and_names_its_contract_or_guard(self):
        # Review findings 1/2 (and the three-low-notes follow-up A): a direct invocation
        # of any managed command with no active claim must read an inline STOP, not just a
        # pointer; every overlay in presets/workflow/commands/*.md must therefore carry the
        # literal word STOP and name either the managed-overlay contract anchor (the 12
        # sanduq-workflow-managed:v1 overlays) or legacy-guard.md (the 3
        # speckit-superpowers-bridge overlays).
        overlays_dir = ROOT / 'presets/workflow/commands'
        overlays = sorted(overlays_dir.glob('*.md'))
        self.assertGreaterEqual(len(overlays), 15, 'Expected all managed + legacy overlays')
        for path in overlays:
            text = path.read_text(encoding='utf-8')
            self.assertIn('STOP', text, path.name)
            self.assertTrue('#managed-overlay-contract' in text or 'legacy-guard.md' in text, path.name)


if __name__ == '__main__':
    unittest.main()
