"""Git and filesystem boundaries for the local archive transaction."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from contextlib import contextmanager


class ArchiveError(Exception):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".archive-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value: object) -> None:
    atomic_write(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode())


class Repository:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._exists: dict[tuple[str, str], bool] = {}
        top = self.git("rev-parse", "--show-toplevel").decode().strip()
        if Path(top).resolve() != self.root:
            raise ArchiveError("Run from the repository root or pass --root explicitly.")
        common = Path(self.git("rev-parse", "--git-common-dir").decode().strip())
        self.state = (common if common.is_absolute() else self.root / common).resolve() / "sanduq-memory"

    def git(self, *args: str, env: dict | None = None, ok: tuple[int, ...] = (0,), stdin: bytes | None = None) -> bytes:
        run = subprocess.run(["git", *args], cwd=self.root, env=env, capture_output=True, input=stdin)
        if run.returncode not in ok:
            raise ArchiveError(f"git {args[0]} failed: {run.stderr.decode(errors='replace').strip()}")
        return run.stdout

    def git_paths(self, *args: str, paths: list[str], env: dict | None = None) -> bytes:
        # Large archives exceed Windows' 32,767-character command line (WinError 206), so pathspecs go on stdin.
        return self.git(*args, "--pathspec-from-file=-", "--pathspec-file-nul", env=env,
                        stdin=b"\0".join(p.encode("utf-8") for p in self.pathspec(paths)))

    def path(self, name: str) -> Path:
        part = PurePosixPath(name)
        if not name or "\\" in name or part.is_absolute() or any(p.casefold() in ("..", ".git") for p in part.parts):
            raise ArchiveError(f"Unsafe repository path: {name!r}")
        if part.as_posix() != name or ":" in name or "\x00" in name:
            raise ArchiveError(f"Noncanonical repository path: {name!r}")
        target = self.root.joinpath(*part.parts)
        for ancestor in (target, *target.parents):
            if ancestor == self.root:
                break
            if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
                raise ArchiveError(f"Archive paths cannot pass through links: {name}")
        if not target.resolve().is_relative_to(self.root):
            raise ArchiveError(f"Path escaped repository: {name}")
        return target

    @staticmethod
    def pathspec(paths: list[str]) -> list[str]:
        return [f":(literal){p}" for p in paths]

    def names(self, *args: str, **options) -> list[str]:
        return [p.decode("utf-8") for p in self.git(*args, **options).split(b"\0") if p]

    def tracked(self) -> list[str]:
        return self.names("ls-files", "-z")

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").decode().strip()

    @staticmethod
    def process_state(pid: int) -> str:
        if not isinstance(pid, int) or pid <= 0:
            return "unknown"
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.GetExitCodeProcess.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return "stale" if ctypes.get_last_error() == 87 else "unknown"
            try:
                code = wintypes.DWORD()
                return "busy" if kernel.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259 else "stale"
            finally:
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle(handle)
        try:
            os.kill(pid, 0)
            return "busy"
        except ProcessLookupError:
            return "stale"
        except PermissionError:
            return "unknown"

    def blob(self, commit: str, path: str) -> bytes:
        self.path(path)
        if not __import__("re").fullmatch(r"[0-9a-f]{40,64}", commit):
            raise ArchiveError("Provenance must use a full immutable commit SHA.")
        return self.git("show", f"{commit}:{path}")

    def exists_at(self, commit: str, paths: list[str]) -> dict[str, bool]:
        """Which paths are files at commit: one batched `cat-file --batch-check` over stdin, cached per (commit, path)."""
        cache = self._exists
        # A newline would desynchronize the batch protocol; such a path cannot be a valid repository file anyway.
        for path in paths:
            if "\n" in path:
                cache[(commit, path)] = False
        missing = sorted({p for p in paths if (commit, p) not in cache})
        if missing:
            lines = self.git("cat-file", "--batch-check=%(objecttype)",
                             stdin="".join(f"{commit}:{p}\n" for p in missing).encode("utf-8")).decode("utf-8").splitlines()
            if len(lines) != len(missing):
                raise ArchiveError("git cat-file returned an unexpected batch result.")
            cache.update({(commit, p): line == "blob" for p, line in zip(missing, lines)})
        return {p: cache[(commit, p)] for p in paths}

    def file_hash(self, path: str) -> str | None:
        target = self.path(path)
        if not target.exists():
            return None
        if not target.is_file():
            raise ArchiveError(f"Expected a regular file: {path}")
        return digest(target.read_bytes())

    def index(self) -> dict[str, str]:
        result = {}
        for record in self.git("ls-files", "--stage", "-z").split(b"\0"):
            if record:
                details, path = record.split(b"\t", 1)
                if details.split()[-1] != b"0":
                    raise ArchiveError("Resolve the Git index conflicts before archiving.")
                result[path.decode()] = details.decode()
        return result

    def dirty(self) -> set[str]:
        return set(self.names("diff", "--name-only", "-z", "HEAD")) | set(
            self.names("ls-files", "--others", "--exclude-standard", "-z"))

    @staticmethod
    def within(path: str, scopes: list[str]) -> bool:
        return any(path == s or path.startswith(s + "/") for s in scopes)

    def scoped_index(self, scopes: list[str]) -> dict[str, str]:
        return {p: v for p, v in self.index().items() if not self.within(p, scopes)}

    def check_scope(self, scopes: list[str], *, clean: bool = False) -> None:
        for path in scopes:
            self.path(path)
        self.index()
        staged = set(self.names("diff", "--cached", "--name-only", "-z"))
        unstaged = set(self.names("diff", "--name-only", "-z"))
        mixed = {p for p in staged & unstaged if self.within(p, scopes)}
        if mixed:
            raise ArchiveError(f"Partially staged archive paths need separate resolution: {sorted(mixed)}")
        if clean:
            changed = sorted(p for p in self.dirty() if self.within(p, scopes))
            if changed:
                raise ArchiveError(f"Automatic archive requires committed inputs: {changed}")

    def expected_tree(self, scopes: list[str]) -> str:
        self.state.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="index-", dir=self.state)
        os.close(fd)
        os.unlink(name)
        env = dict(os.environ, GIT_INDEX_FILE=name)
        try:
            self.git("read-tree", "HEAD", env=env)
            self.git_paths("add", "-A", paths=scopes, env=env)
            return self.git("write-tree", env=env).decode().strip()
        finally:
            for index_path in (name, name + ".lock"):
                if os.path.exists(index_path):
                    os.unlink(index_path)

    def commit(self, scopes: list[str], message: str, expected: str) -> str:
        before_index = self.scoped_index(scopes)
        before_head = self.head()
        new = [p for p in self.names("ls-files", "--others", "--exclude-standard", "-z")
               if self.within(p, scopes)]
        if new:
            self.git_paths("add", "--intent-to-add", paths=new)
        self.git_paths("commit", "--only", "--allow-empty", "-m", message, paths=scopes)
        head = self.head()
        tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        parent = self.git("rev-parse", "HEAD^").decode().strip()
        if tree != expected or parent != before_head or before_index != self.scoped_index(scopes):
            raise ArchiveError("Commit or hook changed unexpected paths/index entries. Inspect Git; no reset was performed.")
        return head

    @contextmanager
    def lock(self):
        self.state.mkdir(parents=True, exist_ok=True)
        lock = self.state / "writer.lock"
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            raise ArchiveError(f"Archive writer lock exists: {lock}. Check its PID before removing a stale lock.") from None
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"pid": os.getpid(), "root": str(self.root)}, stream)
            yield
        finally:
            lock.unlink(missing_ok=True)
