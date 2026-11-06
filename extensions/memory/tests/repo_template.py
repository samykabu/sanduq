"""PM20: build a test repository once per class, then restore a fresh copy before each test.

The archive state stores absolute roots (approval `root`, queue entries, journals), so every copy lands
at the same fixed path, never a new one. Each test still starts from identical, isolated files.
"""
import os
import shutil
import stat
import tempfile
from pathlib import Path


def _writable(func, path, _):
    os.chmod(path, stat.S_IWRITE)  # Git writes read-only object files; Windows refuses to delete those
    func(path)


class TemplateRepo:
    """Mixin for a TestCase: `build(self)` runs once against `self.root`; `restored(self)` runs after each copy."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base = tempfile.TemporaryDirectory(prefix="memory-template-")
        cls.addClassCleanup(base.cleanup)
        cls.root = Path(base.name).resolve() / "repo"
        cls.template = cls.root.with_name("template")
        cls.root.mkdir()
        builder = cls.__new__(cls)
        builder.build()
        cls.built = {k: v for k, v in vars(builder).items() if not k.startswith("_")}
        shutil.copytree(cls.root, cls.template, symlinks=True)

    def setUp(self):
        super().setUp()
        shutil.rmtree(self.root, onerror=_writable)
        shutil.copytree(self.template, self.root, symlinks=True)
        self.restored()

    def build(self):
        raise NotImplementedError

    def restored(self):
        pass
