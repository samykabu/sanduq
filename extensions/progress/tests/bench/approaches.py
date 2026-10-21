"""Model-visible content for each approach, event by event.

Every approach returns, per trace event, a list of `(tag, text)` messages: the exact text that enters the
model's context. Tool calls are serialized as the JSON arguments object the agent emits; tool results are
the literal text returned. Fixed per-call framing (tool names, ids) is identical across approaches and is
not counted.
"""
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import model
from .model import FEATURE, REPORT_PATH

HERE = Path(__file__).resolve().parent
EXT = HERE.parent.parent
REPO = EXT.parent.parent
# A repository that vendors this bench in another layout (Sanduq) names its CLI line and skill file here.
NEW_CLI = os.environ.get("PROGRESS_BENCH_CLI", "python .claude/skills/progress-report/scripts/progress.py")
LEGACY_CLI = "python .specify/extensions/workflow/scripts/progress.py"
LEGACY_OUT = "specs/%s/workflow/progress" % FEATURE
SKILL_PATH = EXT / os.environ.get("PROGRESS_BENCH_SKILL", "SKILL.md")
LEGACY_PROTOCOL = REPO / "extensions" / "workflow" / "skills" / "workflow" / "references" / "execution-report.md"
LEGACY_SCRIPT = REPO / "extensions" / "workflow" / "scripts" / "progress.py"
EDIT_OK = "The file %s has been updated successfully." % REPORT_PATH


def call(**args):
    return json.dumps(args, ensure_ascii=False, separators=(",", ":"))


def bash(command):
    return call(command=command)


def quote(text):
    return '"' + text.replace('"', '\\"') + '"'


def numbered(lines, start=1):
    return "\n".join("%6d\t%s" % (i, line) for i, line in enumerate(lines, start))


# ---------------------------------------------------------------- NEW and MD-RENDER (real CLI)

NEW_SCRIPT = EXT / "scripts" / "progress.py"


def new_available():
    return NEW_SCRIPT.is_file()


def skill_text():
    return SKILL_PATH.read_text(encoding="utf-8")


def skill_load():
    return [("skill-call", call(skill=SKILL_PATH.parent.name)), ("skill", skill_text())]


def _git(args, cwd):
    subprocess.run(["git", "-c", "user.email=bench@example.invalid", "-c", "user.name=bench"] + args, cwd=cwd,
                   check=True, capture_output=True)


def _run_new(args, cwd):
    proc = subprocess.run([sys.executable, str(NEW_SCRIPT)] + args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = proc.stdout.strip() or proc.stderr.strip()
    # The bind nonce is random; pin it so token counts are reproducible.
    return proc.returncode, re.sub(r"bind=[0-9a-f]+", "bind=a1b2c3d4e5f6", out)


def _write_tasks(path, state):
    lines = ["# Tasks: %s" % FEATURE, ""]
    phase = None
    for tid, t in state["tasks"].items():
        if t["phase"] != phase:
            phase = t["phase"]
            lines += ["## Phase: " + phase, ""]
        lines.append("- [%s] %s %s" % ("X" if t["state"] == "done" else " ", tid, t["title"]))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def real_cli_run(trace):
    """Run the verbs of the trace through the real Progress CLI in a sandbox repository.

    Returns (new_setup, new_events, render_events). NEW messages are the command line the agent types and the
    CLI's own output. Events with no verb (task start, completion, reopening, no-op refresh) type nothing; the
    sandbox only mirrors the checkbox edit the agent makes in tasks.md anyway, then refreshes as a hook would.
    MD-RENDER reads the real `export --format md` file at re-orientation events.
    """
    state = model.new_state()
    new_events, render_events = [], []
    with tempfile.TemporaryDirectory(prefix="progress-bench-") as tmp:
        (Path(tmp) / ".specify").mkdir()
        feature = Path(tmp) / "specs" / FEATURE
        feature.mkdir(parents=True)
        _write_tasks(feature / "tasks.md", state)
        _git(["init", "-q"], tmp)
        _git(["add", "-A"], tmp)
        _git(["commit", "-qm", "init"], tmp)
        _git(["checkout", "-qb", FEATURE], tmp)
        code, init_out = _run_new(["init"], tmp)
        setup = skill_load() + [("call", bash(NEW_CLI + " init")), ("result", init_out)]
        for ev in trace:
            k = ev["kind"]
            args = None
            if k == "assign_lane":
                args = ["lane", ev["lane"], "--tasks", model.task_range(ev["tasks"]), "--owner", ev["owner"], "--label", ev["label"],
                        "--harness", ev["harness"], "--model", ev["model"], "--effort", ev["effort"]]
            elif k == "fail_retry":
                args = ["note", ev["note"], "--target", ev["task"]]
            elif k == "block":
                args = ["block", ev["task"], "--by", ev["by_arg"]]
            elif k == "unblock":
                args = ["unblock", ev["blocker"]]
            elif k == "decision_ask":
                args = ["decide", "ask", ev["question"], "--options", ",".join(ev["options"])]
            elif k == "decision_made":
                args = ["decide", "made", ev["id"], ev["selected"], "--by", ev["by"], "--evidence", ev["evidence"]]
            elif k in ("resume", "compaction"):
                args = ["status"]
            msgs = []
            if args:
                code, out = _run_new(args, tmp)
                shown = " ".join(_shell_quote(a) for a in args)
                msgs = (skill_load() if k in ("resume", "compaction") else []) + [
                    ("call", bash(NEW_CLI + " " + shown)), ("result", out)]
            model.apply(state, ev)
            _write_tasks(feature / "tasks.md", state)
            if not args:
                _run_new(["refresh"], tmp)  # what the hooks do silently
            new_events.append(dict(kind=k, messages=msgs, exit_code=(code if args else 0)))
            rmsgs = []
            if k in ("resume", "compaction"):
                _, text = _run_new(["export", "--format", "md"], tmp)
                rmsgs = [("call", call(file_path=REPORT_PATH)), ("result", numbered(text.split("\n")))]
            render_events.append(dict(kind=k, messages=rmsgs))
    return setup, new_events, render_events


def _shell_quote(arg):
    return quote(arg) if (" " in arg or not arg) else arg


# ---------------------------------------------------------------- MD-EDIT


def md_setup():
    state = model.new_state()
    return [("call", call(file_path=REPORT_PATH, content=model.render(state))),
            ("result", "File created successfully at: " + REPORT_PATH)]


def _hunks(old, new):
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    hunks = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            anchor = old[i1 - 1] if i1 else old[0]
            inserted = "\n".join(new[j1:j2])
            hunks.append((anchor, anchor + "\n" + inserted if i1 else inserted + "\n" + anchor))
        elif tag == "delete":
            hunks.append(("\n".join(old[i1:i2]) + "\n", ""))
        else:
            hunks.append(("\n".join(old[i1:i2]), "\n".join(new[j1:j2])))
    return hunks


def md_events(trace, measure, reads_required=True):
    """A competent hand-maintained report: read what must be edited, then the minimal Edit calls.

    The agent reads either each affected section or the whole file, whichever is cheaper (`measure` sizes
    a candidate), then issues one Edit per changed hunk. Events that change nothing cost nothing.

    With `reads_required=False` (the LEAN sensitivity variant) the agent is assumed to remember the whole file
    from setup and issues only the Edit calls; re-orientation events still re-read the whole file.
    """
    state = model.new_state()
    result = []
    for ev in trace:
        k = ev["kind"]
        before = model.sections(state)
        # Header and blank lines occupy fixed rows; section line numbers follow the rendered file.
        file_lines = model.render(state).rstrip("\n").split("\n")
        if k in ("resume", "compaction"):
            msgs = [("call", call(file_path=REPORT_PATH)), ("result", numbered(file_lines))]
            model.apply(state, ev)
            result.append(dict(kind=k, messages=msgs))
            continue
        model.apply(state, ev)
        after = model.sections(state)
        changed = [(b, a) for b, a in zip(before, after) if b[1] != a[1]]
        if not changed:
            result.append(dict(kind=k, messages=[]))
            continue
        # Line offset of each section body in the pre-edit file.
        offsets, row = {}, 3
        for name, lines in before:
            offsets[name] = row + 2  # row is the 1-based heading line; a blank line follows it
            row += len(lines) + 3
        per_section = []
        for (name, old), (_, _new) in changed:
            start = offsets[name]
            per_section.append(("call", call(file_path=REPORT_PATH, offset=start, limit=len(old))))
            per_section.append(("result", numbered(old, start)))
        whole = [("call", call(file_path=REPORT_PATH)), ("result", numbered(file_lines))]
        size = lambda msgs: sum(measure(text) for _, text in msgs)  # noqa: E731
        reads = whole if size(whole) < size(per_section) else per_section
        msgs = list(reads) if reads_required else []
        for (_name, old), (_n, new) in changed:
            for old_string, new_string in _hunks(old, new):
                msgs.append(("call", call(file_path=REPORT_PATH, old_string=old_string, new_string=new_string)))
                msgs.append(("result", EDIT_OK))
        result.append(dict(kind=k, messages=msgs))
    return result


# ---------------------------------------------------------------- LEGACY


def legacy_available():
    return LEGACY_SCRIPT.is_file() and LEGACY_PROTOCOL.is_file()


def _legacy_commands(ev, state):
    """Command argument lists (after the script name) for one event, per execution-report.md."""
    k = ev["kind"]
    owner = lambda lane: state["lanes"][lane]["owner"]  # noqa: E731

    def task(tid, status, lane, note):
        return ["task", "--output", LEGACY_OUT, "--id", tid, "--status", status, "--agent", owner(lane), "--note", note, "--summary"]

    def event(message):
        return ["event", "--output", LEGACY_OUT, "--message", message, "--summary"]

    if k == "assign_lane":
        return [event("%s %s assigned to %s (%s/%s/%s): %s" % (
            ev["lane"], ev["label"], ev["owner"], ev["harness"], ev["model"], ev["effort"], model.task_range(ev["tasks"])))]
    if k == "start_task":
        return [task(ev["task"], "running", ev["lane"], ev["note"])]
    if k == "complete_task":
        return [task(ev["task"], "done", ev["lane"], ev["note"])]
    if k == "fail_retry":
        return [task(ev["task"], "blocked", ev["lane"], ev["note"]),
                task(ev["task"], "running", ev["lane"], "Retrying %s in a fresh attempt after the recorded failure" % ev["task"])]
    if k == "block":
        return [task(ev["task"], "blocked", ev["lane"], ev["note"])]
    if k == "unblock":
        return [task(ev["task"], "running", ev["lane"], ev["note"])]
    if k == "decision_ask":
        return [event("Decision %s needed: %s Options: %s" % (ev["id"], ev["question"], ", ".join(ev["options"])))]
    if k == "decision_made":
        return [event("Decision %s made: %s (decided by %s; evidence: %s)" % (ev["id"], ev["selected"], ev["by"], ev["evidence"]))]
    if k == "reopen_task":
        return [task(ev["task"], "running", ev["lane"], ev["note"])]
    if k in ("resume", "compaction"):
        return [["sync", "--output", LEGACY_OUT, "--summary"]]
    return []


def _tasks_md():
    lines = ["# Tasks: %s" % FEATURE, ""]
    phase = None
    for tid, ph, title in model.TASKS:
        if ph != phase:
            phase = ph
            lines += ["## Phase: " + ph, ""]
        lines.append("- [ ] %s %s" % (tid, title))
    return "\n".join(lines) + "\n"


def _run_legacy(args, cwd):
    proc = subprocess.run([sys.executable, str(LEGACY_SCRIPT)] + args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return proc.stdout.strip() or proc.stderr.strip()


def legacy_setup_and_events(trace):
    """Run the real legacy progress.py in a sandbox so every output line is the script's own."""
    protocol = LEGACY_PROTOCOL.read_text(encoding="utf-8")
    state = model.new_state()
    with tempfile.TemporaryDirectory(prefix="legacy-bench-") as tmp:
        feature = Path(tmp) / "specs" / FEATURE
        feature.mkdir(parents=True)
        (feature / "tasks.md").write_text(_tasks_md(), encoding="utf-8")
        init = ["init", "--output", LEGACY_OUT, "--tasks", "specs/%s/tasks.md" % FEATURE, "--summary"]
        init_out = _run_legacy(init, tmp)
        setup = [("protocol-call", call(file_path=str(LEGACY_PROTOCOL.relative_to(REPO)))), ("protocol", protocol),
                 ("call", bash(LEGACY_CLI + " " + " ".join(_shell(a) for a in init))), ("result", init_out)]
        events = []
        for ev in trace:
            msgs = []
            if ev["kind"] in ("resume", "compaction"):
                msgs += [("protocol-call", call(file_path=str(LEGACY_PROTOCOL.relative_to(REPO)))), ("protocol", protocol)]
            if ev["kind"] == "assign_lane":
                model.apply(state, ev)  # lane owners are needed by later task commands
            for args in _legacy_commands(ev, state):
                out = _run_legacy(args, tmp)
                msgs += [("call", bash(LEGACY_CLI + " " + " ".join(_shell(a) for a in args))), ("result", out)]
            if ev["kind"] != "assign_lane":
                model.apply(state, ev)
            events.append(dict(kind=ev["kind"], messages=msgs))
    return setup, events


def _shell(arg):
    return quote(arg) if (" " in arg or not arg) else arg
