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

DELEGATE_CANDIDATES = (".agents/skills/delegate-task/delegate.mjs", ".claude/skills/delegate-task/delegate.mjs")


def find_delegate(cwd=None):
    """env DELEGATE_SCRIPT, else the first delegate.mjs under the cwd; None when neither exists."""
    env = os.environ.get("DELEGATE_SCRIPT")
    if env:
        return Path(env)
    base = Path(cwd) if cwd else Path.cwd()
    for rel in DELEGATE_CANDIDATES:
        if (base / rel).is_file():
            return base / rel
    return None


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
        how = ("Record each step with the Progress CLI exactly as .claude/skills/progress-report/SKILL.md says. "
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
        target = root / ".claude" / "skills" / "progress-report"
        for name in ("scripts", "assets", "references", "docs"):
            shutil.copytree(EXT / name, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.png", "token-benchmark.md"))
        shutil.copyfile(EXT / "SKILL.md", target / "SKILL.md")
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


def model_mod_done(model_mod, trace):
    state = model_mod.new_state()
    for ev in trace:
        model_mod.apply(state, ev)
    return [t for t in state["tasks"].values() if t["state"] == "done"]


def expected(model_mod, trace):
    """The semantic end state both arms must reach: lanes, open blockers, decisions and failed attempts."""
    state = model_mod.new_state()
    for ev in trace:
        model_mod.apply(state, ev)
    return dict(
        done=sum(1 for t in state["tasks"].values() if t["state"] == "done"),
        task_states={tid: t["state"] for tid, t in state["tasks"].items()},
        lanes={lid: dict(owner=lane["owner"], tasks=sorted(lane["tasks"])) for lid, lane in state["lanes"].items()},
        blockers=sorted((b["target"], str(b["by"])) for b in state["blockers"].values()),
        blocker_ids=sorted(state["blockers"]),
        pending=sorted(d["question"] for d in state["decisions"].values() if d["status"] == "pending"),
        made={d["question"]: d["selected"] for d in state["decisions"].values() if d["status"] == "made"},
        decision_ids={did: d["status"] for did, d in state["decisions"].items()},
        retries=sorted({ev["task"] for ev in trace if ev["kind"] == "fail_retry"}),
        recent_events=list(state["events"]),
    )


def check_new(data, want):
    """Problems found comparing a Progress `status --json` projection with the expected end state."""
    if not isinstance(data, dict) or data.get("schema") != "sanduq.progress.v2":
        return ["projection unavailable: progress status --json did not return sanduq.progress.v2"]
    problems = []
    held, groups_by_owner = {}, {}
    for lane in data.get("lanes") or []:
        groups = lane.get("tasks") or {}
        ids = list(groups.get("active") or []) + list(groups.get("waiting") or []) + list(groups.get("done") or [])
        ids += [b.get("task") for b in groups.get("blocked") or []]
        held.setdefault(lane.get("owner"), set()).update(ids)
        merged = groups_by_owner.setdefault(lane.get("owner"), {"active": set(), "waiting": set(), "blocked": set(), "done": set()})
        merged["active"].update(groups.get("active") or [])
        merged["waiting"].update(groups.get("waiting") or [])
        merged["blocked"].update(b.get("task") for b in groups.get("blocked") or [])
        merged["done"].update(groups.get("done") or [])
    states = want["task_states"]
    for lid, lane in want["lanes"].items():
        if held.get(lane["owner"]) != set(lane["tasks"]):
            problems.append("lane %s (%s): tasks %s differ from expected %s" % (
                lid, lane["owner"], sorted(held.get(lane["owner"], [])), lane["tasks"]))
        got_groups = groups_by_owner.get(lane["owner"], {"active": set(), "waiting": set(), "blocked": set(), "done": set()})
        expect = {"done": {t for t in lane["tasks"] if states.get(t) == "done"},
                  "blocked": {t for t in lane["tasks"] if states.get(t) == "blocked"},
                  "active": {t for t in lane["tasks"] if states.get(t) == "active"}}
        expect["waiting"] = set(lane["tasks"]) - expect["done"] - expect["blocked"] - expect["active"]
        for group in ("done", "blocked", "active", "waiting"):
            if got_groups[group] != expect[group]:
                problems.append("lane %s (%s): %s tasks %s differ from expected %s" % (
                    lid, lane["owner"], group, sorted(got_groups[group]), sorted(expect[group])))
    got = sorted((b.get("target"), str((b.get("by") or {}).get("ref"))) for b in data.get("blockers") or [])
    wanted = sorted((t, by[4:].strip('"') if by.startswith("ext:") else by) for t, by in want["blockers"])
    if got != wanted:
        problems.append("blockers %s differ from expected %s" % (got, wanted))
    decisions = data.get("decisions") or {}
    pending = sorted(d.get("question") for d in decisions.get("pending") or [])
    made = {d.get("question"): d.get("selected") for d in decisions.get("made") or []}
    if pending != want["pending"]:
        problems.append("pending decisions %s differ from expected %s" % (pending, want["pending"]))
    if made != want["made"]:
        problems.append("made decisions %s differ from expected %s" % (made, want["made"]))
    texts = " ".join(str(e.get("text")) for e in data.get("events") or [])
    for task in want["retries"]:
        if task not in texts or "fail" not in texts:
            problems.append("attempt: no recorded failed attempt for %s" % task)
    projected = data.get("tasks") or {}
    for tid, state in states.items():
        task = projected.get(tid)
        if not isinstance(task, dict):
            problems.append("task %s is missing from the projection" % tid)
        elif bool(task.get("done")) != (state == "done"):
            problems.append("task %s is %s in the projection, expected %s" % (
                tid, "done" if task.get("done") else "not done", state))
    return problems


def md_sections(text):
    found, name = {}, None
    for line in text.splitlines():
        m = re.match(r"##\s+(\S.*?)\s*$", line)
        if m:
            name = m.group(1)
            found[name] = []
        elif name:
            found[name].append(line)
    return found


def table_rows(lines):
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines if l.strip().startswith("|")]
    return rows[2:]  # header and separator


def check_md(text, want):
    """Problems found parsing the hand-edited Markdown report's six sections against the expected end state."""
    sec = md_sections(text)
    problems = ["missing section %s" % n for n in ("Summary", "Lanes", "Tasks", "Decisions", "Blockers", "Events") if n not in sec]
    lanes = table_rows(sec.get("Lanes", []))
    for lid, lane in want["lanes"].items():
        row = next((r for r in lanes if r and r[0].split()[:1] == [lid]), None)
        if row is None or len(row) < 5 or row[1] != lane["owner"] or not row[-1].endswith("/%d" % len(lane["tasks"])):
            problems.append("lane %s (%s) missing or wrong in the Lanes table" % (lid, lane["owner"]))
    tasks = {r[0]: r for r in table_rows(sec.get("Tasks", [])) if len(r) >= 3}
    for tid, state in want["task_states"].items():
        if tasks.get(tid, [None] * 3)[2] != state:
            problems.append("task %s is not %s in the Tasks table" % (tid, state))
    block = sec.get("Blockers", [])
    ids = sorted(set(re.findall(r"\bB\d+\b", "\n".join(block))))
    if ids != want["blocker_ids"] or any("resolved" in l for l in block):
        problems.append("blockers %s differ from expected %s" % (ids, want["blocker_ids"]))
    dec = "\n".join(sec.get("Decisions", []))
    for did, status in want["decision_ids"].items():
        m = re.search(r"\b%s\s+(pending|made)\b" % did, dec)
        if not m or m.group(1) != status:
            problems.append("decision %s should be %s" % (did, status))
    for question, selected in want["made"].items():
        if not re.search(r"->\s*%s\b" % re.escape(str(selected)), dec):
            problems.append("decision %r lacks its selection %s" % (question, selected))
    events = "\n".join(sec.get("Events", []))
    for line in want["recent_events"]:
        task = re.search(r"\bT\d{3}\b", line)
        if "fail" in line and task and task.group(0) not in events:
            problems.append("attempt: failed attempt for %s missing from Events" % task.group(0))
    return problems


def status_new(root, feature):
    """`progress status --json` of the NEW arm's sandbox, or None when the CLI answers nothing usable."""
    script = root / ".claude" / "skills" / "progress-report" / "scripts" / "progress.py"
    try:
        done = subprocess.run([sys.executable, str(script), "--root", str(root), "status", "--json", "--schema", "v2", "--feature", feature],
                              capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=root)
        return json.loads(done.stdout) if done.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def verify(arm, root, model_mod, trace):
    """End-state check: checked tasks plus semantic equivalence of the arm's report, so a cheap-but-wrong
    run is not counted as a win. `ok` is False on any problem; `problems` says why."""
    want = expected(model_mod, trace)
    feature = model_mod.FEATURE
    tasks = (root / "specs" / feature / "tasks.md").read_text(encoding="utf-8")
    checked = len(re.findall(r"- \[[xX]\]", tasks))
    problems = [] if checked == want["done"] else ["%d tasks checked, expected %d" % (checked, want["done"])]
    if arm == "md":
        report = root / "specs" / feature / "progress" / "report.md"
        problems += check_md(report.read_text(encoding="utf-8"), want) if report.exists() else ["report.md missing"]
    else:
        problems += check_new(status_new(root, feature), want)
    return dict(checked_tasks=checked, expected_tasks=want["done"], ok=not problems, problems=problems)


FIELDS = ("input_fresh", "output_total", "total")


def summarize(results):
    """Per (harness, model, arm): usage is summed over measured, successful, equivalent runs only. Unknown usage
    stays null (never zero); failed and non-equivalent runs are counted apart, not folded into the cost."""
    groups = {}
    for r in results:
        key = (r["harness"], r["model"], r["arm"])
        g = groups.setdefault(key, dict(runs=0, ok=0, measured=0, unknown=0, failed=0, invalid=0,
                                        input_fresh=None, output_total=None, total=None))
        g["runs"] += 1
        tokens = r.get("tokens") or {}
        total = tokens.get("total")
        exact = tokens.get("fidelity") == "exact" and isinstance(total, int) and not isinstance(total, bool)
        valid = bool((r.get("verified") or {}).get("ok"))
        g["ok"] += valid
        if r.get("status") != "successful":
            g["failed"] += 1
        elif not valid:
            g["invalid"] += 1
        elif not exact:
            g["unknown"] += 1
        else:
            g["measured"] += 1
            for field in FIELDS:
                value = tokens.get(field)
                if isinstance(value, int) and not isinstance(value, bool):
                    g[field] = (g[field] or 0) + value
    return groups


def write_reports(out, args, planned, results):
    out.mkdir(parents=True, exist_ok=True)
    groups = summarize(results)
    payload = dict(args={k: str(v) for k, v in vars(args).items()}, planned=planned, results=results,
                   summary=[dict(harness=k[0], model=k[1], arm=k[2], **v) for k, v in sorted(groups.items())])
    (out / "live-ab.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# Live A/B report", "",
             "Real harness token usage from the delegate-task driver. `fidelity` is the driver's own flag; `unavailable` means unknown, not zero.",
             "No Claude tokenizer count is claimed here.", "",
             "Cost columns sum only measured, successful, equivalent runs; `unknown` appears when no run was measured. Failed and invalid runs are counted apart, never summed as zero.", "",
             "| Harness | Model | Arm | Runs | Measured | Unknown usage | Failed | Invalid | Input fresh | Output | Total |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    def num(v):
        return "unknown" if v is None else str(v)

    for (h, m, a), g in sorted(groups.items()):
        lines.append("| %s | %s | %s | %d | %d | %d | %d | %d | %s | %s | %s |" % (
            h, m, a, g["runs"], g["measured"], g["unknown"], g["failed"], g["invalid"],
            num(g["input_fresh"]), num(g["output_total"]), num(g["total"])))
    (out / "live-ab.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--delegate", type=Path, default=None,
                   help="path to delegate.mjs (default: env DELEGATE_SCRIPT, else .agents/ or .claude/skills/delegate-task/delegate.mjs under the cwd)")
    p.add_argument("--node", default="node")
    p.add_argument("--targets", default=DEFAULT_TARGETS, help="comma list of harness:model (explicit model required)")
    p.add_argument("--pairs", type=int, default=3)
    p.add_argument("--updates", type=int, default=20, help="number of trace events per run")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--runs-dir", type=Path, default=Path(".delegate/runs"))
    p.add_argument("--out", type=Path, default=Path("live-ab-report"))
    p.add_argument("--dry-run", action="store_true", help="print the planned runs and exit without spending tokens")
    args = p.parse_args(argv)
    if args.delegate is None:
        args.delegate = find_delegate()
        if args.delegate is None:
            p.error("no delegate-task driver found: pass --delegate PATH, set DELEGATE_SCRIPT, or run from a "
                    "project with .agents/skills/delegate-task/delegate.mjs or .claude/skills/delegate-task/delegate.mjs")
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
