from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from git_state import ArchiveError, Repository

TRACKED = "artifacts/issue842/aspire/j842-dfd518af8b8a/journey-summary.json"
LOG = "artifacts/issue842/checks-final/01-git-state.log"
SPACED = "artifacts/issue842/odd dir/it's [x]&(y)#.log"


class TrackedIgnoredScopeTests(unittest.TestCase):
    """Consumers keep files under an ignored parent tracked (added with -f); the archive scopes name them."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="memory-git-state-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-b", "develop")
        for key, value in {"user.name": "Archive Test", "user.email": "archive@example.invalid", "core.autocrlf": "false",
                           "core.hooksPath": ".git/hooks", "commit.gpgsign": "false"}.items():
            self.git("config", key, value)
        self.write(".gitignore", "artifacts/\n")
        for name in (TRACKED, LOG, SPACED):
            self.write(name, "one\n")
        self.write("other.txt", "other\n")
        self.git("add", ".gitignore", "other.txt")
        self.git("add", "-f", "artifacts")
        self.git("commit", "-m", "Initial")
        self.repo = Repository(self.root)

    def git(self, *args):
        run = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        if run.returncode:
            raise AssertionError(run.stderr.decode(errors="replace"))
        return run.stdout.decode().strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode())

    def tree_with(self, *changes):
        """The tree the working files should produce, built independently in a throwaway index."""
        index = Path(self.temp.name) / "oracle-index"
        env = dict(__import__("os").environ, GIT_INDEX_FILE=str(index))
        subprocess.run(["git", "read-tree", "HEAD"], cwd=self.root, env=env, check=True)
        for name in changes:
            if (self.root / name).exists():
                subprocess.run(["git", "update-index", "--add", "--", name], cwd=self.root, env=env, check=True)
            else:
                subprocess.run(["git", "update-index", "--force-remove", "--", name], cwd=self.root, env=env, check=True)
        tree = subprocess.run(["git", "write-tree"], cwd=self.root, env=env, check=True, capture_output=True)
        index.unlink()
        return tree.stdout.decode().strip()

    def test_plain_add_refuses_the_reproduction(self):
        # Proves the fixture reproduces the blocker: Git itself exits 1 for these tracked paths.
        self.write(TRACKED, "two\n")
        with self.assertRaisesRegex(ArchiveError, "ignored"):
            self.repo.git_paths("add", "-A", "-n", paths=[TRACKED])

    def test_ignored_keeps_pattern_semantics_for_mixed_nul_delimited_paths(self):
        untracked = "artifacts/odd dir/تقرير [1].json"
        self.write(untracked, "untracked ignored bytes\n")
        self.assertEqual([SPACED, untracked, TRACKED], self.repo.ignored([SPACED, "other.txt", untracked, TRACKED]))
        self.assertEqual([], self.repo.ignored([]))
        for unsafe in ("../outside", "other.txt\0artifacts/unsafe"):
            with self.assertRaises(ArchiveError):
                self.repo.ignored([TRACKED, unsafe])

    def test_expected_tree_stages_edits_deletions_and_new_files_under_ignored_parent(self):
        self.write(TRACKED, "two\n")
        (self.root / LOG).unlink()
        self.write(SPACED, "changed\n")
        self.write("new/dir/fresh file.md", "fresh\n")
        scopes = [TRACKED, LOG, SPACED, "new"]
        tree = self.repo.expected_tree(scopes)
        self.assertEqual(self.tree_with(TRACKED, LOG, SPACED, "new/dir/fresh file.md"), tree)
        self.assertNotIn(LOG, self.git("ls-tree", "-r", "--name-only", tree).splitlines())

    def test_directory_scope_over_ignored_parent_keeps_untracked_ignored_files_out(self):
        self.write(TRACKED, "two\n")
        self.write("artifacts/issue842/untracked.bin", "secret\n")
        tree = self.repo.expected_tree(["artifacts/issue842"])
        self.assertEqual(self.tree_with(TRACKED), tree)
        self.assertNotIn("artifacts/issue842/untracked.bin", self.git("ls-tree", "-r", "--name-only", tree).splitlines())

    def test_untracked_ignored_file_named_by_a_scope_is_still_refused(self):
        self.write("artifacts/issue842/untracked.bin", "secret\n")
        with self.assertRaisesRegex(ArchiveError, "ignored untracked"):
            self.repo.expected_tree(["artifacts/issue842/untracked.bin"])

    def test_unrelated_index_and_working_bytes_are_untouched(self):
        self.write(TRACKED, "two\n")
        self.write("other.txt", "staged by the user\n")
        self.git("add", "other.txt")
        self.write("other.txt", "edited again\n")
        before = (self.git("ls-files", "--stage"), (self.root / "other.txt").read_bytes())
        tree = self.repo.expected_tree([TRACKED])
        self.assertEqual(before, (self.git("ls-files", "--stage"), (self.root / "other.txt").read_bytes()))
        self.assertEqual(self.tree_with(TRACKED), tree)
        self.assertEqual(self.git("rev-parse", "HEAD:other.txt"), self.git("rev-parse", f"{tree}:other.txt"))

    def test_large_scope_list_goes_through_stdin(self):
        many = [f"bulk/{'n' * 120}-{i}.md" for i in range(600)]
        for name in many:
            self.write(name, "x\n")
        self.write(TRACKED, "two\n")
        tree = self.repo.expected_tree([TRACKED, "bulk"])
        listed = self.git("ls-tree", "-r", "--name-only", tree).splitlines()
        self.assertEqual(600, sum(name.startswith("bulk/") for name in listed))
        scopes = [TRACKED, *many]
        self.assertEqual(tree, self.repo.expected_tree(scopes))
        self.assertGreater(sum(len(s) + 1 for s in scopes), 32767)

    def test_commit_matches_expected_tree_for_tracked_ignored_scopes(self):
        self.write(TRACKED, "two\n")
        (self.root / LOG).unlink()
        self.write(SPACED, "changed\n")
        self.write("new/fresh.md", "fresh\n")
        self.write("other.txt", "unrelated dirty\n")
        self.write("artifacts/issue842/untracked.bin", "secret\n")
        scopes = [TRACKED, LOG, SPACED, "new"]
        expected = self.repo.expected_tree(scopes)
        head = self.repo.commit(scopes, "Archive", expected)
        self.assertEqual(expected, self.git("rev-parse", f"{head}^{{tree}}"))
        self.assertEqual("other\n", self.git("show", f"{head}:other.txt").replace("\r", "") + "\n")
        self.assertIn("other.txt", self.git("diff", "--name-only").splitlines())
        self.assertEqual("", self.git("ls-files", "artifacts/issue842/untracked.bin"))


class LocalRuntimeTests(unittest.TestCase):
    """B6: only files ignored by an exclude line an owner declared as its runtime are disposable."""
    setUp = TrackedIgnoredScopeTests.setUp
    git = TrackedIgnoredScopeTests.git
    write = TrackedIgnoredScopeTests.write

    def test_only_declared_exclude_lines_make_a_file_runtime(self):
        report, backup, notes, logged = ("specs/2-x/workflow/progress/index.html", "specs/2-x/workflow/backups/a.json",
                                         "specs/2-x/notes.local", "specs/2-x/run.log")
        self.write(".git/info/exclude", "/specs/*/workflow/progress/\n/specs/*/workflow/backups/\n*.local\n")
        self.write(".gitignore", "artifacts/\n*.log\n")
        for name in (report, backup, notes, logged):
            self.write(name, "x")
        ignored = self.repo.ignored([report, backup, notes, logged])
        self.assertEqual(4, len(ignored))
        self.assertEqual(set(), self.repo.local_runtime(ignored))  # no declaration: nothing is disposable
        self.write(".git/info/sanduq-runtime.json",
                   '{"workflow": ["/specs/*/workflow/progress/", "/specs/*/workflow/backups/", "*.log"]}')
        # `*.log` is declared, but the deciding rule is the tracked .gitignore's, so run.log stays protected.
        self.assertEqual({report, backup}, self.repo.local_runtime(ignored))
        self.write(".git/info/sanduq-runtime.json", "not json")
        self.assertEqual(set(), self.repo.local_runtime(ignored))


if __name__ == "__main__":
    unittest.main()
