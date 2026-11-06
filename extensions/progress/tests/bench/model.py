"""A small in-memory feature state and the deterministic Markdown report built from it.

The same renderer produces the document a hand-maintained report would contain (MD-EDIT) and the
deterministic export (MD-RENDER), so the two approaches are compared on the same content.
"""
import copy

FEATURE = "624-uc-1b-02b-add-dependencies-when-creating-a-task"
REPORT_PATH = "specs/%s/progress/report.md" % FEATURE
MAX_EVENTS = 5

TASKS = [
    ("T001", "Setup", "Add task dependency table migration"),
    ("T002", "Setup", "Add TaskDependency entity and EF configuration"),
    ("T003", "Setup", "Add dependency cycle validator"),
    ("T004", "Setup", "Add dependency DTOs and request validation"),
    ("T005", "API", "Accept dependsOn on POST /tasks"),
    ("T006", "API", "Persist dependencies in the create-task handler"),
    ("T007", "API", "Return dependencies from GET /tasks/{id}"),
    ("T008", "API", "Reject self and cyclic dependencies with 422"),
    ("T009", "UI", "Add dependency picker to the create-task form"),
    ("T010", "UI", "Show dependency chips on the task card"),
    ("T011", "UI", "Validate dependency selection in the form"),
    ("T012", "UI", "Add Arabic labels for dependency fields"),
    ("T013", "Tests", "Unit tests for the cycle validator"),
    ("T014", "Tests", "Integration tests for create-task with dependencies"),
    ("T015", "Tests", "Playwright scenario for creating a dependent task"),
    ("T016", "Tests", "Playwright scenario for a rejected cycle"),
    ("T017", "Docs", "Update the API contract"),
    ("T018", "Docs", "Update the English user manual page"),
    ("T019", "Docs", "Update the Arabic user manual page"),
    ("T020", "Docs", "Capture dependency screenshots"),
    ("T021", "Polish", "Add structured logging for rejected dependencies"),
    ("T022", "Polish", "Review accessibility of the picker"),
    ("T023", "Polish", "Run the quickstart validation"),
    ("T024", "Polish", "Final cleanup and changelog entry"),
]


def new_state():
    return {
        "tasks": {tid: {"title": title, "phase": phase, "state": "pending", "lane": ""} for tid, phase, title in TASKS},
        "lanes": {},
        "blockers": {},
        "decisions": {},
        "events": [],
        "clock": 0,
    }


def stamp(state):
    state["clock"] += 1
    minutes = 540 + state["clock"] * 3
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def task_range(ids):
    """T001-T004 for a contiguous run longer than two, otherwise a comma list."""
    nums = [int(t[1:]) for t in ids]
    if nums == list(range(nums[0], nums[-1] + 1)) and len(nums) > 2:
        return "%s-%s" % (ids[0], ids[-1])
    return ",".join(ids)


def summary(state):
    tasks = state["tasks"].values()
    done = sum(t["state"] == "done" for t in tasks)
    active = sum(t["state"] == "active" for t in tasks)
    blocked = sum(t["state"] == "blocked" for t in tasks)
    pending = sum(d["status"] == "pending" for d in state["decisions"].values())
    return done, active, blocked, pending, len(state["tasks"])


def sections(state):
    """Return the six report sections as an ordered list of (name, [lines])."""
    done, active, blocked, pending, total = summary(state)
    out = []
    out.append(("Summary", ["%d/%d tasks done, %d active, %d blocked, %d decisions pending" % (done, total, active, blocked, pending)]))
    lanes = ["| Lane | Owner | Requested model | Status | Done |", "| --- | --- | --- | --- | ---: |"]
    for lid, lane in state["lanes"].items():
        mine = lane["tasks"]
        n_done = sum(state["tasks"][t]["state"] == "done" for t in mine)
        lanes.append("| %s %s | %s | %s | %s | %d/%d |" % (lid, lane["label"], lane["owner"], lane["model"], lane["status"], n_done, len(mine)))
    out.append(("Lanes", lanes))
    board = ["| Task | Title | State | Lane |", "| --- | --- | --- | --- |"]
    for tid, t in state["tasks"].items():
        board.append("| %s | %s | %s | %s |" % (tid, t["title"], t["state"], t["lane"] or "-"))
    out.append(("Tasks", board))
    decisions = []
    for did, d in state["decisions"].items():
        if d["status"] == "pending":
            decisions.append("- %s pending: %s (%s)" % (did, d["question"], ", ".join(d["options"])))
        else:
            decisions.append("- %s made: %s -> %s (%s, %s)" % (did, d["question"], d["selected"], d["by"], d["evidence"]))
    out.append(("Decisions", decisions or ["None."]))
    blockers = ["- %s %s %s by %s" % (bid, b["state"], b["target"], b["by"]) for bid, b in state["blockers"].items()]
    out.append(("Blockers", blockers or ["None."]))
    out.append(("Events", list(state["events"]) or ["None."]))
    return out


def render(state):
    parts = ["# Progress: %s" % FEATURE, ""]
    for name, lines in sections(state):
        parts += ["## " + name, ""] + lines + [""]
    return "\n".join(parts).rstrip("\n") + "\n"


def log(state, text):
    state["events"].append("%s %s" % (stamp(state), text))
    del state["events"][:-MAX_EVENTS]


def apply(state, ev):
    """Apply one trace event to the state, the way a careful hand-maintained report would record it."""
    k = ev["kind"]
    t = state["tasks"]
    if k == "assign_lane":
        for tid in ev["tasks"]:
            t[tid]["lane"] = ev["lane"]
        state["lanes"][ev["lane"]] = {"label": ev["label"], "owner": ev["owner"], "tasks": list(ev["tasks"]),
                                      "model": "%s/%s/%s" % (ev["harness"], ev["model"], ev["effort"]), "status": "waiting"}
        log(state, "%s assigned to %s: %s" % (ev["lane"], ev["owner"], task_range(ev["tasks"])))
    elif k == "start_task":
        t[ev["task"]]["state"] = "active"
        state["lanes"][ev["lane"]]["status"] = "active"
        log(state, "%s started %s" % (ev["lane"], ev["task"]))
    elif k == "complete_task":
        t[ev["task"]]["state"] = "done"
        lane = state["lanes"][ev["lane"]]
        lane["status"] = "done" if all(t[x]["state"] == "done" for x in lane["tasks"]) else "waiting"
        log(state, "%s finished %s" % (ev["lane"], ev["task"]))
    elif k == "fail_retry":
        log(state, ev["note"])
    elif k == "block":
        t[ev["task"]]["state"] = "blocked"
        state["blockers"][ev["blocker"]] = {"target": ev["task"], "by": ev["by"], "state": "open"}
        state["lanes"][ev["lane"]]["status"] = "blocked"
        log(state, "%s blocked by %s (%s)" % (ev["task"], ev["by"], ev["blocker"]))
    elif k == "unblock":
        b = state["blockers"].pop(ev["blocker"])
        t[b["target"]]["state"] = "active"
        state["lanes"][ev["lane"]]["status"] = "active"
        log(state, "%s unblocked (%s resolved)" % (b["target"], ev["blocker"]))
    elif k == "decision_ask":
        state["decisions"][ev["id"]] = {"question": ev["question"], "options": ev["options"], "status": "pending"}
        log(state, "%s asked" % ev["id"])
    elif k == "decision_made":
        d = state["decisions"][ev["id"]]
        d.update(status="made", selected=ev["selected"], by=ev["by"], evidence=ev["evidence"])
        log(state, "%s decided: %s" % (ev["id"], ev["selected"]))
    elif k == "reopen_task":
        t[ev["task"]]["state"] = "active"
        state["lanes"][ev["lane"]]["status"] = "active"
        log(state, "%s reopened: %s" % (ev["task"], ev["reason"]))
    elif k in ("noop_refresh", "resume", "compaction"):
        pass
    else:
        raise ValueError("unknown event kind " + k)


def snapshot(state):
    return copy.deepcopy(state)
