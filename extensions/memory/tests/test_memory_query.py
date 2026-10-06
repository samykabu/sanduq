from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import memory_query as mq
import memory_store as ms
from git_state import ArchiveError

C = "1" * 40


def entry(eid, domain, kind, title, text, evidence=(), sources=1, relations=None, selectors=()):
    return {"id": eid, "domain": domain, "kind": kind, "title": title, "text": text,
            "sources": [{"commit": C, "path": "specs/1/spec.md", "unit": f"specs/1/spec.md:L{n}"} for n in range(sources)],
            "evidence": [{"commit": C, "path": p} for p in evidence], "relations": relations, "selectors": list(selectors)}


ENTRIES = [
    entry("PM-upload-route", "Uploads", "behavior", "Admin upload route",
          "`POST /api/v1/admin/uploads` stores files and returns `invalid_file_type` for bad types.",
          evidence=["src/Api/Features/Uploads/UploadEndpoints.cs"]),
    entry("PM-upload-size-limit", "Uploads", "limit", "Upload size limit is not configurable",
          "The 10 MB cap is a constant. See PM-upload-route.", evidence=[]),
    entry("PM-member-detail", "Members", "behavior", "Member detail route",
          "`GET /api/v1/admin/members/{member_id}` returns the member. Errors use `forbidden_client_scope`.",
          evidence=["src/Api/Features/Members/MemberEndpoints.cs"]),
    entry("PM-member-otp", "Members", "behavior", "Member OTP verification",
          "Verify-otp sends the transaction id and code to IdentityMs.",
          evidence=["src/Api/Features/Members/Services/MemberOtpService.cs"]),
    entry("PM-scope-rule", "Tenancy", "decision", "Tenant scope comes from X-Client-Id",
          "Every tenant route resolves scope from the X-Client-Id header.", evidence=[],
          selectors=[{"kind": "route", "value": "GET /api/v1/admin/members/{id}"}]),
]


class MemoryQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="memory-query-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        outputs = ms.migration_outputs([{k: v for k, v in e.items() if k not in ("relations", "selectors")}
                                        for e in ENTRIES], "0" * 64)
        self.write_all(outputs)
        for e in ENTRIES:  # add the declared selectors the migration does not invent
            if e["selectors"]:
                path = self.root / ms.ENTRIES / f"{e['id']}.md"
                parsed = ms.parse_entry(path.read_bytes(), path.name)
                parsed["selectors"] = e["selectors"]
                path.write_bytes(ms.emit_entry(parsed))
        self.write_all(ms.generated(ms.Store(self.root)))
        (self.root / "src/Api/Features/Members").mkdir(parents=True)
        (self.root / "src/Api/Features/Members/MemberEndpoints.cs").write_text("// present\n")
        self.store = ms.Store(self.root)

    def write_all(self, outputs):
        for path, data in outputs.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def ids(self, result):
        return [e["id"] for e in result["entries"]]

    def test_route_match_normalizes_placeholders_and_ranks_declared_first(self):
        result = mq.query(self.store, self.root, routes=["GET /api/v1/admin/members/{mid}"])
        self.assertEqual(["PM-scope-rule", "PM-member-detail"], self.ids(result)[:2])
        reasons = {e["id"]: e["reasons"][0] for e in result["entries"]}
        self.assertEqual("declared", reasons["PM-scope-rule"]["confidence"])
        self.assertEqual("inferred", reasons["PM-member-detail"]["confidence"])
        self.assertEqual({"present": 1, "missing": 0}, result["entries"][1]["evidence"])

    def test_relations_pull_in_constraints_and_unreturned_relations_are_reported(self):
        result = mq.query(self.store, self.root, routes=["POST /api/v1/admin/uploads"])
        self.assertEqual(["PM-upload-route", "PM-upload-size-limit"], self.ids(result))
        self.assertEqual("relation", result["entries"][1]["reasons"][0]["by"])
        only = mq.query(self.store, self.root, ids=["PM-upload-size-limit"], budget=1)
        self.assertEqual(["PM-upload-size-limit"], self.ids(only))
        self.assertEqual(["PM-upload-route"], only["unreturned_relations"])

    def link(self, eid, **links):
        path = self.root / ms.ENTRIES / f"{eid}.md"
        path.write_bytes(ms.emit_entry({**ms.parse_entry(path.read_bytes(), path.name), **links}))
        self.store = ms.Store(self.root)

    def test_constraining_entries_follow_their_hit_and_superseded_entries_drop(self):
        self.link("PM-scope-rule", constrains=["PM-upload-route"])
        # Incoming typed links count as related entries when they are not on the page.
        small = mq.query(self.store, self.root, ids=["PM-upload-route"], budget=1)
        self.assertEqual(["PM-upload-route"], self.ids(small))
        self.assertIn("PM-scope-rule", small["unreturned_relations"])
        # A constraining rule in another domain is returned even under a domain filter.
        filtered = mq.query(self.store, self.root, ids=["PM-upload-route"], domains=["uploads"])
        self.assertIn("PM-scope-rule", self.ids(filtered))
        self.link("PM-upload-size-limit", relations=[], supersedes=["PM-upload-route"])
        result = mq.query(self.store, self.root, routes=["POST /api/v1/admin/uploads"])
        by = {e["id"]: e for e in result["entries"]}
        self.assertIn({"by": "constrains", "value": "PM-upload-route", "confidence": "declared"},
                      by["PM-scope-rule"]["reasons"])
        self.assertNotIn("relation", [r["by"] for r in by["PM-scope-rule"]["reasons"]])
        self.assertIn({"by": "superseded-by", "value": "PM-upload-size-limit", "confidence": "declared"},
                      by["PM-upload-route"]["reasons"])
        self.assertIn({"by": "supersedes", "value": "PM-upload-route", "confidence": "declared"},
                      by["PM-upload-size-limit"]["reasons"])
        # The replacement leads, the superseded hit follows, and its constraining rule sits just below it.
        self.assertEqual(["PM-upload-size-limit", "PM-upload-route", "PM-scope-rule"], self.ids(result)[:3])
        self.assertIn("Constrained by: PM-scope-rule.", by["PM-upload-route"]["markdown"])
        self.assertIn("Superseded by: PM-upload-size-limit.", by["PM-upload-route"]["markdown"])
        self.assertIn("Constrains: PM-upload-route.", mq.render_entry(self.store, "PM-scope-rule"))

    def test_path_and_error_code_hints_are_inferred_and_never_exclude(self):
        result = mq.query(self.store, self.root, paths=["src/Api/Features/Members/Services/MemberOtpService.cs"])
        self.assertEqual("PM-member-otp", self.ids(result)[0])
        self.assertIn("PM-member-detail", self.ids(result))  # same feature slice, weaker match
        self.assertTrue(all(r["confidence"] == "inferred" for e in result["entries"] for r in e["reasons"]
                            if r["by"].startswith("path")))
        coded = mq.query(self.store, self.root, error_codes=["invalid_file_type"])
        self.assertEqual("PM-upload-route", self.ids(coded)[0])

    def test_budget_packs_whole_entries_and_cursor_resumes_exactly(self):
        full = mq.query(self.store, self.root, text="route member upload scope", budget=100000)
        seen, cursor = [], None
        while True:
            page = mq.query(self.store, self.root, text="route member upload scope", budget=60, cursor=cursor)
            self.assertGreaterEqual(page["returned"], 1)
            for item in page["entries"]:
                self.assertIn(self.store.entries[item["id"]]["text"], item["markdown"])
            seen += self.ids(page)
            cursor = page["cursor"]
            if not cursor:
                break
        self.assertEqual(self.ids(full), seen)

    def test_stale_cursor_and_unknown_inputs_are_rejected(self):
        page = mq.query(self.store, self.root, text="route", budget=60)
        self.assertTrue(page["cursor"])
        path = self.root / ms.ENTRIES / "PM-member-otp.md"
        path.write_bytes(path.read_bytes().replace(b"IdentityMs.", b"IdentityMs only."))
        with self.assertRaisesRegex(ArchiveError, "Memory changed"):
            mq.query(ms.Store(self.root), self.root, text="route", budget=60, cursor=page["cursor"])
        with self.assertRaisesRegex(ArchiveError, "Unknown domain"):
            mq.query(self.store, self.root, domains=["nowhere"])
        with self.assertRaisesRegex(ArchiveError, "Unknown memory id"):
            mq.query(self.store, self.root, ids=["PM-nope"])

    def test_empty_result_says_it_is_not_proof(self):
        result = mq.query(self.store, self.root, routes=["DELETE /api/v1/nothing"])
        self.assertEqual(0, result["matched"])
        self.assertIn("not prove", result["note"])
        self.assertIn("not prove", mq.to_markdown(result))

    def test_text_reranks_equal_structured_matches_without_widening(self):
        result = mq.query(self.store, self.root, paths=["src/Api/Features/Members"], text="otp identityms")
        self.assertEqual(["PM-member-otp", "PM-member-detail"], self.ids(result)[:2])
        self.assertNotIn("PM-upload-route", self.ids(result))

    def test_domain_filter_and_text_fallback(self):
        result = mq.query(self.store, self.root, domains=["members"])
        self.assertEqual({"PM-member-detail", "PM-member-otp"}, set(self.ids(result)))
        fallback = mq.query(self.store, self.root, routes=["PUT /api/v1/none"], text="otp identityms")
        self.assertEqual("PM-member-otp", self.ids(fallback)[0])

    def test_cli_query_show_provenance_catalog(self):
        subprocess.run(["git", "init", "-q", "-b", "develop"], cwd=self.root, check=True)
        (self.root / ".specify/extensions/memory").mkdir(parents=True)
        (self.root / ".specify/memory-policy.json").write_bytes(json.dumps({"schema_version": 1, "target_branch": "develop"}).encode())
        cli = [sys.executable, str(SCRIPTS / "archive.py"), "--root", str(self.root), "memory"]
        md = subprocess.run(cli + ["query", "--route", "POST /api/v1/admin/uploads"], capture_output=True, text=True,
                            encoding="utf-8")
        self.assertEqual(0, md.returncode, md.stdout)
        self.assertIn("## PM-upload-route", md.stdout)
        as_json = json.loads(subprocess.run(cli + ["query", "--text", "otp", "--format", "json"], capture_output=True,
                                            text=True, encoding="utf-8").stdout)
        self.assertEqual("PM-member-otp", as_json["data"]["entries"][0]["id"])
        shown = subprocess.run(cli + ["show", "--id", "PM-upload-size-limit"], capture_output=True, text=True,
                               encoding="utf-8").stdout
        self.assertIn("Related: PM-upload-route", shown)
        prov = json.loads(subprocess.run(cli + ["provenance", "--id", "PM-member-otp"], capture_output=True,
                                         text=True, encoding="utf-8").stdout)
        self.assertEqual(["specs/1/spec.md:L0"], [s["unit"] for s in prov["data"]["folded"]["sources"]])
        catalog = subprocess.run(cli + ["catalog", "--domain", "members"], capture_output=True, text=True,
                                 encoding="utf-8").stdout
        self.assertIn("PM-member-otp", catalog)


if __name__ == "__main__":
    unittest.main()
