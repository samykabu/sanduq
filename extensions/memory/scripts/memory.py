"""Inventory and validation for current product knowledge, never a changelog."""

from __future__ import annotations

import json
import re
from pathlib import Path

from git_state import ArchiveError, Repository, digest

MEMORY = "specs/project-memory.md"
REGISTRY = "specs/.archive-index.json"
MARKER = re.compile(r"^<!-- archive-entry (.+) -->$", re.M)
ID = re.compile(r"PM-[a-z][a-z0-9-]{1,79}$")


def inventory(repo: Repository, checkpoint: str, files: list[str]) -> list[dict]:
    units = []
    for path in files:
        data = repo.blob(checkpoint, path)
        try:
            text = data.decode("utf-8-sig")
            if "\0" in text:
                raise UnicodeError()
        except UnicodeError:
            units.append({"id": f"{path}:binary", "path": path, "line": 0,
                          "sha256": digest(data), "kind": "binary", "bytes": len(data)})
            continue
        if not text.strip():
            units.append({"id": f"{path}:empty", "path": path, "line": 0, "kind": "empty", "text": ""})
            continue
        # Paragraphs and fenced blocks retain surrounding headings as context.
        block, line, heading, fenced = [], 1, "", False
        for number, value in enumerate(text.splitlines(), 1):
            if value.startswith("#") and not fenced:
                heading = value
            if value.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
            if value.strip() or fenced:
                if not block:
                    line = number
                block.append(value)
            elif block:
                units.append({"id": f"{path}:L{line}", "path": path, "line": line,
                              "kind": "text", "heading": heading, "text": "\n".join(block)})
                block = []
        if block:
            units.append({"id": f"{path}:L{line}", "path": path, "line": line,
                          "kind": "text", "heading": heading, "text": "\n".join(block)})
    return units


def read_memory(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    entries = parse_memory(text)
    if render(entries).decode().strip() != text.strip():
        raise ArchiveError("Existing memory has unsupported or unaccounted content; reconcile it explicitly before rewriting.")
    return entries


def parse_memory(text: str) -> list[dict]:
    matches = list(MARKER.finditer(text))
    if not matches:
        raise ArchiveError("Existing project memory has no archive-entry markers; adopt it explicitly before rewriting.")
    entries = []
    for i, marker in enumerate(matches):
        try:
            metadata = json.loads(marker.group(1))
        except ValueError as error:
            raise ArchiveError(f"Invalid memory marker: {error}") from error
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[marker.end():end].strip()
        # Domain headings preceding the next marker are outside this entry.
        body = re.split(r"\n## [^#]", body, maxsplit=1)[0].strip()
        title, separator, content = body.partition("\n")
        if not separator or not title.startswith("### "):
            raise ArchiveError("Each memory marker must precede its title and body.")
        shown_title = title[4:]
        prefix = metadata["id"] + ": "
        metadata.update(title=shown_title.removeprefix(prefix), text=content.strip())
        entries.append(metadata)
    return entries


def render(entries: list[dict]) -> bytes:
    lines = ["# Project memory", "",
             "Current product behavior, constraints, decisions and open follow-ups. "
             "Consult relevant entries when specifying or analyzing impact.", ""]
    for domain in sorted({e["domain"] for e in entries}):
        lines.extend([f"## {domain}", ""])
        for entry in sorted((e for e in entries if e["domain"] == domain), key=lambda e: e["id"]):
            metadata = {k: entry[k] for k in ("id", "domain", "kind", "sources", "evidence")}
            lines.extend(["<!-- archive-entry " + json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) + " -->",
                          "### " + entry["id"] + ": " + entry["title"], "", entry["text"].strip(), ""])
    return ("\n".join(lines).rstrip() + "\n").encode()


def validate_knowledge(repo: Repository, run: dict, candidate: dict) -> bytes:
    units = {u["id"]: u for u in run["units"]}
    entries = candidate.get("entries", [])
    if not isinstance(entries, list) or not entries:
        raise ArchiveError("Candidate needs reconciled memory entries, not an empty document.")
    ids = [e.get("id", "") for e in entries]
    registry_path = repo.path(REGISTRY)
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    if set(ids) & set(registry.get("retired_memory_ids", {})):
        raise ArchiveError("A retired memory ID cannot be reused.")
    if len(set(ids)) != len(ids) or any(not ID.fullmatch(i) for i in ids):
        raise ArchiveError("Memory IDs must be unique stable PM-<slug> identifiers.")
    for entry in entries:
        if entry.get("kind") not in ("behavior", "decision", "limit", "follow-up", "dependency", "lesson"):
            raise ArchiveError("Unknown memory entry kind.")
        for field in ("domain", "title", "text"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ArchiveError(f"Memory entry needs {field}.")
        if "\n" in entry["title"] or "\n" in entry["domain"] or "<!-- archive-entry" in entry["text"]:
            raise ArchiveError("Invalid heading or embedded memory marker.")
        if re.search(r"^#{1,2}\s", entry["text"], re.M):
            raise ArchiveError("Memory entry text cannot contain document/domain headings; use level 3 or deeper.")
        if re.search(r"\b(?:TODO|TBD|NEEDS CLARIFICATION|UNRESOLVED CONFLICT)\b|^(?:<<<<<<<|=======|>>>>>>>)", entry["text"], re.M):
            raise ArchiveError("Resolve candidate conflict/placeholders before archiving.")
        sources = entry.get("sources", [])
        if not isinstance(sources, list) or not sources:
            raise ArchiveError(f"Entry {entry['id']} needs source provenance.")
        for source in sources:
            repo.blob(source["commit"], source["path"])
            if source["commit"] == run["checkpoint"] and source.get("unit") not in units:
                raise ArchiveError("New checkpoint provenance must name an inventoried unit.")
            if source["commit"] == run["checkpoint"] and units[source["unit"]]["path"] != source["path"]:
                raise ArchiveError("Source path does not match its inventoried unit.")
        if not isinstance(entry.get("evidence"), list):
            raise ArchiveError("Every entry needs an evidence list (empty only for non-behavior entries).")
        if entry["kind"] == "behavior" and not entry["evidence"]:
            raise ArchiveError("Current behavior needs committed implementation/test evidence.")
        for evidence in entry["evidence"]:
            repo.blob(evidence["commit"], evidence["path"])
            if evidence["path"].startswith("specs/"):
                raise ArchiveError("A specification is not implementation evidence.")
            if run["retire"] and evidence["commit"] != run["checkpoint"]:
                raise ArchiveError("Retired behavior requires evidence from the current checkpoint.")
        if entry["kind"] == "behavior":
            present = False
            for evidence in entry["evidence"]:
                try:
                    repo.blob(run["checkpoint"], evidence["path"])
                    present = True
                except ArchiveError:
                    continue
            if not present:
                raise ArchiveError("Current behavior needs an evidence path present in the current checkpoint.")
        # Local links must survive deletion. Historical sources use the metadata above.
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", entry["text"]):
            if target.startswith(("https://", "http://", "#")):
                continue
            target = target.split("#", 1)[0]
            if not target or Repository.within(target, run["specs"]) or not repo.path(target).is_file():
                raise ArchiveError(f"Memory link would not survive archive: {target}")
    coverage = candidate.get("coverage", {})
    if set(coverage) != set(units):
        raise ArchiveError("Every inventoried source unit must have exactly one coverage disposition.")
    for unit, disposition in coverage.items():
        action = disposition.get("action")
        targets = disposition.get("memory_ids", [])
        if action not in ("retained", "merged", "superseded", "omitted"):
            raise ArchiveError(f"Unknown coverage disposition for {unit}.")
        if action == "omitted":
            if not disposition.get("reason", "").strip() or targets:
                raise ArchiveError("Omitted source units need a reason and no target IDs.")
        elif not targets or any(target not in ids for target in targets):
            raise ArchiveError("Retained/merged/superseded units must resolve to memory IDs.")
        for target in targets:
            entry = entries[ids.index(target)]
            if not any(s.get("unit") == unit and s["commit"] == run["checkpoint"] for s in entry["sources"]):
                raise ArchiveError("Coverage target lacks the corresponding source provenance.")
    old = {e["id"]: e for e in run["previous_entries"]}
    removed = candidate.get("removed", {})
    if set(removed) != set(old) - set(ids):
        raise ArchiveError("Every removed previous memory ID needs an explicit disposition.")
    for old_id, reason in removed.items():
        if not reason.get("reason", "").strip() or reason.get("source_unit") not in units:
            raise ArchiveError("Removed memory entries need a reason and current source unit.")
        if reason.get("replacement") is not None and reason["replacement"] not in ids:
            raise ArchiveError("Superseding memory ID does not exist.")
    rendered = render(entries)
    # Check the exact serializer/parser pair before any publication.
    for entry in entries:
        if entry["text"] != entry["text"].strip():
            raise ArchiveError("Memory entry text must be trimmed for a lossless round-trip.")
    if parse_memory(rendered.decode()) != sorted(entries, key=lambda e: (e["domain"], e["id"])):
        raise ArchiveError("Memory candidate is not lossless through rendering and parsing.")
    return rendered
