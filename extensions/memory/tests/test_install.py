"""Portability and non-destructive initialization in disposable projects."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "scripts"))
from archive import Archive, EXTENSION, FORMAT_1_REFERENCE, POLICY
from git_state import ArchiveError, write_json
from install import COMMANDS, GUARD_MARK, HOOK_FILES, HOOK_ONLY, HOOKS, SESSION, install


class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sanduq-memory-init-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
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

    def test_reinstall_keeps_a_disabled_hook_byte_for_byte(self):
        """D3: Workflow's reconcile disables session and prepare; a Memory re-init must not re-enable them (its
        journal compares the whole entry), while the enabled hooks are still rewritten."""
        install(self.root)
        config = self.root / ".specify/extensions.yml"
        text = config.read_text()
        for command in ("session", "prepare"):
            text = text.replace("command: speckit.memory." + command + "\n    enabled: true",
                                "command: speckit.memory." + command + "\n    enabled: false\n    note: reconciled")
        config.write_text(text)
        disabled = [block for block in re.findall(r"^  - extension: memory\n(?:    .*\n)*", text, re.M) if "enabled: false" in block]
        self.assertEqual(2, len(disabled))
        install(self.root)
        after = config.read_text()
        for block in disabled:
            self.assertEqual(1, after.count(block), block)
        self.assertEqual(2, after.count("command: speckit.memory.impact\n    enabled: true"))
        self.assertEqual(1, after.count("command: speckit.memory.session"))
        self.assertEqual(1, after.count("command: speckit.memory.prepare"))

    def test_keys_after_hooks_are_kept_in_place(self):
        """Spec Kit 8147943's yaml.dump can write `settings:` after `hooks:`; init edits only the hooks mapping."""
        settings = "settings:\n  auto_execute_hooks: true\n"
        self.write(".specify/extensions.yml", "installed:\n- workflow\n- memory\nhooks:\n"
                   "  before_specify:\n  - extension: workflow\n    command: speckit.workflow.scope\n    enabled: true\n"
                   "  after_implement:\n  - extension: memory\n    command: speckit.memory.prepare\n    enabled: true\n"
                   "    optional: false\n    priority: 10\n    prompt: Execute speckit.memory.prepare?\n"
                   "    description: Queue archive work without deleting feature files\n    condition: null\n" + settings)
        install(self.root)
        install(self.root)
        text = (self.root / ".specify/extensions.yml").read_text()
        self.assertTrue(text.endswith("\n" + settings), text)
        self.assertEqual(1, text.count("settings:"))
        hooks = text[text.index("hooks:\n"):text.index(settings)]
        self.assertEqual(len(HOOKS), hooks.count("extension: memory"))
        self.assertEqual(len(HOOKS), text.count("extension: memory"))
        self.assertLess(text.index("installed:"), text.index("hooks:"))

    def test_coexisting_archive_tooling_refuses_without_changes(self):
        self.write(".specify/extensions/legacy-archive/scripts/archive.py", "# Local archive helper\n")
        self.write(".specify/extensions/legacy-archive/archive-policy.json", "{}\n")
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

    def test_wrappers_take_frontmatter_descriptions_and_claude_hides_hook_only_commands(self):
        rendered = self.root / ".claude/skills/speckit-memory-run/SKILL.md"
        self.write(rendered.relative_to(self.root).as_posix(), "---\nname: speckit-memory-run\ndescription: old\n"
                   "metadata:\n  author: sanduq\n  source: memory:commands/run.md\nargument-hint: \"<feature>\"\n---\n\nold\n")
        install(self.root)
        manifest = (SOURCE / "extension.yml").read_text(encoding="utf-8")
        for name in COMMANDS:
            source = (SOURCE / "commands" / (name + ".md")).read_text(encoding="utf-8")
            summary = re.search(r"^description: (.+)$", source, re.M).group(1)
            self.assertIn("    description: '" + summary + "'\n", manifest)
            agents = (self.root / ".agents/skills" / ("speckit-memory-" + name) / "SKILL.md").read_text(encoding="utf-8")
            claude = (self.root / ".claude/skills" / ("speckit-memory-" + name) / "SKILL.md").read_text(encoding="utf-8")
            copilot = (self.root / ".github/agents" / ("speckit.memory." + name + ".agent.md")).read_text(encoding="utf-8")
            for text in (agents, claude, copilot):
                self.assertIn("description: " + summary + "\n", text)
            self.assertNotIn("user-invocable", agents)
            self.assertEqual(name in HOOK_ONLY, "user-invocable: false\n" in claude)
        claude = rendered.read_text(encoding="utf-8")
        self.assertIn("argument-hint: \"<feature>\"\n", claude)
        self.assertIn("metadata:\n  author: sanduq\n  source: memory:commands/run.md\n", claude)
        install(self.root)
        self.assertEqual(claude, rendered.read_text(encoding="utf-8"))

    def test_run_has_no_duplicate_preflight_and_the_catalog_stays_short(self):
        run = (SOURCE / "commands/run.md").read_text(encoding="utf-8")
        self.assertNotIn("preflight --spec", run)  # verify and prepare run the preflight themselves (PM7)
        self.assertNotIn("data.ok", run)  # the preflight result is never false; failures raise
        summaries = [re.search(r"^description: (.+)$", (SOURCE / "commands" / (name + ".md")).read_text(encoding="utf-8"),
                               re.M).group(1) for name in COMMANDS]
        self.assertLessEqual(sum(map(len, summaries)), 750)  # PM8: about 700 characters for all seven
        for summary in summaries:
            self.assertNotIn(" hook)", summary)
            self.assertRegex(summary, r'^[A-Z][a-z]+s .*\bUse when asked\b.*"[^"]{3,}"')

    def test_registry_version_and_the_four_hook_registrations_follow_one_list(self):
        install(self.root)
        registry = json.loads((self.root / ".specify/extensions/.registry").read_text())
        version = re.search(r'^  version: "(.+)"$', (SOURCE / "extension.yml").read_text(), re.M).group(1)
        self.assertEqual(version, registry["extensions"]["memory"]["version"])
        self.assertEqual(4, len(HOOKS))
        text = (self.root / ".specify/extensions.yml").read_text()
        sections = dict(re.findall(r"^  ([a-z_]+):\n((?:(?!  [a-z_]+:).*\n?)*)", text, re.M))
        for event, command, _, _ in HOOKS:
            self.assertEqual(1, sections[event].count("command: speckit.memory." + command + "\n"), event)
        self.assertEqual(len(HOOKS), text.count("extension: memory"))

    def test_session_block_states_the_four_standing_facts(self):
        install(self.root)
        block = re.search(r"<!-- SANDUQ MEMORY SESSION START -->\n(.*)<!-- SANDUQ MEMORY SESSION END -->",
                          (self.root / "CLAUDE.md").read_text(encoding="utf-8"), re.S).group(1)
        self.assertEqual(4, len(block.strip().splitlines()))
        for fact in ("archive.py pending`", "commands/session.md", "pending --gate", "commands/impact.md",
                     "Do not load project memory into ordinary implementation tasks", "Workflow's claim runs this check"):
            self.assertIn(fact, block)
        # I1: a managed project runs neither the session check nor the gate itself; the claim covers both.
        self.assertIn("Workflow's claim covers this gate too, so do not run it separately", block.splitlines()[1])

    def test_session_and_prepare_follow_the_workflow_handoff(self):
        """D3: the handoff dispatches session with --run/--spec and prepare only to choose checks."""
        session = (SOURCE / "commands/session.md").read_text(encoding="utf-8")
        prepare = (SOURCE / "commands/prepare.md").read_text(encoding="utf-8")
        self.assertIn("with `--run <id>`, recover only that\ntransaction", session)
        self.assertIn("With `--spec <dir>`, inspect and verify only that\nfeature", session)
        self.assertIn("workflow.py memory-handoff --transition execute\n--feature specs/<full-feature-name> --check", prepare)
        self.assertIn("Never run `queue` directly there", prepare)

    def test_guard_hooks_register_on_both_hosts_only_when_enabled(self):
        install(self.root)
        for name in HOOK_FILES.values():
            self.assertFalse((self.root / name).exists())
        self.assertIs(False, json.loads((self.root / POLICY).read_text())["guard_hooks"])
        self.write(".claude/settings.json", json.dumps({"model": "x", "hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "owner-hook"}]}]}}))
        policy = json.loads((self.root / POLICY).read_text())
        policy["guard_hooks"] = "yes"
        write_json(self.root / POLICY, policy)
        with self.assertRaisesRegex(ArchiveError, "guard_hooks"):
            install(self.root)
        policy["guard_hooks"] = True
        write_json(self.root / POLICY, policy)
        self.assertEqual(sorted(HOOK_FILES.values()), install(self.root)["guard_hooks"])
        install(self.root)
        for name in HOOK_FILES.values():
            data = json.loads((self.root / name).read_text())
            commands = [h["command"] for g in data["hooks"]["PreToolUse"] for h in g["hooks"]]
            self.assertEqual(1, sum(GUARD_MARK in c for c in commands), name)
            self.assertNotIn("{python}", json.dumps(data))
        claude = json.loads((self.root / ".claude/settings.json").read_text())
        self.assertEqual("x", claude["model"])
        self.assertEqual("owner-hook", claude["hooks"]["PreToolUse"][0]["hooks"][0]["command"])

    def test_every_reference_is_named_by_a_command_or_reference_exists_and_stays_short(self):
        references = {p.name for p in (SOURCE / "references").glob("*.md")}
        named = {Path(FORMAT_1_REFERENCE).name}  # prepare returns it on a format-1 project
        for page in [*(SOURCE / "commands").glob("*.md"), *(SOURCE / "references").glob("*.md")]:
            named |= set(re.findall(r"\.specify/extensions/memory/references/([a-z0-9-]+\.md)", page.read_text(encoding="utf-8")))
        self.assertEqual(references, named)
        for name in references:
            self.assertLess(len((SOURCE / "references" / name).read_text(encoding="utf-8").splitlines()), 500, name)


if __name__ == "__main__":
    unittest.main()
