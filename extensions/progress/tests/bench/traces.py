"""A scripted, 624-like feature trace.

Each event carries the facts every approach needs. Nothing here is tuned per approach: an event is what
happened, and each approach decides what it must write to record it. `note` is the prose the legacy
protocol requires with every task update.
"""
from .model import FEATURE

LANES = {
    "L1": dict(label="Data layer", owner="agent-a", harness="codex", model="gpt-6-sol", effort="high",
               tasks=["T001", "T002", "T003", "T004"]),
    "L2": dict(label="API endpoints", owner="agent-b", harness="claude", model="claude-sonnet-5-5", effort="medium",
               tasks=["T005", "T006", "T007", "T008"]),
    "L3": dict(label="Create-task form", owner="agent-c", harness="codex", model="gpt-6-sol", effort="medium",
               tasks=["T009", "T010", "T011", "T012"]),
    "L4": dict(label="Test suites", owner="agent-d", harness="claude", model="claude-opus-5-5", effort="high",
               tasks=["T013", "T014", "T015", "T016"]),
}

# Classes in display order; the first group is recorded by a verb in the NEW approach, the second is automatic.
CLASSES = [
    "assign_lane", "start_task", "complete_task", "fail_retry", "block", "unblock",
    "decision_ask", "decision_made", "reopen_task", "noop_refresh", "resume", "compaction",
]
AUTOMATIC = ("start_task", "complete_task", "reopen_task", "noop_refresh")


def _assign(lane):
    return dict(kind="assign_lane", lane=lane, **{k: v for k, v in LANES[lane].items()})


def _start(task, lane, note):
    return dict(kind="start_task", task=task, lane=lane, note=note)


def _done(task, lane, note):
    return dict(kind="complete_task", task=task, lane=lane, note=note)


def build():
    ev = []
    ev += [_assign("L1"), _assign("L2"), _assign("L3")]
    ev += [
        _start("T001", "L1", "Own db/migrations/0042_task_dependency.sql; no dependencies"),
        _start("T005", "L2", "Own src/Api/Tasks/CreateTaskRequest.cs; depends on T004 contract only"),
        _start("T009", "L3", "Own web/src/tasks/CreateTaskForm.tsx; mock the dependency lookup until T007"),
        _done("T001", "L1", "Migration applies and rolls back on a clean database; evidence: evidence/T001.txt"),
        _start("T002", "L1", "Own src/Domain/TaskDependency.cs and its EF configuration"),
        dict(kind="noop_refresh"),
        _done("T005", "L2", "Request validation passes the unit checks; evidence: evidence/T005.txt"),
        _start("T006", "L2", "Own src/Api/Tasks/CreateTaskHandler.cs; depends on T002 entity"),
        _done("T009", "L3", "Picker renders with mock data and keyboard navigation; evidence: evidence/T009.txt"),
        _start("T010", "L3", "Own web/src/tasks/TaskCard.tsx dependency chips"),
        dict(kind="fail_retry", task="T006", lane="L2",
             note="T006 attempt 1 failed: migration lock timeout in the test database; retrying with a fresh container"),
        dict(kind="noop_refresh"),
        _done("T002", "L1", "Entity and EF configuration compile and map; evidence: evidence/T002.txt"),
        _start("T003", "L1", "Own src/Domain/DependencyCycleValidator.cs"),
        dict(kind="decision_ask", id="D1", question="Should a dependency on a closed task be allowed?",
             options=["allow", "reject"]),
        _done("T006", "L2", "Handler persists dependencies on retry; evidence: evidence/T006.txt"),
        _start("T007", "L2", "Own src/Api/Tasks/GetTaskHandler.cs; needs the cycle validator for read-back checks"),
        dict(kind="block", task="T007", lane="L2", by="T003", by_arg="T003", blocker="B1",
             note="T007 cannot verify read-back ordering until the T003 cycle validator lands"),
        dict(kind="noop_refresh"),
        _done("T003", "L1", "Validator rejects self and transitive cycles; evidence: evidence/T003.txt"),
        dict(kind="unblock", blocker="B1", task="T007", lane="L2", note="T007 unblocked: T003 validator merged to the feature branch"),
        dict(kind="decision_made", id="D1", selected="reject", by="user", evidence="chat"),
        dict(kind="noop_refresh"),
        dict(kind="resume"),
        _done("T007", "L2", "GET returns dependency ids in stable order; evidence: evidence/T007.txt"),
        _start("T008", "L2", "Own src/Api/Tasks/DependencyErrors.cs; 422 body per the contract"),
        _done("T008", "L2", "422 returned for self and cyclic dependencies; evidence: evidence/T008.txt"),
        _start("T004", "L1", "Own src/Api/Tasks/DependencyDtos.cs"),
        _done("T004", "L1", "DTOs validated by the request tests; evidence: evidence/T004.txt"),
        dict(kind="reopen_task", task="T002", lane="L1",
             reason="review found a missing index", note="T002 reopened: review found a missing index on dependency_id"),
        _done("T002", "L1", "Index added, migration regenerated; evidence: evidence/T002.txt"),
        dict(kind="compaction"),
        _done("T010", "L3", "Chips render and wrap at narrow widths; evidence: evidence/T010.txt"),
        _start("T011", "L3", "Own web/src/tasks/dependencyValidation.ts"),
        _done("T011", "L3", "Selection validation shows inline errors; evidence: evidence/T011.txt"),
        _start("T012", "L3", "Own web/src/i18n/ar/tasks.json labels"),
        _done("T012", "L3", "Arabic labels reviewed against the glossary; evidence: evidence/T012.txt"),
        _assign("L4"),
        _start("T013", "L4", "Own tests/unit/DependencyCycleValidatorTests.cs"),
        _done("T013", "L4", "14 cases pass including the diamond graph; evidence: evidence/T013.txt"),
        _start("T014", "L4", "Own tests/integration/CreateTaskDependencyTests.cs"),
        dict(kind="block", task="T014", lane="L4", by='staging database unavailable', by_arg='ext:"staging database unavailable"',
             blocker="B2", note="T014 waits on the staging database; infrastructure ticket opened"),
        dict(kind="noop_refresh"),
        dict(kind="unblock", blocker="B2", task="T014", lane="L4", note="T014 unblocked: staging database restored"),
        _done("T014", "L4", "Integration tests pass against staging; evidence: evidence/T014.txt"),
        dict(kind="decision_ask", id="D2", question="Is a maximum dependency depth of 10 acceptable?",
             options=["10", "25", "unlimited"]),
        dict(kind="decision_made", id="D2", selected="10", by="assumption", evidence="no limit in the spec; 10 is conservative"),
        dict(kind="noop_refresh"),
        _start("T015", "L4", "Own tests/e2e/create-dependent-task.spec.ts"),
        dict(kind="fail_retry", task="T015", lane="L4",
             note="T015 attempt 1 failed: picker locator changed after the T010 chips; retrying with the role locator"),
        _done("T015", "L4", "Scenario passes with the role locator; evidence: evidence/T015.txt"),
        dict(kind="noop_refresh"),
    ]
    return ev


FEATURE_DIR = "specs/" + FEATURE
