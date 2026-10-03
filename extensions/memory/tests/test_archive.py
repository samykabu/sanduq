from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from archive import Archive, EXTENSION, POLICY
from git_state import ArchiveError, digest, write_json
from memory import MEMORY, REGISTRY, read_memory, validate_knowledge
from numbering import reservations

FEATURE = "specs/007-invoice"
CONTRACT = FEATURE + "/contracts/rule.json"
FIXTURE = "tests/Fixtures/spec-memory/007-invoice/contracts/rule.json"


class ArchiveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="memory-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git("init", "-b", "develop")
        for key, value in {"user.name": "Archive Test", "user.email": "archive@example.invalid",
                           "core.autocrlf": "false", "core.hooksPath": ".git/hooks", "commit.gpgsign": "false"}.items():
            self.git("config", key, value)
        self.write(EXTENSION + "/extension.yml", "version: 1\n")
        self.write(POLICY, json.dumps({"schema_version": 1, "target_branch": "develop", "default_checks": ["consumer"],
            "checks": {"consumer": {"argv": ["{python}", "tests/consumer.py"], "covers": ["src/*", "tests/*"], "timeout_seconds": 20}}}))
        self.write(FEATURE + "/spec.md", "# Invoice\n\nFR-001: Invoices use EUR.\n\n## Follow-up\n\nConfirm retention.\n")
        self.write(FEATURE + "/tasks.md", "# Tasks\n\n- [x] T001 Implement and verify\n")
        self.write(CONTRACT, '{"currency":"EUR"}\n')
        self.write(FEATURE + "/capture.png", b"\x89PNG\0capture")
        self.write("src/app.py", "CURRENCY = 'EUR'\n")
        self.write("tests/consumer.py", "import json\nfrom pathlib import Path\nassert json.loads(Path('" + CONTRACT + "').read_text())['currency'] == 'EUR'\n")
        self.write("README.md", "Current contract: " + CONTRACT + "\n")
        self.write("unrelated.txt", "initial\n")
        self.git("add", "-A")
        self.git("commit", "-m", "Initial product")
        self.archive = Archive(self.root)

    def git(self, *args):
        run = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        if run.returncode:
            raise AssertionError(run.stderr.decode(errors="replace"))
        return run.stdout.decode().strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())

    def prepare(self, **options):
        self.archive.verify(FEATURE, ["consumer"])
        return self.archive.prepare([FEATURE], [], ["consumer"], **options)

    def candidate(self, prepared):
        run = self.archive.journal(prepared["run_id"])
        unit = next(u for u in run["units"] if "FR-001" in u.get("text", ""))
        entry = {"id": "PM-invoice-currency", "domain": "Billing", "kind": "behavior", "title": "Invoice currency",
                 "text": "Invoices use EUR.", "sources": [{"commit": run["checkpoint"], "path": unit["path"], "unit": unit["id"]}],
                 "evidence": [{"commit": run["checkpoint"], "path": "src/app.py"}]}
        coverage = {u["id"]: {"action": "omitted", "memory_ids": [], "reason": "Execution detail or recoverable artifact"} for u in run["units"]}
        coverage[unit["id"]] = {"action": "retained", "memory_ids": [entry["id"]]}
        candidate = {"entries": [entry], "coverage": coverage, "removed": {},
                     "migrations": [{"source": CONTRACT, "destination": FIXTURE}],
                     "repairs": [{"path": "tests/consumer.py", "replacements": [{"before": CONTRACT, "after": FIXTURE, "count": 1}]},
                                 {"path": "README.md", "replacements": [{"before": CONTRACT,
                                  "after": f"git:{run['checkpoint']}:{CONTRACT}", "count": 1}]}]}
        self.save_candidate(prepared, candidate)
        return candidate

    def save_candidate(self, prepared, candidate):
        directory = self.archive.run_path(prepared["run_id"])
        write_json(directory / "candidate.json", candidate)
        write_json(directory / "review.json", {"candidate_sha256": digest((directory / "candidate.json").read_bytes()),
            "reviewer": "independent test reviewer", "passed": True, "summary": "Inputs and repairs independently reviewed", "findings": []})

    def test_two_commits_fixture_relocation_and_unrelated_index(self):
        self.write("unrelated.txt", "staged owner change\n")
        self.git("add", "unrelated.txt")
        self.write("unrelated.txt", "unstaged owner change\n")
        before_index = self.git("show", ":unrelated.txt")
        initial = self.git("rev-parse", "HEAD")
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        result = self.archive.finalize(prepared["run_id"])
        self.assertEqual("done", result["phase"])
        self.assertFalse((self.root / FEATURE).exists())
        self.assertEqual(b'{"currency":"EUR"}\n', (self.root / FIXTURE).read_bytes())
        self.assertEqual(before_index, self.git("show", ":unrelated.txt"))
        self.assertEqual("unstaged owner change\n", (self.root / "unrelated.txt").read_text())
        self.assertEqual("2", self.git("rev-list", "--count", initial + "..HEAD"))
        for commit in (prepared["checkpoint"], result["final_commit"]):
            self.assertEqual("initial", self.git("show", commit + ":unrelated.txt"))
        self.assertEqual('{"currency":"EUR"}', self.git("show", prepared["checkpoint"] + ":" + CONTRACT))
        self.assertEqual(candidate["entries"], read_memory(self.root / MEMORY))
        self.assertEqual(result, self.archive.finalize(prepared["run_id"]))
        self.assertEqual((7, {7}), reservations(self.root / "specs"))

    def test_missing_source_coverage_blocks_before_deletion(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        candidate["coverage"].pop(next(iter(candidate["coverage"])))
        self.save_candidate(prepared, candidate)
        with self.assertRaisesRegex(ArchiveError, "Every inventoried"):
            self.archive.finalize(prepared["run_id"])
        self.assertTrue((self.root / FEATURE).exists())
        self.assertFalse((self.root / MEMORY).exists())

    def test_candidate_edit_invalidates_critique(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        candidate["entries"][0]["text"] += " Altered after review."
        write_json(self.archive.run_path(prepared["run_id"]) / "candidate.json", candidate)
        with self.assertRaisesRegex(ArchiveError, "Independent critique"):
            self.archive.finalize(prepared["run_id"])

    def test_stale_memory_blocks_before_deletion(self):
        prepared = self.prepare()
        self.candidate(prepared)
        self.write(MEMORY, "Owner wrote a newer memory document\n")
        with self.assertRaisesRegex(ArchiveError, "memory/registry changed"):
            self.archive.finalize(prepared["run_id"])
        self.assertTrue((self.root / FEATURE).exists())

    def test_dangling_consumer_blocks_before_deletion(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        candidate["repairs"] = [r for r in candidate["repairs"] if r["path"] != "tests/consumer.py"]
        self.save_candidate(prepared, candidate)
        with self.assertRaisesRegex(ArchiveError, "All preflight references"):
            self.archive.finalize(prepared["run_id"])

    def test_partial_staging_and_ignored_artifacts_block(self):
        self.write(FEATURE + "/spec.md", "staged\n")
        self.git("add", FEATURE + "/spec.md")
        self.write(FEATURE + "/spec.md", "unstaged\n")
        with self.assertRaisesRegex(ArchiveError, "Partially staged"):
            self.archive.repo.check_scope([FEATURE])
        self.write(".gitignore", "*.secret\n")
        self.write(FEATURE + "/token.secret", "private")
        with self.assertRaisesRegex(ArchiveError, "Ignored artifacts"):
            self.archive.spec_files([FEATURE])

    def test_interruption_after_delete_resumes(self):
        prepared = self.prepare()
        self.candidate(prepared)
        with patch.object(self.archive, "run_checks", side_effect=ArchiveError("infrastructure unavailable")):
            with self.assertRaisesRegex(ArchiveError, "unavailable"):
                self.archive.finalize(prepared["run_id"])
        self.assertFalse((self.root / FEATURE).exists())
        self.assertEqual("checking", self.archive.journal(prepared["run_id"])["phase"])
        self.assertEqual("done", self.archive.finalize(prepared["run_id"])["phase"])

    def test_resume_preserves_owner_edits(self):
        prepared = self.prepare()
        self.candidate(prepared)
        with patch.object(self.archive, "run_checks", side_effect=ArchiveError("failed check")):
            with self.assertRaises(ArchiveError):
                self.archive.finalize(prepared["run_id"])
        self.write(MEMORY, "Owner edits during recovery\n")
        with self.assertRaisesRegex(ArchiveError, "Unexpected edit"):
            self.archive.finalize(prepared["run_id"])
        self.assertEqual("Owner edits during recovery\n", (self.root / MEMORY).read_text())

    def test_automatic_waits_for_merge_and_verification(self):
        self.archive.enable(self.archive.policy_hash())
        self.git("checkout", "-b", "007-invoice")
        self.write(FEATURE + "/review.md", "Implementation reviewed\n")
        self.git("add", "-A")
        self.git("commit", "-m", "Finish feature")
        self.archive.queue(FEATURE, ["consumer"])
        self.assertEqual([], self.archive.pending()["ready"])
        self.git("checkout", "develop")
        self.git("merge", "--no-ff", "007-invoice", "-m", "Merge feature")
        self.assertEqual(FEATURE, self.archive.pending()["needs_verification"][0]["spec"])
        self.archive.verify(FEATURE, ["consumer"])
        self.assertEqual([FEATURE], self.archive.pending()["ready"])
        prepared = self.archive.prepare([FEATURE], [], [], automatic=True)
        self.candidate(prepared)
        self.assertEqual("done", self.archive.finalize(prepared["run_id"])["phase"])
        self.assertEqual([], self.archive.pending()["ready"])

    def test_policy_renewal_after_implementation_change(self):
        self.archive.enable(self.archive.policy_hash())
        self.write(EXTENSION + "/scripts/changed.py", "print('changed')\n")
        self.assertFalse(self.archive.pending()["enabled"])

    def test_squash_merge_uses_content_identity_then_fresh_verification(self):
        self.archive.enable(self.archive.policy_hash())
        self.git("checkout", "-b", "007-invoice")
        self.write("src/app.py", "CURRENCY = 'EUR'\nMAX_ITEMS = 100\n")
        self.git("add", "src/app.py")
        self.git("commit", "-m", "Finish implementation")
        self.archive.queue(FEATURE, ["consumer"])
        self.git("checkout", "develop")
        self.git("merge", "--squash", "007-invoice")
        self.git("commit", "-m", "Squashed feature")
        self.assertEqual(FEATURE, self.archive.pending()["needs_verification"][0]["spec"])
        self.archive.verify(FEATURE, ["consumer"])
        self.assertEqual([FEATURE], self.archive.pending()["ready"])

    def test_unfinished_requires_explicit_retirement(self):
        self.write(FEATURE + "/tasks.md", "- [ ] T001 Unbuilt\n")
        self.git("add", FEATURE + "/tasks.md")
        self.git("commit", "-m", "Unfinished proposal")
        with self.assertRaisesRegex(ArchiveError, "unfinished"):
            self.archive.verify(FEATURE, ["consumer"])
        prepared = self.archive.prepare([FEATURE], [], ["consumer"], retire="Cancelled duplicate proposal")
        self.candidate(prepared)
        self.assertEqual("done", self.archive.finalize(prepared["run_id"])["phase"])

    def test_related_changes_verified_and_checkpointed(self):
        self.write("src/app.py", "CURRENCY = 'EUR'\nMAX_ITEMS = 100\n")
        self.archive.verify(FEATURE, ["consumer"], ["src/app.py"])
        prepared = self.archive.prepare([FEATURE], ["src/app.py"], ["consumer"])
        self.assertIn("MAX_ITEMS", self.git("show", prepared["checkpoint"] + ":src/app.py"))

    def test_traversal_and_symlink_rejected(self):
        for name in ("specs/../unrelated.txt", ".git/config", "/tmp/escape"):
            with self.assertRaises(ArchiveError):
                self.archive.repo.path(name)
        try:
            (self.root / "linked").symlink_to(self.root / "specs", target_is_directory=True)
        except OSError:
            return  # Symlink privilege is optional on Windows; traversal assertions above still run.
        with self.assertRaisesRegex(ArchiveError, "links"):
            self.archive.repo.path("linked/007-invoice/spec.md")

    def test_commit_to_journal_interruption_recovers_without_extra_commit(self):
        prepared = self.prepare()
        self.candidate(prepared)
        real_save = self.archive.save
        def interrupted_save(run):
            if run["phase"] == "done":
                raise OSError("journal write interrupted")
            real_save(run)
        with patch.object(self.archive, "save", side_effect=interrupted_save):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.archive.finalize(prepared["run_id"])
        final = self.git("rev-parse", "HEAD")
        self.assertEqual(final, self.archive.finalize(prepared["run_id"])["final_commit"])

    def test_checkpoint_inventory_interruption_is_recoverable(self):
        self.archive.verify(FEATURE, ["consumer"])
        with patch("archive.inventory", side_effect=OSError("inventory interrupted")):
            with self.assertRaisesRegex(OSError, "inventory interrupted"):
                self.archive.prepare([FEATURE], [], ["consumer"])
        run_id = self.archive.active_id()
        checkpoint = self.git("rev-parse", "HEAD")
        self.assertEqual("checkpoint", self.archive.journal(run_id)["phase"])
        with self.assertRaisesRegex(ArchiveError, "Checkpoint recovered"):
            self.archive.finalize(run_id)
        prepared = {"run_id": run_id, "checkpoint": checkpoint}
        self.candidate(prepared)
        self.assertEqual("done", self.archive.finalize(run_id)["phase"])

    def test_verification_failure_does_not_record_completion(self):
        self.write("tests/consumer.py", "raise RuntimeError('unverified')\n")
        self.git("add", "tests/consumer.py")
        self.git("commit", "-m", "Failing implementation")
        with self.assertRaisesRegex(ArchiveError, "Check consumer failed"):
            self.archive.verify(FEATURE, ["consumer"])
        self.assertFalse(self.archive.evidence_file(FEATURE).exists())

    def test_successive_archive_updates_existing_rule_and_retires_follow_up(self):
        first = self.prepare()
        candidate = self.candidate(first)
        follow_unit = next(u for u in self.archive.journal(first["run_id"])["units"] if "Confirm retention" in u.get("text", ""))
        follow = dict(candidate["entries"][0], id="PM-retention-follow-up", kind="follow-up", title="Retention follow-up",
                      text="Confirm retention.", evidence=[], sources=[{"commit": first["checkpoint"], "path": follow_unit["path"], "unit": follow_unit["id"]}])
        candidate["entries"].append(follow)
        candidate["coverage"][follow_unit["id"]] = {"action": "retained", "memory_ids": [follow["id"]]}
        self.save_candidate(first, candidate)
        self.archive.finalize(first["run_id"])
        second_spec = "specs/008-new-currency"
        self.write(second_spec + "/spec.md", "FR-001: Invoices now use GBP. Retention is configured.\n")
        self.write(second_spec + "/tasks.md", "- [x] T001 Complete\n")
        self.write("src/app.py", "CURRENCY = 'GBP'\n")
        self.git("add", "-A")
        self.git("commit", "-m", "Replace currency and settle retention")
        self.archive.verify(second_spec, ["consumer"])
        second = self.archive.prepare([second_spec], [], ["consumer"])
        run = self.archive.journal(second["run_id"])
        current_unit = next(u for u in run["units"] if "FR-001" in u.get("text", ""))
        current = dict(run["previous_entries"][0])
        current["text"] = "Invoices use GBP."
        current["sources"] = [*current["sources"], {"commit": second["checkpoint"], "path": current_unit["path"], "unit": current_unit["id"]}]
        current["evidence"] = [{"commit": second["checkpoint"], "path": "src/app.py"}]
        changed = {"entries": [current], "coverage": {u["id"]: {"action": "omitted", "memory_ids": [], "reason": "Execution detail"} for u in run["units"]},
                   "removed": {follow["id"]: {"reason": "Retention is configured", "source_unit": current_unit["id"], "replacement": None}},
                   "repairs": [], "migrations": []}
        changed["coverage"][current_unit["id"]] = {"action": "merged", "memory_ids": [current["id"]]}
        self.save_candidate(second, changed)
        self.archive.finalize(second["run_id"])
        text = (self.root / MEMORY).read_text()
        self.assertIn("Invoices use GBP", text)
        self.assertNotIn("Invoices use EUR", text)
        self.assertNotIn("Confirm retention", text)
        self.assertEqual("PM-invoice-currency", read_memory(self.root / MEMORY)[0]["id"])
        registry = json.loads((self.root / REGISTRY).read_text())
        self.assertIn(follow["id"], registry["retired_memory_ids"])
        # A later proposal cannot resurrect that stable ID.
        changed["entries"].append(follow)
        with self.assertRaisesRegex(ArchiveError, "retired memory ID"):
            validate_knowledge(self.archive.repo, run, changed)

    def test_unpublished_stale_proposal_can_be_abandoned_without_changes(self):
        prepared = self.prepare()
        checkpoint = self.git("rev-parse", "HEAD")
        self.assertEqual("abandoned", self.archive.abandon(prepared["run_id"])["phase"])
        self.assertIsNone(self.archive.active_id())
        self.assertEqual(checkpoint, self.git("rev-parse", "HEAD"))
        self.assertTrue((self.root / FEATURE).exists())

    def test_active_local_pointer_is_cleared_only_if_it_still_points_at_archive(self):
        self.write(".gitignore", ".specify/feature.json\n")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "Local pointer policy")
        self.write(".specify/feature.json", json.dumps({"feature_dir": FEATURE}))
        prepared = self.prepare()
        self.candidate(prepared)
        self.archive.finalize(prepared["run_id"])
        self.assertFalse((self.root / ".specify/feature.json").exists())

    def test_new_artifact_during_recovery_is_preserved(self):
        prepared = self.prepare()
        self.candidate(prepared)
        real_write = __import__("archive").atomic_write
        def interrupt(path, data):
            if path == self.root / MEMORY:
                raise OSError("publication interrupted")
            real_write(path, data)
        with patch("archive.atomic_write", side_effect=interrupt):
            with self.assertRaises(OSError):
                self.archive.finalize(prepared["run_id"])
        self.write(FEATURE + "/new-owner-note.md", "Keep this new note\n")
        with self.assertRaisesRegex(ArchiveError, "New feature artifacts"):
            self.archive.finalize(prepared["run_id"])
        self.assertTrue((self.root / FEATURE / "new-owner-note.md").exists())

    def test_git_hook_unexpected_commit_scope_is_detected(self):
        self.archive.verify(FEATURE, ["consumer"])
        self.write(".git/hooks/pre-commit", "#!/bin/sh\nprintf 'hook edit\\n' > unrelated.txt\ngit add unrelated.txt\n")
        (self.root / ".git/hooks/pre-commit").chmod(0o755)
        with self.assertRaisesRegex(ArchiveError, "unexpected paths"):
            self.archive.prepare([FEATURE], [], ["consumer"])
        self.assertTrue((self.root / FEATURE).exists())
        self.assertFalse((self.root / MEMORY).exists())

    def test_repair_commands_need_approved_test_coverage(self):
        policy = self.archive.policy
        policy["checks"]["consumer"]["covers"] = []
        self.write(POLICY, json.dumps(policy))
        self.git("add", POLICY)
        self.git("commit", "-m", "Restrict check coverage")
        self.archive = Archive(self.root)
        with self.assertRaisesRegex(ArchiveError, "No selected verification"):
            self.archive.verify(FEATURE, ["consumer"])

    def test_empty_feature_directories_resume_after_unlink_interruption(self):
        prepared = self.prepare()
        self.candidate(prepared)
        original = Path.rmdir
        def interrupted(path):
            if path == self.root / FEATURE / "contracts":
                raise OSError("interrupted before removing empty directories")
            original(path)
        with patch.object(Path, "rmdir", interrupted):
            with self.assertRaisesRegex(OSError, "empty directories"):
                self.archive.finalize(prepared["run_id"])
        self.assertTrue((self.root / FEATURE).exists())
        self.assertEqual([], list((self.root / FEATURE).rglob("*.*")))
        self.assertEqual("done", self.archive.finalize(prepared["run_id"])["phase"])

    def test_permanent_post_publication_failure_can_rollback_exactly(self):
        self.write("unrelated.txt", "owner staged\n")
        self.git("add", "unrelated.txt")
        self.write("unrelated.txt", "owner unstaged\n")
        prepared = self.prepare()
        self.candidate(prepared)
        original = {p: (self.root / p).read_bytes() for p in self.archive.journal(prepared["run_id"])["original_files"]}
        with patch.object(self.archive, "run_checks", side_effect=ArchiveError("permanent check failure")):
            with self.assertRaisesRegex(ArchiveError, "permanent"):
                self.archive.finalize(prepared["run_id"])
        result = self.archive.rollback(prepared["run_id"])
        self.assertEqual("rolled-back", result["phase"])
        self.assertEqual(prepared["checkpoint"], self.git("rev-parse", "HEAD"))
        self.assertEqual(original, {p: (self.root / p).read_bytes() for p in original})
        self.assertIn(CONTRACT, (self.root / "tests/consumer.py").read_text())
        self.assertFalse((self.root / FIXTURE).exists())
        self.assertFalse((self.root / MEMORY).exists())
        self.assertFalse((self.root / REGISTRY).exists())
        self.assertEqual("owner staged", self.git("show", ":unrelated.txt"))
        self.assertEqual("owner unstaged\n", (self.root / "unrelated.txt").read_text())
        self.assertIsNone(self.archive.active_id())
        self.assertEqual(result, self.archive.rollback(prepared["run_id"]))

    def test_rollback_preserves_edits_and_resumes_after_interruption(self):
        prepared = self.prepare()
        self.candidate(prepared)
        with patch.object(self.archive, "run_checks", side_effect=ArchiveError("failed")):
            with self.assertRaises(ArchiveError):
                self.archive.finalize(prepared["run_id"])
        memory = (self.root / MEMORY).read_bytes()
        self.write(MEMORY, "owner edit\n")
        with self.assertRaisesRegex(ArchiveError, "Unexpected edit"):
            self.archive.rollback(prepared["run_id"])
        self.write(MEMORY, memory)
        original = __import__("archive").atomic_write
        def interrupted(path, data):
            if path == self.root / CONTRACT:
                raise OSError("rollback interrupted")
            original(path, data)
        with patch("archive.atomic_write", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "rollback interrupted"):
                self.archive.rollback(prepared["run_id"])
        self.assertEqual("rolled-back", self.archive.rollback(prepared["run_id"])["phase"])

    def test_done_journal_cleanup_is_idempotent(self):
        prepared = self.prepare()
        self.candidate(prepared)
        original = self.archive.save
        def interrupted(run):
            original(run)
            if run["phase"] == "done":
                raise OSError("cleanup interrupted")
        with patch.object(self.archive, "save", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "cleanup interrupted"):
                self.archive.finalize(prepared["run_id"])
        self.assertIsNotNone(self.archive.active_id())
        self.archive.finalize(prepared["run_id"])
        self.assertIsNone(self.archive.active_id())

    def test_late_artifact_blocks_before_final_commit(self):
        prepared = self.prepare()
        self.candidate(prepared)
        with patch.object(self.archive.repo, "commit", side_effect=ArchiveError("commit interrupted")):
            with self.assertRaisesRegex(ArchiveError, "commit interrupted"):
                self.archive.finalize(prepared["run_id"])
        self.write(FEATURE + "/owner-note.md", "preserve this\n")
        with self.assertRaisesRegex(ArchiveError, "New feature artifacts"):
            self.archive.finalize(prepared["run_id"])
        self.assertEqual(prepared["checkpoint"], self.git("rev-parse", "HEAD"))
        self.assertEqual("preserve this\n", (self.root / FEATURE / "owner-note.md").read_text())

    def test_current_behavior_cannot_depend_only_on_deleted_evidence(self):
        self.write("src/obsolete.py", "OLD = True\n")
        self.git("add", "src/obsolete.py")
        self.git("commit", "-m", "Old implementation")
        old = self.git("rev-parse", "HEAD")
        self.git("rm", "src/obsolete.py")
        self.git("commit", "-m", "Remove implementation")
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        candidate["entries"][0]["evidence"] = [{"commit": old, "path": "src/obsolete.py"}]
        self.save_candidate(prepared, candidate)
        with self.assertRaisesRegex(ArchiveError, "current checkpoint"):
            self.archive.finalize(prepared["run_id"])

    def test_domain_headings_in_memory_text_are_rejected(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        candidate["entries"][0]["text"] += "\n\n## Hidden lost section\nKeep this detail."
        self.save_candidate(prepared, candidate)
        with self.assertRaisesRegex(ArchiveError, "document/domain headings"):
            self.archive.finalize(prepared["run_id"])

    def test_unaccounted_existing_memory_content_is_preserved(self):
        prepared = self.prepare()
        self.candidate(prepared)
        self.archive.finalize(prepared["run_id"])
        path = self.root / MEMORY
        altered = path.read_text() + "\n## Owner note\nNever lose this knowledge.\n"
        path.write_text(altered)
        with self.assertRaisesRegex(ArchiveError, "unaccounted content"):
            read_memory(path)
        self.assertEqual(altered, path.read_text())

    def test_cli_read_only_state_survives_held_lock_and_gates_specification(self):
        prepared = self.prepare()
        command = [sys.executable, str(SCRIPTS / "archive.py"), "--root", str(self.root)]
        with self.archive.repo.lock():
            state = subprocess.run([*command, "pending"], capture_output=True)
            self.assertEqual(0, state.returncode, state.stdout)
            data = json.loads(state.stdout)["data"]
            self.assertEqual(prepared["run_id"], data["active_run"])
            self.assertEqual("synthesis", data["active_phase"])
            self.assertEqual("busy", data["writer"]["state"])
            gate = subprocess.run([*command, "pending", "--gate"], capture_output=True)
            self.assertEqual(1, gate.returncode)
        write_json(self.archive.repo.state / "writer.lock", {"pid": 2147483647, "root": str(self.root)})
        state = subprocess.run([*command, "status"], capture_output=True)
        self.assertEqual(0, state.returncode, state.stdout)
        self.assertEqual("stale", json.loads(state.stdout)["data"]["pending"]["writer"]["state"])
        (self.archive.repo.state / "writer.lock").unlink()

    def test_queue_and_verify_require_implementation_coverage(self):
        self.archive.policy["checks"]["docs"] = {"argv": ["{python}", "-c", "pass"], "covers": ["Docs/*"]}
        self.write(POLICY, json.dumps(self.archive.policy))
        self.git("add", POLICY)
        self.git("commit", "-m", "Add passive check")
        self.archive = Archive(self.root)
        with self.assertRaisesRegex(ArchiveError, "No selected verification"):
            self.archive.verify(FEATURE, ["docs"])
        self.archive.enable(self.archive.policy_hash())
        self.git("checkout", "-b", "007-invoice")
        self.write("src/app.py", "CURRENCY = 'EUR'\nLIMIT = 1\n")
        self.git("add", "src/app.py")
        self.git("commit", "-m", "Implement limit")
        with self.assertRaisesRegex(ArchiveError, "No selected verification"):
            self.archive.queue(FEATURE, ["docs"])

    def test_number_guard_loss_and_passive_slug_references(self):
        self.write(REGISTRY, json.dumps({"schema_version": 1, "high_water": 6, "archived": {}}))
        self.assertEqual(2, len(self.archive.pending()["guard_blockers"]))
        self.assertFalse(self.archive.live_reference("Branch: 007-invoice; Docs/007-invoice", [FEATURE]))
        self.assertTrue(self.archive.live_reference("Path.Combine('specs', '007-invoice', 'contract')", [FEATURE]))
        self.assertTrue(self.archive.live_reference("specs\\007-invoice\\tasks.md", [FEATURE]))

    def copy_entry_points(self):
        workspace = Path(__file__).parent / "fixtures/entry-points"
        shutil.copytree(workspace / ".specify/scripts", self.root / ".specify/scripts", dirs_exist_ok=True)
        shutil.copytree(workspace / ".specify/extensions/git/scripts", self.root / ".specify/extensions/git/scripts", dirs_exist_ok=True)
        shutil.copytree(SCRIPTS, self.root / EXTENSION / "scripts", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        from install import prepare_guards
        for path, data in prepare_guards(self.archive.repo).items():
            (self.root / path).write_bytes(data)

    def test_real_auto_commit_and_feature_commands_gate_failed_archive(self):
        prepared = self.prepare()
        self.candidate(prepared)
        with patch.object(self.archive, "run_checks", side_effect=ArchiveError("permanent failure")):
            with self.assertRaises(ArchiveError):
                self.archive.finalize(prepared["run_id"])
        self.copy_entry_points()
        self.write(".specify/extensions/git/git-config.yml", "auto_commit:\n  default: true\n")
        git = Path(shutil.which("git"))
        bash = str(git.parents[1] / "bin/bash.exe") if (git.parents[1] / "bin/bash.exe").exists() else shutil.which("bash")
        shells = [(shutil.which("pwsh"), ["-NoProfile", "-File"], "powershell", "ps1"), (bash, [], "bash", "sh")]
        checkpoint = self.git("rev-parse", "HEAD")
        index = self.archive.repo.index()
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_BRANCH_NAME", "SPECIFY_FEATURE", "SPECIFY_FEATURE_DIRECTORY", "SPECIFY_INIT_DIR")}
        for executable, flags, language, suffix in shells:
            if not executable:
                continue
            for directory, name, args in [(".specify/extensions/git/scripts", "auto-commit", ["after_specify"]),
                                          (".specify/scripts", "create-new-feature", ["gate probe"]),
                                          (".specify/extensions/git/scripts", "create-new-feature", ["gate probe"])]:
                command = [executable, *flags, f"{directory}/{language}/{name}.{suffix}", *args]
                result = subprocess.run(command, cwd=self.root, env=env, capture_output=True)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertEqual(checkpoint, self.git("rev-parse", "HEAD"))
                self.assertEqual("develop", self.git("branch", "--show-current"))
                self.assertEqual(index, self.archive.repo.index())

    def test_autocrlf_archive_and_selected_file_formatting_hook(self):
        self.git("config", "core.autocrlf", "true")
        self.write(".gitattributes", "* text=auto\n*.png binary\n")
        self.write(FEATURE + "/spec.md", (self.root / FEATURE / "spec.md").read_bytes().replace(b"\n", b"\r\n"))
        self.write("src/app.py", b"CURRENCY = 'EUR'\r\nMAX_ITEMS = 2\r\n")
        self.git("add", ".gitattributes", "src/app.py", FEATURE + "/spec.md")
        self.git("commit", "-m", "Windows text policy")
        prepared = self.prepare()
        self.candidate(prepared)
        self.assertEqual("done", self.archive.finalize(prepared["run_id"])["phase"])
        next_spec = "specs/008-hook"
        self.write(next_spec + "/spec.md", "Formatting feature\n")
        self.write(next_spec + "/tasks.md", "- [x] Complete\n")
        self.git("add", next_spec)
        self.git("commit", "-m", "Next spec")
        self.archive.verify(next_spec, ["consumer"])
        self.write(".git/hooks/pre-commit", "#!/bin/sh\nprintf 'formatted by hook\\n' >> specs/008-hook/spec.md\ngit add specs/008-hook/spec.md\n")
        (self.root / ".git/hooks/pre-commit").chmod(0o755)
        with self.assertRaisesRegex(ArchiveError, "unexpected paths"):
            self.archive.prepare([next_spec], [], ["consumer"])

    def test_ignored_fixture_output_blocks_before_deletion(self):
        self.write(".gitignore", "tests/Fixtures/\n")
        self.git("add", ".gitignore")
        self.git("commit", "-m", "Ignored fixture policy")
        prepared = self.prepare()
        self.candidate(prepared)
        with self.assertRaisesRegex(ArchiveError, "ignored and unrecoverable"):
            self.archive.finalize(prepared["run_id"])
        self.assertTrue((self.root / FEATURE).exists())

    def test_writer_lock_serializes_worktrees(self):
        with self.archive.repo.lock():
            with self.assertRaisesRegex(ArchiveError, "writer lock exists"):
                with Archive(self.root).repo.lock():
                    self.fail("A second writer acquired the same Git lock")

    def test_number_reservations_enforced_by_powershell_entry_points(self):
        pwsh = shutil.which("pwsh")
        if not pwsh:
            self.skipTest("PowerShell is not installed on this platform")
        workspace = Path(__file__).parent / "fixtures/entry-points"
        shutil.copytree(workspace / ".specify/scripts/powershell", self.root / ".specify/scripts/powershell")
        shutil.copytree(workspace / ".specify/extensions/git/scripts/powershell", self.root / ".specify/extensions/git/scripts/powershell")
        shutil.copytree(SCRIPTS, self.root / EXTENSION / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        self.copy_entry_points()
        self.write(REGISTRY, json.dumps({"schema_version": 1, "high_water": 47,
            "archived": {"specs/047-retired": {"checkpoint": self.git("rev-parse", "HEAD")}}}))
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_BRANCH_NAME", "SPECIFY_FEATURE", "SPECIFY_FEATURE_DIRECTORY", "SPECIFY_INIT_DIR")}
        for script in (".specify/scripts/powershell/create-new-feature.ps1", ".specify/extensions/git/scripts/powershell/create-new-feature.ps1"):
            executed = subprocess.run([pwsh, "-NoProfile", "-File", script, "-Number", "47", "numbering probe"],
                                      cwd=self.root, env=env, capture_output=True)
            self.assertNotEqual(0, executed.returncode, executed.stdout.decode(errors="replace"))
            self.assertFalse(any((self.root / "specs").glob("047-*")))
        auto = subprocess.run([pwsh, "-NoProfile", "-File", ".specify/scripts/powershell/create-new-feature.ps1",
                               "-Json", "-ShortName", "numbering-probe", "probe"], cwd=self.root, env=env, capture_output=True)
        self.assertEqual(0, auto.returncode, auto.stderr.decode(errors="replace"))
        self.assertTrue(json.loads(auto.stdout)["BRANCH_NAME"].startswith("048-"))

    def test_number_reservations_enforced_by_bash_entry_points(self):
        git = Path(shutil.which("git"))
        git_bash = git.parents[1] / "bin/bash.exe"
        bash = str(git_bash) if git_bash.exists() else shutil.which("bash")
        if not bash:
            self.skipTest("Bash is not installed on this platform")
        workspace = Path(__file__).parent / "fixtures/entry-points"
        shutil.copytree(workspace / ".specify/scripts/bash", self.root / ".specify/scripts/bash")
        shutil.copytree(workspace / ".specify/extensions/git/scripts/bash", self.root / ".specify/extensions/git/scripts/bash")
        shutil.copytree(SCRIPTS, self.root / EXTENSION / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        self.copy_entry_points()
        self.write(REGISTRY, json.dumps({"schema_version": 1, "high_water": 47,
            "archived": {"specs/047-retired": {"checkpoint": self.git("rev-parse", "HEAD")}}}))
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_BRANCH_NAME", "SPECIFY_FEATURE", "SPECIFY_FEATURE_DIRECTORY", "SPECIFY_INIT_DIR")}
        for script in (".specify/scripts/bash/create-new-feature.sh", ".specify/extensions/git/scripts/bash/create-new-feature.sh"):
            executed = subprocess.run([bash, script, "--number", "47", "numbering probe"], cwd=self.root, env=env, capture_output=True)
            self.assertNotEqual(0, executed.returncode, executed.stdout.decode(errors="replace"))
            self.assertFalse(any((self.root / "specs").glob("047-*")))
        auto = subprocess.run([bash, ".specify/scripts/bash/create-new-feature.sh", "--json", "--short-name", "numbering-probe", "probe"],
                              cwd=self.root, env=env, capture_output=True)
        self.assertEqual(0, auto.returncode, auto.stderr.decode(errors="replace"))
        self.assertTrue(json.loads(auto.stdout)["BRANCH_NAME"].startswith("048-"))


if __name__ == "__main__":
    unittest.main()
