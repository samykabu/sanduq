"""Packet orchestration for large format-2 archive runs.

`packets` partitions the run's units into packets and assigns every taxonomy domain one owner packet. Drafters
write one fragment per packet (candidate v2 plus `proposals` for entries they do not own) and run
`fragment_check` until valid. `merge` composes the fragments into `candidate.json` or writes a conflict report.
`review_packets` builds one partition packet per fragment and one integration packet over the combined result,
so a partition approval survives unrelated fragment edits while any result change invalidates the integration.
Merge never runs memory_delta.validate; `archive.py validate` does.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import memory_delta as md
import memory_query as mq
import memory_store as ms
from git_state import ArchiveError, atomic_write, digest, write_json
from memory import ID

PACKET_SCHEMA = 1
LISTS = ("additions", "updates", "removals", "provenance", "tombstones", "taxonomy_changes", "coverage",
         "migrations", "repairs")
FRAGMENT_KEYS = set(md.empty_candidate("", "")) | {"packet", "proposals"}
PKT = re.compile(r"p\d{2,}")
TOKEN = re.compile(r"[a-z0-9]+")
NEAR_DUPLICATE = 0.6
REVIEW_TOKENS = 40_000  # one reviewer packet, chars/4 over its compact JSON
EXCERPT = 100  # omitted units show their first line only; the journal holds the full text


def packet_hash(packet: dict) -> str:
    return digest(json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _words(text: str) -> set[str]:
    return set(TOKEN.findall(text.lower()))


def _jaccard(x: set, y: set) -> float:
    return len(x & y) / len(x | y) if x | y else 0.0


def jaccard(a: str, b: str) -> float:
    return _jaccard(_words(a), _words(b))


def _guard(run: dict) -> None:
    if run.get("memory_format") != 2 or run.get("phase") != "synthesis":
        raise ArchiveError("Packet orchestration needs a format-2 run in the synthesis phase.")


def _load(path: Path):
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8-sig")), raw
    except (OSError, ValueError) as error:
        raise ArchiveError(f"Cannot read JSON at {path}: {error}") from error


def _packet_hashes(run_dir: Path) -> dict[str, str]:
    return {p.stem: digest(p.read_bytes()) for p in sorted((Path(run_dir) / "packets").glob("*.json"))}


def _packets(run_dir: Path) -> dict[str, dict]:
    paths = sorted((Path(run_dir) / "packets").glob("*.json"), key=lambda p: (len(p.stem), p.stem))
    return {p.stem: _load(p)[0] for p in paths}


def _hints(units: list[dict]) -> tuple[list[str], list[str], list[str]]:
    text = "\n".join(u.get("text", "") for u in units)
    routes = [f"{m} {p}" if m else p for m, p in dict.fromkeys(mq.ROUTE_IN_TEXT.findall(text))]
    return routes, list(dict.fromkeys(mq.FILE_IN_TEXT.findall(text))), list(dict.fromkeys(mq.CODE_IN_TEXT.findall(text)))


# ---- packets ------------------------------------------------------------

def _split(units: list[dict], limit: int) -> list[list[dict]]:
    """A file larger than `limit` splits at heading changes; a single oversized section splits at `limit`."""
    if len(units) <= limit:
        return [units]
    sections: list[list[dict]] = []
    for u in units:
        if sections and sections[-1][-1].get("heading") == u.get("heading"):
            sections[-1].append(u)
        else:
            sections.append([u])
    chunks: list[list[dict]] = [[]]
    for section in sections:
        for piece in (section[i:i + limit] for i in range(0, len(section), limit)):
            if chunks[-1] and len(chunks[-1]) + len(piece) > limit:
                chunks.append([])
            chunks[-1] += piece
    return chunks


def packets(repo, run: dict, run_dir: Path, *, by: str = "domain", max_units: int = 2500) -> dict:
    _guard(run)
    if by not in ("domain", "spec") or not isinstance(max_units, int) or max_units < 1:
        raise ArchiveError("Packets need --by domain|spec and a positive --max-units.")
    run_dir = Path(run_dir)
    pdir, fdir = run_dir / "packets", run_dir / "fragments"
    if any(pdir.glob("*.json")) and any(fdir.glob("*.json")):
        raise ArchiveError(f"Fragments exist; delete {fdir} before re-packeting.")
    store = ms.Store(repo.root)
    specs, order = list(run["specs"]), {u["id"]: n for n, u in enumerate(run["units"])}
    spec_of = {u["id"]: next((s for s in specs if repo.within(u["path"], [s])), None) for u in run["units"]}
    if None in spec_of.values():
        raise ArchiveError("Every inventoried unit must belong to a selected spec.")
    ranked, counts = {}, {}
    for spec in specs:
        routes, paths, codes = _hints([u for u in run["units"] if spec_of[u["id"]] == spec])
        # ponytail: rank() rebuilds its index per spec; build the index once if runs reach hundreds of specs.
        ranked[spec] = mq.rank(store, routes=routes, paths=paths, error_codes=codes) if routes or paths or codes else []
        counts[spec] = Counter(store.entries[h["id"]]["domain"] for h in ranked[spec][:25])
    if by == "spec":
        groups = [[s] for s in specs]
    else:
        keyed: dict[str | None, list[str]] = {}
        for s in specs:
            keyed.setdefault(min(counts[s].items(), key=lambda kv: (-kv[1], kv[0]))[0] if counts[s] else None, []).append(s)
        groups = [g for d, g in keyed.items() if d is not None] + ([keyed[None]] if None in keyed else [])
    packs: list[list[dict]] = []
    fresh = True
    for group in groups:
        units = [u for u in run["units"] if spec_of[u["id"]] in group]
        files: dict[str, list[dict]] = {}
        for u in units:
            files.setdefault(u["path"], []).append(u)
        atoms = [units] if len(units) <= max_units else [a for f in files.values() for a in _split(f, max_units)]
        for atom in (a for a in atoms if a):
            if fresh or len(packs[-1]) + len(atom) > max_units:
                packs.append([])
            packs[-1] += atom
            fresh = False
        fresh = by == "spec"  # spec mode: one packet (or file-split run of packets) per spec
    if not packs:
        raise ArchiveError("The run has no inventoried units to packet.")
    ids = [f"p{n:02d}" for n in range(1, len(packs) + 1)]
    packs = [sorted(pack, key=lambda u: order[u["id"]]) for pack in packs]
    pspecs = {pkt: [s for s in specs if any(spec_of[u["id"]] == s for u in pack)] for pkt, pack in zip(ids, packs)}
    size = {pkt: len(pack) for pkt, pack in zip(ids, packs)}
    ownership = {d: max(ids, key=lambda p: (sum(counts[s][d] for s in pspecs[p]), -size[p], -int(p[1:])))
                 for d in sorted(store.domains)}
    texts = {}
    for ref in run["references"]:
        try:
            texts[ref] = repo.path(ref).read_bytes().decode("utf-8", "replace")
        except OSError:
            texts[ref] = ""
    for old in pdir.glob("*.json"):
        old.unlink()
    result = []
    for pkt, pack in zip(ids, packs):
        owned = sorted(d for d, owner in ownership.items() if owner == pkt)
        best: dict[str, float] = {}
        for s in pspecs[pkt]:
            for hit in ranked[s]:
                best[hit["id"]] = max(best.get(hit["id"], 0.0), hit["score"])
        related = [eid for eid in sorted(best, key=lambda e: (-best[e], e))
                   if ownership.get(store.entries[eid]["domain"]) != pkt][:50]
        packet = {"schema_version": PACKET_SCHEMA, "packet": pkt, "run_id": run["run_id"], "checkpoint": run["checkpoint"],
                  "base_memory_root": run["base_memory_root"], "by": by, "specs": pspecs[pkt], "units": pack,
                  "references": [r for r in run["references"]
                                 if any(re.search(re.escape(s) + r"(?![\w-])", texts[r]) for s in pspecs[pkt])],
                  "owned_domains": owned,
                  "entries": [{"id": eid, "domain": e["domain"], "title": e["title"],
                               "expected_hash": digest((repo.root / ms.ENTRIES / f"{eid}.md").read_bytes())}
                              for eid, e in sorted(store.entries.items()) if e["domain"] in owned],
                  "related": [{"id": eid, "domain": store.entries[eid]["domain"], "title": store.entries[eid]["title"],
                               "owner": ownership.get(store.entries[eid]["domain"])} for eid in related],
                  "ownership": ownership, "fragment": f"fragments/{pkt}.json"}
        path = pdir / f"{pkt}.json"
        write_json(path, packet)
        result.append({"packet": pkt, "specs": pspecs[pkt], "units": len(pack), "owned_domains": owned, "path": str(path)})
    return {"packets": result, "ownership": ownership}


# ---- fragment check -----------------------------------------------------

def fragment_check(repo, run: dict, run_dir: Path, fragment_path: Path, retired_ids: set[str]) -> dict:
    """Check one drafter fragment against its packet; read-only and lock-free. Raises only for unreadable input."""
    _guard(run)
    run_dir, fragment_path = Path(run_dir), Path(fragment_path)
    fragment, _ = _load(fragment_path)
    problems: list[str] = []
    warnings: list[str] = []
    pkt = fragment.get("packet") if isinstance(fragment, dict) else None
    summary: dict = {}
    if not isinstance(fragment, dict):
        problems.append("The fragment must be a JSON object.")
    elif not isinstance(pkt, str) or not PKT.fullmatch(pkt) or not (run_dir / "packets" / f"{pkt}.json").is_file():
        problems.append(f"packet {pkt!r} names no packet of this run.")
    else:
        if fragment_path.stem != pkt:
            problems.append(f"packet {pkt} must equal the fragment file name ({fragment_path.stem}).")
        packet = _load(run_dir / "packets" / f"{pkt}.json")[0]
        try:
            summary = _check(repo, run, run_dir, fragment_path, fragment, packet, set(retired_ids), problems, warnings)
        except (TypeError, AttributeError) as error:  # wrong value types in an authored fragment
            problems.append(f"Fragment is malformed: {error}")
    return {"valid": not problems, "packet": pkt, "problems": problems, "warnings": warnings, "summary": summary}


def _check(repo, run, run_dir, path, fragment, packet, retired_ids, problems, warnings) -> dict:
    pkt, ownership = packet["packet"], packet["ownership"]
    missing, extra = FRAGMENT_KEYS - set(fragment), set(fragment) - FRAGMENT_KEYS
    if missing or extra:
        problems.append(f"missing keys {sorted(missing)}, unexpected keys {sorted(extra)}.")
    if fragment.get("schema_version") != md.SCHEMA:
        problems.append(f"schema_version must be {md.SCHEMA}.")
    for key in ("base_memory_root", "checkpoint"):
        if fragment.get(key) != run[key]:
            problems.append(f"{key} differs from the run's {key}.")
    lists = {}
    for key in (*LISTS, "proposals"):
        lists[key] = fragment.get(key, [])
        if not isinstance(lists[key], list):
            problems.append(f"{key} must be a list.")
            lists[key] = []
    base = ms.Store(repo.root)
    retired = retired_ids | set(base.retired)
    units = {u["id"] for u in packet["units"]}
    run_units = {u["id"] for u in run["units"]}

    def owner(eid: str):
        return ownership.get(base.entries[eid]["domain"])

    others: set = set()
    for other in sorted((run_dir / "fragments").glob("*.json")):
        if other.resolve() != path.resolve():
            try:
                others |= {e.get("id") for e in _load(other)[0].get("additions", []) if isinstance(e, dict)}
            except (ArchiveError, AttributeError, TypeError):
                pass  # another drafter's half-written file; merge rechecks every fragment

    def resolve(eid, known: set, label: str, what: str) -> None:
        if eid in known:
            return
        if eid in others:
            warnings.append(f"{label}: {what} {eid} is not in base or this fragment; added by another fragment? "
                            "merge rechecks it.")
        else:
            problems.append(f"{label}: {what} {eid!r} does not resolve.")

    # 3. Additions (taxonomy changes only get a shape check here; validate applies them).
    for number, change in enumerate(lists["taxonomy_changes"]):
        if md._shape(change, {"op", "id", "label"}, {"definition"}, f"taxonomy_changes[{number}]", problems)                 and not isinstance(change["id"], str):
            problems.append(f"taxonomy_changes[{number}]: id must be a string.")
    new_domains = {c.get("id") for c in lists["taxonomy_changes"] if isinstance(c, dict) and c.get("op") == "add"}
    added: set[str] = set()
    entries: list[tuple[str, dict]] = []  # entries whose references are checked
    for number, entry in enumerate(lists["additions"]):
        label = f"additions[{number}]"
        if not md._entry_problems(entry, label, problems):
            continue
        entries.append((label, entry))
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
        if entry["domain"] not in base.domains and entry["domain"] not in new_domains:
            problems.append(f"{label}: unknown domain {entry['domain']!r}; add it in taxonomy_changes.")

    # 4. Updates and removals: owner only, against the current entry file.
    touched: set[str] = set()

    def target(eid, expected, label: str) -> bool:
        if eid in touched:
            problems.append(f"{label}: {eid} is touched more than once.")
            return False
        touched.add(eid)
        if eid not in base.entries:
            problems.append(f"{label}: unknown entry {eid!r}.")
            return False
        if owner(eid) != pkt:
            problems.append(f"{label}: {eid} is owned by {owner(eid)}; submit a proposal.")
            return False
        if digest((repo.root / ms.ENTRIES / f"{eid}.md").read_bytes()) != expected:
            problems.append(f"{label}: expected_hash does not match the current {eid} file.")
            return False
        return True

    for number, update in enumerate(lists["updates"]):
        label = f"updates[{number}]"
        if (md._shape(update, {"id", "expected_hash", "entry"}, {"reason"}, label, problems)
                and target(update["id"], update["expected_hash"], label)
                and md._entry_problems(update["entry"], label + ".entry", problems)):
            entries.append((label, update["entry"]))
            if update["entry"]["id"] != update["id"]:
                problems.append(f"{label}: entry id must stay {update['id']}; retire and add to rename.")
    removed: set[str] = set()
    removals = []
    for number, removal in enumerate(lists["removals"]):
        label = f"removals[{number}]"
        if not md._shape(removal, {"id", "expected_hash", "reason", "source_unit", "replacement"}, set(), label, problems):
            continue
        if not isinstance(removal["reason"], str) or not removal["reason"].strip():
            problems.append(f"{label}: a removal needs a reason.")
        if removal["source_unit"] not in units:
            problems.append(f"{label}: source_unit {removal['source_unit']!r} is not a unit of {pkt}.")
        if target(removal["id"], removal["expected_hash"], label):
            removed.add(removal["id"])
            removals.append((label, removal))
    live = (set(base.entries) | added) - removed
    for label, removal in removals:
        if removal["replacement"] is not None:
            resolve(removal["replacement"], live, label, "replacement")

    # 5. Provenance.
    cited: set[tuple] = set()
    evidence_paths: set[str] = set()
    for number, item in enumerate(lists["provenance"]):
        label = f"provenance[{number}]"
        if not md._shape(item, {"entry"}, {"units", "evidence"}, label, problems):
            continue
        resolve(item["entry"], live, label, "entry")
        ids = [] if item.get("units", {}) == {} else md._unit_ids(item["units"], label, problems)
        problems += [f"{label}: unit {uid} is not in {pkt}." for uid in ids if uid not in units]
        cited |= {(item["entry"], uid) for uid in ids}
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list) or not all(isinstance(p, str) for p in evidence):
            problems.append(f"{label}: evidence must be a list of paths.")
            continue
        if not ids and not evidence:
            problems.append(f"{label}: a provenance record needs units, evidence or both.")
        for name in evidence:
            try:
                repo.path(name)
            except ArchiveError as error:
                problems.append(f"{label}: {error}")
                continue
            if name.startswith("specs/"):
                problems.append(f"{label}: {name} is a specification, not implementation evidence.")
            else:
                evidence_paths.add(name)
    present = repo.exists_at(run["checkpoint"], sorted(evidence_paths))
    problems += [f"provenance: evidence {p} does not exist at the checkpoint." for p in sorted(evidence_paths)
                 if not present[p]]

    # 2 and 6. Coverage: exactly this packet's units, targets live and cited by this fragment's provenance.
    covered: set[str] = set()
    for number, group in enumerate(lists["coverage"]):
        label = f"coverage[{number}]"
        if not md._shape(group, {"units", "action"}, {"memory_ids", "reason", "reason_code"}, label, problems):
            continue
        action, targets = group["action"], group.get("memory_ids", [])
        if not isinstance(targets, list):
            problems.append(f"{label}: memory_ids must be a list.")
            targets = []
        if action not in md.ACTIONS:
            problems.append(f"{label}: unknown action {action!r}.")
        elif action == "omitted":
            if not str(group.get("reason", "")).strip() or targets:
                problems.append(f"{label}: omitted units need a reason and no memory ids.")
        elif not targets:
            problems.append(f"{label}: {action} units must name memory ids.")
        else:
            for t in targets:
                resolve(t, live, label, "target")
        for uid in md._unit_ids(group["units"], label, problems):
            if uid not in units:
                problems.append(f"{label}: unit {uid} is {'not in ' + pkt if uid in run_units else 'unknown'}.")
            elif uid in covered:
                problems.append(f"{label}: unit {uid} is covered more than once.")
            else:
                covered.add(uid)
                if action in md.ACTIONS and action != "omitted":
                    problems += [f"{label}: target {t} has no provenance record in this fragment citing {uid}."
                                 for t in targets if (t, uid) not in cited]
    problems += [f"coverage: unit {uid} has no disposition." for uid in sorted(units - covered)]

    # 8. Tombstones.
    adds = {(r["entry"], ms.record_hash(r)) for _, _, rs in base.ledgers for r in rs if r.get("op") == "add"}
    for number, item in enumerate(lists["tombstones"]):
        label = f"tombstones[{number}]"
        if not md._shape(item, {"entry", "record", "reason"}, set(), label, problems):
            continue
        if item["entry"] in base.entries and owner(item["entry"]) != pkt:
            problems.append(f"{label}: {item['entry']} is owned by {owner(item['entry'])}; submit a proposal.")
        elif (item["entry"], item["record"]) not in adds:
            problems.append(f"{label}: record {item['record']!r} matches no existing add record for {item['entry']}.")
        elif not isinstance(item["reason"], str) or not item["reason"].strip():
            problems.append(f"{label}: a tombstone needs a reason.")

    # 9. Repairs and migrations.
    for number, repair in enumerate(lists["repairs"]):
        if not isinstance(repair, dict) or repair.get("path") not in run["references"]:
            problems.append(f"repairs[{number}]: path must be a preflight reference of this run.")
    for number, migration in enumerate(lists["migrations"]):
        label = f"migrations[{number}]"
        if not md._shape(migration, {"source", "destination"}, set(), label, problems):
            continue
        source = migration["source"]
        if source not in run["original_files"] or not repo.within(source, packet["specs"]):
            problems.append(f"{label}: source must be an original file of {pkt}'s specs.")
        elif migration["destination"] != "tests/Fixtures/spec-memory/" + source.removeprefix("specs/"):
            problems.append(f"{label}: destination must be tests/Fixtures/spec-memory/{source.removeprefix('specs/')}.")

    # 10. Proposals for entries another packet owns.
    for number, proposal in enumerate(lists["proposals"]):
        label = f"proposals[{number}]"
        if not md._shape(proposal, {"id", "action", "reason", "entry"}, set(), label, problems):
            continue
        eid, entry = proposal["id"], proposal["entry"]
        if eid not in base.entries:
            problems.append(f"{label}: unknown entry {eid!r}.")
        elif owner(eid) == pkt:
            problems.append(f"{label}: {pkt} owns {eid}; use updates or removals.")
        if not isinstance(proposal["reason"], str) or not proposal["reason"].strip():
            problems.append(f"{label}: a proposal needs a reason.")
        if proposal["action"] == "update":
            if md._entry_problems(entry, label + ".entry", problems):
                entries.append((label, entry))
                if entry["id"] != eid:
                    problems.append(f"{label}: entry id must stay {eid}.")
        elif proposal["action"] == "remove":
            if entry is not None:
                problems.append(f"{label}: a remove proposal carries entry: null.")
        else:
            problems.append(f"{label}: action must be update or remove.")

    # 7. References of additions, updates and proposals.
    known = set(base.entries) | retired | added
    for label, entry in entries:
        for ref in dict.fromkeys(ms.inline_refs(entry) + entry["relations"]):
            resolve(ref, known, label, "reference")
    return {**{key: len(lists[key]) for key in (*LISTS, "proposals")}, "units": len(units), "covered": len(covered)}


# ---- merge --------------------------------------------------------------

def merge(repo, run: dict, run_dir: Path, retired_ids: set[str]) -> dict:
    _guard(run)
    run_dir = Path(run_dir)
    packets_ = _packets(run_dir)
    if not packets_:
        raise ArchiveError("No packets; run packets first.")
    conflicts: list[dict] = []

    def conflict(kind: str, detail: str, pkts: list[str]) -> None:
        conflicts.append({"class": kind, "detail": detail, "packets": list(dict.fromkeys(pkts))})

    fragments, hashes = {}, {}
    for pkt in packets_:
        path = run_dir / "fragments" / f"{pkt}.json"
        if not path.is_file():
            conflict("missing-fragment", f"{pkt} has no fragment at {path}.", [pkt])
            continue
        before = digest(path.read_bytes())
        report = fragment_check(repo, run, run_dir, path, retired_ids)
        if not report["valid"]:
            conflict("fragment-invalid", f"{pkt}: {len(report['problems'])} problem(s): "
                     + "; ".join(report["problems"][:3]), [pkt])
            continue
        fragments[pkt], raw = _load(path)
        if digest(raw) != before:
            conflict("fragment-invalid", f"{pkt} changed while it was being checked; merge again.", [pkt])
            continue
        hashes[pkt] = digest(raw)
    base = ms.Store(repo.root)
    ownership = next(iter(packets_.values()))["ownership"]
    if any(packet.get("ownership") != ownership for packet in packets_.values()):
        conflict("ownership", "The packets' ownership maps disagree; re-run packets.", list(packets_))

    def owner(eid: str):
        return ownership.get(base.entries[eid]["domain"])

    routed: dict = {}
    for pkt, fragment in fragments.items():
        for proposal in fragment["proposals"]:
            routed.setdefault(owner(proposal["id"]), []).append({"from": pkt, **proposal})
    proposals = {p: routed[p] for p in [*packets_, *routed] if p in routed}

    def reject() -> None:
        path = run_dir / "merge.json"
        write_json(path, {"merged": False, "conflicts": conflicts, "proposals": proposals})
        raise ArchiveError(f"Merge rejected: {len(conflicts)} conflict(s); see {path}")

    # Cross-fragment checks need every fragment; stop at fragment-level conflicts.
    if conflicts:
        reject()

    def by_id(key: str) -> dict[str, list[str]]:
        seen: dict[str, list[str]] = {}
        for pkt, fragment in fragments.items():
            for item in fragment[key]:
                seen.setdefault(item["id"], []).append(pkt)
        return seen

    updates, removals = by_id("updates"), by_id("removals")
    for eid, pkts in by_id("additions").items():
        if len(pkts) > 1:
            conflict("id-collision", f"{eid} is added by {', '.join(pkts)}.", pkts)
    for eid, pkts in updates.items():
        if len(pkts) > 1:
            conflict("double-update", f"{eid} is updated by {', '.join(pkts)}.", pkts)
    for eid in sorted(updates.keys() & removals.keys()):
        conflict("update-removal", f"{eid} is updated by {', '.join(updates[eid])} and removed by "
                 f"{', '.join(removals[eid])}.", updates[eid] + removals[eid])
    for eid, pkts in removals.items():
        if len(pkts) > 1:
            conflict("double-removal", f"{eid} is removed by {', '.join(pkts)}.", pkts)
    covered: dict[str, list[str]] = {}
    for pkt, fragment in fragments.items():
        for group in fragment["coverage"]:
            for uid in md._unit_ids(group["units"], "coverage", []):
                covered.setdefault(uid, []).append(pkt)
    for uid, pkts in covered.items():
        if len(pkts) > 1:
            conflict("double-coverage", f"unit {uid} is covered by {', '.join(pkts)}.", pkts)
    for unit in run["units"]:
        if unit["id"] not in covered:
            conflict("coverage-gap", f"unit {unit['id']} is covered by no fragment.", [])

    def dedupe(key: str, field: str, kind: str, noun: str) -> dict[str, list]:
        kept: dict[str, list] = {}
        first: dict = {}
        for pkt, fragment in fragments.items():
            kept[pkt] = []
            for item in fragment[key]:
                canon = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if item[field] not in first:
                    first[item[field]] = (canon, pkt)
                    kept[pkt].append(item)
                elif first[item[field]][0] != canon:
                    conflict(kind, f"{noun} {item[field]} differs between {first[item[field]][1]} and {pkt}.",
                             [first[item[field]][1], pkt])
        return kept

    composed = {"repairs": dedupe("repairs", "path", "repair-conflict", "repair of"),
                "migrations": dedupe("migrations", "destination", "fixture-collision", "fixture"),
                "taxonomy_changes": dedupe("taxonomy_changes", "id", "taxonomy-conflict", "taxonomy change for"),
                "tombstones": dedupe("tombstones", "record", "tombstone-conflict", "tombstone of record")}
    retired = set(retired_ids) | set(base.retired)
    removed = set(removals)
    result = (set(base.entries) | {e["id"] for f in fragments.values() for e in f["additions"]}) - removed
    resolvable = result | retired | removed
    for pkt, fragment in fragments.items():
        for entry in [*fragment["additions"], *(u["entry"] for u in fragment["updates"])]:
            broken = [r for r in dict.fromkeys(ms.inline_refs(entry) + entry["relations"]) if r not in resolvable]
            if broken:
                conflict("broken-reference", f"{entry['id']} references {', '.join(broken)}, which resolve to nothing.",
                         [pkt])
        for removal in fragment["removals"]:
            if removal["replacement"] is not None and removal["replacement"] not in result:
                conflict("broken-replacement", f"replacement {removal['replacement']} for {removal['id']} is not live "
                         "in the composed result.", [pkt, *removals.get(removal["replacement"], [])])
        for item in [*fragment["updates"], *fragment["removals"]]:
            if owner(item["id"]) != pkt:
                conflict("ownership", f"{item['id']} is owned by {owner(item['id'])}, not {pkt}.", [pkt])
    if conflicts:
        reject()
    candidate = md.empty_candidate(run["base_memory_root"], run["checkpoint"])
    for key in LISTS:
        candidate[key] = [item for pkt, fragment in fragments.items()
                          for item in (composed[key][pkt] if key in composed else fragment[key])]
    path = run_dir / "candidate.json"
    write_json(path, candidate)
    report = {"merged": True, "candidate_sha256": digest(path.read_bytes()), "fragments": hashes,
              "packets": _packet_hashes(run_dir), "conflicts": [], "proposals": proposals}
    write_json(run_dir / "merge.json", report)
    return report


# ---- review packets -----------------------------------------------------

def _review_contents(repo, run: dict, run_dir: Path, m, candidate_raw: bytes) -> tuple[dict[str, dict], dict]:
    _guard(run)
    run_dir = Path(run_dir)
    if not (run_dir / "merge.json").is_file():
        raise ArchiveError("Run merge before review-packets.")
    merged = _load(run_dir / "merge.json")[0]
    if not isinstance(merged, dict) or not isinstance(merged.get("fragments"), dict):
        raise ArchiveError("merge.json is malformed; re-run merge.")
    if merged.get("merged") is not True or merged.get("candidate_sha256") != digest(candidate_raw):
        raise ArchiveError("Candidate changed after merge; re-run merge.")
    packets_ = _packets(run_dir)
    if set(packets_) != set(merged["fragments"]) or _packet_hashes(run_dir) != merged.get("packets"):
        raise ArchiveError("Packets changed after merge; re-run merge.")
    fragments = {}
    for pkt in packets_:
        fragments[pkt], raw = _load(run_dir / "fragments" / f"{pkt}.json")
        if digest(raw) != merged["fragments"][pkt]:
            raise ArchiveError(f"Fragment {pkt} changed after merge; re-run merge.")
    base = ms.Store(repo.root)
    partitions = {}
    for pkt, f in fragments.items():
        partitions.update(_partitions(run, pkt, packets_[pkt], f, base))
    candidate = json.loads(candidate_raw.decode("utf-8-sig"))
    source, removed_by = {}, {}
    for pkt, f in fragments.items():
        source.update({e["id"]: pkt for e in f["additions"]} | {u["id"]: pkt for u in f["updates"]})
        removed_by.update({r["id"]: pkt for r in f["removals"]})
    entries = dict(base.entries)
    entries.update({e["id"]: e for e in candidate["additions"]} | {u["id"]: u["entry"] for u in candidate["updates"]})
    for removal in candidate["removals"]:
        entries.pop(removal["id"], None)

    def of(eid: str) -> str:
        return source.get(eid, "base")

    def listed(ids) -> list[dict]:
        return [{"id": eid, "packet": of(eid)} for eid in ids]

    changed = set(source) & set(entries)
    selectors: dict[tuple, list[str]] = {}
    relations: dict[str, list[str]] = {}
    for eid in sorted(entries):
        for s in entries[eid]["selectors"]:
            selectors.setdefault((s["kind"], s["value"]), []).append(eid)
        for t in dict.fromkeys(entries[eid]["relations"]):
            relations.setdefault(t, []).append(eid)
    words = {eid: _words(e["title"]) for eid, e in entries.items()}
    pairs: dict[tuple, float] = {}
    # ponytail: O(changed x entries) title scan; index titles by token if result memory reaches tens of thousands.
    for a in sorted(changed):
        for b in entries:
            pair = tuple(sorted((a, b)))
            if a != b and of(a) != of(b) and pair not in pairs:
                score = _jaccard(words[a], words[b])
                if score >= NEAR_DUPLICATE:
                    pairs[pair] = round(score, 4)
    integration = {
        "kind": "integration", "candidate_sha256": digest(candidate_raw), "base_memory_root": run["base_memory_root"],
        "result_memory_root": m.result_root, "outputs_sha256": m.outputs_sha256,
        "shared_selectors": [{"selector": {"kind": k, "value": v}, "entries": listed(dict.fromkeys(ids))}
                             for (k, v), ids in sorted(selectors.items())
                             if len(set(ids)) >= 2 and changed & set(ids)],
        "shared_relations": [{"target": t, "entries": listed(ids)} for t, ids in sorted(relations.items())
                             if len({of(e) for e in ids}) >= 2 and changed & set(ids)],
        "near_duplicates": [{"a": a, "b": b, "packets": [of(a), of(b)], "jaccard": score,
                             "titles": [entries[a]["title"], entries[b]["title"]]}
                            for (a, b), score in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))],
        "taxonomy_changes": candidate["taxonomy_changes"],
        "updates": [{"id": u["id"], "packet": of(u["id"]), "reason": u.get("reason"), "before": base.entries[u["id"]],
                     "after": u["entry"]} for u in candidate["updates"]],
        "removals": [{**r, "packet": removed_by.get(r["id"])} for r in candidate["removals"]],
        "proposals": merged.get("proposals", {})}
    return partitions, integration


def _compact(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _cost(value) -> int:
    return ms.tokens(_compact(value).decode("utf-8"))


def _partitions(run: dict, pkt: str, packet: dict, f: dict, base: ms.Store) -> dict[str, dict]:
    """Cut one fragment's review into parts under REVIEW_TOKENS, from its packet, fragment and base memory only,
    so edits to other fragments never change them. Each delta item goes with the earliest unit it cites."""
    units = packet["units"]
    order = {u["id"]: n for n, u in enumerate(units)}
    omitted = {uid: number for number, g in enumerate(f["coverage"]) if g["action"] == "omitted"
               for uid in md._unit_ids(g["units"], "coverage", [])}

    def first(uids) -> int | None:
        return min((order[u] for u in uids if u in order), default=None)

    def cited(item) -> list[str]:
        return md._unit_ids(item["units"], "units", []) if item.get("units") else []

    home: dict[str, int] = {}
    for item in [*f["provenance"], *(g for g in f["coverage"] if g["action"] != "omitted")]:
        n = first(cited(item))
        for eid in [item["entry"]] if "entry" in item else item.get("memory_ids", []):
            if n is not None and n < home.get(eid, n + 1):
                home[eid] = n
    places = [("additions", lambda e: home.get(e["id"])), ("updates", lambda u: home.get(u["id"])),
              ("provenance", lambda p: first(cited(p)) if cited(p) else home.get(p["entry"])),
              ("removals", lambda r: order.get(r["source_unit"]))]
    places += [(k, lambda _: None) for k in ("tombstones", "taxonomy_changes", "migrations", "repairs", "proposals")]
    attached: dict[int | None, list[tuple[str, dict]]] = {}
    for key, place in places:
        for item in f[key]:
            attached.setdefault(place(item), []).append((key, item))

    def touched(items) -> set[str]:
        ids = {item["id"] for key, item in items if key in ("updates", "removals", "proposals")}
        ids |= {item["entry"] for key, item in items if key == "provenance"}
        return {eid for eid in ids if eid in base.entries}

    def view(u: dict) -> str:
        text = u.get("text", "") if u.get("kind") != "binary" else f"<binary {u['bytes']} bytes sha256 {u['sha256']}>"
        return text.split("\n", 1)[0][:EXCERPT] if u["id"] in omitted else text

    def cost(items) -> int:
        return sum(_cost(i) for _, i in items) + sum(_cost(base.entries[e]) for e in touched(items))

    parts: list[list[int]] = [[]]
    used = cost(attached.get(None, []))
    for n, u in enumerate(units):
        c = _cost(view(u)) + 8 + cost(attached.get(n, []))
        if parts[-1] and used + c > REVIEW_TOKENS * 0.9:  # headroom for keys and coverage targets
            parts.append([])
            used = 0
        parts[-1].append(n)
        used += c
    result = {}
    for index, numbers in enumerate(parts, 1):
        items = [*(attached.get(None, []) if index == 1 else []), *(x for n in numbers for x in attached.get(n, []))]
        delta: dict[str, list] = {k: [] for k in (*LISTS, "proposals")}
        for key, item in items:
            delta[key].append(item)
        mine = {units[n]["id"] for n in numbers}
        shown: dict[str, dict] = {}
        skipped: dict[int, dict] = {}
        for n in numbers:
            u = units[n]
            item = u["id"][len(u["path"]) + 1:]
            if u["id"] in omitted:
                g = f["coverage"][omitted[u["id"]]]
                group = skipped.setdefault(omitted[u["id"]],
                                           {**{k: g[k] for k in ("reason", "reason_code") if k in g}, "units": {}})
                group["units"].setdefault(u["path"], {})[item] = view(u)
            else:
                shown.setdefault(u["path"], {})[item] = view(u)
        for g in f["coverage"]:
            ids = [uid for uid in md._unit_ids(g["units"], "coverage", []) if uid in mine]
            if g["action"] != "omitted" and ids:
                grouped: dict[str, list[str]] = {}
                for uid in ids:
                    path = units[order[uid]]["path"]
                    grouped.setdefault(path, []).append(uid[len(path) + 1:])
                delta["coverage"].append({**g, "units": grouped})
        targets = {t for g in delta["coverage"] for t in g.get("memory_ids", []) if t in base.entries}
        result[f"{pkt}-{index:02d}"] = {
            "kind": "partition", "packet": pkt, "part": index, "parts": len(parts), "run_id": run["run_id"],
            "checkpoint": run["checkpoint"], "base_memory_root": run["base_memory_root"], "units": shown,
            "omitted": list(skipped.values()), "delta": delta,
            "touched": {eid: base.entries[eid] for eid in sorted(touched(items) | targets)}}
    return result


def current_hashes(repo, run: dict, run_dir: Path, m, candidate_raw: bytes) -> dict:
    partitions, integration = _review_contents(repo, run, run_dir, m, candidate_raw)
    return {"partitions": {pkt: packet_hash(c) for pkt, c in partitions.items()}, "integration": packet_hash(integration)}


def review_packets(repo, run: dict, run_dir: Path, m, candidate_raw: bytes) -> dict:
    run_dir = Path(run_dir)
    partitions, integration = _review_contents(repo, run, run_dir, m, candidate_raw)
    review: dict = {}
    if (run_dir / "review.json").is_file():
        try:
            review = _load(run_dir / "review.json")[0]
        except ArchiveError:
            review = {}
    review = review if isinstance(review, dict) else {}
    approved = review.get("partitions") if isinstance(review.get("partitions"), dict) else {}

    def write(name: str, content: dict, approval) -> dict:
        path = run_dir / "review" / name
        atomic_write(path, _compact(content) + b"\n")  # compact: agents read these, budgeted in tokens
        sha = packet_hash(content)
        got = approval.get("packet_sha256") if isinstance(approval, dict) else None
        return {"path": str(path), "packet_sha256": sha, "tokens": ms.tokens(path.read_bytes().decode("utf-8")),
                "approval": "missing" if got is None else "valid" if got == sha else "stale"}

    for old in (run_dir / "review").glob("*.json"):
        old.unlink()
    return {"partitions": {pkt: write(f"partition-{pkt}.json", c, approved.get(pkt)) for pkt, c in partitions.items()},
            "integration": write("integration.json", integration, review.get("integration"))}


def approval_problems(run_dir: Path, review: dict, current: dict) -> list[str]:
    """Problems with the partition and integration approvals in review.json against `current_hashes`."""
    problems: list[str] = []
    review = review if isinstance(review, dict) else {}

    def check(label: str, approval, sha: str, packet: str) -> None:
        if not isinstance(approval, dict):
            problems.append(f"{label} approval is missing; review {Path(run_dir) / 'review' / packet}.")
            return
        if approval.get("packet_sha256") != sha:
            problems.append(f"{label} approval is stale; re-review {Path(run_dir) / 'review' / packet}.")
        if approval.get("passed") is not True:
            problems.append(f"{label} approval must have passed: true.")
        if approval.get("findings") != []:
            problems.append(f"{label} approval must have findings: [].")
        if not isinstance(approval.get("reviewer"), str) or not approval["reviewer"].strip():
            problems.append(f"{label} approval needs a nonempty reviewer.")

    parts = review.get("partitions") if isinstance(review.get("partitions"), dict) else {}
    for pkt, sha in current["partitions"].items():
        check(f"partition {pkt}", parts.get(pkt), sha, f"partition-{pkt}.json")
    problems += [f"partition {pkt} is not a packet of this run." for pkt in parts if pkt not in current["partitions"]]
    check("integration", review.get("integration"), current["integration"], "integration.json")
    return problems
