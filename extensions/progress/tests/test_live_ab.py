"""Regression tests for the manual live A/B tool: semantic equivalence and honest usage summaries.

No harness is started and no tokens are spent.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import live_ab  # noqa: E402
from bench import model, traces  # noqa: E402

TRACE = traces.build()


def final_state(trace=TRACE):
    state = model.new_state()
    for ev in trace:
        model.apply(state, ev)
    return state


def good_projection(state):
    """A projection that carries everything the trace should have produced."""
    lanes = []
    for i, (lid, lane) in enumerate(state["lanes"].items(), 1):
        groups = {"active": [], "waiting": [], "blocked": [], "done": []}
        for t in lane["tasks"]:
            groups["done" if state["tasks"][t]["state"] == "done" else "waiting"].append(t)
        lanes.append({"id": "L%d" % i, "owner": lane["owner"], "tasks": groups, "attempts": []})
    blockers = [{"id": bid, "target": b["target"], "by": {"type": "task", "ref": b["by"]}} for bid, b in state["blockers"].items()]
    made = [{"id": d_id, "question": d["question"], "selected": d["selected"]} for d_id, d in state["decisions"].items() if d["status"] == "made"]
    pending = [{"id": d_id, "question": d["question"]} for d_id, d in state["decisions"].items() if d["status"] == "pending"]
    events = [{"kind": "note", "text": "%s attempt 1 failed" % ev["task"]} for ev in TRACE if ev["kind"] == "fail_retry"]
    tasks = {t: {"done": v["state"] == "done"} for t, v in state["tasks"].items()}
    return {"schema": "sanduq.progress.v2", "lanes": lanes, "blockers": blockers, "tasks": tasks,
            "decisions": {"pending": pending, "made": made}, "events": events}


class Equivalence(unittest.TestCase):
    def test_a_complete_projection_is_equivalent(self):
        problems = live_ab.check_new(good_projection(final_state()), live_ab.expected(model, TRACE))
        self.assertEqual(problems, [])

    def test_checkboxes_plus_a_one_byte_facts_file_is_not_equivalent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "specs" / model.FEATURE / "progress").mkdir(parents=True)
            (root / "specs" / model.FEATURE / "progress" / "facts.jsonl").write_text("x", encoding="utf-8")
            tasks = "\n".join("- [x] %s t" % t for t, _, _ in model.TASKS[:live_ab.expected(model, TRACE)["done"]])
            (root / "specs" / model.FEATURE / "tasks.md").write_text(tasks, encoding="utf-8")
            result = live_ab.verify("new", root, model, TRACE)
        self.assertFalse(result["ok"])
        self.assertTrue(result["problems"])

    def test_missing_lane_blocker_decision_and_attempt_are_each_reported(self):
        expected = live_ab.expected(model, TRACE)
        data = good_projection(final_state())
        data["lanes"] = data["lanes"][:1]
        data["blockers"] = [{"id": "B9", "target": "T001", "by": {"type": "task", "ref": "T002"}}]
        data["decisions"] = {"pending": [], "made": []}
        data["events"] = []
        text = " ".join(live_ab.check_new(data, expected))
        for word in ("lane", "blocker", "decision", "attempt"):
            self.assertIn(word, text)

    def test_markdown_arm_is_parsed_by_section(self):
        state = final_state()
        expected = live_ab.expected(model, TRACE)
        self.assertEqual(live_ab.check_md(model.render(state), expected), [])
        broken = model.render(state).replace("## Decisions", "## Notes")
        self.assertTrue(any("decision" in p for p in live_ab.check_md(broken, expected)))
        no_blockers = model.render(state).replace("## Blockers", "## Other")
        self.assertTrue(any("blocker" in p for p in live_ab.check_md(no_blockers, expected)) or not expected["blockers"])


class UsageSummary(unittest.TestCase):
    def result(self, arm="new", status="successful", tokens=None, ok=True):
        return dict(harness="codex", model="m", arm=arm, status=status, tokens=tokens, verified={"ok": ok})

    def test_unknown_usage_stays_null_and_is_not_summed_as_zero(self):
        results = [self.result(status="failed", tokens={"fidelity": "unavailable", "input_fresh": 0, "output_total": 0, "total": 0})]
        group = live_ab.summarize(results)[("codex", "m", "new")]
        self.assertEqual((group["measured"], group["failed"]), (0, 1))
        self.assertIsNone(group["total"])
        self.assertIsNone(group["input_fresh"])

    def test_measured_unknown_failed_and_invalid_are_separated(self):
        exact = {"fidelity": "exact", "input_fresh": 10, "output_total": 5, "total": 15}
        results = [self.result(tokens=exact), self.result(tokens=exact),
                   self.result(tokens=None),
                   self.result(status="failed", tokens=exact),
                   self.result(tokens=exact, ok=False)]
        group = live_ab.summarize(results)[("codex", "m", "new")]
        self.assertEqual((group["measured"], group["unknown"], group["failed"], group["invalid"]), (2, 1, 1, 1))
        self.assertEqual((group["total"], group["input_fresh"], group["output_total"]), (30, 20, 10))

    def test_report_prints_unknown_not_zero(self):
        results = [self.result(status="start-failed", tokens=None)]
        with tempfile.TemporaryDirectory() as tmp:
            class A:
                pass
            live_ab.write_reports(Path(tmp), A(), [], results)
            payload = json.loads((Path(tmp) / "live-ab.json").read_text(encoding="utf-8"))
            md = (Path(tmp) / "live-ab.md").read_text(encoding="utf-8")
        self.assertIsNone(payload["summary"][0]["total"])
        self.assertIn("unknown", md)


if __name__ == "__main__":
    unittest.main()
