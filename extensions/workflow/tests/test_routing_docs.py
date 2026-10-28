"""Instruction lint: one routing rule, stated once in references/delegation.md, linked from the rest."""
import re
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REFERENCES = PACKAGE / 'skills' / 'workflow' / 'references'
USER_DOC = PACKAGE.parents[1] / 'docs' / 'workflow' / 'delegation.md'
RULE = "The claim's route decides: each candidate's `route_kind` says who runs the work."
LINKERS = ('execute/orchestrator.md', 'execute/lean.md', 'execute/delegated-workers.md', 'execution-assign.md',
           'delegation-and-decisions.md')
# Wording from before native-first routing that sent work to the external driver whatever the host could do.
FORCES_EXTERNAL = (
    "When `delegation.enabled` is true, use the claim's `delegation` route: `delegate_dispatch.py start",
    'When `.specify/workflow.yml` enables delegation, start each ready `T###` worker',
    'routes workflow stages and implementation tasks to a preferred agent CLI and model through the bundled',
    'A per-work-type native preference is not a route key yet.',
)


def flat(path):
    return re.sub(r'\s+', ' ', path.read_text(encoding='utf-8'))


class RoutingDocs(unittest.TestCase):
    def test_the_rule_is_stated_once_in_the_delegation_reference(self):
        text = flat(REFERENCES / 'delegation.md')
        self.assertEqual(text.count('## Routing rule'), 1)
        self.assertEqual(text.count(RULE), 1)
        for term in ('native-first', 'native-unsupported:', 'native-failed:', 'external:cross-vendor',
                     'lean_execution.max_attempts', 'FALLBACK_CONFIRMATION_REQUIRED'):
            self.assertIn(term, text)

    def test_the_user_doc_mirrors_it_and_points_back(self):
        text = flat(USER_DOC)
        self.assertEqual(text.count(RULE), 1)
        self.assertIn('references/delegation.md#routing-rule', text)

    def test_the_other_references_link_instead_of_restating(self):
        for name in LINKERS:
            with self.subTest(name=name):
                text = flat(REFERENCES / name)
                self.assertIn('delegation.md#routing-rule', text)
                self.assertNotIn(RULE, text)

    def test_no_reference_forces_external_routing(self):
        for path in (*sorted(REFERENCES.rglob('*.md')), USER_DOC):
            text = flat(path)
            for phrase in FORCES_EXTERNAL:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertNotIn(phrase, text)


if __name__ == '__main__':
    unittest.main()
