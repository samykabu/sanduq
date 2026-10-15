#!/usr/bin/env python3
"""Manual paired A/B run: Progress verbs against a hand-edited Markdown report, with real harness token usage.

This is a measurement tool, not a unit test. It costs tokens, so it never runs from the test suite.
Each pair runs the same scripted update trace twice through the delegate-task driver, once per arm:

  new   record the updates with the Progress CLI (the skill text is placed in the sandbox)
  md    record the same updates by editing specs/<feature>/progress/report.md by hand

Pairs alternate arm order. Token figures come from the driver's result.json (`tokens`, with its fidelity flag).
Results are written as JSON and Markdown. Nothing here claims a Claude tokenizer count.

  python live_ab.py --dry-run                       print the planned runs and exit
  python live_ab.py --pairs 3 --updates 20          run (spends tokens)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXT = HERE.parent
sys.path.insert(0, str(EXT / "tests"))

DEFAULT_DELEGATE = Path(os.environ.get(
    "DELEGATE", r"D:\Projects\abushanab-net\Bunyan\.agents\skills\delegate-task\delegate.mjs"))
DEFAULT_TARGETS = "claude:claude-haiku-5-5,codex:gpt-6-luna"
ARMS = ("new", "md")


def load_trace(updates):
    from bench import model, traces  # imported lazily so --help works without the tests directory
    return model, traces.build()[:updates]


def describe(ev):
    """One plain sentence per trace event, the same for both arms."""
    k = ev["kind"]
    if k == "assign_lane":
        return "Assign lane %s (%s) to %s for %s, requested %s/%s/%s." % (
            ev["lane"], ev["label"], ev["owner"], ",".join(ev["tasks"]), ev["harness"], ev["model"], ev["effort"])
    if k == "start_task":
        return "%s starts %s." % (ev["lane"], ev["task"])
    if k == "complete_task":
        return "%s finishes %s; check it off in tasks.md." % (ev["lane"], ev["task"])
    if k == "fail_retry":
        return "Attempt on %s failed (%s); it is being retried." % (ev["task"], ev["note"])
    if k == "block":
        return "%s is blocked by %s." % (ev["task"], ev["by"])
    if k == "unblock":
        return "Blocker %s on %s is resolved." % (ev["blocker"], ev["task"])
    if k == "decision_ask":
        return "Open question %s: %s Options: %s." % (ev["id"], ev["question"], ", ".join(ev["options"]))
    if k == "decision_made":
        return "Decision %s made: %s (by %s, evidence: %s)." % (ev["id"], ev["selected"], ev["by"], ev["evidence"])
    if k == "reopen_task":
        return "%s is reopened (%s); uncheck it in tasks.md." % (ev["task"], ev["reason"])
    return "Nothing changed; do not touch any file for this step."


def task_text(arm, trace, feature):
    steps = "\n".join("%d. %s" % (i, describe(ev)) for i, ev in enumerate(trace, 1) if ev["kind"] not in ("noop_refresh", "resume", "compaction"))
    if arm == "new":
        how = ("Record each step with the Progress CLI exactly as .specify/extensions/progress/skills/progress/SKILL.md says. "
               "Record only facts the CLI cannot collect itself: lane assignments, blockers, decisions and notes. "
               "Task starts, completions and reopenings need no command beyond editing tasks.md checkboxes.")
    else:
        how = ("Keep specs/%s/progress/report.md up to date by hand with minimal edits. It has six sections: Summary, Lanes, Tasks, "
               "Decisions, Blockers, Events. Update every section a step affects, including the Summary counts and a one-line Events entry "
               "(keep the last 5)." % feature)
    return ("You are the orchestrator for feature %s. Apply these updates in order. %s Do nothing else: no analysis, no extra files, "
            "no summaries beyond one closing line.\n\n%s" % (feature, how, steps))


def prepare(arm, model_mod, trace, root):
    """Create the sandbox repository for one run."""
    feature = model_mod.FEATURE
    fdir = root / "specs" / feature
    fdir.mkdir(parents=True)
    state = model_mod.new_state()
    lines = ["# Tasks: %s" % feature, ""]
    lines += ["- [ ] %s %s" % (tid, t["title"]) for tid, t in state["tasks"].items()]
    (fdir / "tasks.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if arm == "md":
        (fdir / "progress").mkdir()
        (fdir / "progress" / "report.md").write_text(model_mod.render(state), encoding="utf-8")
    else:
        target = root / ".specify" / "extensions" / "progress"
        for name in ("scripts", "assets", "skills", "docs"):
            shutil.copytree(EXT / name, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.png", "token-benchmark.md"))
        skill = target / "skills" / "progress"
        (skill / "SKILL.md").write_text((skill / "SKILL.ext.md").read_text(encoding="utf-8"), encoding="utf-8")
    git = ["git", "-c", "user.email=ab@example.invalid", "-c", "user.name=ab"]
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(git + ["add", "-A"], cwd=root, check=True)
    subprocess.run(git + ["commit", "-qm", "baseline"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-qb", feature], cwd=root, check=True)
    return feature


def plan(args):
    targets = [t.split(":", 1) for t in args.targets.split(",") if t]
    runs = []
    for harness, model_id in targets:
        for pair in range(1, args.pairs + 1):
            order = ARMS if pair % 2 else ARMS[::-1]
            for arm in order:
                runs.append(dict(harness=harness, model=model_id, pair=pair, arm=arm))
    return runs


def delegate(cmd, runs_dir, node):
    env = dict(os.environ, DELEGATE_RUNS_DIR=str(runs_dir))
    return subprocess.run([node] + cmd, capture_output=True, text=True, encoding="utf-8", env=env)


def run_one(spec, args, model_mod, trace, runs_dir):
    with tempfile.TemporaryDirectory(prefix="live-ab-") as tmp:
        root = Path(tmp)
        feature = prepare(spec["arm"], model_mod, trace, root)
        text = task_text(spec["arm"], trace, feature)
        started = delegate([str(args.delegate), "start", "--harness", spec["harness"], "--model", spec["model"],
                            "--cwd", str(root), "--timeout", str(args.timeout), "--task", text], runs_dir, args.node)
        if started.returncode != 0:
            return dict(spec, status="start-failed", detail=started.stderr.strip()[:300])
        match = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]{5,}", started.stdout.strip().splitlines()[-1])
        run_id = match[-1] if match else ""
        done = delegate([str(args.delegate), "collect", run_id, "--wait", str(args.timeout), "--json"], runs_dir, args.node)
        try:
            result = json.loads(done.stdout)
        except ValueError:
            return dict(spec, run_id=run_id, status="collect-failed", detail=done.stdout[:300] + done.stderr[:300])
        return dict(spec, run_id=run_id, status=result.get("status"), status_reason=result.get("status_reason"),
                    requested_model=result.get("requested_model"), actual_model=result.get("actual_model"),
                    model_reported=result.get("model_reported"), tokens=result.get("tokens"),
                    verified=verify(spec["arm"], root, model_mod, trace))


def verify(arm, root, model_mod, trace):
    """Cheap end-state check so a cheap-but-wrong run is not counted as a win."""
    expected = sum(1 for _ in model_mod_done(model_mod, trace))
    feature = model_mod.FEATURE
    tasks = (root / "specs" / feature / "tasks.md").read_text(encoding="utf-8")
    checked = len(re.findall(r"- \[[xX]\]", tasks))
    ok = checked == expected
    if arm == "md":
        report = root / "specs" / feature / "progress" / "report.md"
        ok = ok and report.exists() and ("%d/24 tasks done" % expected) in report.read_text(encoding="utf-8")
    else:
        facts = root / "specs" / feature / "progress" / "facts.jsonl"
        ok = ok and facts.exists() and facts.stat().st_size > 0
    return dict(checked_tasks=checked, expected_tasks=expected, ok=ok)


def model_mod_done(model_mod, trace):
    state = model_mod.new_state()
    for ev in trace:
        model_mod.apply(state, ev)
    return [t for t in state["tasks"].values() if t["state"] == "done"]


def summarize(results):
    groups = {}
    for r in results:
        t = r.get("tokens") or {}
        key = (r["harness"], r["model"], r["arm"])
        g = groups.setdefault(key, dict(runs=0, ok=0, input_fresh=0, output_total=0, total=0, fidelity=set()))
        g["runs"] += 1
        g["ok"] += bool((r.get("verified") or {}).get("ok"))
        for field in ("input_fresh", "output_total", "total"):
            g[field] += t.get(field) or 0
        g["fidelity"].add(str(t.get("fidelity")))
    return groups


def write_reports(out, args, planned, results):
    out.mkdir(parents=True, exist_ok=True)
    groups = summarize(results)
    payload = dict(args={k: str(v) for k, v in vars(args).items()}, planned=planned, results=results,
                   summary=[dict(harness=k[0], model=k[1], arm=k[2], **{**v, "fidelity": sorted(v["fidelity"])}) for k, v in sorted(groups.items())])
    (out / "live-ab.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# Live A/B report", "",
             "Real harness token usage from the delegate-task driver. `fidelity` is the driver's own flag; `unavailable` means unknown, not zero.",
             "No Claude tokenizer count is claimed here.", "",
             "| Harness | Model | Arm | Runs | Verified | Input fresh | Output | Total | Fidelity |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for (h, m, a), g in sorted(groups.items()):
        lines.append("| %s | %s | %s | %d | %d | %d | %d | %d | %s |" % (h, m, a, g["runs"], g["ok"], g["input_fresh"], g["output_total"], g["total"], ", ".join(sorted(g["fidelity"]))))
    (out / "live-ab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--delegate", type=Path, default=DEFAULT_DELEGATE, help="path to delegate.mjs")
    p.add_argument("--node", default="node")
    p.add_argument("--targets", default=DEFAULT_TARGETS, help="comma list of harness:model (explicit model required)")
    p.add_argument("--pairs", type=int, default=3)
    p.add_argument("--updates", type=int, default=20, help="number of trace events per run")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--runs-dir", type=Path, default=Path(".delegate/runs"))
    p.add_argument("--out", type=Path, default=Path("live-ab-report"))
    p.add_argument("--dry-run", action="store_true", help="print the planned runs and exit without spending tokens")
    args = p.parse_args(argv)
    for t in args.targets.split(","):
        if ":" not in t:
            p.error("every target needs harness:model, got %r" % t)
    try:
        model_mod, trace = load_trace(args.updates)
    except ImportError:
        p.error("the benchmark trace (tests/bench) is only in the source checkout, not in an installed package")
    planned = plan(args)
    print("Planned %d runs (%d pairs x %d targets x 2 arms), %d trace events each." % (
        len(planned), args.pairs, len(args.targets.split(",")), len(trace)))
    for i, spec in enumerate(planned, 1):
        text = task_text(spec["arm"], trace, model_mod.FEATURE)
        print("%2d. harness=%s model=%s pair=%d arm=%s task=%d chars" % (i, spec["harness"], spec["model"], spec["pair"], spec["arm"], len(text)))
    if args.dry_run:
        print("Dry run: no sandbox created, no harness started. driver: %s (%s)" % (args.delegate, "found" if args.delegate.is_file() else "NOT FOUND"))
        return 0
    if not args.delegate.is_file():
        print("delegate.mjs not found: %s" % args.delegate, file=sys.stderr)
        return 2
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in planned:
        print("running", spec, flush=True)
        results.append(run_one(spec, args, model_mod, trace, args.runs_dir.resolve()))
        write_reports(args.out, args, planned, results)
    print("wrote", args.out / "live-ab.json", "and", args.out / "live-ab.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
