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
    ("If the bound PR is already merged, use the post-merge verification protocol below;",
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
    ("execute the domain work below once",
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
        cls.new_files = [core] + references
        cls.new_corpus = normalize('\n\n'.join(p.read_text(encoding='utf-8') for p in cls.new_files))
        cls.exceptions = [normalize(text) for text, _reason in REWORD_EXCEPTIONS]

    def covered(self, unit):
        if unit in self.new_corpus:
            return True
        # An exception covers a unit when the unit is (part of) the documented original
        # phrase; it never manufactures coverage for unrelated text.
        return any(unit in exc or exc in unit for exc in self.exceptions)

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


if __name__ == '__main__':
    unittest.main()
