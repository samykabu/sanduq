"""Portability and non-destructive initialization in disposable projects."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "scripts"))
from archive import Archive, EXTENSION, POLICY
from git_state import ArchiveError, write_json
from install import COMMANDS, install


class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sanduq-memory-init-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        shutil.copytree(SOURCE, self.root / EXTENSION, ignore=shutil.ignore_patterns("tests", "__pycache__"))
        shutil.copytree(SOURCE / "tests/fixtures/entry-points/.specify/scripts", self.root / ".specify/scripts")
        self.write("AGENTS.md", "Owner instructions\n")
        self.write(".specify/extensions.yml", "installed:\n- workflow\nsettings:\n  auto_execute_hooks: true\nhooks:\n  before_specify:\n  - extension: workflow\n    command: speckit.workflow.scope\n")
        write_json(self.root / ".specify/extensions/.registry", {"extensions": {"workflow": {"source": "catalog"}, "memory": {"source": "catalog"}}})

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*")
                if p.is_file() and ".git" not in p.relative_to(self.root).parts and "__pycache__" not in p.parts}

    def test_preserves_other_extensions_and_orders_hooks(self):
        result = install(self.root)
        self.assertFalse(result["automatic_enabled"])
        self.assertEqual(7, len(result["commands"]))
        policy = json.loads((self.root / POLICY).read_text())
        self.assertEqual("main", policy["target_branch"])
        self.assertEqual({}, policy["checks"])
        with self.assertRaisesRegex(ArchiveError, "Configure verification"):
            Archive(self.root).enable(Archive(self.root).policy_hash())
        for name in COMMANDS:
            for host in (".agents", ".claude"):
                self.assertTrue((self.root / host / "skills" / ("speckit-memory-" + name) / "SKILL.md").is_file())
            self.assertTrue((self.root / ".github/agents" / ("speckit.memory." + name + ".agent.md")).is_file())
        text = (self.root / ".specify/extensions.yml").read_text()
        self.assertLess(text.index("speckit.memory.session"), text.index("speckit.memory.impact"))
        self.assertLess(text.index("speckit.memory.impact"), text.index("speckit.workflow.scope"))
        registry = json.loads((self.root / ".specify/extensions/.registry").read_text())
        self.assertEqual("catalog", registry["extensions"]["memory"]["source"])
        self.assertEqual({"source": "catalog"}, registry["extensions"]["workflow"])
        self.assertTrue((self.root / "AGENTS.md").read_text().startswith("Owner instructions"))

    def test_reinitialize_preserves_policy_customizations_and_guards(self):
        install(self.root, "develop")
        policy = json.loads((self.root / POLICY).read_text())
        policy["product_prefixes"] = ["custom/"]
        policy["checks"] = {"unit": {"argv": ["python", "test.py"], "covers": ["custom/*"]}}
        write_json(self.root / POLICY, policy)
        script = self.root / ".specify/scripts/bash/create-new-feature.sh"
        script.write_bytes(script.read_bytes() + b"\n# Owner customization\n")
        expected = script.read_bytes()
        install(self.root)
        self.assertEqual(expected, script.read_bytes())
        self.assertEqual(policy, json.loads((self.root / POLICY).read_text()))
        text = (self.root / ".specify/extensions.yml").read_text()
        self.assertEqual(1, text.count("command: speckit.memory.session"))
        self.assertEqual(1, (self.root / "AGENTS.md").read_text().count("SANDUQ MEMORY SESSION START"))

    def test_coexisting_engage_refuses_without_changes(self):
        (self.root / ".specify/extensions/engage-archive").mkdir()
        before = self.snapshot()
        with self.assertRaisesRegex(ArchiveError, "owner confirms cutover"):
            install(self.root)
        self.assertEqual(before, self.snapshot())

    def test_unknown_context_and_invalid_configuration_preserve_files(self):
        path = ".specify/scripts/powershell/create-new-feature.ps1"
        original = (self.root / path).read_bytes()
        self.write(path, "Unsupported custom feature creator\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ArchiveError, "guard context"):
            install(self.root)
        self.assertEqual(before, self.snapshot())
        (self.root / path).write_bytes(original)
        self.write(".specify/extensions.yml", "installed: [workflow]\nhooks: {}\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ArchiveError, "supported installed"):
            install(self.root)
        self.assertEqual(before, self.snapshot())

    def test_single_shell_is_supported_and_disappearance_is_detected(self):
        target = (self.root / ".specify/scripts/bash").resolve()
        self.assertTrue(target.is_relative_to(self.root.resolve()))
        shutil.rmtree(target)
        result = install(self.root)
        self.assertEqual([".specify/scripts/powershell/create-new-feature.ps1"], result["guards"])
        write_json(self.root / "specs/.archive-index.json", {"schema_version": 1, "high_water": 9, "archived": {}})
        self.assertEqual([], Archive(self.root).pending()["guard_blockers"])
        (self.root / result["guards"][0]).unlink()
        self.assertEqual(result["guards"], Archive(self.root).pending()["guard_blockers"])

    def test_target_branch_change_requires_explicit_policy_edit(self):
        install(self.root)
        before = self.snapshot()
        with self.assertRaisesRegex(ArchiveError, "Existing policy is preserved"):
            install(self.root, "develop")
        self.assertEqual(before, self.snapshot())

    def test_custom_product_inputs_control_verification_scope(self):
        install(self.root)
        policy = json.loads((self.root / POLICY).read_text())
        policy.update(product_prefixes=["custom/"], product_files=["root.py"])
        write_json(self.root / POLICY, policy)
        for path in ("custom/app.py", "root.py", "src/unrelated.py"):
            self.write(path, "PRODUCT = 1\n")
        subprocess.run(["git", "add", "custom/app.py", "root.py", "src/unrelated.py"], cwd=self.root, check=True, capture_output=True)
        self.assertEqual({"custom/app.py", "root.py"}, set(Archive(self.root).product_state()))

    def test_invalid_existing_policy_preserves_files(self):
        install(self.root)
        policy = json.loads((self.root / POLICY).read_text())
        policy["memory_path"] = "other-memory.md"
        write_json(self.root / POLICY, policy)
        before = self.snapshot()
        with self.assertRaisesRegex(ArchiveError, "locations are fixed"):
            install(self.root)
        self.assertEqual(before, self.snapshot())

    def test_external_wrapper_link_is_never_followed(self):
        target = self.root / "owner.md"
        target.write_text("Owner file\n")
        wrapper = self.root / ".agents/skills/speckit-memory-init/SKILL.md"
        wrapper.parent.mkdir(parents=True)
        try:
            wrapper.symlink_to(target)
        except OSError:
            self.skipTest("Creating symlinks is not supported by this account")
        before = self.snapshot()
        with self.assertRaisesRegex(ArchiveError, "outside this extension"):
            install(self.root)
        self.assertTrue(wrapper.is_symlink())
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
