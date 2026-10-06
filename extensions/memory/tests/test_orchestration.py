from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS.parent / "tests")]
from archive import Archive, EXTENSION, POLICY
import memory_delta as md
import memory_store as ms
import orchestration as orch
from git_state import ArchiveError, digest, write_json
from memory import MEMORY, REGISTRY, render
from test_memory_store import legacy_entries

VAT, FX = "specs/010-vat", "specs/011-fx"
VSPEC, VTASKS, FSPEC, FTASKS = VAT + "/spec.md", VAT + "/tasks.md", FX + "/spec.md", FX + "/tasks.md"
REASON = "Verification runs in a separate pipeline"
CUR, ROUND, TENANT = "PM-invoice-currency", "PM-invoice-rounding", "PM-tenant-scope"
TENANT_DOMAIN = "tenant-scoping-and-shell"


def group(*uids):
    out = {}
    for uid in uids:
        path, item = uid.rsplit(":", 1)
        out.setdefault(path, []).append(item)
    return out


def entry(eid, title, text, domain="billing", relations=(), selectors=()):
    return {"id": eid, "domain": domain, "kind": "decision", "title": title, "text": text,
            "relations": list(relations), "selectors": list(selectors)}


def prov(eid, *uids):
    return {"entry": eid, "units": group(*uids)}


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="memory-orch-test-")
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
        # VAT names src/app.py (ranks the billing entries); FX has no hints and fewer units, so it gets the rest.
        self.write(VSPEC, "# VAT\n\nInvoices use GBP per `src/app.py`.\n\nRounding is replaced by VAT rules.\n")
        self.write(VTASKS, "# Tasks\n\n- [x] T001 Add VAT\n")
        self.write(FSPEC, "# FX\n\nRates refresh hourly.\n")
        self.write(FTASKS, "# Tasks\n\n- [x] T001 Add FX\n")
        self.prepare()

    def prepare(self):
        self.git("add", "-A")
        self.git("commit", "-m", "Features")
        self.prepared = self.archive.prepare([VAT, FX], [], [], skip_verification=REASON)
        self.run_id = self.prepared["run_id"]
        self.run_dir = self.archive.run_path(self.run_id)

    def git(self, *args):
        run = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        if run.returncode:
            raise AssertionError(run.stderr.decode(errors="replace"))
        return run.stdout.decode().strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())

    def load(self, path):
        return json.loads(Path(path).read_bytes())

    def journal(self):
        return self.archive.journal(self.run_id)

    def cli(self, *args):
        run = subprocess.run([sys.executable, str(SCRIPTS / "archive.py"), "--root", str(self.root), *args],
                             capture_output=True)
        return run.returncode, json.loads(run.stdout)

    def entry_file(self, eid):
        return (self.root / ms.ENTRIES / f"{eid}.md").read_bytes()

    def base(self, eid):
        return ms.parse_entry(self.entry_file(eid), eid)

    # ---- packets and fragments ----

    def packets(self, **kw):
        return orch.packets(self.archive.repo, self.journal(), self.run_dir, **{"by": "spec", **kw})

    def packet(self, pkt):
        return self.load(self.run_dir / "packets" / f"{pkt}.json")

    def tamper(self, pkt, fn):
        packet = self.packet(pkt)
        fn(packet)
        write_json(self.run_dir / "packets" / f"{pkt}.json", packet)

    def claim(self, pkt, domain):
        """Tamper one packet file so it (alone) believes it owns `domain`; the other packets are unchanged."""
        def fn(p):
            p["ownership"][domain] = pkt
            p["owned_domains"] = sorted(set(p["owned_domains"]) | {domain})
            p["entries"] = sorted(p["entries"] + [
                {"id": e["id"], "domain": domain, "title": e["title"], "expected_hash": digest(self.entry_file(e["id"]))}
                for e in ms.Store(self.root).entries.values() if e["domain"] == domain], key=lambda x: x["id"])
            p["related"] = [r for r in p["related"] if r["domain"] != domain]
        self.tamper(pkt, fn)

    def fragment(self, pkt, covered=None, **lists):
        """Every packet unit not in `covered` ({uid: (action, ids)}) is omitted."""
        covered = covered or {}
        uids = [u["id"] for u in self.packet(pkt)["units"]]
        omitted = [u for u in uids if u not in covered]
        run = self.journal()
        frag = {**md.empty_candidate(run["base_memory_root"], run["checkpoint"]), "packet": pkt, "proposals": [],
                "coverage": ([{"units": group(*omitted), "action": "omitted", "reason": "Headings and tasks"}]
                             if omitted else [])
                + [{"units": group(u), "action": a, "memory_ids": ids} for u, (a, ids) in covered.items()]}
        frag.update(lists)
        return frag

    def save(self, frag):
        path = self.run_dir / "fragments" / f"{frag['packet']}.json"
        write_json(path, frag)
        return path

    def check(self, frag):
        return orch.fragment_check(self.archive.repo, self.journal(), self.run_dir, self.save(frag), set())

    def update(self, eid, **changes):
        return {"id": eid, "expected_hash": digest(self.entry_file(eid)), "entry": {**self.base(eid), **changes}}

    def removal(self, eid, source_unit, replacement=None):
        return {"id": eid, "expected_hash": digest(self.entry_file(eid)), "reason": "Superseded",
                "source_unit": source_unit, "replacement": replacement}

    def frag_a(self, **lists):
        """p01 (VAT): updates the currency entry it owns."""
        return self.fragment("p01", {VSPEC + ":L3": ("merged", [CUR])},
                             updates=[self.update(CUR, title="Invoices use GBP", text="Invoices use GBP. See PM-invoice-rounding.")],
                             provenance=[prov(CUR, VSPEC + ":L3")], **lists)

    def frag_b(self, title="FX rates refresh hourly", **lists):
        """p02 (FX): adds one decision."""
        return self.fragment("p02", {FSPEC + ":L3": ("retained", ["PM-fx-rates"])},
                             additions=[entry("PM-fx-rates", title, "Exchange rates refresh every hour.")],
                             provenance=[prov("PM-fx-rates", FSPEC + ":L3")], **lists)

    def unchecked(self):
        """Merge past fragment_check, to reach the defensive cross-fragment checks valid fragments cannot trigger."""
        return patch.object(orch, "fragment_check", lambda repo, run, run_dir, path, retired: {
            "valid": True, "packet": Path(path).stem, "problems": [], "warnings": [], "summary": {}})

    def merge(self):
        return orch.merge(self.archive.repo, self.journal(), self.run_dir, set())

    def conflicts(self, *frags):
        for frag in frags:
            self.save(frag)
        before = (self.run_dir / "candidate.json").read_bytes()
        with self.assertRaisesRegex(ArchiveError, r"Merge rejected: \d+ conflict"):
            self.merge()
        self.assertEqual(before, (self.run_dir / "candidate.json").read_bytes())
        report = self.load(self.run_dir / "merge.json")
        self.assertFalse(report["merged"])
        for conflict in report["conflicts"]:
            self.assertEqual({"class", "detail", "packets"}, set(conflict))
        return [c["class"] for c in report["conflicts"]], report

    def assert_valid(self, frag):
        report = self.check(frag)
        self.assertTrue(report["valid"], report["problems"])
        return report

    # ---- packets ----

    def test_packets_partition_units_and_assign_every_domain_one_owner(self):
        result = self.packets()
        run = self.journal()
        self.assertEqual(["p01", "p02"], [p["packet"] for p in result["packets"]])
        files = {p: (self.run_dir / "packets" / f"{p}.json").read_bytes() for p in ("p01", "p02")}
        self.packets()
        self.assertEqual(files, {p: (self.run_dir / "packets" / f"{p}.json").read_bytes() for p in files})
        self.assertEqual(["p01.json", "p02.json"], sorted(p.name for p in (self.run_dir / "packets").iterdir()))
        p1, p2 = self.packet("p01"), self.packet("p02")
        self.assertEqual(([VAT], [FX]), (p1["specs"], p2["specs"]))
        self.assertEqual(run["units"], p1["units"] + p2["units"])
        for p in (p1, p2):
            self.assertEqual((1, run["run_id"], run["checkpoint"], run["base_memory_root"], "spec", f"fragments/{p['packet']}.json"),
                             (p["schema_version"], p["run_id"], p["checkpoint"], p["base_memory_root"], p["by"], p["fragment"]))
        store = ms.Store(self.root)
        self.assertEqual({"billing": "p01", TENANT_DOMAIN: "p02"}, result["ownership"])
        self.assertEqual(set(store.domains), set(result["ownership"]))
        self.assertEqual(result["ownership"], p1["ownership"])
        self.assertEqual(result["ownership"], p2["ownership"])
        self.assertEqual((["billing"], [TENANT_DOMAIN]), (p1["owned_domains"], p2["owned_domains"]))
        self.assertEqual([CUR, ROUND], [e["id"] for e in p1["entries"]])
        self.assertEqual([TENANT], [e["id"] for e in p2["entries"]])
        for e in p1["entries"] + p2["entries"]:
            self.assertEqual(digest(self.entry_file(e["id"])), e["expected_hash"])
            self.assertEqual((store.entries[e["id"]]["domain"], store.entries[e["id"]]["title"]), (e["domain"], e["title"]))
        self.assertEqual(([], []), (p1["related"], p2["related"]))  # p01's hits are its own; p02 has no hints
        # Re-packeting with drafts on disk would orphan them.
        self.save(self.frag_a())
        with self.assertRaisesRegex(ArchiveError, "Fragments exist"):
            self.packets()

    def test_max_units_splits_at_file_boundaries_and_oversized_files_at_headings(self):
        result = self.packets(max_units=2)
        packets = [self.packet(p["packet"]) for p in result["packets"]]
        self.assertEqual(["p01", "p02", "p03", "p04", "p05"], [p["packet"] for p in packets])
        self.assertEqual([[VSPEC], [VSPEC], [VTASKS], [FSPEC], [FTASKS]],
                         [sorted({u["path"] for u in p["units"]}) for p in packets])
        self.assertEqual([2, 1], [len(p["units"]) for p in packets[:2]])  # the 3-unit spec splits under one heading
        self.assertTrue(all(len(p["units"]) <= 2 for p in packets))
        self.assertEqual(self.journal()["units"], [u for p in packets for u in p["units"]])
        self.assertEqual([[VAT], [VAT], [VAT], [FX], [FX]], [p["specs"] for p in packets])
        self.assertEqual(set(ms.Store(self.root).domains), set(result["ownership"]))

    def test_domain_packets_are_a_valid_partition_with_full_ownership(self):
        result = self.packets(by="domain", max_units=6)
        # Dominant domains split the specs: VAT ranks billing; FX has no hints and comes last.
        self.assertEqual([[VAT], [FX]], [p["specs"] for p in result["packets"]])
        run = self.journal()
        packets = [self.packet(p["packet"]) for p in result["packets"]]
        units = [u for p in packets for u in p["units"]]
        self.assertEqual(sorted(u["id"] for u in run["units"]), sorted(u["id"] for u in units))
        self.assertEqual(len(units), len({u["id"] for u in units}))
        order = [u["id"] for u in run["units"]]
        for p in packets:
            self.assertEqual("domain", p["by"])
            ids = [u["id"] for u in p["units"]]
            self.assertEqual(sorted(ids, key=order.index), ids)
            self.assertEqual(result["ownership"], p["ownership"])
        self.assertEqual(set(ms.Store(self.root).domains), set(result["ownership"]))
        self.assertTrue(set(result["ownership"].values()) <= {p["packet"] for p in packets})
        self.assertEqual(sorted(result["ownership"]), sorted(d for p in packets for d in p["owned_domains"]))

    # ---- fragment_check ----

    def test_valid_fragment_passes_and_cli_exit_codes(self):
        self.packets()
        report = self.assert_valid(self.frag_a())
        self.assertEqual(("p01", []), (report["packet"], report["problems"]))
        self.assert_valid(self.frag_b())
        code, output = self.cli("fragment-check", "--run", self.run_id, "--fragment", str(self.run_dir / "fragments" / "p02.json"))
        self.assertEqual((0, True, True), (code, output["success"], output["data"]["valid"]))
        frag = self.frag_b()
        frag["coverage"].pop()
        self.save(frag)
        code, output = self.cli("fragment-check", "--run", self.run_id, "--fragment", str(self.run_dir / "fragments" / "p02.json"))
        self.assertEqual((1, False, False), (code, output["success"], output["data"]["valid"]))
        self.assertRegex(output["error"], r"Fragment has \d+ problem\(s\)\.")

    def test_non_owner_update_is_rejected_with_a_proposal_hint(self):
        self.packets()
        frag = self.fragment("p02", {FSPEC + ":L3": ("merged", [CUR])},
                             updates=[self.update(CUR, text="Invoices use GBP. See PM-invoice-rounding.")],
                             provenance=[prov(CUR, FSPEC + ":L3")])
        report = self.check(frag)
        self.assertFalse(report["valid"])
        self.assertTrue(any(f"{CUR} is owned by p01; submit a proposal" in p for p in report["problems"]), report["problems"])
        frag = self.fragment("p02", removals=[self.removal(ROUND, FSPEC + ":L3")])
        self.assertTrue(any("owned by p01" in p for p in self.check(frag)["problems"]))

    def test_coverage_must_be_exactly_the_packet_units(self):
        self.packets()
        outside = self.frag_b()
        outside["coverage"].append({"units": group(VSPEC + ":L1"), "action": "omitted", "reason": "Not mine"})
        gap = self.frag_b()
        gap["coverage"][0]["units"][FTASKS].remove("L3")
        double = self.frag_b()
        double["coverage"].append({"units": group(FTASKS + ":L3"), "action": "omitted", "reason": "Twice"})
        for frag in (outside, gap, double):
            report = self.check(frag)
            self.assertFalse(report["valid"], frag["coverage"])
            self.assertTrue(report["problems"])

    def test_bad_expected_hash_is_rejected(self):
        self.packets()
        frag = self.frag_a()
        frag["updates"][0]["expected_hash"] = "0" * 64
        report = self.check(frag)
        self.assertFalse(report["valid"])
        self.assertTrue(any("expected_hash" in p for p in report["problems"]), report["problems"])

    # ---- merge ----

    def test_merge_success_writes_candidate_and_merge_report(self):
        self.packets()
        a, b = self.frag_a(), self.frag_b()
        paths = [self.save(a), self.save(b)]
        code, output = self.cli("merge", "--run", self.run_id)
        self.assertEqual((0, True), (code, output["success"]), output)
        raw = (self.run_dir / "candidate.json").read_bytes()
        expected = md.empty_candidate(self.journal()["base_memory_root"], self.journal()["checkpoint"])
        for key in ("additions", "updates", "removals", "provenance", "tombstones", "taxonomy_changes", "coverage",
                    "migrations", "repairs"):
            expected[key] = a[key] + b[key]
        self.assertEqual(expected, json.loads(raw))
        report = self.load(self.run_dir / "merge.json")
        self.assertEqual({"merged": True, "candidate_sha256": digest(raw), "conflicts": [], "proposals": {},
                          "fragments": {"p01": digest(paths[0].read_bytes()), "p02": digest(paths[1].read_bytes())},
                          "packets": {p: digest((self.run_dir / "packets" / f"{p}.json").read_bytes())
                                      for p in ("p01", "p02")}}, report)
        self.assertEqual(report, output["data"])
        _, materialized = self.archive.materialize(self.journal())
        self.assertEqual(({"additions": 1, "updates": 1, "removals": 0}, "missing"),
                         ({k: materialized["summary"][k] for k in ("additions", "updates", "removals")},
                          materialized["review"]["status"]))

    def test_proposals_route_to_the_owner_and_never_enter_the_candidate(self):
        self.packets()
        proposals = [{"id": CUR, "action": "update", "reason": "FX invoices may use USD",
                      "entry": {**self.base(CUR), "text": "Invoices use GBP or USD."}},
                     {"id": ROUND, "action": "remove", "reason": "FX rounding replaces it", "entry": None}]
        self.save(self.frag_a())
        self.assert_valid(self.frag_b(proposals=proposals))
        report = self.merge()
        self.assertEqual({"p01": [{"from": "p02", **p} for p in proposals]}, report["proposals"])
        candidate = self.load(self.run_dir / "candidate.json")
        self.assertNotIn("proposals", candidate)
        self.assertEqual(self.frag_a()["updates"], candidate["updates"])
        self.assertEqual([], candidate["removals"])

    def test_merge_missing_fragment(self):
        self.packets()
        classes, _ = self.conflicts(self.frag_a())
        self.assertIn("missing-fragment", classes)

    def test_merge_fragment_invalid(self):
        self.packets()
        b = self.frag_b()
        b["coverage"].pop()
        classes, report = self.conflicts(self.frag_a(), b)
        self.assertIn("fragment-invalid", classes)
        self.assertTrue(any("p02" in c["packets"] for c in report["conflicts"] if c["class"] == "fragment-invalid"))

    def test_merge_id_collision(self):
        self.packets()
        a = self.frag_a(additions=[entry("PM-fx-rates", "FX rates refresh hourly", "Exchange rates refresh every hour.")])
        a["provenance"].append(prov("PM-fx-rates", VSPEC + ":L5"))
        a["coverage"][0]["units"][VSPEC].remove("L5")
        a["coverage"].append({"units": group(VSPEC + ":L5"), "action": "retained", "memory_ids": ["PM-fx-rates"]})
        self.assert_valid(a)
        self.assertEqual(["id-collision"], self.conflicts(a, self.frag_b())[0])

    # Ownership makes these unreachable through checked fragments; merge still rejects them defensively.
    def test_merge_double_update(self):
        self.packets()
        b = self.fragment("p02", {FSPEC + ":L3": ("merged", [CUR])},
                          updates=[self.update(CUR, text="Invoices use USD. See PM-invoice-rounding.")],
                          provenance=[prov(CUR, FSPEC + ":L3")])
        with self.unchecked():
            classes = self.conflicts(self.frag_a(), b)[0]
        self.assertEqual(["double-update", "ownership"], classes)

    def test_merge_update_removal(self):
        self.packets()
        b = self.fragment("p02", removals=[self.removal(CUR, FSPEC + ":L3")])
        with self.unchecked():
            self.assertEqual(["update-removal", "ownership"], self.conflicts(self.frag_a(), b)[0])

    def test_merge_double_removal(self):
        self.packets()
        a = self.fragment("p01", removals=[self.removal(ROUND, VSPEC + ":L5")])
        b = self.fragment("p02", removals=[self.removal(ROUND, FSPEC + ":L3")])
        self.assert_valid(a)
        with self.unchecked():
            self.assertEqual(["double-removal", "ownership"], self.conflicts(a, b)[0])

    def test_merge_ownership_rejects_any_tampered_packet_map(self):
        for tampered in ("p01", "p02"):
            with self.subTest(tampered=tampered):
                for path in (self.run_dir / "fragments").glob("*.json"):
                    path.unlink()
                self.packets()
                self.claim(tampered, TENANT_DOMAIN if tampered == "p01" else "billing")
                classes, report = self.conflicts(self.fragment("p01"), self.fragment("p02"))
                self.assertEqual(["ownership"], classes)
                self.assertEqual(["p01", "p02"], report["conflicts"][0]["packets"])

    def test_merge_tombstones_are_owned_and_deduplicated(self):
        self.packets()
        record = next(ms.record_hash(r) for _, _, rs in ms.Store(self.root).ledgers for r in rs if r["entry"] == CUR)
        stone = {"entry": CUR, "record": record, "reason": "Wrong source"}
        report = self.check(self.frag_b(tombstones=[stone]))
        self.assertTrue(any("owned by p01; submit a proposal" in p for p in report["problems"]), report["problems"])
        with self.unchecked():
            classes = self.conflicts(self.frag_a(tombstones=[stone]), self.frag_b(tombstones=[{**stone, "reason": "Other"}]))[0]
        self.assertEqual(["tombstone-conflict"], classes)

    def test_merge_double_coverage(self):
        self.packets()
        stolen = self.packet("p01")["units"][-1]
        self.tamper("p02", lambda p: p["units"].append(stolen))
        b = self.fragment("p02")
        self.assert_valid(b)
        self.assertEqual(["double-coverage"], self.conflicts(self.frag_a(), b)[0])

    def test_merge_coverage_gap(self):
        self.packets()
        self.tamper("p02", lambda p: p["units"].pop())
        b = self.fragment("p02")
        self.assert_valid(b)
        self.assertEqual(["coverage-gap"], self.conflicts(self.frag_a(), b)[0])

    def test_merge_repair_conflict_and_identical_repairs_deduplicate(self):
        self.archive.abandon(self.run_id)
        self.write("docs/notes.md", "See specs/010-vat for VAT.\n")
        self.prepare()
        self.assertEqual(["docs/notes.md"], self.journal()["references"])
        self.packets()

        def repair(after):
            return {"path": "docs/notes.md", "replacements": [{"before": "specs/010-vat", "after": after, "count": 1}]}
        a, b = self.frag_a(repairs=[repair("the VAT history")]), self.frag_b(repairs=[repair("the archived VAT spec")])
        self.assert_valid(a)
        self.assert_valid(b)
        self.assertEqual(["repair-conflict"], self.conflicts(a, b)[0])
        self.save(self.frag_b(repairs=[repair("the VAT history")]))
        self.merge()
        self.assertEqual([repair("the VAT history")], self.load(self.run_dir / "candidate.json")["repairs"])
        self.archive.materialize(self.journal())

    def test_merge_fixture_collision(self):
        # Unreachable through valid fragments (the destination is derived from the source); merge checks it defensively.
        self.packets()
        dest = "tests/Fixtures/spec-memory/010-vat/spec.md"
        a = self.frag_a(migrations=[{"source": VSPEC, "destination": dest}])
        b = self.frag_b(migrations=[{"source": VTASKS, "destination": dest}])
        with patch.object(orch, "fragment_check", lambda repo, run, run_dir, path, retired: {
                "valid": True, "packet": Path(path).stem, "problems": [], "warnings": [], "summary": {}}):
            self.assertEqual(["fixture-collision"], self.conflicts(a, b)[0])

    def test_merge_taxonomy_conflict(self):
        self.packets()
        a = self.frag_a(taxonomy_changes=[{"op": "add", "id": "tax", "label": "Tax", "definition": "Tax rules."}])
        b = self.frag_b(taxonomy_changes=[{"op": "add", "id": "tax", "label": "Taxes", "definition": "Tax rules."}])
        self.assert_valid(a)
        self.assert_valid(b)
        self.assertEqual(["taxonomy-conflict"], self.conflicts(a, b)[0])
        self.save(self.frag_b(taxonomy_changes=a["taxonomy_changes"]))
        self.merge()
        self.assertEqual(a["taxonomy_changes"], self.load(self.run_dir / "candidate.json")["taxonomy_changes"])

    def test_merge_broken_reference(self):
        # fragment_check only warns about refs to other fragments' additions; merge rechecks the composed result.
        self.packets()
        a = self.frag_a()
        a["updates"][0]["entry"]["relations"] = [ROUND, "PM-fx-nowhere"]
        with patch.object(orch, "fragment_check", lambda repo, run, run_dir, path, retired: {
                "valid": True, "packet": Path(path).stem, "problems": [], "warnings": [], "summary": {}}):
            self.assertEqual(["broken-reference"], self.conflicts(a, self.frag_b())[0])

    def test_constrains_must_target_a_live_entry(self):
        self.packets()
        b = self.frag_b()
        b["additions"][0]["constrains"] = [ROUND]
        self.assert_valid(b)
        # p01 removes the entry p02's new rule constrains: each fragment is valid alone, the composition is not.
        a = self.fragment("p01", removals=[self.removal(ROUND, VSPEC + ":L5")])
        self.assert_valid(a)
        classes, report = self.conflicts(a, b)
        self.assertEqual(["broken-reference"], classes)
        self.assertIn(ROUND, report["conflicts"][0]["detail"])
        b["additions"][0]["constrains"] = ["PM-fx-rates"]
        self.assertIn("links cannot point to the entry itself", "\n".join(self.check(b)["problems"]))

    def test_merge_broken_replacement(self):
        self.packets()
        a = self.fragment("p01", removals=[self.removal(ROUND, VSPEC + ":L5", replacement=TENANT)])
        b = self.fragment("p02", removals=[self.removal(TENANT, FSPEC + ":L3")])
        self.assert_valid(a)
        self.assert_valid(b)
        self.assertEqual(["broken-replacement"], self.conflicts(a, b)[0])

    # ---- review ----

    def review_packets(self):
        run = self.journal()
        raw = (self.run_dir / "candidate.json").read_bytes()
        m = md.validate(self.archive.repo, run, json.loads(raw), self.archive.budgets(), set())
        return orch.review_packets(self.archive.repo, run, self.run_dir, m, raw)

    def approve(self, hashes):
        _, report = self.archive.materialize(self.journal())
        approval = {"reviewer": "packet reviewer", "passed": True, "findings": []}
        write_json(self.run_dir / "review.json", {
            **{k: report[k] for k in ("candidate_sha256", "base_memory_root", "result_memory_root", "outputs_sha256")},
            "verification_override": REASON, "reviewer": "independent test reviewer", "passed": True,
            "summary": "Delta independently reviewed", "findings": [],
            "partitions": {p: {**approval, "packet_sha256": v["packet_sha256"]} for p, v in hashes["partitions"].items()},
            "integration": {**approval, "packet_sha256": hashes["integration"]["packet_sha256"]}})

    def test_partition_approval_survives_an_unrelated_fragment_edit(self):
        self.packets()
        self.save(self.frag_a())
        self.save(self.frag_b())
        self.merge()
        first = self.review_packets()
        self.assertEqual({"missing"}, {v["approval"] for v in [*first["partitions"].values(), first["integration"]]})
        for v in [*first["partitions"].values(), first["integration"]]:
            written = self.load(v["path"])
            self.assertEqual(orch.packet_hash(written), v["packet_sha256"])
        partition = self.load(first["partitions"]["p01-01"]["path"])
        self.assertEqual(("partition", "p01", self.base(CUR)), (partition["kind"], partition["packet"], partition["touched"][CUR]))
        self.approve(first)
        self.assertEqual("passed", self.archive.materialize(self.journal())[1]["review"]["status"])
        again = self.review_packets()
        self.assertEqual({"valid"}, {v["approval"] for v in [*again["partitions"].values(), again["integration"]]})
        # Editing fragment B changes B's partition and the result; A's partition approval carries over.
        self.save(self.frag_b(title="FX rates refresh every hour"))
        self.merge()
        edited = self.review_packets()
        self.assertEqual(first["partitions"]["p01-01"]["packet_sha256"], edited["partitions"]["p01-01"]["packet_sha256"])
        self.assertEqual(("valid", "stale", "stale"), (edited["partitions"]["p01-01"]["approval"],
                                                       edited["partitions"]["p02-01"]["approval"],
                                                       edited["integration"]["approval"]))
        self.assertNotEqual(first["integration"]["packet_sha256"], edited["integration"]["packet_sha256"])
        review = self.archive.materialize(self.journal())[1]["review"]
        self.assertEqual("mismatch", review["status"])
        self.assertTrue(any("p02" in p and "stale" in p for p in review["problems"]), review["problems"])
        self.assertFalse(any("p01" in p for p in review["problems"]), review["problems"])

    def test_packet_edits_or_a_deleted_merge_report_fail_review(self):
        self.packets()
        self.save(self.frag_a())
        self.save(self.frag_b())
        self.merge()
        self.approve(self.review_packets())
        self.assertEqual("passed", self.archive.materialize(self.journal())[1]["review"]["status"])
        self.tamper("p02", lambda p: p.update(note="edited after merge"))
        review = self.archive.materialize(self.journal())[1]["review"]
        self.assertEqual("mismatch", review["status"])
        self.assertTrue(any("Packets changed after merge" in p for p in review["problems"]), review["problems"])
        (self.run_dir / "merge.json").unlink()
        review = self.archive.materialize(self.journal())[1]["review"]
        self.assertEqual("mismatch", review["status"])
        self.assertTrue(any("Run merge before review-packets" in p for p in review["problems"]), review["problems"])

    def test_review_partitions_cut_to_budget_keep_every_unit_and_item_once(self):
        self.packets()
        self.save(self.frag_a())
        self.save(self.frag_b())
        self.merge()
        with patch.object(orch, "REVIEW_TOKENS", 60):
            result = self.review_packets()
        parts = {k: self.load(v["path"]) for k, v in result["partitions"].items() if k.startswith("p01-")}
        self.assertGreater(len(parts), 1)
        self.assertEqual(list(range(1, len(parts) + 1)), [p["part"] for p in parts.values()])
        seen = [f"{path}:{item}" for p in parts.values() for group in [p["units"], *(o["units"] for o in p["omitted"])]
                for path, items in group.items() for item in items]
        self.assertEqual(sorted(u["id"] for u in self.packet("p01")["units"]), sorted(seen))
        frag = self.frag_a()
        for key in ("updates", "provenance"):
            self.assertEqual(frag[key], [i for p in parts.values() for i in p["delta"][key]])
        units = {u["id"]: u for u in self.packet("p01")["units"]}
        for p in parts.values():
            for o in p["omitted"]:
                self.assertEqual("Headings and tasks", o["reason"])
                for path, items in o["units"].items():
                    for item, excerpt in items.items():
                        self.assertEqual(units[f"{path}:{item}"]["text"].split("\n")[0][:orch.EXCERPT], excerpt)
        self.assertTrue(any(CUR in p["touched"] for p in parts.values()))

    def test_oversized_files_split_at_headings(self):
        units = [{"id": f"f.md:L{n}", "path": "f.md", "heading": h} for n, h in enumerate("aaabbbbbcc")]
        self.assertEqual([3, 5, 2], [len(c) for c in orch._split(units, 5)])
        self.assertEqual([2, 1, 2, 2, 1, 2], [len(c) for c in orch._split(units, 2)])
        self.assertEqual([units], orch._split(units, 10))

    def test_review_packets_requires_the_merged_candidate(self):
        self.packets()
        self.save(self.frag_a())
        self.save(self.frag_b())
        self.merge()
        candidate = self.load(self.run_dir / "candidate.json")
        candidate["additions"][0]["title"] = "FX rates refresh each hour"
        write_json(self.run_dir / "candidate.json", candidate)
        with self.assertRaisesRegex(ArchiveError, "Candidate changed after merge"):
            self.review_packets()

    def test_approval_problems(self):
        current = {"partitions": {"p01": "a" * 64, "p02": "b" * 64}, "integration": "c" * 64}
        good = {"reviewer": "r", "passed": True, "findings": []}
        review = {"partitions": {"p01": {**good, "packet_sha256": "a" * 64}, "p02": {**good, "packet_sha256": "b" * 64}},
                  "integration": {**good, "packet_sha256": "c" * 64}}
        self.assertEqual([], orch.approval_problems(self.run_dir, review, current))
        bad = json.loads(json.dumps(review))
        bad["partitions"]["p02"]["packet_sha256"] = "0" * 64
        bad["partitions"]["p03"] = bad["partitions"].pop("p01")
        bad["integration"].update(reviewer="", passed=False, findings=["x"])
        problems = orch.approval_problems(self.run_dir, bad, current)
        for needle in ("p01", "p03", "partition p02 approval is stale"):
            self.assertTrue(any(needle in p for p in problems), (needle, problems))
        self.assertGreaterEqual(len([p for p in problems if "integration" in p]), 1)
        self.assertEqual(0.0, orch.jaccard("", ""))
        self.assertEqual(1.0, orch.jaccard("Rates, refresh", "rates REFRESH"))

    def test_integration_flags_shared_selectors_and_near_duplicate_titles(self):
        self.packets()
        selector = {"kind": "route", "value": "GET /api/v1/rates"}
        a = self.frag_a(additions=[entry("PM-invoice-fx", "Exchange rates refresh every hour for invoices",
                                         "Invoice exchange rates refresh hourly.", selectors=[selector])])
        a["provenance"].append(prov("PM-invoice-fx", VSPEC + ":L5"))
        a["coverage"][0]["units"][VSPEC].remove("L5")
        a["coverage"].append({"units": group(VSPEC + ":L5"), "action": "retained", "memory_ids": ["PM-invoice-fx"]})
        b = self.frag_b(title="Exchange rates refresh every hour")
        b["additions"][0]["selectors"] = [selector]
        self.assert_valid(a)
        self.assert_valid(b)
        self.merge()
        integration = self.load(self.review_packets()["integration"]["path"])
        self.assertEqual("integration", integration["kind"])
        shared = [s for s in integration["shared_selectors"] if s["selector"] == selector]
        self.assertEqual(1, len(shared), integration["shared_selectors"])
        self.assertEqual([{"id": "PM-fx-rates", "packet": "p02"}, {"id": "PM-invoice-fx", "packet": "p01"}],
                         sorted(shared[0]["entries"], key=lambda e: e["id"]))
        dupes = [(d["a"], d["b"], d["packets"]) for d in integration["near_duplicates"]]
        self.assertIn(("PM-fx-rates", "PM-invoice-fx", ["p02", "p01"]), dupes)
        pair = next(d for d in integration["near_duplicates"] if (d["a"], d["b"]) == ("PM-fx-rates", "PM-invoice-fx"))
        self.assertAlmostEqual(5 / 7, pair["jaccard"], delta=0.01)
        self.assertEqual(["Exchange rates refresh every hour", "Exchange rates refresh every hour for invoices"], pair["titles"])
        self.assertEqual([{"id": CUR, "packet": "p01", "reason": None, "before": self.base(CUR), "after": a["updates"][0]["entry"]}],
                         integration["updates"])


if __name__ == "__main__":
    unittest.main()
