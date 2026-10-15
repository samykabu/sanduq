"""Token budget: Progress verbs must never cost more than a hand-maintained Markdown report.

Skipped when tiktoken is not installed. Counts are o200k_base serialized-content tokens, exact for that encoding.
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import tiktoken  # noqa: F401
    HAVE_TIKTOKEN = True
except ImportError:  # pragma: no cover
    HAVE_TIKTOKEN = False

if HAVE_TIKTOKEN:
    from bench import approaches, report, run, traces

ENC = "o200k_base"
REQUIRES_CLI = unittest.skipUnless(HAVE_TIKTOKEN and approaches.new_available() if HAVE_TIKTOKEN else False,
                                   "tiktoken or the Progress CLI is not available")


@unittest.skipUnless(HAVE_TIKTOKEN, "tiktoken is not installed")
@REQUIRES_CLI
class TokenBudget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = run.compute()
        cls.new = cls.data["results"]["NEW"]
        cls.md = cls.data["results"]["MD-EDIT"]

    def test_every_event_new_not_above_md_edit(self):
        for i, (n, m) in enumerate(zip(self.new["events"], self.md["events"])):
            self.assertLessEqual(n[ENC], m[ENC], "event %d (%s)" % (i, n["kind"]))

    def test_every_class_new_not_above_md_edit(self):
        new = run.per_class(self.data, "NEW", ENC)
        md = run.per_class(self.data, "MD-EDIT", ENC)
        for kind in traces.CLASSES:
            self.assertLessEqual(new[kind], md[kind], kind)

    def test_aggregate_and_every_prefix(self):
        new = run.prefix_totals(self.data, "NEW", ENC)
        md = run.prefix_totals(self.data, "MD-EDIT", ENC)
        self.assertLessEqual(new[-1], md[-1])
        for i, (a, b) in enumerate(zip(new, md)):
            self.assertLessEqual(a, b, "prefix %d" % (i + 1))

    def test_automatic_events_cost_nothing(self):
        for event in self.new["events"]:
            if event["kind"] in traces.AUTOMATIC:
                self.assertEqual(event[ENC], 0, event["kind"])
                self.assertEqual(event["bytes"], 0, event["kind"])

    def test_verbs_ran_cleanly(self):
        for event in self.new["raw_events"]:
            self.assertEqual(event["exit_code"], 0, event["kind"])
            for tag, text in event["messages"]:
                self.assertNotIn("error", text.lower() if tag == "result" else "", event["kind"])

    def test_every_verb_output_is_one_line(self):
        for event in self.new["raw_events"]:
            for tag, text in event["messages"]:
                if tag == "result":
                    self.assertEqual(len(text.splitlines()), 1, text)

    def test_skill_is_short(self):
        lines = approaches.SKILL_PATH.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), 60)
        text = "\n".join(lines)
        self.assertIn("Reporting is a deterministic projection. Never spawn, retain, message or poll an agent solely to maintain it.", text)

    def test_generated_report_is_current(self):
        doc = report.DOC.read_text(encoding="utf-8")
        self.assertEqual(doc, report.render(self.data), "run: python -m tests.bench.report")


if __name__ == "__main__":
    unittest.main()
