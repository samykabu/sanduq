from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from archive import Archive, EXTENSION, POLICY
import memory_delta as md
import memory_store as ms
from git_state import ArchiveError, Repository, digest
from memory import MEMORY, REGISTRY, inventory, render
from test_memory_store import legacy_entries

SPEC = "specs/010-vat/spec.md"
TASKS = "specs/010-vat/tasks.md"
RUN_ID = "abcdef0123456789abcdef0123456789"


class MemoryDeltaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="memory-delta-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-b", "develop")
        for key, value in {"user.name": "Delta Test", "user.email": "delta@example.invalid",
                           "core.autocrlf": "false", "commit.gpgsign": "false"}.items():
            self.git("config", key, value)
        self.write(EXTENSION + "/extension.yml", "version: 1\n")
        self.write(POLICY, json.dumps({"schema_version": 1, "target_branch": "develop", "checks": {}}))
        self.write(MEMORY, render(legacy_entries()))
        self.write(REGISTRY, json.dumps({"schema_version": 1, "archived": {}, "high_water": 8}, indent=2) + "\n")
        self.write("src/app.py", "CURRENCY = 'EUR'\n")
        self.git("add", "-A")
        self.git("commit", "-m", "Initial")
        Archive(self.root).migrate()
        self.checkpoint_with()

    def checkpoint_with(self, *remove):
        self.write(SPEC, "# VAT\n\nInvoices use GBP.\n\nRounding is replaced by VAT rules.\n")
        self.write(TASKS, "# Tasks\n\n- [x] T001 Add VAT\n")
        for path in remove:
            (self.root / path).unlink()
        self.git("add", "-A")
        self.git("commit", "-m", "Checkpoint")
        self.repo = Repository(self.root)
        checkpoint = self.repo.head()
        self.run_ = {"checkpoint": checkpoint, "run_id": RUN_ID, "specs": ["specs/010-vat"],
                     "units": inventory(self.repo, checkpoint, [SPEC, TASKS]),
                     "base_memory_root": ms.memory_root(self.root), "skip_verification": "Manual test archive"}

    def git(self, *args):
        run = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        if run.returncode:
            raise AssertionError(run.stderr.decode(errors="replace"))
        return run.stdout.decode().strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())

    def entry_file(self, eid):
        return (self.root / ms.ENTRIES / f"{eid}.md").read_bytes()

    def omitted_all(self):
        candidate = md.empty_candidate(self.run_["base_memory_root"], self.run_["checkpoint"])
        candidate["coverage"] = [{"units": {SPEC: ["L1", "L3", "L5"], TASKS: ["L1", "L3"]}, "action": "omitted",
                                  "reason": "Context only"}]
        return candidate

    def full(self):
        currency = ms.parse_entry(self.entry_file("PM-invoice-currency"), "x")
        currency["text"] = "Invoices use GBP. VAT applies per PM-invoice-vat."
        currency["relations"] = ["PM-invoice-vat"]
        candidate = md.empty_candidate(self.run_["base_memory_root"], self.run_["checkpoint"])
        candidate.update(
            taxonomy_changes=[{"op": "add", "id": "tax", "label": "Tax", "definition": "Tax rules."}],
            additions=[{"id": "PM-invoice-vat", "domain": "tax", "kind": "decision", "title": "VAT replaces rounding",
                        "text": "VAT rules replace half-up rounding.", "relations": [], "selectors": []}],
            updates=[{"id": "PM-invoice-currency", "expected_hash": digest(self.entry_file("PM-invoice-currency")),
                      "entry": currency}],
            removals=[{"id": "PM-invoice-rounding", "expected_hash": digest(self.entry_file("PM-invoice-rounding")),
                       "reason": "Replaced by VAT rules", "source_unit": SPEC + ":L5", "replacement": "PM-invoice-vat"}],
            provenance=[{"entry": "PM-invoice-vat", "units": {SPEC: ["L5"], TASKS: ["L3"]}},
                        {"entry": "PM-invoice-currency", "units": {SPEC: ["L3"]}, "evidence": ["src/app.py"]}],
            coverage=[{"units": {SPEC: ["L1"], TASKS: ["L1", "L3"]}, "action": "omitted", "reason_code": "structural",
                       "reason": "Headings and task bookkeeping"},
                      {"units": {SPEC: ["L3"]}, "action": "merged", "memory_ids": ["PM-invoice-currency"]},
                      {"units": {SPEC: ["L5"]}, "action": "superseded", "memory_ids": ["PM-invoice-vat"]}])
        return candidate

    def validate(self, candidate, retired=()):
        return md.validate(self.repo, self.run_, candidate, ms.DEFAULT_BUDGETS, set(retired))

    def reject(self, mutate, pattern, retired=()):
        candidate = self.full()
        mutate(candidate)
        with self.assertRaisesRegex(ArchiveError, pattern):
            self.validate(candidate, retired)

    def test_delta_materializes_additions_updates_removals_and_taxonomy(self):
        tracked_before = self.git("ls-files", "-s", ms.MEMORY_DIR)
        base = self.run_["base_memory_root"]
        m = self.validate(self.full())
        ledger = f"{ms.PROVENANCE}/0001-{self.run_['checkpoint'][:8]}-{RUN_ID[:8]}.jsonl"
        self.assertIsNone(m.outputs[f"{ms.ENTRIES}/PM-invoice-rounding.md"])
        self.assertIn(b"VAT rules replace", m.outputs[f"{ms.ENTRIES}/PM-invoice-vat.md"])
        self.assertIn(b"Invoices use GBP", m.outputs[f"{ms.ENTRIES}/PM-invoice-currency.md"])
        self.assertNotIn(f"{ms.ENTRIES}/PM-tenant-scope.md", m.outputs)
        self.assertIn('"id": "tax"', m.outputs[ms.TAXONOMY].decode())
        for path in (f"{ms.CATALOGS}/tax/01.md", f"{ms.CATALOGS}/billing/01.md", ms.INDEX):
            self.assertIn(path, m.outputs)
        self.assertTrue(all(p.startswith(ms.MEMORY_DIR + "/") for p in m.outputs))
        header, records = ms.parse_ledger(m.outputs[ledger], "ledger")
        self.assertEqual({"ledger": Path(ledger).stem, "run_id": RUN_ID, "checkpoint": self.run_["checkpoint"],
                          "specs": ["specs/010-vat"], "verification": {"status": "skipped", "reason": "Manual test archive"}},
                         header)
        self.assertEqual([("PM-invoice-currency", "add"), ("PM-invoice-rounding", "retire"), ("PM-invoice-vat", "add")],
                         [(r["entry"], r["op"]) for r in records])
        self.assertEqual({"op": "add", "entry": "PM-invoice-vat", "units": {SPEC: ["L5"], TASKS: ["L3"]}, "evidence": []},
                         records[2])
        self.assertEqual("PM-invoice-vat", records[1]["replacement"])
        self.assertEqual({"additions": 1, "updates": 1, "removals": 1, "provenance_records": 2, "coverage_units": 5},
                         m.summary)
        # Deterministic, and the digest binds exactly these outputs.
        again = self.validate(self.full())
        self.assertEqual((m.outputs, m.result_root, m.outputs_sha256), (again.outputs, again.result_root, again.outputs_sha256))
        pairs = [[p, None if d is None else digest(d)] for p, d in sorted(m.outputs.items())]
        self.assertEqual(digest(json.dumps(pairs, separators=(",", ":")).encode()), m.outputs_sha256)
        # The real tree is untouched.
        self.assertNotEqual(base, m.result_root)
        self.assertEqual(base, ms.memory_root(self.root))
        self.assertEqual("", self.git("status", "--short"))
        self.assertEqual(tracked_before, self.git("ls-files", "-s", ms.MEMORY_DIR))
        # Applying the outputs reproduces the result root, and the result passes the memory check.
        for path, data in m.outputs.items():
            (self.root / path).unlink() if data is None else self.write(path, data)
        self.assertEqual(m.result_root, ms.memory_root(self.root))
        store = ms.Store(self.root)
        self.assertEqual([], ms.check(store))
        self.assertEqual({"PM-invoice-rounding": "PM-invoice-vat"}, store.retired)
        self.assertIn({"commit": self.run_["checkpoint"], "path": SPEC, "unit": SPEC + ":L3"},
                      store.provenance["PM-invoice-currency"]["sources"])

    def test_tombstone_and_stale_catalog_page(self):
        baseline = ms.Store(self.root).ledgers[0][2]
        scope = next(r for r in baseline if r["entry"] == "PM-tenant-scope")
        self.write(f"{ms.CATALOGS}/billing/02.md", "stray\n")
        self.checkpoint_with()
        candidate = self.omitted_all()
        candidate["tombstones"] = [{"entry": "PM-tenant-scope", "record": ms.record_hash(scope), "reason": "Wrong source"}]
        candidate["provenance"] = [{"entry": "PM-tenant-scope", "units": {SPEC: ["L1"]}}]
        m = self.validate(candidate)
        self.assertIsNone(m.outputs[f"{ms.CATALOGS}/billing/02.md"])
        _, records = ms.parse_ledger(next(d for p, d in m.outputs.items() if p.startswith(ms.PROVENANCE)), "x")
        self.assertEqual(["add", "tombstone"], [r["op"] for r in records])
        bad = self.omitted_all()
        bad["tombstones"] = [{"entry": "PM-invoice-currency", "record": ms.record_hash(scope), "reason": "Wrong"}]
        with self.assertRaisesRegex(ArchiveError, "matches no existing add record"):
            self.validate(bad)

    def test_binding_rejections(self):
        self.reject(lambda c: c.update(schema_version=1), "schema_version must be 2")
        self.reject(lambda c: c.update(base_memory_root="0" * 64), "base_memory_root differs")
        self.reject(lambda c: c.update(checkpoint="0" * 40), "checkpoint differs")
        self.write(f"{ms.ENTRIES}/PM-drift.md", "x")
        self.reject(lambda c: None, "memory root drift")

    def test_entry_rejections(self):
        add = lambda c: c["additions"][0]
        self.reject(lambda c: add(c).update(id="PM-tenant-scope"), "PM-tenant-scope already exists")
        self.reject(lambda c: add(c).update(id="PM-gone"), "PM-gone is retired", retired={"PM-gone"})
        self.reject(lambda c: c["additions"].append(copy.deepcopy(add(c))), "added more than once")
        self.reject(lambda c: add(c).update(extra=1), r"unexpected keys \['extra'\]")
        self.reject(lambda c: add(c).pop("selectors"), r"missing keys \['selectors'\]")
        self.reject(lambda c: add(c).update(text="Padded. "), "trimmed")
        self.reject(lambda c: c["updates"][0].update(id="PM-unknown"), "unknown entry 'PM-unknown'")
        self.reject(lambda c: c["updates"][0].update(expected_hash="0" * 64), "expected_hash does not match")
        self.reject(lambda c: c["removals"][0].update(id="PM-invoice-currency",
                                                      expected_hash=c["updates"][0]["expected_hash"]),
                    "PM-invoice-currency is touched more than once")
        self.reject(lambda c: c["updates"].append(copy.deepcopy(c["updates"][0])), "touched more than once")
        self.reject(lambda c: c["removals"][0].update(reason=" "), "removal needs a reason")
        self.reject(lambda c: c["removals"][0].update(source_unit=SPEC + ":L99"), "not an inventoried unit")
        self.reject(lambda c: c["removals"][0].update(replacement="PM-nowhere"), "replacement 'PM-nowhere'")

    def test_taxonomy_provenance_and_coverage_rejections(self):
        self.reject(lambda c: c["taxonomy_changes"].append({"op": "add", "id": "billing", "label": "Again"}),
                    "cannot add domain 'billing'")
        self.reject(lambda c: c["taxonomy_changes"].append({"op": "update", "id": "nope", "label": "N"}),
                    "cannot update unknown domain")
        self.reject(lambda c: c["provenance"].append({"entry": "PM-invoice-rounding", "units": {SPEC: ["L3"]}}),
                    "PM-invoice-rounding' is not in the result")
        self.reject(lambda c: c["provenance"][0]["units"].update({SPEC: ["L7"]}), "L7 is not inventoried")
        self.reject(lambda c: c["provenance"][0].update(evidence=[SPEC]), "is a specification")
        self.reject(lambda c: c["provenance"][0].update(evidence=["src/missing.py"]), "src/missing.py does not exist")
        self.reject(lambda c: c["coverage"].pop(), "L5 has no disposition")
        self.reject(lambda c: c["coverage"][1]["units"][SPEC].append("L5"), "covered more than once")
        self.reject(lambda c: c["coverage"][0]["units"].update({"specs/x.md": ["L1"]}), "unknown unit specs/x.md:L1")
        self.reject(lambda c: c["coverage"][0].update(reason=""), "needs a reason and no memory ids")
        self.reject(lambda c: c["coverage"][0].update(memory_ids=["PM-invoice-vat"]), "needs a reason and no memory ids")
        self.reject(lambda c: c["coverage"][1].update(memory_ids=[]), "must name memory ids in the result")
        self.reject(lambda c: c["coverage"][1].update(memory_ids=["PM-invoice-rounding"]), "must name memory ids")
        self.reject(lambda c: c["coverage"][1].update(memory_ids=["PM-invoice-vat"]),
                    "PM-invoice-vat lacks provenance for specs/010-vat/spec.md:L3")

    def test_result_check_rejections_aggregate(self):
        def broken(c):
            c["additions"][0]["text"] = "See PM-missing-entry. " + "x" * 5000
            c["additions"].append({"id": "PM-vat-flow", "domain": "nowhere", "kind": "behavior", "title": "Flow",
                                   "text": "Flows.", "relations": [], "selectors": []})
            c["provenance"].append({"entry": "PM-vat-flow", "units": {SPEC: ["L5"]}})
        candidate = self.full()
        broken(candidate)
        with self.assertRaises(ArchiveError) as caught:
            self.validate(candidate)
        for expected in ("PM-missing-entry does not resolve", "entry budget is 1024", "unknown domain 'nowhere'",
                         "PM-vat-flow: behavior needs implementation evidence"):
            self.assertIn(expected, str(caught.exception))

    def test_behavior_without_evidence_at_checkpoint_is_rejected(self):
        self.checkpoint_with("src/app.py")
        with self.assertRaisesRegex(ArchiveError, "PM-invoice-currency: behavior has no evidence path present"):
            self.validate(self.omitted_all())

    def test_helpers(self):
        self.assertEqual("0004-c0ffee12-abcdef01.jsonl",
                         md.ledger_name(["0000-baseline.jsonl", "0003-a-b.jsonl"], "c0ffee12" * 5, RUN_ID))
        self.assertEqual("0000-c0ffee12-abcdef01.jsonl", md.ledger_name([], "c0ffee12" * 5, RUN_ID))
        coverage = md.expand_coverage(self.full(), self.run_["units"])
        self.assertEqual([u["id"] for u in self.run_["units"]], list(coverage))
        self.assertEqual({"action": "merged", "memory_ids": ["PM-invoice-currency"], "reason": ""}, coverage[SPEC + ":L3"])
        with self.assertRaisesRegex(ArchiveError, "exhausted"):
            md.ledger_name(["9999-a-b.jsonl"], "c0ffee12" * 5, RUN_ID)
        with self.assertRaisesRegex(ArchiveError, "malformed"):
            candidate = self.full()
            candidate["updates"][0]["id"] = ["not", "a", "string"]
            self.validate(candidate)

    def test_unknown_keys_unanchored_update_and_reserved_domains(self):
        self.reject(lambda c: c.update(notes="x"), r"unknown candidate keys \['notes'\]")
        scope = ms.parse_entry(self.entry_file("PM-tenant-scope"), "x")
        scope["text"] = "Rewritten without any anchor."
        self.reject(lambda c: c["updates"].append({"id": "PM-tenant-scope", "entry": scope,
                                                   "expected_hash": digest(self.entry_file("PM-tenant-scope"))}),
                    "update of PM-tenant-scope has no provenance or coverage anchor in this run")
        # An evidence-only record cites no unit from this run, so it does not anchor the update.
        self.reject(lambda c: (c["updates"].append({"id": "PM-tenant-scope", "entry": scope,
                                                    "expected_hash": digest(self.entry_file("PM-tenant-scope"))}),
                               c["provenance"].append({"entry": "PM-tenant-scope", "units": {},
                                                       "evidence": ["src/app.py"]})),
                    "update of PM-tenant-scope has no provenance or coverage anchor in this run")
        # A stated reason makes it a reviewed correction instead; a blank reason does not.
        correction = {"id": "PM-tenant-scope", "entry": scope, "expected_hash": digest(self.entry_file("PM-tenant-scope"))}
        self.reject(lambda c: c["updates"].append({**correction, "reason": " "}), "reason must be a nonempty string")
        candidate = self.full()
        candidate["updates"].append({**correction, "reason": "Reviewer removed stale narrative."})
        self.validate(candidate)
        # A coverage target is an anchor too (the coverage provenance check then fails on its own terms).
        self.reject(lambda c: c["provenance"].pop(), "(?s)^(?!.*update of).*PM-invoice-currency lacks provenance")
        for did in ("con", "lpt9", "com1"):
            self.reject(lambda c: c["taxonomy_changes"].append({"op": "add", "id": did, "label": did.upper()}),
                        f"domain id '{did}' is a reserved Windows name")
        self.reject(lambda c: c["taxonomy_changes"].append({"op": "update", "id": "nul", "label": "N"}),
                    "'nul' is a reserved Windows name")
        candidate = self.full()
        candidate["taxonomy_changes"][0].update(id="com10")  # only the exact reserved names are refused
        candidate["additions"][0]["domain"] = "com10"
        self.validate(candidate)

    def test_stray_files_in_the_base_are_rejected(self):
        for stray in ("Thumbs.db", "notes.txt", "entries/.archive-x1y2", "catalogs/billing/notes.md"):
            self.write(f"{ms.MEMORY_DIR}/{stray}", "x")
        self.assertEqual(self.run_["base_memory_root"], ms.memory_root(self.root))  # strays are not hashed
        with self.assertRaises(ArchiveError) as caught:
            self.validate(self.full())
        for stray in ("Thumbs.db", "notes.txt", "entries/.archive-x1y2", "catalogs/billing/notes.md"):
            self.assertIn(f"{ms.MEMORY_DIR}/{stray}: stray file in the base memory", str(caught.exception))

    def test_binary_and_empty_units_in_coverage_and_provenance(self):
        image, empty = "specs/010-vat/flow.png", "specs/010-vat/notes.md"
        self.write(image, b"\x89PNG\x00\x01")
        self.write(empty, "\n")
        self.checkpoint_with()
        self.run_["units"] = inventory(self.repo, self.run_["checkpoint"], [SPEC, TASKS, image, empty])
        candidate = self.full()
        candidate["provenance"][0]["units"][image] = ["binary"]
        candidate["coverage"] += [{"units": {image: ["binary"]}, "action": "retained", "memory_ids": ["PM-invoice-vat"]},
                                  {"units": {empty: ["empty"]}, "action": "omitted", "reason": "Empty file"}]
        coverage = md.expand_coverage(candidate, self.run_["units"])
        self.assertEqual("retained", coverage[image + ":binary"]["action"])
        self.assertEqual("omitted", coverage[empty + ":empty"]["action"])
        m = self.validate(candidate)
        _, records = ms.parse_ledger(next(d for p, d in m.outputs.items() if p.startswith(ms.PROVENANCE)), "x")
        self.assertEqual({SPEC: ["L5"], TASKS: ["L3"], image: ["binary"]}, records[2]["units"])
        candidate["coverage"].pop()
        with self.assertRaisesRegex(ArchiveError, "notes.md:empty has no disposition"):
            self.validate(candidate)

    def test_evidence_only_record_repairs_behavior_evidence_rot(self):
        self.write("src/billing.py", "CURRENCY = 'GBP'\n")
        self.checkpoint_with("src/app.py")
        candidate = self.omitted_all()
        with self.assertRaisesRegex(ArchiveError, "PM-invoice-currency: behavior has no evidence path present"):
            self.validate(candidate)
        candidate["provenance"] = [{"entry": "PM-invoice-currency", "units": {}}]
        with self.assertRaisesRegex(ArchiveError, "needs units, evidence or both"):
            self.validate(candidate)
        candidate["provenance"] = [{"entry": "PM-invoice-currency", "evidence": ["src/billing.py"]}]
        m = self.validate(candidate)
        _, records = ms.parse_ledger(next(d for p, d in m.outputs.items() if p.startswith(ms.PROVENANCE)), "x")
        self.assertEqual([{"op": "add", "entry": "PM-invoice-currency", "units": {}, "evidence": ["src/billing.py"]}],
                         records)
        # An evidence-only record adds no source, so it cannot satisfy a coverage target for a unit.
        target = copy.deepcopy(candidate)
        target["coverage"] = [{"units": {SPEC: ["L1", "L3", "L5"], TASKS: ["L1"]}, "action": "omitted", "reason": "x"},
                              {"units": {TASKS: ["L3"]}, "action": "retained", "memory_ids": ["PM-invoice-currency"]}]
        with self.assertRaisesRegex(ArchiveError, "PM-invoice-currency lacks provenance for specs/010-vat/tasks.md:L3"):
            self.validate(target)
        for path, data in m.outputs.items():
            (self.root / path).unlink() if data is None else self.write(path, data)
        store = ms.Store(self.root)
        self.assertEqual([], ms.check(store))
        folded = store.provenance["PM-invoice-currency"]
        self.assertEqual(["specs/007-invoice/spec.md:L3"], [s["unit"] for s in folded["sources"]])  # no sources added
        self.assertEqual(["src/app.py", "src/billing.py"], [e["path"] for e in folded["evidence"]])


if __name__ == "__main__":
    unittest.main()
