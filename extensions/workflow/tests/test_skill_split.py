"""The gate rules the dispatcher, Scope skills and preset overlays must keep, as a curated
inventory (fixtures/rules-inventory.json: file, rule text, one-line reason).

This replaced a sentence-by-sentence comparison against frozen pre-split originals. That test
proved the 2026 split moved every sentence, but it also froze the wording of every sentence, so
any pruning or deduplication failed it. The inventory instead names the rules that gate real
behavior; wording around them may change, the rules may not disappear.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / 'extensions/workflow/skills/workflow'
REFERENCES = SKILL / 'references'
INVENTORY = Path(__file__).resolve().parent / 'fixtures' / 'rules-inventory.json'
sys.path.insert(0, str(ROOT / 'extensions/workflow/scripts'))
import workflow as w  # noqa: E402


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip()


class RuleInventoryTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding='utf-8')

    def test_every_inventoried_rule_is_still_stated(self):
        entries = json.loads(INVENTORY.read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(entries), 50)
        missing = [entry for entry in entries
                   if normalize(entry['rule']) not in normalize(self.read(entry['file']))]
        self.assertEqual(missing, [], 'Gate rules dropped from the instruction text')

    def test_every_inventory_entry_gives_a_reason(self):
        for entry in json.loads(INVENTORY.read_text(encoding='utf-8')):
            self.assertGreaterEqual(len(entry['reason']), 10, entry)

    def test_every_reference_is_reachable(self):
        # Stage references arrive through the claim (`stage_reference()`); every other
        # reference must be named by the core skill, another reference or a command.
        texts = [self.read(SKILL / 'SKILL.ext.md')]
        texts += [p.read_text(encoding='utf-8') for p in REFERENCES.glob('*.md')]
        texts += [p.read_text(encoding='utf-8') for p in (ROOT / 'extensions/workflow/commands').glob('*.md')]
        claimed = {Path(w.stage_reference(stage)).name for stage in w.BASE_STAGES}
        orphans = [p.name for p in REFERENCES.glob('*.md') if p.name not in claimed
                   and sum(text.count(p.name) for text in texts) - p.read_text(encoding='utf-8').count(p.name) < 1]
        self.assertEqual(orphans, [])

    def test_scope_skill_references_are_linked_from_their_skill(self):
        common = ['analysis-json.md', 'controls.md', 'managed.md', 'standalone.md']
        # Stream C: the local clarification transport has its own reference in github-clarification.
        for skill, expected in (('scope-analyst', common), ('github-clarification', sorted(common + ['local.md']))):
            folder = ROOT / 'extensions/workflow/skills' / skill
            core = (folder / 'SKILL.ext.md').read_text(encoding='utf-8')
            names = sorted(p.name for p in (folder / 'references').glob('*.md'))
            self.assertEqual(names, expected, skill)
            for name in names:
                self.assertIn('references/' + name, core, f'{skill} does not link {name}')

    def test_core_reads_receipt_rules_before_every_receipt(self):
        core = self.read(SKILL / 'SKILL.ext.md')
        self.assertIn('Before writing any receipt, read', core)
        self.assertIn('receipt-rules.md', core)
        self.assertIn('reference_text', core)

    def test_verify_review_ready_point_at_the_publication_preflight(self):
        anchor = 'stage-pr.md#publication-preflight-and-post-merge-verification'
        for name in ('stage-verify.md', 'stage-review.md', 'stage-ready.md'):
            self.assertIn(anchor, self.read(REFERENCES / name), name)

    def test_handoff_and_github_rules_are_linked_from_their_consumers(self):
        anchor = 'dispatcher-operations.md#interruption-and-github-behavior'
        self.assertIn(anchor, self.read(SKILL / 'SKILL.ext.md'))
        for name in ('stage-clarify.md', 'stage-taskstoissues.md'):
            self.assertIn(anchor, self.read(REFERENCES / name), name)

    def test_shared_paragraphs_live_in_one_place(self):
        # The managed binding rules and the required-only checkpoint rule each exist once.
        binding = 'This narrow path permits mapped Feature Specification'
        checkpoints = 'project policy pre-authorizes routine phase checkpoints'
        sources = list(REFERENCES.glob('*.md')) + list((ROOT / 'extensions/workflow/commands').glob('*.md'))
        sources += list((ROOT / 'presets').rglob('*.md'))
        for phrase, home in ((binding, 'scope-binding.md'), (checkpoints, 'superspec-checkpoints.md')):
            holders = [p.name for p in sources if phrase in normalize(p.read_text(encoding='utf-8'))]
            self.assertEqual(holders, [home], phrase)

    def test_every_overlay_inlines_stop_and_names_its_contract_or_guard(self):
        overlays = sorted((ROOT / 'presets/workflow/commands').glob('*.md'))
        self.assertGreaterEqual(len(overlays), 15)
        for path in overlays:
            text = path.read_text(encoding='utf-8')
            self.assertIn('STOP', text, path.name)
            self.assertTrue('#managed-overlay-contract' in text or 'legacy-guard.md' in text, path.name)

    def test_descriptions_follow_the_agent_skills_rules(self):
        import yaml
        files = list((ROOT / 'presets').rglob('commands/*.md'))
        files += list((ROOT / 'extensions/workflow/commands').glob('*.md'))
        files += [ROOT / 'extensions/workflow/skills/workflow/SKILL.ext.md',
                  ROOT / 'extensions/workflow/skills/scope-analyst/SKILL.ext.md',
                  ROOT / 'extensions/workflow/skills/github-clarification/SKILL.ext.md']
        for path in files:
            front = yaml.safe_load(path.read_text(encoding='utf-8').split('---')[1])
            description = front['description']
            self.assertTrue(1 <= len(description) <= 1024, path)
            self.assertNotIn('Sanduq managed lifecycle overlay', description, path)
            if 'presets' in path.parts:
                self.assertTrue(description.endswith('(Sanduq managed)'), path)
        self.assertEqual(yaml.safe_load(self.read(SKILL / 'SKILL.ext.md').split('---')[1])['name'], 'speckit-workflow')

    def test_review_and_version_identifiers_stay_out_of_agent_text(self):
        # Review ids (B11, F1, W01d, "round 3", "Scope 1.6.1") belong in the CHANGELOG.
        # Headings worker_brief.py parses (F1, F2, T0, F3, T7, T8) are the known exceptions.
        pattern = re.compile(r'\b(?:W0\d[a-z]?|P0\d|B1\d|Scope \d+\.\d+|review round \d|finding \d+|Sprint \d)\b')
        roots = [ROOT / 'extensions/workflow/skills', ROOT / 'extensions/workflow/commands', ROOT / 'presets']
        hits = [(p.name, m.group(0)) for root in roots for p in root.rglob('*.md')
                for m in pattern.finditer(p.read_text(encoding='utf-8'))]
        self.assertEqual(hits, [])


class CommandDescriptionTests(unittest.TestCase):
    def test_frontmatter_description_equals_the_manifest(self):
        # D1: the catalog reads extension.yml, the host reads the frontmatter; they must say the same.
        import yaml
        root = ROOT / 'extensions/workflow'
        manifest = yaml.safe_load((root / 'extension.yml').read_text(encoding='utf-8'))
        for command in manifest['provides']['commands']:
            text = (root / command['file']).read_text(encoding='utf-8')
            front = yaml.safe_load(text.split('---', 2)[1])
            self.assertEqual(front['description'], command['description'], command['name'])


if __name__ == '__main__':
    unittest.main()
