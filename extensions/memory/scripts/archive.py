#!/usr/bin/env python3
"""Sanduq Spec Kit Memory archival. All CLI results are JSON; failures exit 1."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from contextlib import nullcontext

from git_state import ArchiveError, Repository, atomic_write, digest, write_json
from memory import MEMORY, REGISTRY, inventory, read_memory, validate_knowledge

EXTENSION = ".specify/extensions/memory"
POLICY = ".specify/memory-policy.json"
PRODUCT_PREFIXES = ("src/", "tests/", "scripts/", "e2e/")
PRODUCT_FILES = ("Directory.Build.props", "global.json", "package.json", "package-lock.json")
GUARD_PATHS = [f"{directory}/{language}/create-new-feature.{suffix}"
               for directory in (".specify/scripts", ".specify/extensions/git/scripts")
               for language, suffix in (("bash", "sh"), ("powershell", "ps1"))]
GUARD_PATHS += [f".specify/extensions/git/scripts/{language}/auto-commit.{suffix}"
                for language, suffix in (("bash", "sh"), ("powershell", "ps1"))]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, default=None):
    if not path.exists() and default is not None:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ArchiveError(f"Cannot read JSON at {path}: {error}") from error


def verification_report(run: dict) -> dict:
    """Report an explicit manual override without turning a skip into a pass."""
    reason = run.get("skip_verification")
    if reason is None:
        return {"status": "passed" if run.get("phase") == "done" else "required"}
    if (run.get("automatic") or not isinstance(reason, str) or not reason.strip()
            or len(reason.strip()) > 500
            or not reason.isprintable()):
        raise ArchiveError("Skipping verification requires a nonempty single-line reason of at most 500 characters and manual selection.")
    return {"status": "skipped", "reason": reason.strip()}


class Archive:
    def __init__(self, root: str | Path):
        self.repo = Repository(root)
        self.policy = load(self.repo.path(POLICY))
        if self.policy.get("schema_version") != 1:
            raise ArchiveError("Unsupported memory policy. Run the memory init command first.")
        if self.policy.get("memory_path", MEMORY) != MEMORY or self.policy.get("fixture_root", "tests/Fixtures/spec-memory") != "tests/Fixtures/spec-memory":
            raise ArchiveError("Memory and fixture locations are fixed for this extension version.")
        branch = self.policy.get("target_branch", "")
        if not isinstance(branch, str) or not branch or branch.startswith("-"):
            raise ArchiveError("Configure a valid target_branch in .specify/memory-policy.json.")
        self.repo.git("check-ref-format", "--branch", branch)
        self.product_prefixes = tuple(self.policy.get("product_prefixes", PRODUCT_PREFIXES))
        self.product_files = tuple(self.policy.get("product_files", PRODUCT_FILES))
        for prefix in self.product_prefixes:
            if not isinstance(prefix, str) or not prefix.endswith("/"):
                raise ArchiveError("Product prefixes must be canonical directories with a trailing slash.")
            self.repo.path(prefix[:-1])
        for path in self.product_files:
            self.repo.path(path)

    def policy_hash(self) -> str:
        values = [POLICY.encode(), self.repo.path(POLICY).read_bytes()]
        root = self.repo.path(EXTENSION)
        for file in sorted(root.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts and "tests" not in file.relative_to(root).parts:
                values.extend([file.relative_to(root).as_posix().encode(), file.read_bytes()])
        for path in self.approval_paths():
            values.extend([path.encode(), self.repo.path(path).read_bytes()])
        for path in ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"):
            target = self.repo.path(path)
            if target.exists():
                block = re.search(r"<!-- SANDUQ MEMORY SESSION START -->.*?<!-- SANDUQ MEMORY SESSION END -->", target.read_text(encoding="utf-8"), re.S)
                values.extend([path.encode(), block.group().encode() if block else b"missing"])
        config = self.repo.path(".specify/extensions.yml")
        if config.exists():
            own_hooks = re.findall(r"^  - extension: memory\n(?:(?!^  - |^  [a-z_]+:).*(?:\n|$))*", config.read_text(encoding="utf-8"), re.M)
            values.extend([b"hooks", "\n".join(own_hooks).encode()])
        return digest(b"\0".join(values))

    def approval_paths(self) -> list[str]:
        paths = list(GUARD_PATHS)
        for command in self.repo.path(EXTENSION + "/commands").glob("*.md"):
            for host in (".agents", ".claude"):
                paths.append(f"{host}/skills/speckit-memory-{command.stem}/SKILL.md")
            for host, suffix in (("agents", "agent"), ("prompts", "prompt")):
                paths.append(f".github/{host}/speckit.memory.{command.stem}.{suffix}.md")
        return sorted(p for p in paths if self.repo.path(p).is_file())

    def approval(self) -> dict:
        approval = load(self.repo.state / "approval.json", {})
        if approval.get("policy_hash") != self.policy_hash():
            raise ArchiveError("Automatic mode is disabled or needs policy/implementation review and renewal.")
        return approval

    def enable(self, approved_hash: str) -> dict:
        if approved_hash != self.policy_hash():
            raise ArchiveError("Review the current policy and pass its exact policy_hash to enable.")
        if not self.policy.get("checks"):
            raise ArchiveError("Configure verification commands before enabling automatic archival.")
        self.repo.check_scope([EXTENSION], clean=True)
        committed_integration = [POLICY] + [p for p in self.approval_paths() if not p.startswith(".agents/")]
        committed_integration += [p for p in ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md", ".specify/extensions.yml")
                                  if self.repo.path(p).exists()]
        self.repo.check_scope(committed_integration, clean=True)
        approval = {"policy_hash": approved_hash, "enabled_at": now(), "root": str(self.repo.root)}
        write_json(self.repo.state / "approval.json", approval)
        return approval

    def spec(self, name: str) -> str:
        path = self.repo.path(name)
        if path.parent != self.repo.root / "specs" or not re.fullmatch(r"\d{3,}(?:-[a-zA-Z0-9]+)+", path.name):
            raise ArchiveError("Select a full feature directory directly under specs/.")
        if not path.is_dir():
            raise ArchiveError(f"Feature directory does not exist: {name}")
        return name

    def queue(self, spec: str, checks: list[str] | None = None) -> dict:
        spec = self.spec(spec)
        approval = self.approval()
        branch = self.repo.git("branch", "--show-current").decode().strip()
        if branch == self.policy["target_branch"]:
            raise ArchiveError("Automatic work must be queued on its implementation branch before merge.")
        checks = checks or self.policy.get("default_checks", [])
        self.require_checks(checks, [])
        base = self.repo.git("merge-base", "HEAD", self.policy["target_branch"]).decode().strip()
        changed = set(self.repo.names("diff", "--name-only", "-z", base, "HEAD")) | self.repo.dirty()
        links = {p for p, details in self.repo.index().items() if details.startswith("160000 ")}
        merge_inputs = {p: (self.product_state()[p] if p in links else self.repo.file_hash(p))
                        for p in changed if p.startswith(self.product_prefixes) or p in self.product_files or p in links}
        self.require_checks(checks, list(merge_inputs))
        merge_inputs[spec + "/spec.md"] = self.repo.file_hash(spec + "/spec.md")
        queue = load(self.repo.state / "pending.json", {})
        queue[spec] = {"queued_at": now(), "enabled_at": approval["enabled_at"],
                       "root": str(self.repo.root), "head": self.repo.head(), "branch": branch,
                       "checks": checks, "base": base, "spec_hashes": self.spec_files([spec]), "merge_inputs": merge_inputs}
        write_json(self.repo.state / "pending.json", queue)
        return {"queued": spec, "deletion": False}

    def product_state(self) -> dict:
        result = {}
        for path, details in self.repo.index().items():
            if details.startswith("160000 "):
                sub = self.repo.path(path)
                actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sub, capture_output=True)
                dirty = subprocess.run(["git", "status", "--porcelain"], cwd=sub, capture_output=True)
                expected = details.split()[1]
                if actual.returncode or dirty.returncode or actual.stdout.decode().strip() != expected or dirty.stdout:
                    raise ArchiveError(f"Submodule evidence is missing, dirty or differs from its gitlink: {path}")
                result[path] = expected
            elif path.startswith(self.product_prefixes) or path in self.product_files:
                result[path] = self.repo.file_hash(path)
        for path in self.repo.names("ls-files", "--others", "--exclude-standard", "-z"):
            if path.startswith(self.product_prefixes) or path in self.product_files:
                result[path] = self.repo.file_hash(path)
        return result

    def complete(self, spec: str) -> None:
        taskfile = self.repo.path(spec + "/tasks.md")
        if not taskfile.is_file():
            raise ArchiveError(f"Completion requires tasks.md: {spec}")
        tasks = re.findall(r"^\s*[-*]\s+\[([ xX])\]", taskfile.read_text(encoding="utf-8-sig"), re.M)
        if not tasks or any(marker == " " for marker in tasks):
            raise ArchiveError(f"Feature has absent or unfinished tasks: {spec}")
        context = load(self.repo.path(spec + "/.spec-context.json"), {})
        if context and context.get("status") not in ("implemented", "completed"):
            raise ArchiveError(f"Feature is not at a completion boundary: {spec}")

    def run_checks(self, checks: list[str]) -> list[dict]:
        if not checks or len(set(checks)) != len(checks):
            raise ArchiveError("Specify a nonempty unique list of approved checks.")
        results = []
        for name in checks:
            check = self.policy.get("checks", {}).get(name)
            if not check or not isinstance(check.get("argv"), list) or not check["argv"]:
                raise ArchiveError(f"Unknown/invalid approved check: {name}")
            argv = [sys.executable if a == "{python}" else a for a in check["argv"]]
            if any(not isinstance(a, str) for a in argv):
                raise ArchiveError("Verification commands must be argument arrays, not shell text.")
            logdir = self.repo.state / "checks"
            logdir.mkdir(parents=True, exist_ok=True)
            logfile = logdir / f"{uuid.uuid4().hex}.log"
            try:
                with logfile.open("wb") as log:
                    executed = subprocess.run(argv, cwd=self.repo.root, stdout=log, stderr=subprocess.STDOUT,
                                              timeout=check.get("timeout_seconds", 900), shell=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ArchiveError(f"Check {name} could not run: {error}. Log: {logfile}") from error
            if executed.returncode:
                raise ArchiveError(f"Check {name} failed ({executed.returncode}). Log: {logfile}")
            results.append({"name": name, "exit_code": 0, "log": str(logfile),
                            "sha256": digest(logfile.read_bytes())})
        return results

    def evidence_file(self, spec: str) -> Path:
        return self.repo.state / "verification" / (Path(spec).name + ".json")

    def verify(self, spec: str, checks: list[str], related: list[str] | None = None) -> dict:
        spec = self.spec(spec)
        self.complete(spec)
        related = related or []
        self.repo.check_scope([spec, *related])
        for path in related:
            self.repo.path(path)
            if self.repo.path(path).is_dir() or not path.startswith(self.product_prefixes):
                raise ArchiveError("Verification related scope must enumerate implementation files.")
        other = [p for p in self.repo.dirty() if p.startswith(self.product_prefixes) and p not in related]
        if other:
            raise ArchiveError(f"Commit other implementation changes or enumerate related files: {other}")
        head = self.repo.head()
        product = self.product_state()
        spec_hashes = self.spec_files([spec])
        self.require_checks(checks, self.verification_paths(spec))
        results = self.run_checks(checks)
        if head != self.repo.head() or product != self.product_state() or spec_hashes != self.spec_files([spec]):
            raise ArchiveError("Verification changed source inputs. Commit those changes and verify again.")
        result = {"spec": spec, "completed": True, "head": head, "policy_hash": self.policy_hash(),
                  "product": product, "spec_hashes": spec_hashes, "checks": results, "verified_at": now()}
        write_json(self.evidence_file(spec), result)
        return result

    def verification_paths(self, spec: str) -> list[str]:
        queued = load(self.repo.state / "pending.json", {}).get(spec, {})
        base = queued.get("base")
        if not base:
            introduced = self.repo.git("log", "--reverse", "--diff-filter=A", "--format=%H", "--", spec + "/spec.md").decode().splitlines()
            if introduced:
                parents = self.repo.git("rev-list", "--parents", "-n", "1", introduced[0]).decode().split()
                base = parents[1] if len(parents) > 1 else None
        if base:
            changed = set(self.repo.names("diff", "--name-only", "-z", base, "HEAD")) | self.repo.dirty()
        else:
            changed = set(self.product_state())
        links = {p for p, details in self.repo.index().items() if details.startswith("160000 ")}
        return sorted(p for p in changed if p.startswith(self.product_prefixes) or p in self.product_files or p in links)

    def spec_files(self, specs: list[str], *, allow_empty=False) -> dict:
        files = {}
        for spec in specs:
            directory = self.repo.path(spec)
            for path in sorted(directory.rglob("*")):
                relative = path.relative_to(self.repo.root).as_posix()
                self.repo.path(relative)
                if path.is_file():
                    files[relative] = self.repo.file_hash(relative)
                elif not path.is_dir():
                    raise ArchiveError(f"Nonregular archive artifact: {relative}")
            ignored = self.repo.names("ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--",
                                      *self.repo.pathspec([spec]))
            if ignored:
                raise ArchiveError(f"Ignored artifacts are not recoverable from the checkpoint: {ignored}")
        if not files and not allow_empty:
            raise ArchiveError("Selected features contain no artifacts.")
        return files

    @staticmethod
    def live_reference(text: str, specs: list[str]) -> bool:
        # Historical references name an immutable commit and can survive deletion.
        text = re.sub(r"(?:git:[0-9a-f]{40,64}:|git show [0-9a-f]{40,64}:)[^\s`<>\"]+", "", text)
        text = re.sub(r"https?://[^\s)]+/blob/[0-9a-f]{40,64}/[^\s)]+", "", text)
        text = re.sub(r"tests/Fixtures/spec-memory/[^\s`<>\"']+", "", text)
        for spec in specs:
            text = re.sub(r"(['\"]spec-memory['\"]\s*,\s*['\"])" + re.escape(Path(spec).name) + r"(['\"])", r"\1fixture\2", text)
        return any(re.search(r"specs[/\\\\]" + re.escape(Path(spec).name) + r"(?:[/\\\\\"'\s)<>`]|$)", text)
                   or re.search(r"['\"]specs['\"]\s*(?:,|/)\s*['\"]" + re.escape(Path(spec).name) + r"['\"]", text)
                   for spec in specs)

    def references(self, specs: list[str]) -> list[str]:
        result = []
        for path in self.repo.tracked():
            if (self.repo.within(path, specs) or path in (MEMORY, REGISTRY)
                    or path.startswith((".specify/extensions/", "tests/Fixtures/spec-memory/"))):
                continue
            target = self.repo.path(path)
            if not target.is_file():
                continue
            try:
                text = target.read_text(encoding="utf-8-sig")
            except UnicodeError:
                continue
            if self.live_reference(text, specs):
                result.append(path)
        return result

    def eligibility(self, spec: str) -> dict:
        self.complete(spec)
        evidence = load(self.evidence_file(spec), {})
        if not evidence.get("completed") or evidence.get("policy_hash") != self.policy_hash():
            raise ArchiveError(f"Run verified completion checks for {spec} under the current policy.")
        if evidence["product"] != self.product_state() or evidence["spec_hashes"] != self.spec_files([spec]):
            raise ArchiveError(f"Completion evidence is stale: {spec}")
        self.repo.git("merge-base", "--is-ancestor", evidence["head"], self.repo.head())
        return evidence

    def pending(self) -> dict:
        try:
            approval = self.approval()
        except ArchiveError as error:
            return {"enabled": False, "ready": [], "blocked": [], "reason": str(error),
                    **self.operational_state()}
        queue = load(self.repo.state / "pending.json", {})
        branch = self.repo.git("branch", "--show-current").decode().strip()
        result = {"enabled": True, "ready": [], "needs_verification": [], "blocked": [], **self.operational_state()}
        if result["guard_blockers"]:
            result["blocked"].append({"reason": "Archive number guards need reinstall/repair", "paths": result["guard_blockers"]})
            return result
        for spec, item in queue.items():
            try:
                if item["root"] != str(self.repo.root) or item["enabled_at"] != approval["enabled_at"]:
                    raise ArchiveError("Queue entry predates current enablement or belongs to another worktree.")
                if branch != self.policy["target_branch"]:
                    raise ArchiveError("Awaiting local merge/check-out of the configured target branch.")
                current_product = self.product_state()
                if any((current_product[p] if p in current_product else self.repo.file_hash(p)) != value
                       for p, value in item.get("merge_inputs", {}).items()):
                    raise ArchiveError("Queued feature inputs changed; re-queue after final review fixes or archive manually.")
                try:
                    self.repo.git("merge-base", "--is-ancestor", item["head"], "HEAD")
                except ArchiveError:
                    # Squash/rebase merges do not retain the queued commit. Require
                    # identical feature inputs on the configured target branch, then fresh verification.
                    inputs = item.get("merge_inputs", {})
                    if len(inputs) < 2:
                        raise ArchiveError("Queued implementation is not merged, or its squash/rebase inputs differ.") from None
                self.complete(self.spec(spec))
                try:
                    self.eligibility(spec)
                except ArchiveError as error:
                    result["needs_verification"].append({"spec": spec, "checks": item["checks"], "reason": str(error)})
                    continue
                result["ready"].append(spec)
            except ArchiveError as error:
                result["blocked"].append({"spec": spec, "reason": str(error)})
        return result

    def active_id(self) -> str | None:
        return load(self.repo.state / "active.json", {}).get("run_id")

    def operational_state(self) -> dict:
        active = self.active_id()
        phase = self.journal(active)["phase"] if active else None
        guards = []
        if self.repo.path(REGISTRY).exists():
            for path in self.policy.get("guard_paths", GUARD_PATHS):
                target = self.repo.path(path)
                if not target.exists() and path.startswith(".specify/extensions/git/") and "guard_paths" not in self.policy:
                    continue
                if not target.is_file():
                    guards.append(path)
                    continue
                text = target.read_text(encoding="utf-8-sig")
                if "pending --gate" not in text or ("create-new-feature" in path and "memory/scripts/numbering.py" not in text):
                    guards.append(path)
        lock = self.repo.state / "writer.lock"
        writer = load(lock, {}) if lock.exists() else None
        if writer:
            writer["state"] = self.repo.process_state(writer.get("pid"))
        return {"active_run": active, "active_phase": phase, "guard_blockers": guards, "writer": writer}

    def run_path(self, run_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ArchiveError("Invalid archive run ID.")
        return self.repo.state / "runs" / run_id

    def journal(self, run_id: str) -> dict:
        run = load(self.run_path(run_id) / "journal.json")
        if run["root"] != str(self.repo.root):
            raise ArchiveError("Resume this run in the worktree that prepared it.")
        return run

    def save(self, run: dict) -> None:
        write_json(self.run_path(run["run_id"]) / "journal.json", run)

    def prepare(self, specs: list[str], related: list[str], checks: list[str], *, automatic=False, retire="",
                skip_verification: str | None = None) -> dict:
        if self.active_id():
            raise ArchiveError("An archive is unfinished. Inspect/resume it before preparing another.")
        verification = verification_report({"skip_verification": skip_verification, "automatic": automatic})
        skip_verification = verification.get("reason")
        if skip_verification is not None and checks:
            raise ArchiveError("--skip-verification cannot combine with --check.")
        if (skip_verification is not None
                and self.repo.git("branch", "--show-current").decode().strip() != self.policy["target_branch"]):
            raise ArchiveError("Prepare a verification override on the configured target branch.")
        specs = sorted({self.spec(s) for s in specs})
        if not specs or (retire and (automatic or len(specs) != 1)):
            raise ArchiveError("Retirement selects exactly one explicit feature and never runs automatically.")
        if automatic:
            ready = self.pending()["ready"]
            if related or retire or any(spec not in ready for spec in specs):
                raise ArchiveError("Automatic mode accepts only ready queued features and committed scope.")
        if skip_verification is not None and not retire:
            for spec in specs:
                self.complete(spec)
        evidence = [self.eligibility(s) for s in specs] if not retire and skip_verification is None else []
        references = self.references(specs)
        # Repairs are enumerated before checkpointing. Their current edits cannot be silently attributed to archival.
        self.repo.check_scope(references + [MEMORY, REGISTRY], clean=True)
        files = self.spec_files(specs)
        for path in related:
            self.repo.path(path)
            if path not in self.repo.tracked() and not self.repo.path(path).is_file():
                raise ArchiveError(f"Related scope must enumerate existing or tracked files: {path}")
            if path.startswith(".specify/") or path in (MEMORY, REGISTRY) or self.repo.path(path).is_dir():
                raise ArchiveError("Related changes must be explicit implementation files, not directories or archive configuration.")
        scopes = sorted(set(specs + references + related + [p for p in (MEMORY, REGISTRY) if self.repo.path(p).exists()]))
        self.repo.check_scope(scopes, clean=automatic)
        # Other product edits make implementation evidence ambiguous even if the selected spec is untouched.
        outside_product = [p for p in self.repo.dirty() if p.startswith(self.product_prefixes) and p not in related]
        if outside_product:
            raise ArchiveError(f"Uncommitted implementation evidence needs explicit related scope: {outside_product}")
        all_checks = checks or sorted({c["name"] for e in evidence for c in e["checks"]})
        if skip_verification is None:
            self.require_checks(all_checks, references)
            if not retire:
                self.require_checks(all_checks, sorted({p for spec in specs for p in self.verification_paths(spec)}))
        run_id = uuid.uuid4().hex
        run = {"schema_version": 1, "run_id": run_id, "root": str(self.repo.root), "specs": specs,
               "retire": retire, "automatic": automatic, "skip_verification": skip_verification,
               "checks": all_checks, "scope": scopes,
               "references": references, "original_files": files, "memory_hash": self.repo.file_hash(MEMORY),
               "registry_hash": self.repo.file_hash(REGISTRY), "previous_entries": read_memory(self.repo.path(MEMORY)),
               "product": self.product_state(), "policy_hash": self.policy_hash(), "phase": "checkpoint",
               "created_at": now(), "input_head": self.repo.head(), "input_index": self.repo.scoped_index(scopes)}
        run["source_hashes"] = {p: self.repo.file_hash(p) for p in set(references + related)}
        pointer = self.repo.path(".specify/feature.json")
        run["local_pointer_hash"] = (self.repo.file_hash(".specify/feature.json")
                                     if pointer.exists() and self.live_reference(pointer.read_text(encoding="utf-8"), specs) else None)
        run["checkpoint_tree"] = self.repo.expected_tree(scopes)
        self.save(run)
        write_json(self.repo.state / "active.json", {"run_id": run_id})
        message = "[Spec Kit Archive] Checkpoint " + ", ".join(Path(s).name for s in specs)
        if skip_verification is not None:
            message += "\n\nVerification-Skipped: " + skip_verification
        checkpoint = self.repo.commit(scopes, message, run["checkpoint_tree"])
        run.update(checkpoint=checkpoint, phase="synthesis")
        self.verification_guard(run)
        run["units"] = inventory(self.repo, checkpoint, list(files))
        self.save(run)
        candidate = {"entries": run["previous_entries"], "coverage": {}, "removed": {}, "migrations": [], "repairs": []}
        write_json(self.run_path(run_id) / "candidate.json", candidate)
        return {"run_id": run_id, "checkpoint": checkpoint, "units": str(self.run_path(run_id) / "journal.json"),
                "candidate": str(self.run_path(run_id) / "candidate.json"), "references": references,
                "phase": run["phase"], "verification": verification}

    def require_checks(self, names: list[str], paths: list[str]) -> None:
        if not names or any(name not in self.policy.get("checks", {}) for name in names):
            raise ArchiveError("Select named verification commands from .specify/memory-policy.json.")
        for path in paths:
            if path.startswith(self.product_prefixes) or path in self.product_files or path.startswith(".github/workflows/") or self.repo.path(path).is_dir():
                if not any(fnmatch.fnmatchcase(path, glob) for name in names for glob in self.policy["checks"][name].get("covers", [])):
                    raise ArchiveError(f"No selected verification command covers repaired consumer: {path}")

    def candidate(self, run: dict) -> tuple[dict, bytes]:
        path = self.run_path(run["run_id"]) / "candidate.json"
        return load(path), path.read_bytes()

    def verification_guard(self, run: dict) -> dict:
        verification = verification_report(run)
        if run.get("checkpoint"):
            message = self.repo.git("show", "-s", "--format=%B", run["checkpoint"]).decode("utf-8")
            markers = [line.removeprefix("Verification-Skipped: ") for line in message.splitlines()
                       if line.startswith("Verification-Skipped: ")]
            expected = [verification["reason"]] if verification["status"] == "skipped" else []
            if markers != expected:
                raise ArchiveError("Journal override differs from checkpoint verification marker; use explicit recovery, not journal edits.")
        return verification

    def validate(self, run: dict) -> dict[str, bytes | None]:
        verification = self.verification_guard(run)
        candidate, raw = self.candidate(run)
        memory = validate_knowledge(self.repo, run, candidate)
        review = load(self.run_path(run["run_id"]) / "review.json", {})
        if (review.get("candidate_sha256") != digest(raw) or review.get("passed") is not True
                or not review.get("reviewer", "").strip() or not review.get("summary", "").strip()
                or review.get("findings") != []):
            raise ArchiveError("Independent critique must pass for the exact candidate hash with no unresolved findings.")
        if (verification["status"] == "skipped"
                and review.get("verification_override") != verification["reason"]):
            raise ArchiveError("Independent critique must acknowledge the exact verification override reason.")
        outputs = {MEMORY: memory, **{p: None for p in run["original_files"]}}
        for migration in candidate.get("migrations", []):
            source, destination = migration["source"], migration["destination"]
            if source not in run["original_files"]:
                raise ArchiveError("Only selected feature artifacts can become permanent fixtures.")
            expected = "tests/Fixtures/spec-memory/" + source.removeprefix("specs/")
            if destination != expected or self.repo.path(destination).exists() or destination in outputs:
                raise ArchiveError(f"Fixture destination must be new and exactly {expected}.")
            outputs[destination] = self.repo.blob(run["checkpoint"], source)
        repaired = set()
        for repair in candidate.get("repairs", []):
            path = repair["path"]
            if path not in run["references"] or path in repaired:
                raise ArchiveError("Repairs must uniquely name a preflight reference path.")
            content = self.repo.path(path).read_text(encoding="utf-8")
            for change in repair.get("replacements", []):
                before, after = change["before"], change["after"]
                if not before or before == after or content.count(before) != change.get("count", 1):
                    raise ArchiveError(f"Repair context/count changed: {path}")
                content = content.replace(before, after)
            if self.live_reference(content, run["specs"]):
                raise ArchiveError(f"Unresolved feature-folder reference after repair: {path}")
            outputs[path] = content.encode()
            repaired.add(path)
        if repaired != set(run["references"]):
            raise ArchiveError("All preflight references need explicit repairs.")
        if verification["status"] != "skipped":
            self.require_checks(run["checks"], list(repaired))
        registry = load(self.repo.path(REGISTRY), {"schema_version": 1, "archived": {}, "high_water": 0})
        for spec in run["specs"]:
            if spec in registry["archived"]:
                raise ArchiveError("Feature ID is already reserved in archive registry.")
            registry["archived"][spec] = {"checkpoint": run["checkpoint"], "retired": bool(run["retire"])}
            if verification["status"] == "skipped":
                registry["archived"][spec]["verification"] = verification
            match = re.match(r"specs/(\d{3,})-", spec)
            if match and not re.match(r"specs/\d{8}-\d{6}-", spec):
                registry["high_water"] = max(registry["high_water"], int(match.group(1)))
        registry.setdefault("retired_memory_ids", {}).update(
            {identifier: {"replacement": info.get("replacement")} for identifier, info in candidate.get("removed", {}).items()})
        outputs[REGISTRY] = (json.dumps(registry, indent=2) + "\n").encode()
        for path, content in outputs.items():
            if content is not None and self.repo.git("check-ignore", "--no-index", "--", path, ok=(0, 1)):
                raise ArchiveError(f"Archive output would be ignored and unrecoverable from Git: {path}")
        return outputs

    def source_guard(self, run: dict) -> None:
        if run["policy_hash"] != self.policy_hash():
            raise ArchiveError("Policy/implementation changed since preparation. Candidate cannot be applied.")
        if self.repo.git("branch", "--show-current").decode().strip() != self.policy["target_branch"]:
            raise ArchiveError("Deletion requires the locally merged configured target branch.")
        self.repo.git("merge-base", "--is-ancestor", run["checkpoint"], "HEAD")
        if self.repo.file_hash(MEMORY) != run["memory_hash"] or self.repo.file_hash(REGISTRY) != run["registry_hash"]:
            raise ArchiveError("Project memory/registry changed. Reconcile a new candidate; do not apply the stale proposal.")
        if self.spec_files(run["specs"]) != run["original_files"] or self.product_state() != run["product"]:
            raise ArchiveError("Feature artifacts or implementation evidence changed since preparation.")
        if any(self.repo.file_hash(p) != h for p, h in run["source_hashes"].items()):
            raise ArchiveError("A repair/related input changed since checkpointing.")
        if self.repo.git("diff", "--name-only", run["checkpoint"], "HEAD", "--", *self.repo.pathspec(run["scope"])):
            raise ArchiveError("Merged history changed archive scope since checkpointing.")
        if self.repo.scoped_index(run["scope"]) != run["input_index"]:
            raise ArchiveError("Unrelated index changed during this archive. Resolve before resuming.")

    def publishing_guard(self, run: dict) -> None:
        current = self.product_state()
        for path in set(current) | set(run["product"]):
            expected = {run["product"].get(path)}
            if path in run["after"]:
                expected.add(run["after"][path])
            if current.get(path) not in expected:
                raise ArchiveError(f"Implementation evidence changed during publication: {path}")

    def cleanup_terminal(self, run: dict) -> None:
        queue = load(self.repo.state / "pending.json", {})
        for spec in run["specs"]:
            queue.pop(spec, None)
        write_json(self.repo.state / "pending.json", queue)
        if self.active_id() == run["run_id"]:
            (self.repo.state / "active.json").unlink(missing_ok=True)

    def rollback(self, run_id: str) -> dict:
        run = self.journal(run_id)
        if run["phase"] == "rolled-back":
            self.cleanup_terminal(run)
            return {"run_id": run_id, "phase": "rolled-back", "checkpoint": run["checkpoint"]}
        if self.active_id() != run_id or run["phase"] not in ("publishing", "checking", "committing", "rolling-back"):
            raise ArchiveError("Rollback requires an active published run that has not made its final commit.")
        if self.repo.head() != run["final_parent"]:
            raise ArchiveError("HEAD changed; inspect the committed archive before considering recovery.")
        if self.repo.scoped_index(run["scope"]) != run["input_index"]:
            raise ArchiveError("Unrelated index changed; preserving user work before rollback.")
        self.publishing_guard(run)
        for path in run["outputs"]:
            if self.repo.file_hash(path) not in (run["before"][path], run["after"][path]):
                raise ArchiveError(f"Unexpected edit to archive output; preserving user work: {path}")
        run["phase"] = "rolling-back"
        self.save(run)
        # Restore recorded worktree bytes, preserving CRLF and the exact checkpoint inputs.
        for path, encoded in run["original_outputs"].items():
            target = self.repo.path(path)
            if encoded is None:
                target.unlink(missing_ok=True)
            else:
                atomic_write(target, base64.b64decode(encoded))
        indexed = [p for p in self.repo.index() if p in run["outputs"]]
        if indexed:
            self.repo.git("restore", "--source=" + run["final_parent"], "--staged", "--", *self.repo.pathspec(indexed))
        run.update(phase="rolled-back", rolled_back_at=now())
        self.save(run)
        self.cleanup_terminal(run)
        return {"run_id": run_id, "phase": "rolled-back", "checkpoint": run["checkpoint"]}

    def abandon(self, run_id: str) -> dict:
        run = self.journal(run_id)
        if self.active_id() != run_id or run["phase"] not in ("checkpoint", "synthesis"):
            raise ArchiveError("Only an unpublished active proposal can be abandoned. Resume a published transaction.")
        run.update(phase="abandoned", abandoned_at=now())
        self.save(run)
        (self.repo.state / "active.json").unlink()
        return {"run_id": run_id, "phase": "abandoned", "checkpoint": run.get("checkpoint"), "files_changed": False}

    def finalize(self, run_id: str) -> dict:
        run = self.journal(run_id)
        self.verification_guard(run)
        if run["phase"] == "done":
            self.cleanup_terminal(run)
            return {"run_id": run_id, "phase": "done", "checkpoint": run["checkpoint"], "final_commit": run["final_commit"],
                    "verification": verification_report(run)}
        if self.active_id() != run_id:
            raise ArchiveError("This is not the active archive run.")
        if run["automatic"]:
            self.approval()
        if run["phase"] == "checkpoint":
            # Recover the commit->journal interruption without creating a second checkpoint.
            if (self.repo.git("rev-parse", "HEAD^{tree}").decode().strip() != run["checkpoint_tree"]
                    or self.repo.git("rev-parse", "HEAD^").decode().strip() != run["input_head"]):
                raise ArchiveError("Checkpoint was not recorded. Inspect Git before resuming; no reset performed.")
            run.update(checkpoint=self.repo.head(), phase="synthesis")
            run["units"] = inventory(self.repo, run["checkpoint"], list(run["original_files"]))
            self.save(run)
            raise ArchiveError("Checkpoint recovered. Create/review candidate.json before finalizing.")
        if run["phase"] == "synthesis":
            self.source_guard(run)
            outputs = self.validate(run)
            scope = sorted(set(run["scope"] + list(outputs)))
            self.repo.check_scope(scope)
            run["outputs"] = {p: None if data is None else base64.b64encode(data).decode() for p, data in outputs.items()}
            run["before"] = {p: self.repo.file_hash(p) for p in outputs}
            run["original_outputs"] = {p: base64.b64encode(self.repo.path(p).read_bytes()).decode()
                                       if run["before"][p] is not None else None for p in outputs}
            run["after"] = {p: None if data is None else digest(data) for p, data in outputs.items()}
            run["scope"] = scope
            run["input_index"] = self.repo.scoped_index(scope)
            run["final_parent"] = self.repo.head()
            run["phase"] = "publishing"
            self.save(run)
        if run["policy_hash"] != self.policy_hash():
            raise ArchiveError("Implementation/policy changed; inspect the unfinished run before recovery.")
        if self.repo.git("branch", "--show-current").decode().strip() != self.policy["target_branch"]:
            raise ArchiveError("Resume finalization on the configured target branch.")
        for path in run["outputs"]:
            if self.repo.file_hash(path) not in (run["before"][path], run["after"][path]):
                raise ArchiveError(f"Unexpected edit to archive output; preserving user work: {path}")
        self.publishing_guard(run)
        for spec in run["specs"]:
            if self.repo.path(spec).exists():
                current = self.spec_files([spec], allow_empty=True)
                if set(current) - set(run["original_files"]):
                    raise ArchiveError("New feature artifacts appeared during archive publication.")
        if run["phase"] == "publishing":
            if self.repo.head() != run["final_parent"]:
                raise ArchiveError("HEAD changed during publication; inspect before resuming.")
            if self.repo.scoped_index(run["scope"]) != run["input_index"]:
                raise ArchiveError("Unrelated index changed during publication.")
            # Refuse new files in a selected folder, even during a partially completed delete.
            for spec in run["specs"]:
                if self.repo.path(spec).exists():
                    current = self.spec_files([spec], allow_empty=True)
                    if set(current) - set(run["original_files"]):
                        raise ArchiveError("New feature artifacts appeared during archive publication.")
            for path, encoded in run["outputs"].items():
                if encoded is not None and self.repo.file_hash(path) != run["after"][path]:
                    atomic_write(self.repo.path(path), base64.b64decode(encoded))
            for path, encoded in run["outputs"].items():
                if encoded is None:
                    self.repo.path(path).unlink(missing_ok=True)
            for spec in run["specs"]:
                directory = self.repo.path(spec)
                if directory.exists():
                    for subdir in sorted((p for p in directory.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                        subdir.rmdir()
                    directory.rmdir()
            run["phase"] = "checking"
            self.save(run)
        if run["phase"] == "checking":
            if self.repo.head() != run["final_parent"] or self.repo.scoped_index(run["scope"]) != run["input_index"]:
                raise ArchiveError("HEAD/unrelated index changed during checking; inspect before recovery.")
            remaining = self.references(run["specs"])
            if remaining:
                raise ArchiveError(f"References still require deleted feature folders: {remaining}")
            run["final_checks"] = None if run.get("skip_verification") is not None else self.run_checks(run["checks"])
            self.publishing_guard(run)
            for path, expected in run["after"].items():
                if self.repo.file_hash(path) != expected:
                    raise ArchiveError(f"Verification changed archive outputs: {path}")
            run["final_tree"] = self.repo.expected_tree(run["scope"])
            run["phase"] = "committing"
            self.save(run)
        if run["phase"] == "committing":
            if self.repo.scoped_index(run["scope"]) != run["input_index"]:
                raise ArchiveError("Unrelated index changed before final commit; preserving user work.")
            if any(self.repo.file_hash(p) != expected for p, expected in run["after"].items()):
                raise ArchiveError("Archive outputs changed after verification; preserve edits and inspect before recovery.")
            if self.repo.head() != run["final_parent"]:
                # Recover a successful final commit whose journal update was interrupted.
                if (self.repo.git("rev-parse", "HEAD^{tree}").decode().strip() != run["final_tree"]
                        or self.repo.git("rev-parse", "HEAD^").decode().strip() != run["final_parent"]):
                    raise ArchiveError("Unexpected commit during archive. Inspect Git without resetting.")
                final = self.repo.head()
            else:
                message = "[Spec Kit Archive] Finalize " + ", ".join(Path(s).name for s in run["specs"])
                if run.get("skip_verification") is not None:
                    message += "\n\nVerification-Skipped: " + run["skip_verification"]
                final = self.repo.commit(run["scope"], message, run["final_tree"])
            self.publishing_guard(run)
            pointer = ".specify/feature.json"
            if run.get("local_pointer_hash") and self.repo.file_hash(pointer) == run["local_pointer_hash"]:
                self.repo.path(pointer).unlink()
            run.update(phase="done", final_commit=final, finalized_at=now())
            self.save(run)
            self.cleanup_terminal(run)
        return {"run_id": run_id, "phase": run["phase"], "checkpoint": run["checkpoint"], "final_commit": run.get("final_commit"),
                "verification": verification_report(run)}

    def status(self) -> dict:
        run_id = self.active_id()
        return {"policy_hash": self.policy_hash(), "pending": self.pending(),
                "active": self.journal(run_id) if run_id else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="verb", required=True)
    sub.add_parser("status")
    pending = sub.add_parser("pending")
    pending.add_argument("--gate", action="store_true", help="Block new specification/commit workflows while recovery is required.")
    sub.add_parser("policy")
    enable = sub.add_parser("enable")
    enable.add_argument("--approve-hash", required=True)
    sub.add_parser("disable")
    queue = sub.add_parser("queue")
    queue.add_argument("--spec", required=True)
    queue.add_argument("--check", action="append", default=[])
    verify = sub.add_parser("verify")
    verify.add_argument("--spec", required=True)
    verify.add_argument("--check", action="append", required=True)
    verify.add_argument("--related", action="append", default=[])
    verify.add_argument("--complete", action="store_true", required=True,
                        help="Explicitly declare that implementation and required QA/review/documentation are complete.")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--spec", action="append", default=[])
    prepare.add_argument("--all-completed", action="store_true")
    prepare.add_argument("--related", action="append", default=[])
    prepare.add_argument("--check", action="append", default=[])
    prepare.add_argument("--automatic", action="store_true")
    prepare.add_argument("--retire-reason", default="")
    prepare.add_argument("--skip-verification", metavar="REASON",
                         help="Manually archive explicit specs without verification commands; record why checks are skipped.")
    for verb in ("validate", "finalize", "abandon", "rollback"):
        command = sub.add_parser(verb)
        command.add_argument("--run", required=True)
    args = parser.parse_args()
    try:
        archive = Archive(args.root)
        with nullcontext() if args.verb in ("status", "pending", "policy") else archive.repo.lock():
            if args.verb == "status":
                result = archive.status()
            elif args.verb == "pending":
                result = archive.pending()
                if args.gate and (result.get("active_run") or result.get("writer") or result.get("guard_blockers")):
                    print(json.dumps({"success": False, "error": "Archive recovery/busy writer/number guard blocks new specification and commit workflows.", "data": result}))
                    return 1
            elif args.verb == "policy":
                result = {"policy": archive.policy, "policy_hash": archive.policy_hash()}
            elif args.verb == "enable":
                result = archive.enable(args.approve_hash)
            elif args.verb == "disable":
                (archive.repo.state / "approval.json").unlink(missing_ok=True)
                result = {"enabled": False}
            elif args.verb == "queue":
                result = archive.queue(args.spec, args.check)
            elif args.verb == "verify":
                result = archive.verify(args.spec, args.check, args.related)
            elif args.verb == "prepare":
                specs = args.spec
                if args.skip_verification is not None and (args.automatic or args.all_completed):
                    raise ArchiveError("--skip-verification requires explicit manual --spec selection.")
                if args.all_completed:
                    if specs or args.retire_reason:
                        raise ArchiveError("--all-completed cannot combine with explicit selection or retirement.")
                    specs = []
                    skipped = []
                    for directory in sorted((archive.repo.root / "specs").iterdir()):
                        if directory.is_dir():
                            name = "specs/" + directory.name
                            try:
                                archive.eligibility(archive.spec(name))
                                specs.append(name)
                            except ArchiveError as error:
                                skipped.append({"spec": name, "reason": str(error)})
                    if not specs:
                        result = {"prepared": False, "skipped": skipped}
                    else:
                        result = archive.prepare(specs, args.related, args.check, automatic=args.automatic)
                        result["skipped"] = skipped
                else:
                    result = archive.prepare(specs, args.related, args.check, automatic=args.automatic,
                                             retire=args.retire_reason, skip_verification=args.skip_verification)
            elif args.verb == "validate":
                run = archive.journal(args.run)
                archive.source_guard(run)
                result = {"valid": True, "paths": sorted(archive.validate(run))}
            elif args.verb == "abandon":
                result = archive.abandon(args.run)
            elif args.verb == "rollback":
                result = archive.rollback(args.run)
            else:
                result = archive.finalize(args.run)
        print(json.dumps({"success": True, "data": result}, ensure_ascii=False))
        return 0
    except (ArchiveError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"success": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
