from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import archive as archive_module
from archive import Archive, EXTENSION, POLICY
import memory_delta as md
import memory_store as ms
from git_state import ArchiveError, digest, write_json
from memory import MEMORY, REGISTRY, render
from test_memory_store import legacy_entries

FEATURE = "specs/010-vat"
SPEC = FEATURE + "/spec.md"
TASKS = FEATURE + "/tasks.md"
REASON = "Verification runs in a separate pipeline"
VAT = f"{ms.ENTRIES}/PM-invoice-vat.md"
CURRENCY = f"{ms.ENTRIES}/PM-invoice-currency.md"
ROUNDING = f"{ms.ENTRIES}/PM-invoice-rounding.md"


class ArchiveV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="memory-v2-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-b", "develop")
        for key, value in {"user.name": "Archive Test", "user.email": "archive@example.invalid", "core.autocrlf": "false",
                           "core.hooksPath": ".git/hooks", "commit.gpgsign": "false"}.items():
            self.git("config", key, value)
        self.write(EXTENSION + "/extension.yml", "version: 1\n")
        self.write(POLICY, json.dumps({"schema_version": 1, "target_branch": "develop", "checks": {}}))
        self.write(MEMORY, render(legacy_entries()))
        self.write(REGISTRY, json.dumps({"schema_version": 1, "archived": {}, "high_water": 8}, indent=2) + "\n")
        self.write("src/app.py", "CURRENCY = 'GBP'\n")
        self.git("add", "-A")
        self.git("commit", "-m", "Initial")
        self.archive = Archive(self.root)
        self.archive.migrate()
        self.write(SPEC, "# VAT\n\nInvoices use GBP.\n\nRounding is replaced by VAT rules.\n")
        self.write(TASKS, "# Tasks\n\n- [x] T001 Add VAT\n")
        self.git("add", "-A")
        self.git("commit", "-m", "VAT feature")
        self.base_root = ms.memory_root(self.root)
        self.prepared = self.archive.prepare([FEATURE], [], [], skip_verification=REASON)
        self.run_dir = self.archive.run_path(self.prepared["run_id"])

    def git(self, *args):
        run = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        if run.returncode:
            raise AssertionError(run.stderr.decode(errors="replace"))
        return run.stdout.decode().strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())

    def read(self, name):
        return (self.root / name).read_bytes()

    def journal(self):
        return self.archive.journal(self.prepared["run_id"])

    def candidate(self):
        currency = ms.parse_entry(self.read(CURRENCY), "x")
        currency.update(text="Invoices use GBP. VAT applies per PM-invoice-vat.", relations=["PM-invoice-vat"])
        candidate = json.loads((self.run_dir / "candidate.json").read_text(encoding="utf-8"))
        candidate.update(
            taxonomy_changes=[{"op": "add", "id": "tax", "label": "Tax", "definition": "Tax rules."}],
            additions=[{"id": "PM-invoice-vat", "domain": "tax", "kind": "decision", "title": "VAT replaces rounding",
                        "text": "VAT rules replace half-up rounding.", "relations": [], "selectors": []}],
            updates=[{"id": "PM-invoice-currency", "expected_hash": digest(self.read(CURRENCY)), "entry": currency}],
            removals=[{"id": "PM-invoice-rounding", "expected_hash": digest(self.read(ROUNDING)),
                       "reason": "Replaced by VAT rules", "source_unit": SPEC + ":L5", "replacement": "PM-invoice-vat"}],
            provenance=[{"entry": "PM-invoice-vat", "units": {SPEC: ["L5"]}},
                        {"entry": "PM-invoice-currency", "units": {SPEC: ["L3"]}, "evidence": ["src/app.py"]}],
            coverage=[{"units": {SPEC: ["L1"], TASKS: ["L1", "L3"]}, "action": "omitted", "reason": "Headings and tasks"},
                      {"units": {SPEC: ["L3"]}, "action": "merged", "memory_ids": ["PM-invoice-currency"]},
                      {"units": {SPEC: ["L5"]}, "action": "superseded", "memory_ids": ["PM-invoice-vat"]}])
        return candidate

    def save(self, candidate, review=True, **overrides):
        write_json(self.run_dir / "candidate.json", candidate)
        (self.run_dir / "review.json").unlink(missing_ok=True)
        if review:
            _, report = self.archive.materialize(self.journal())
            write_json(self.run_dir / "review.json", {
                **{k: report[k] for k in ("candidate_sha256", "base_memory_root", "result_memory_root", "outputs_sha256")},
                "verification_override": REASON, "reviewer": "independent test reviewer", "passed": True,
                "summary": "Delta independently reviewed", "findings": [], **overrides})

    def cli(self, *args):
        run = subprocess.run([sys.executable, str(SCRIPTS / "archive.py"), "--root", str(self.root), *args],
                             capture_output=True)
        return run.returncode, json.loads(run.stdout)

    def test_prepare_writes_a_v2_journal_and_delta_skeleton(self):
        run = self.journal()
        self.assertEqual((2, self.base_root), (run["memory_format"], run["base_memory_root"]))
        self.assertNotIn("previous_entries", run)
        self.assertNotIn("memory_hash", run)
        self.assertIn(ms.MEMORY_DIR, run["scope"])
        self.assertEqual(md.empty_candidate(self.base_root, run["checkpoint"]),
                         json.loads((self.run_dir / "candidate.json").read_text(encoding="utf-8")))
        with self.assertRaisesRegex(ArchiveError, "unfinished"):
            self.archive.prepare([FEATURE], [], [], skip_verification=REASON)

    def test_full_transaction_publishes_delta_and_commits_scoped_result(self):
        before = {p: self.read(p) for p in (CURRENCY, f"{ms.ENTRIES}/PM-tenant-scope.md")}
        self.save(self.candidate())
        _, report = self.archive.materialize(self.journal())
        self.assertEqual("passed", report["review"]["status"])
        result = self.archive.finalize(self.prepared["run_id"])
        self.assertEqual(("done", {"status": "skipped", "reason": REASON}), (result["phase"], result["verification"]))
        # Entry files: one added, one updated, one deleted, the rest byte-identical.
        self.assertFalse((self.root / ROUNDING).exists())
        self.assertIn(b"VAT rules replace", self.read(VAT))
        self.assertIn(b"Invoices use GBP", self.read(CURRENCY))
        self.assertNotEqual(before[CURRENCY], self.read(CURRENCY))
        self.assertEqual(before[f"{ms.ENTRIES}/PM-tenant-scope.md"], self.read(f"{ms.ENTRIES}/PM-tenant-scope.md"))
        self.assertFalse((self.root / FEATURE).exists())
        # The new ledger.
        checkpoint = self.prepared["checkpoint"]
        ledger = f"{ms.PROVENANCE}/0001-{checkpoint[:8]}-{self.prepared['run_id'][:8]}.jsonl"
        header, records = ms.parse_ledger(self.read(ledger), "ledger")
        self.assertEqual({"status": "skipped", "reason": REASON}, header["verification"])
        self.assertEqual((checkpoint, [FEATURE]), (header["checkpoint"], header["specs"]))
        self.assertEqual([("PM-invoice-currency", "add"), ("PM-invoice-rounding", "retire"), ("PM-invoice-vat", "add")],
                         [(r["entry"], r["op"]) for r in records])
        # The registry.
        registry = json.loads(self.read(REGISTRY))
        self.assertEqual({"checkpoint": checkpoint, "retired": False, "verification": result["verification"]},
                         registry["archived"][FEATURE])
        self.assertEqual(10, registry["high_water"])
        self.assertEqual({"PM-invoice-rounding": {"reason": "Replaced by VAT rules", "replacement": "PM-invoice-vat"}},
                         registry["retired_memory_ids"])
        self.assertEqual(2, registry["memory_format"])
        # The whole result passes the memory check and is exactly what the review bound.
        self.assertEqual([], self.archive.memory_check()["problems"])
        self.assertEqual(report["result_memory_root"], ms.memory_root(self.root))
        # The commit: exactly the archive scope, clean worktree, override marker retained.
        final = result["final_commit"]
        self.assertEqual(final, self.git("rev-parse", "HEAD"))
        self.assertEqual(checkpoint, self.git("rev-parse", "HEAD^"))
        self.assertIn("Verification-Skipped: " + REASON, self.git("show", "-s", "--format=%B", final))
        changed = dict(line.split("\t")[::-1] for line in self.git("diff", "--no-renames", "--name-status", checkpoint, final).splitlines())
        for path, status in {ROUNDING: "D", VAT: "A", CURRENCY: "M", ledger: "A", REGISTRY: "M", ms.TAXONOMY: "M",
                             f"{ms.CATALOGS}/tax/01.md": "A", ms.INDEX: "M", SPEC: "D", TASKS: "D"}.items():
            self.assertEqual(status, changed.get(path), path)
        self.assertTrue(all(p.startswith((ms.MEMORY_DIR + "/", FEATURE + "/")) or p == REGISTRY for p in changed))
        self.assertEqual("", self.git("status", "--short"))
        self.assertIsNone(self.archive.active_id())

    def test_checking_failure_rolls_back_every_output(self):
        tracked = {p: self.read(p) for p in self.git("ls-files", ms.MEMORY_DIR, FEATURE, REGISTRY).splitlines()}
        self.save(self.candidate())
        with patch.object(self.archive, "references", side_effect=ArchiveError("Consumer check failed")):
            with self.assertRaisesRegex(ArchiveError, "Consumer check failed"):
                self.archive.finalize(self.prepared["run_id"])
        self.assertEqual("checking", self.journal()["phase"])
        self.assertTrue((self.root / VAT).exists())
        self.assertFalse((self.root / ROUNDING).exists())
        result = self.archive.rollback(self.prepared["run_id"])
        self.assertEqual("rolled-back", result["phase"])
        self.assertEqual(result, self.archive.rollback(self.prepared["run_id"]))
        # Updated and removed entries, specs and registry are restored byte for byte; created files are gone.
        self.assertEqual(tracked, {p: self.read(p) for p in tracked})
        self.assertFalse((self.root / VAT).exists())
        self.assertEqual([], list((self.root / ms.PROVENANCE).glob("0001-*.jsonl")))
        self.assertEqual([], [p for p in (self.root / ms.CATALOGS).rglob("*") if p.is_file()
                              and p.relative_to(self.root).as_posix() not in tracked])
        # Empty catalog directories may remain; they change neither the root, the check nor Git.
        self.assertEqual(self.base_root, ms.memory_root(self.root))
        self.assertEqual([], self.archive.memory_check()["problems"])
        self.assertEqual("", self.git("status", "--short"))
        self.assertEqual(self.prepared["checkpoint"], self.git("rev-parse", "HEAD"))
        self.assertIsNone(self.archive.active_id())

    def test_base_drift_is_refused_before_publication(self):
        self.save(self.candidate())
        self.write(f"{ms.ENTRIES}/PM-drift.md", "drift\n")
        with self.assertRaisesRegex(ArchiveError, "Project memory/registry changed"):
            self.archive.finalize(self.prepared["run_id"])
        code, output = self.cli("validate", "--run", self.prepared["run_id"])
        self.assertEqual((1, False), (code, output["success"]))
        self.assertEqual("synthesis", self.journal()["phase"])
        self.assertTrue((self.root / SPEC).exists())

    def test_expected_hash_mismatch_is_refused(self):
        candidate = self.candidate()
        candidate["updates"][0]["expected_hash"] = "0" * 64
        self.save(candidate, review=False)
        with self.assertRaisesRegex(ArchiveError, "expected_hash does not match"):
            self.archive.finalize(self.prepared["run_id"])
        self.assertEqual("synthesis", self.journal()["phase"])
        self.assertTrue((self.root / ROUNDING).exists())

    def test_review_must_bind_the_exact_result(self):
        self.save(self.candidate(), result_memory_root="0" * 64)
        _, report = self.archive.materialize(self.journal())
        self.assertEqual("mismatch", report["review"]["status"])
        with self.assertRaisesRegex(ArchiveError, "result_memory_root must be"):
            self.archive.finalize(self.prepared["run_id"])
        self.save(self.candidate(), verification_override="Another reason")
        with self.assertRaisesRegex(ArchiveError, "verification_override must be"):
            self.archive.finalize(self.prepared["run_id"])
        # Any candidate edit after review invalidates it.
        self.save(self.candidate())
        candidate = self.candidate()
        candidate["additions"][0]["title"] = "VAT supersedes rounding"
        write_json(self.run_dir / "candidate.json", candidate)
        with self.assertRaisesRegex(ArchiveError, "candidate_sha256 must be"):
            self.archive.finalize(self.prepared["run_id"])
        self.assertEqual("synthesis", self.journal()["phase"])
        self.assertTrue((self.root / ROUNDING).exists())

    def test_validate_reports_bindings_while_review_is_missing(self):
        self.save(self.candidate(), review=False)
        code, output = self.cli("validate", "--run", self.prepared["run_id"])
        self.assertEqual(0, code, output)
        data = output["data"]
        self.assertTrue(data["valid"])
        self.assertEqual("missing", data["review"]["status"])
        self.assertEqual(self.base_root, data["base_memory_root"])
        self.assertEqual(digest((self.run_dir / "candidate.json").read_bytes()), data["candidate_sha256"])
        m = md.validate(self.archive.repo, self.journal(), self.candidate(), self.archive.budgets(), set())
        self.assertEqual((m.result_root, m.outputs_sha256, m.summary),
                         (data["result_memory_root"], data["outputs_sha256"], data["summary"]))
        self.assertIn(VAT, data["paths"])
        self.assertIn(REGISTRY, data["paths"])
        self.assertIn(SPEC, data["paths"])
        with self.assertRaisesRegex(ArchiveError, "review.json does not exist"):
            self.archive.finalize(self.prepared["run_id"])
        # A mechanical problem is the only nonzero exit.
        candidate = self.candidate()
        candidate["coverage"].pop()
        self.save(candidate, review=False)
        code, output = self.cli("validate", "--run", self.prepared["run_id"])
        self.assertEqual(1, code)
        self.assertIn("has no disposition", output["error"])
        self.assertEqual("", self.git("status", "--short"))

    def interrupt_publishing(self):
        """Fail the third output write so publication stops with some outputs written and some pending."""
        self.save(self.candidate())
        real, calls = archive_module.atomic_write, []

        def flaky(path, data):
            calls.append(path)
            if len(calls) == 3:
                raise OSError("disk full")
            real(path, data)
        with patch.object(archive_module, "atomic_write", flaky):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.archive.finalize(self.prepared["run_id"])
        run = self.journal()
        self.assertEqual("publishing", run["phase"])
        written = [p for p, h in run["after"].items() if h is not None and self.archive.repo.file_hash(p) == h]
        pending = [p for p, h in run["after"].items() if h is not None and self.archive.repo.file_hash(p) != h]
        self.assertEqual((2, True), (len(written), bool(pending)))
        self.assertTrue((self.root / ROUNDING).exists())

    def test_interrupted_publishing_resumes_to_done(self):
        self.interrupt_publishing()
        result = self.archive.finalize(self.prepared["run_id"])
        self.assertEqual("done", result["phase"])
        self.assertFalse((self.root / ROUNDING).exists())
        self.assertEqual(self.journal()["result_memory_root"], ms.memory_root(self.root))
        self.assertEqual("", self.git("status", "--short"))

    def test_interrupted_publishing_rolls_back_everything(self):
        tracked = {p: self.read(p) for p in self.git("ls-files", ms.MEMORY_DIR, FEATURE, REGISTRY).splitlines()}
        self.interrupt_publishing()
        self.assertEqual("rolled-back", self.archive.rollback(self.prepared["run_id"])["phase"])
        self.assertEqual(tracked, {p: self.read(p) for p in tracked})
        self.assertEqual(self.base_root, ms.memory_root(self.root))
        self.assertEqual("", self.git("status", "--short"))
        self.assertEqual(self.prepared["checkpoint"], self.git("rev-parse", "HEAD"))

    def test_unreviewed_memory_files_are_never_committed(self):
        self.save(self.candidate())
        stray = f"{ms.MEMORY_DIR}/notes.txt"

        def write_stray(specs):
            self.write(stray, "unreviewed\n")
            return []
        with patch.object(self.archive, "references", side_effect=write_stray):
            with self.assertRaisesRegex(ArchiveError, "reviewed result|Unreviewed project memory"):
                self.archive.finalize(self.prepared["run_id"])
        self.assertEqual(("checking", self.prepared["checkpoint"]), (self.journal()["phase"], self.git("rev-parse", "HEAD")))
        # An edit to an entry the review saw unchanged is refused as well.
        (self.root / stray).unlink()
        tenant = f"{ms.ENTRIES}/PM-tenant-scope.md"
        original = self.read(tenant)
        self.write(tenant, original + b"edited\n")
        with self.assertRaisesRegex(ArchiveError, "reviewed result|Unreviewed project memory"):
            self.archive.finalize(self.prepared["run_id"])
        self.assertEqual(self.prepared["checkpoint"], self.git("rev-parse", "HEAD"))
        # The committing phase guards again before the commit.
        self.write(tenant, original)
        run = self.journal()
        run.update(phase="committing", final_tree=self.archive.repo.expected_tree(run["scope"]))
        self.archive.save(run)
        self.write(stray, "late\n")
        with self.assertRaisesRegex(ArchiveError, "reviewed result|Unreviewed project memory"):
            self.archive.finalize(self.prepared["run_id"])
        self.assertEqual(self.prepared["checkpoint"], self.git("rev-parse", "HEAD"))
        (self.root / stray).unlink()
        final = self.archive.finalize(self.prepared["run_id"])["final_commit"]
        self.assertNotIn(stray, self.git("ls-tree", "-r", "--name-only", final).splitlines())

    def test_review_must_bind_outputs_and_base_individually(self):
        for key in ("outputs_sha256", "base_memory_root"):
            self.save(self.candidate(), **{key: "0" * 64})
            with self.assertRaisesRegex(ArchiveError, key + " must be"):
                self.archive.finalize(self.prepared["run_id"])
            self.assertEqual("synthesis", self.journal()["phase"])
        self.assertTrue((self.root / ROUNDING).exists())

    def test_checkpoint_recovery_writes_a_v2_skeleton(self):
        run = self.journal()
        run["phase"] = "checkpoint"
        self.archive.save(run)
        (self.run_dir / "candidate.json").unlink()
        with self.assertRaisesRegex(ArchiveError, "Checkpoint recovered"):
            self.archive.finalize(self.prepared["run_id"])
        self.assertEqual(md.empty_candidate(self.base_root, self.prepared["checkpoint"]),
                         json.loads((self.run_dir / "candidate.json").read_text(encoding="utf-8")))

    def test_retired_id_cannot_return_in_a_later_run(self):
        self.save(self.candidate())
        self.archive.finalize(self.prepared["run_id"])
        code, output = self.cli("memory", "provenance", "--id", "PM-invoice-rounding")
        self.assertEqual(0, code, output)
        retire = [r for r in output["data"]["records"] if r["record"]["op"] == "retire"]
        self.assertEqual(1, len(retire))
        self.assertEqual(ms.record_hash(retire[0]["record"]), retire[0]["record_hash"])
        self.assertTrue(retire[0]["ledger"].startswith("0001-"))
        refund = "specs/011-refunds"
        self.write(refund + "/spec.md", "# Refunds\n\nRefunds round half-up.\n")
        self.write(refund + "/tasks.md", "# Tasks\n\n- [x] T001 Refunds\n")
        self.git("add", "-A")
        self.git("commit", "-m", "Refunds feature")
        second = self.archive.prepare([refund], [], [], skip_verification=REASON)
        run = self.archive.journal(second["run_id"])
        candidate = md.empty_candidate(run["base_memory_root"], run["checkpoint"])
        candidate.update(
            additions=[{"id": "PM-invoice-rounding", "domain": "tax", "kind": "decision", "title": "Refund rounding",
                        "text": "Refunds round half-up.", "relations": [], "selectors": []}],
            provenance=[{"entry": "PM-invoice-rounding", "units": {refund + "/spec.md": ["L3"]}}],
            coverage=[{"units": {refund + "/spec.md": ["L1"], refund + "/tasks.md": ["L1", "L3"]},
                       "action": "omitted", "reason": "Headings and tasks"},
                      {"units": {refund + "/spec.md": ["L3"]}, "action": "retained",
                       "memory_ids": ["PM-invoice-rounding"]}])
        write_json(self.archive.run_path(second["run_id"]) / "candidate.json", candidate)
        with self.assertRaisesRegex(ArchiveError, "PM-invoice-rounding is retired"):
            self.archive.finalize(second["run_id"])
        # The ledger alone also retires it, even without the registry.
        with self.assertRaisesRegex(ArchiveError, "PM-invoice-rounding is retired"):
            md.validate(self.archive.repo, run, candidate, self.archive.budgets(), set())
        self.assertEqual("synthesis", self.archive.journal(second["run_id"])["phase"])

    def test_binary_unit_is_covered_end_to_end(self):
        self.archive.abandon(self.prepared["run_id"])
        image = FEATURE + "/diagram.png"
        self.write(image, b"\x89PNG\r\n\x1a\n\x00\x00binary")
        self.git("add", "-A")
        self.git("commit", "-m", "Diagram")
        self.base_root = ms.memory_root(self.root)
        self.prepared = self.archive.prepare([FEATURE], [], [], skip_verification=REASON)
        self.run_dir = self.archive.run_path(self.prepared["run_id"])
        self.assertIn(image + ":binary", [u["id"] for u in self.journal()["units"]])
        candidate = self.candidate()
        candidate["coverage"][0]["units"][image] = ["binary"]
        self.save(candidate)
        self.assertEqual("done", self.archive.finalize(self.prepared["run_id"])["phase"])
        self.assertFalse((self.root / image).exists())


if __name__ == "__main__":
    unittest.main()
