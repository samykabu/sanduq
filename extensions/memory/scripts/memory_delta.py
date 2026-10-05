"""Candidate v2: an archive run's delta against format-2 memory, materialized and validated as a whole result.

A candidate names only what changes (additions, updates, removals, provenance, tombstones, taxonomy changes and
grouped coverage). `validate` applies it to a temporary copy of `specs/memory`, regenerates the views, checks the
whole result and returns the exact outputs map. The real tree is never touched.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import memory_store as ms
from git_state import ArchiveError, digest
from memory import ID

SCHEMA = 2
ENTRY_KEYS = {"id", "domain", "kind", "title", "text", "relations", "selectors"}
ACTIONS = ("retained", "merged", "superseded", "omitted")


def empty_candidate(base_root: str, checkpoint: str) -> dict:
    return {"schema_version": SCHEMA, "base_memory_root": base_root, "checkpoint": checkpoint,
            "additions": [], "updates": [], "removals": [], "provenance": [], "tombstones": [],
            "taxonomy_changes": [], "coverage": [], "migrations": [], "repairs": []}


def ledger_name(existing: list[str], checkpoint: str, run_id: str) -> str:
    seq = max((int(n[:4]) for n in existing if n[:4].isdigit()), default=-1) + 1
    if seq > 9999:
        raise ArchiveError("Provenance ledger sequence is exhausted (9999); compact the ledgers first.")
    return f"{seq:04d}-{checkpoint[:8]}-{run_id[:8]}.jsonl"


def _shape(item, required: set, optional: set, label: str, problems: list[str]) -> bool:
    if not isinstance(item, dict):
        problems.append(f"{label}: must be an object.")
        return False
    missing, extra = required - set(item), set(item) - required - optional
    if missing or extra:
        problems.append(f"{label}: missing keys {sorted(missing)}, unexpected keys {sorted(extra)}.")
        return False
    return True


def _unit_ids(units, label: str, problems: list[str]) -> list[str]:
    """Compact `{path: [item, …]}` form to inventory unit ids (`path:item`)."""
    if not isinstance(units, dict) or not units or not all(
            isinstance(p, str) and isinstance(items, list) and items and all(isinstance(i, str) for i in items)
            for p, items in units.items()):
        problems.append(f"{label}: units must be a nonempty {{path: [item, …]}} object.")
        return []
    return [f"{path}:{item}" for path, items in units.items() for item in items]


def expand_coverage(candidate: dict, units: list[dict]) -> dict[str, dict]:
    known = [u["id"] for u in units]
    result: dict[str, dict] = {}
    problems: list[str] = []
    groups = candidate.get("coverage", [])
    if not isinstance(groups, list):
        raise ArchiveError("Coverage must be a list of grouped dispositions.")
    for number, group in enumerate(groups):
        label = f"coverage[{number}]"
        if not _shape(group, {"units", "action"}, {"memory_ids", "reason", "reason_code"}, label, problems):
            continue
        for uid in _unit_ids(group["units"], label, problems):
            if uid not in known:
                problems.append(f"{label}: unknown unit {uid}.")
            elif uid in result:
                problems.append(f"{label}: unit {uid} is covered more than once.")
            else:
                result[uid] = {"action": group["action"], "memory_ids": list(group.get("memory_ids", [])),
                               "reason": group.get("reason", "")}
    problems += [f"coverage: unit {uid} has no disposition." for uid in known if uid not in result]
    if problems:
        raise ArchiveError("Coverage is invalid:\n- " + "\n- ".join(problems))
    return {uid: result[uid] for uid in known}


def _entry_problems(entry, label: str, problems: list[str]) -> bool:
    if not _shape(entry, ENTRY_KEYS, {"summary"}, label, problems):
        return False
    if not all(isinstance(entry[k], str) for k in ("id", "domain", "kind", "title", "text")) \
            or not isinstance(entry.get("summary", ""), str) \
            or not isinstance(entry["relations"], list) or not all(isinstance(r, str) for r in entry["relations"]) \
            or not isinstance(entry["selectors"], list) or not all(
                isinstance(s, dict) and set(s) == {"kind", "value"} and all(isinstance(v, str) for v in s.values())
                for s in entry["selectors"]):
        problems.append(f"{label}: fields have the wrong types.")
        return False
    try:
        if ms.parse_entry(ms.emit_entry(entry), entry["id"]) != entry:
            problems.append(f"{label}: entry does not round-trip; trim the text and drop an empty summary.")
            return False
    except ArchiveError as error:
        problems.append(f"{label}: {error}")
        return False
    return True


def _verification(run: dict) -> dict:
    # ponytail: archive.verification_guard has already validated the reason; the ledger only commits after checks pass.
    reason = run.get("skip_verification")
    return {"status": "skipped", "reason": reason.strip()} if reason is not None else {"status": "passed"}


@dataclass
class Materialized:
    outputs: dict[str, bytes | None]
    result_root: str
    outputs_sha256: str
    summary: dict


def _fail(problems: list[str]) -> None:
    if problems:
        raise ArchiveError(f"Delta candidate rejected ({len(problems)} problem(s)):\n- " + "\n- ".join(problems))


def validate(repo, run: dict, candidate: dict, budgets: dict, retired_ids: set[str]) -> Materialized:
    try:
        return _validate(repo, run, candidate, budgets, retired_ids)
    except (TypeError, AttributeError) as error:  # wrong value types in an authored candidate
        raise ArchiveError(f"Delta candidate is malformed: {error}") from error


def _validate(repo, run: dict, candidate: dict, budgets: dict, retired_ids: set[str]) -> Materialized:
    problems: list[str] = []
    checkpoint = run["checkpoint"]
    units = {u["id"]: u for u in run["units"]}
    # 1. Binding to the run and to the current base. There is no automatic rebase.
    if candidate.get("schema_version") != SCHEMA:
        problems.append(f"schema_version must be {SCHEMA}.")
    current_root = ms.memory_root(repo.root)
    if candidate.get("base_memory_root") != run["base_memory_root"]:
        problems.append("base_memory_root differs from the run's base memory root.")
    if current_root != run["base_memory_root"]:
        problems.append("Project memory changed since prepare (memory root drift); there is no automatic rebase.")
    if candidate.get("checkpoint") != checkpoint:
        problems.append("checkpoint differs from the run's checkpoint.")
    extra = set(candidate) - set(empty_candidate("", ""))
    if extra:
        problems.append(f"unknown candidate keys {sorted(extra)}.")
    problems += [f"{path}: stray file in the base memory; remove it before archiving."
                 for path in ms.memory_files(repo.root)[1]]
    for key in ("additions", "updates", "removals", "provenance", "tombstones", "taxonomy_changes"):
        if not isinstance(candidate.get(key, []), list):
            problems.append(f"{key} must be a list.")
    _fail(problems)

    base = ms.Store(repo.root)
    retired = set(retired_ids) | set(base.retired)
    entries = dict(base.entries)
    outputs: dict[str, bytes | None] = {}
    # 2. Additions, updates and removals.
    added: set[str] = set()
    for number, entry in enumerate(candidate.get("additions", [])):
        label = f"additions[{number}]"
        if not _entry_problems(entry, label, problems):
            continue
        eid = entry["id"]
        if not ID.fullmatch(eid):
            problems.append(f"{label}: invalid id {eid!r}.")
        elif eid in base.entries:
            problems.append(f"{label}: {eid} already exists.")
        elif eid in retired:
            problems.append(f"{label}: {eid} is retired and cannot be reused.")
        elif eid in added:
            problems.append(f"{label}: {eid} is added more than once.")
        else:
            added.add(eid)
            entries[eid] = entry

    def current(eid: str, expected: str, label: str) -> bool:
        if eid not in base.entries:
            problems.append(f"{label}: unknown entry {eid!r}.")
            return False
        if digest((repo.root / ms.ENTRIES / f"{eid}.md").read_bytes()) != expected:
            problems.append(f"{label}: expected_hash does not match the current {eid} file.")
            return False
        return True

    touched: set[str] = set()
    updated: set[str] = set()
    for number, update in enumerate(candidate.get("updates", [])):
        label = f"updates[{number}]"
        if not _shape(update, {"id", "expected_hash", "entry"}, {"reason"}, label, problems):
            continue
        if "reason" in update and (not isinstance(update["reason"], str) or not update["reason"].strip()):
            problems.append(f"{label}: reason must be a nonempty string when given.")
        eid = update["id"]
        if eid in touched:
            problems.append(f"{label}: {eid} is touched more than once.")
            continue
        touched.add(eid)
        if current(eid, update["expected_hash"], label) and _entry_problems(update["entry"], label + ".entry", problems):
            if update["entry"]["id"] != eid:
                problems.append(f"{label}: entry id must stay {eid}; retire and add to rename.")
            else:
                entries[eid] = update["entry"]
                updated.add(eid)
    removals = []
    for number, removal in enumerate(candidate.get("removals", [])):
        label = f"removals[{number}]"
        if not _shape(removal, {"id", "expected_hash", "reason", "source_unit", "replacement"}, set(), label, problems):
            continue
        eid = removal["id"]
        if eid in touched:
            problems.append(f"{label}: {eid} is touched more than once.")
            continue
        touched.add(eid)
        if not isinstance(removal["reason"], str) or not removal["reason"].strip():
            problems.append(f"{label}: a removal needs a reason.")
        if removal["source_unit"] not in units:
            problems.append(f"{label}: source_unit {removal['source_unit']!r} is not an inventoried unit.")
        if current(eid, removal["expected_hash"], label):
            entries.pop(eid, None)
            removals.append(removal)
    for number, removal in enumerate(removals):
        if removal["replacement"] is not None and removal["replacement"] not in entries:
            problems.append(f"removals: replacement {removal['replacement']!r} for {removal['id']} is not in the result.")

    # Taxonomy changes.
    taxonomy = json.loads(json.dumps(base.taxonomy))
    domains = {d["id"]: d for d in taxonomy.get("domains", [])}
    for number, change in enumerate(candidate.get("taxonomy_changes", [])):
        label = f"taxonomy_changes[{number}]"
        if not _shape(change, {"op", "id", "label"}, {"definition"}, label, problems):
            continue
        did, op = change["id"], change["op"]
        if op not in ("add", "update") or not isinstance(did, str):
            problems.append(f"{label}: op must be add or update, with a string id.")
        elif did in ms.RESERVED_IDS:
            problems.append(f"{label}: domain id {did!r} is a reserved Windows name.")
        elif op == "add" and (did in domains or not ms.DOMAIN_ID.fullmatch(did)):
            problems.append(f"{label}: cannot add domain {did!r}; it exists or is not kebab-case.")
        elif op == "update" and did not in domains:
            problems.append(f"{label}: cannot update unknown domain {did!r}.")
        else:
            domains.setdefault(did, {"id": did}).update({k: v for k, v in change.items() if k in ("label", "definition")})
            taxonomy["domains"] = sorted(domains.values(), key=lambda d: str(d.get("label", "")).lower())

    # 4. Provenance in the compact form; the commit is the ledger header's checkpoint.
    records: list[dict] = []
    order = {uid: index for index, uid in enumerate(units)}
    evidence_paths: set[str] = set()
    for number, item in enumerate(candidate.get("provenance", [])):
        label = f"provenance[{number}]"
        if not _shape(item, {"entry"}, {"units", "evidence"}, label, problems):
            continue
        if item["entry"] not in entries:
            problems.append(f"{label}: entry {item['entry']!r} is not in the result.")
        # Units may be empty or absent for an evidence-only record (repairs evidence rot without new sources).
        ids = [] if item.get("units", {}) == {} else _unit_ids(item["units"], label, problems)
        unknown = [uid for uid in ids if uid not in units]
        problems += [f"{label}: unit {uid} is not inventoried." for uid in unknown]
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list) or not all(isinstance(p, str) for p in evidence):
            problems.append(f"{label}: evidence must be a list of paths.")
            continue
        if not ids and not evidence:
            problems.append(f"{label}: a provenance record needs units, evidence or both.")
            continue
        for path in evidence:
            try:
                repo.path(path)
            except ArchiveError as error:
                problems.append(f"{label}: {error}")
                continue
            if "\n" in path:
                problems.append(f"{label}: evidence path {path!r} contains a newline.")
            elif path.startswith("specs/"):
                problems.append(f"{label}: {path} is a specification, not implementation evidence.")
            else:
                evidence_paths.add(path)
        if not unknown:
            grouped: dict[str, list[str]] = {}
            for uid in sorted(dict.fromkeys(ids), key=order.__getitem__):
                grouped.setdefault(units[uid]["path"], []).append(uid[len(units[uid]["path"]) + 1:])
            records.append({"op": "add", "entry": item["entry"], "units": grouped, "evidence": sorted(set(evidence))})
    present = repo.exists_at(checkpoint, sorted(evidence_paths))
    problems += [f"provenance: evidence {p} does not exist at the checkpoint." for p in sorted(evidence_paths)
                 if not present.get(p)]

    # 5. Tombstones supersede existing add records.
    adds = {(r["entry"], ms.record_hash(r)) for _, _, rs in base.ledgers for r in rs if r.get("op") == "add"}
    for number, item in enumerate(candidate.get("tombstones", [])):
        label = f"tombstones[{number}]"
        if not _shape(item, {"entry", "record", "reason"}, set(), label, problems):
            continue
        if (item["entry"], item["record"]) not in adds:
            problems.append(f"{label}: record {item['record']!r} matches no existing add record for {item['entry']}.")
        elif not isinstance(item["reason"], str) or not item["reason"].strip():
            problems.append(f"{label}: a tombstone needs a reason.")
        else:
            records.append({"op": "tombstone", "entry": item["entry"], "record": item["record"], "reason": item["reason"]})
    records += [{"op": "retire", "entry": r["id"], "reason": r["reason"], "source_unit": r["source_unit"],
                 "replacement": r["replacement"]} for r in removals]

    # 6. Grouped coverage, part one: units and group rules.
    try:
        coverage = expand_coverage(candidate, run["units"])
    except ArchiveError as error:
        problems.append(str(error))
        coverage = {}
    for uid, disposition in coverage.items():
        action, targets = disposition["action"], disposition["memory_ids"]
        if action not in ACTIONS:
            problems.append(f"coverage: unknown action {action!r} for {uid}.")
        elif action == "omitted":
            if not str(disposition["reason"]).strip() or targets:
                problems.append(f"coverage: omitted unit {uid} needs a reason and no memory ids.")
        elif not targets or any(t not in entries for t in targets):
            problems.append(f"coverage: {action} unit {uid} must name memory ids in the result.")
    # An update needs an anchor in this run, or a stated reason (a reviewed correction), so a candidate cannot
    # silently rewrite an unrelated entry. Evidence-only records cite no unit from this run, so they cannot anchor one.
    anchors = {item.get("entry") for item in candidate.get("provenance", [])
               if isinstance(item, dict) and item.get("units")}
    anchors |= {t for group in candidate.get("coverage", []) if isinstance(group, dict)
                for t in group.get("memory_ids", []) if isinstance(t, str)}
    reasoned = {u.get("id") for u in candidate.get("updates", []) if isinstance(u, dict)
                and isinstance(u.get("reason"), str) and u["reason"].strip()}
    problems += [f"update of {eid} has no provenance or coverage anchor in this run; give it a reason if it is a "
                 "correction." for eid in sorted(updated - anchors - reasoned)]
    _fail(problems)

    # Materialize on a temporary copy and validate the whole result.
    name = ledger_name([n for n, _, _ in base.ledgers], checkpoint, run["run_id"])
    header = {"ledger": name.removesuffix(".jsonl"), "run_id": run["run_id"], "checkpoint": checkpoint,
              "specs": list(run["specs"]), "verification": _verification(run)}
    records.sort(key=lambda r: (r["entry"], r["op"], ms.record_hash(r)))
    outputs[f"{ms.PROVENANCE}/{name}"] = ms.emit_ledger(header, records)
    for eid in base.entries.keys() - entries.keys():
        outputs[f"{ms.ENTRIES}/{eid}.md"] = None
    for eid, entry in entries.items():
        data = ms.emit_entry(entry)
        path = f"{ms.ENTRIES}/{eid}.md"
        if eid not in base.entries or (repo.root / path).read_bytes() != data:
            outputs[path] = data
    if taxonomy != base.taxonomy:
        outputs[ms.TAXONOMY] = (json.dumps(taxonomy, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    repo.state.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="memory-delta-", dir=repo.state) as temp:
        tree = Path(temp)
        shutil.copytree(repo.root / ms.MEMORY_DIR, tree / ms.MEMORY_DIR)

        def put(path: str, data: bytes | None) -> None:
            target = tree / path
            if data is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

        for path, data in outputs.items():
            put(path, data)
        try:
            result = ms.Store(tree)
        except ArchiveError as error:
            _fail([f"result store: {error}"])
        views = ms.generated(result, budgets)
        existing = {p for p in ms.memory_files(tree)[0] if ms.CATALOG_PAGE.fullmatch(p) or p == ms.INDEX}
        for path in sorted(existing - set(views)):
            outputs[path] = None
            put(path, None)
        for path, data in views.items():
            if not (tree / path).is_file() or (tree / path).read_bytes() != data:
                outputs[path] = data
                put(path, data)
        # 7. Whole-result checks.
        problems += ms.check(result, budgets, retired_ids)
        for uid, disposition in coverage.items():
            for target in disposition["memory_ids"]:
                sources = result.provenance.get(target, {}).get("sources", [])
                if not any(s.get("unit") == uid and s.get("commit") == checkpoint for s in sources):
                    problems.append(f"coverage: target {target} lacks provenance for {uid} at the checkpoint.")
        behaviors = {eid: [e["path"] for e in result.provenance.get(eid, {}).get("evidence", [])]
                     for eid, entry in result.entries.items() if entry["kind"] == "behavior"}
        present = repo.exists_at(checkpoint, sorted({p for paths in behaviors.values() for p in paths}))
        problems += [f"{eid}: behavior has no evidence path present at the checkpoint." for eid, paths in
                     sorted(behaviors.items()) if paths and not any(present.get(p) for p in paths)]
        _fail(problems)
        result_root = ms.memory_root(tree)
    pairs = [[path, None if data is None else digest(data)] for path, data in sorted(outputs.items())]
    summary = {"additions": len(added), "updates": len(candidate.get("updates", [])), "removals": len(removals),
               "provenance_records": sum(1 for r in records if r["op"] == "add"), "coverage_units": len(coverage)}
    return Materialized(outputs=dict(sorted(outputs.items())), result_root=result_root,
                        outputs_sha256=digest(json.dumps(pairs, separators=(",", ":")).encode("utf-8")),
                        summary=summary)
