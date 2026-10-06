from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from archive import Archive, EXTENSION, POLICY
import memory_store as ms
from git_state import ArchiveError, digest
from memory import MEMORY, REGISTRY, render

C1 = "1" * 40
C2 = "2" * 40


def legacy_entries():
    return [
        {"id": "PM-invoice-currency", "domain": "Billing", "kind": "behavior", "title": "Invoices use EUR",
         "text": "Invoices use EUR. See PM-invoice-rounding.\n\n- Arabic: الفواتير باليورو\n- Quote \" and \\ and `code`.",
         "sources": [{"commit": C1, "path": "specs/007-invoice/spec.md", "unit": "specs/007-invoice/spec.md:L3"}],
         "evidence": [{"commit": C1, "path": "src/app.py"}]},
        {"id": "PM-invoice-rounding", "domain": "Billing", "kind": "decision", "title": "Round half up",
         "text": "Amounts round half up.",
         "sources": [{"commit": C1, "path": "specs/007-invoice/spec.md", "unit": "specs/007-invoice/spec.md:L5"}],
         "evidence": []},
        {"id": "PM-tenant-scope", "domain": "Tenant scoping, and shell", "kind": "limit", "title": "Scope is per request",
         "text": "Scope is resolved per request.",
         "sources": [{"commit": C2, "path": "specs/008-scope/spec.md", "unit": "specs/008-scope/spec.md:L1"}],
         "evidence": []},
    ]


class MemoryFormatTests(unittest.TestCase):
    def test_entry_round_trip_preserves_text_and_escapes(self):
        entry = {"id": "PM-x", "domain": "billing", "kind": "limit", "title": "Quote \" back\\slash ç",
                 "text": "Body with `code`, \"quotes\", \\ and DEL \x7f and العربية.", "relations": ["PM-y"],
                 "selectors": [{"kind": "route", "value": "POST /api/v1/x/{id}"}]}
        data = ms.emit_entry(entry)
        self.assertEqual(entry, ms.parse_entry(data, "PM-x.md"))

    def test_typed_links_round_trip_and_empty_lists_are_not_canonical(self):
        entry = {"id": "PM-x", "domain": "billing", "kind": "decision", "title": "T", "text": "Body.",
                 "relations": ["PM-y"], "constrains": ["PM-z"], "supersedes": ["PM-old"], "selectors": []}
        data = ms.emit_entry(entry)
        self.assertIn(b'relations = ["PM-y"]\nconstrains = ["PM-z"]\nsupersedes = ["PM-old"]\n', data)
        self.assertEqual(entry, ms.parse_entry(data, "PM-x.md"))
        self.assertEqual(["PM-y", "PM-z", "PM-old"], ms.links(entry))
        with self.assertRaisesRegex(ArchiveError, "canonical"):
            ms.parse_entry(data.replace(b'supersedes = ["PM-old"]', b"supersedes = []"), "PM-x.md")

    def test_noncanonical_or_unknown_header_is_rejected(self):
        good = ms.emit_entry({"id": "PM-x", "domain": "d", "kind": "limit", "title": "T", "text": "Body."})
        with self.assertRaisesRegex(ArchiveError, "canonical"):
            ms.parse_entry(good.replace(b'title = "T"', b'title="T"'), "PM-x.md")
        with self.assertRaisesRegex(ArchiveError, "unknown header"):
            ms.parse_entry(good.replace(b"+++\nBody", b'owner = "me"\n+++\nBody'), "PM-x.md")
        with self.assertRaisesRegex(ArchiveError, "trimmed"):
            ms.parse_entry(good.replace(b"Body.\n", b"Body.  \n"), "PM-x.md")

    def test_fold_expands_compact_records_and_honours_tombstones_and_retirement(self):
        baseline = {"op": "add", "entry": "PM-a", "sources": [{"commit": C1, "path": "s.md", "unit": "s.md:L1"}],
                    "evidence": [{"commit": C1, "path": "src/a.py"}]}
        later = {"op": "add", "entry": "PM-a", "units": {"t.md": ["L4", "L9"]}, "evidence": ["src/b.py"]}
        ledgers = [("0000-baseline.jsonl", {"ledger": "0000-baseline"}, [baseline]),
                   ("0001-run.jsonl", {"ledger": "0001-run", "checkpoint": C2},
                    [later, {"op": "retire", "entry": "PM-old", "reason": "Superseded", "replacement": "PM-a"}])]
        folded, retired = ms.fold(ledgers)
        self.assertEqual(["s.md:L1", "t.md:L4", "t.md:L9"], [s["unit"] for s in folded["PM-a"]["sources"]])
        self.assertEqual(C2, folded["PM-a"]["sources"][1]["commit"])
        self.assertEqual(["src/a.py", "src/b.py"], [e["path"] for e in folded["PM-a"]["evidence"]])
        self.assertEqual({"PM-old": "PM-a"}, retired)
        ledgers.append(("0002-fix.jsonl", {"ledger": "0002-fix"},
                        [{"op": "tombstone", "entry": "PM-a", "record": ms.record_hash(later), "reason": "Wrong unit"}]))
        folded, _ = ms.fold(ledgers)
        self.assertEqual(["s.md:L1"], [s["unit"] for s in folded["PM-a"]["sources"]])

    def test_compact_record_needs_checkpoint_and_ledger_must_be_canonical(self):
        with self.assertRaisesRegex(ArchiveError, "checkpoint"):
            ms.fold([("0001.jsonl", {"ledger": "0001"}, [{"op": "add", "entry": "PM-a", "units": {"s.md": ["L1"]}}])])
        data = ms.emit_ledger({"ledger": "x"}, [{"op": "add", "entry": "PM-a", "sources": [], "evidence": []}])
        self.assertEqual(({"ledger": "x"}, [{"op": "add", "entry": "PM-a", "sources": [], "evidence": []}]),
                         ms.parse_ledger(data, "x.jsonl"))
        with self.assertRaisesRegex(ArchiveError, "canonical"):
            ms.parse_ledger(data.replace(b'"op":"add"', b'"op": "add"'), "x.jsonl")


class MemoryStoreRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="memory-store-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-b", "develop")
        for key, value in {"user.name": "Memory Test", "user.email": "memory@example.invalid",
                           "core.autocrlf": "false", "commit.gpgsign": "false"}.items():
            self.git("config", key, value)
        self.write(EXTENSION + "/extension.yml", "version: 1\n")
        self.write(POLICY, json.dumps({"schema_version": 1, "target_branch": "develop", "checks": {}}))
        self.legacy = render(legacy_entries())
        self.write(MEMORY, self.legacy)
        self.write(REGISTRY, json.dumps({"schema_version": 1, "archived": {}, "high_water": 8}, indent=2) + "\n")
        self.write("specs/009-open/spec.md", "# Open\n")
        self.write("src/app.py", "CURRENCY = 'EUR'\n")
        self.git("add", "-A")
        self.git("commit", "-m", "Initial")
        self.archive = Archive(self.root)

    def git(self, *args):
        run = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        if run.returncode:
            raise AssertionError(run.stderr.decode(errors="replace"))
        return run.stdout.decode().strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())

    def test_migration_is_lossless_committed_and_one_way(self):
        result = self.archive.migrate()
        self.assertEqual(3, result["entries"])
        self.assertEqual(result["commit"], self.git("rev-parse", "HEAD"))
        self.assertIn("Legacy-Memory-SHA256: " + digest(self.legacy), self.git("log", "-1", "--format=%B"))
        self.assertEqual("", self.git("status", "--short"))
        store = ms.Store(self.root)
        self.assertEqual(self.legacy, ms.export(store))
        self.assertEqual({"billing", "tenant-scoping-and-shell"}, set(store.domains))
        self.assertEqual(["PM-invoice-rounding"], store.entries["PM-invoice-currency"]["relations"])
        self.assertIn("specs/memory/INDEX.md", (self.root / MEMORY).read_text(encoding="utf-8"))
        registry = json.loads((self.root / REGISTRY).read_text(encoding="utf-8"))
        self.assertEqual((2, digest(self.legacy)), (registry["memory_format"], registry["legacy_memory_sha256"]))
        self.assertEqual([], self.archive.memory_check()["problems"])
        with self.assertRaisesRegex(ArchiveError, "already format 2"):
            self.archive.migrate()
        # Format 2 now takes the v2 delta path; this spec fails later, on its missing tasks.
        with self.assertRaisesRegex(ArchiveError, "tasks"):
            self.archive.prepare(["specs/009-open"], [], [], skip_verification="test")

    def test_migration_refuses_uncommitted_memory_edits(self):
        self.write(MEMORY, self.legacy + b"\n")
        with self.assertRaisesRegex(ArchiveError, "committed"):
            self.archive.migrate()
        self.assertFalse((self.root / ms.MEMORY_DIR).exists())

    def test_check_reports_reference_domain_budget_evidence_and_stale_views(self):
        self.archive.migrate()
        entries = self.root / ms.ENTRIES
        rounding = ms.parse_entry((entries / "PM-invoice-rounding.md").read_bytes(), "x")
        rounding["text"] = "See PM-missing-entry. " + "x" * 5000
        (entries / "PM-invoice-rounding.md").write_bytes(ms.emit_entry(rounding))
        scope = ms.parse_entry((entries / "PM-tenant-scope.md").read_bytes(), "x")
        scope.update(domain="nowhere", kind="behavior")
        (entries / "PM-tenant-scope.md").write_bytes(ms.emit_entry(scope))
        problems = "\n".join(ms.check(ms.Store(self.root)))
        for expected in ("PM-missing-entry does not resolve", "unknown domain 'nowhere'", "entry budget is 1024",
                         "behavior needs implementation evidence", "generated view is stale"):
            self.assertIn(expected, problems)

    def test_check_rejects_self_duplicate_and_dead_typed_links(self):
        self.archive.migrate()
        entries = self.root / ms.ENTRIES
        currency = ms.parse_entry((entries / "PM-invoice-currency.md").read_bytes(), "x")
        currency.update(constrains=["PM-invoice-currency", "PM-gone"], supersedes=["PM-invoice-rounding"])
        (entries / "PM-invoice-currency.md").write_bytes(ms.emit_entry(currency))
        problems = "\n".join(ms.check(ms.Store(self.root), None, {"PM-gone"}))
        for expected in ("PM-invoice-currency: links cannot point to the entry itself or repeat an id",
                         "constrains PM-gone, which is not a live entry"):
            self.assertIn(expected, problems)
        currency.update(constrains=["PM-tenant-scope"], supersedes=["PM-gone"])  # a retired id may be superseded
        (entries / "PM-invoice-currency.md").write_bytes(ms.emit_entry(currency))
        self.assertFalse([p for p in ms.check(ms.Store(self.root), None, {"PM-gone"}) if "link" in p or "constrains" in p])

    def test_memory_root_is_order_stable_and_ignores_reported_strays(self):
        self.archive.migrate()
        files = {p: (self.root / p).read_bytes() for p in ms.memory_files(self.root)[0]}
        root = ms.memory_root(self.root)
        for order in (sorted(files), sorted(files, reverse=True)):
            other = Path(tempfile.mkdtemp(dir=self.temp.name))
            for path in order:
                (other / path).parent.mkdir(parents=True, exist_ok=True)
                (other / path).write_bytes(files[path])
            self.assertEqual(root, ms.memory_root(other))
        for stray in ("Thumbs.db", "notes.txt", "entries/.archive-ab12", "provenance/README.md"):
            self.write(f"{ms.MEMORY_DIR}/{stray}", "x")
        self.assertEqual(root, ms.memory_root(self.root))
        problems = ms.check(ms.Store(self.root))
        self.assertEqual(sorted(f"{ms.MEMORY_DIR}/{s}: stray file in {ms.MEMORY_DIR}; remove it." for s in
                                ("Thumbs.db", "notes.txt", "entries/.archive-ab12", "provenance/README.md")), problems)

    def test_check_rejects_reserved_domain_ids(self):
        self.archive.migrate()
        taxonomy = json.loads((self.root / ms.TAXONOMY).read_bytes())
        taxonomy["domains"][0]["id"] = "aux"
        (self.root / ms.TAXONOMY).write_bytes(json.dumps(taxonomy).encode())
        self.assertIn("taxonomy.json: domain id 'aux' is a reserved Windows name.", ms.check(ms.Store(self.root)))

    def test_catalog_pages_respect_budget_and_index_links_every_page(self):
        self.archive.migrate()
        store = ms.Store(self.root)
        for n in range(60):
            store.entries[f"PM-bulk-{n:03d}"] = {"id": f"PM-bulk-{n:03d}", "domain": "billing", "kind": "lesson",
                                                 "title": "A fairly long title describing one billing lesson " * 2,
                                                 "text": "x", "relations": [], "selectors": []}
        outputs = ms.generated(store, {"catalog_page": 600})
        pages = sorted(p for p in outputs if p.startswith(ms.CATALOGS + "/billing/"))
        self.assertGreater(len(pages), 1)
        self.assertTrue(all(ms.tokens(outputs[p].decode()) <= 600 for p in pages))
        index = outputs[ms.INDEX].decode()
        self.assertTrue(all(p.removeprefix(ms.MEMORY_DIR + "/") in index for p in pages))

    def test_memory_directory_is_not_a_live_spec_reference(self):
        self.archive.migrate()
        self.write("specs/memory/entries/note.txt", "historical: specs/009-open/spec.md\n")
        self.write("README.md", "Live pointer: specs/009-open/spec.md\n")
        self.git("add", "-A")
        self.assertEqual(["README.md"], self.archive.references(["specs/009-open"]))

    def test_cli_export_check_and_index(self):
        cli = [sys.executable, str(SCRIPTS / "archive.py"), "--root", str(self.root)]
        self.assertEqual(0, subprocess.run(cli + ["migrate"], capture_output=True).returncode)
        exported = subprocess.run(cli + ["memory", "export"], capture_output=True)
        self.assertEqual(self.legacy, exported.stdout)
        (self.root / ms.INDEX).write_text("stale\n", encoding="utf-8")
        failed = subprocess.run(cli + ["memory", "check"], capture_output=True, text=True)
        self.assertEqual(1, failed.returncode)
        self.assertIn("INDEX.md: generated view is stale", failed.stdout)
        self.assertEqual(0, subprocess.run(cli + ["memory", "index"], capture_output=True).returncode)
        checked = json.loads(subprocess.run(cli + ["memory", "check"], capture_output=True, text=True).stdout)
        self.assertTrue(checked["success"])


if __name__ == "__main__":
    unittest.main()
