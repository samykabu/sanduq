"""Held-out acceptance tests for the T07 issue (issue.md). Written from the issue text only.
Run from a PR checkout merged with main: python -m unittest test_heldout_t07"""
import contextlib
import io
import subprocess
import sys
import unittest

from textkit.cli import main
from textkit.core import initials, slugify, squeeze


def cli(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(list(args))
    return rc, buf.getvalue()


class Initials(unittest.TestCase):
    def test_issue_examples(self):
        self.assertEqual(initials("portable network graphics"), "PNG")
        self.assertEqual(initials("  (big) 'apple' pie "), "BAP")
        self.assertEqual(initials("route 66 ... now"), "R6N")

    def test_empty(self):
        self.assertEqual(initials(""), "")
        self.assertEqual(initials(" \t\n "), "")

    def test_any_whitespace_separates(self):
        self.assertEqual(initials("a\tb\nc"), "ABC")

    def test_punctuation_only_word_contributes_nothing(self):
        self.assertEqual(initials("!!! ?? x"), "X")

    def test_already_upper_and_digits(self):
        self.assertEqual(initials("HTTP 2 server"), "H2S")


class Squeeze(unittest.TestCase):
    def test_issue_example(self):
        self.assertEqual(squeeze("  a \t b\n\nc  "), "a b c")

    def test_empty(self):
        self.assertEqual(squeeze(""), "")
        self.assertEqual(squeeze(" \t\n "), "")

    def test_keeps_inner_text(self):
        self.assertEqual(squeeze("Hello,   World!"), "Hello, World!")

    def test_no_change(self):
        self.assertEqual(squeeze("one two"), "one two")


class Cli(unittest.TestCase):
    def test_initials_cli(self):
        self.assertEqual(cli("initials", "portable network graphics"), (0, "PNG\n"))

    def test_squeeze_cli(self):
        self.assertEqual(cli("squeeze", "  a \t b  "), (0, "a b\n"))

    def test_slugify_unchanged(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
        self.assertEqual(cli("slugify", "A B"), (0, "a-b\n"))

    def test_module_entry_point(self):
        out = subprocess.run([sys.executable, "-m", "textkit", "initials", "route 66 ... now"],
                             capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "R6N"))


if __name__ == "__main__":
    unittest.main()
