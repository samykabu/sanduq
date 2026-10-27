"""Git and filesystem boundaries for the local archive transaction."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import subprocess
import tempfile

try:
    import sanduq_fs
except ModuleNotFoundError:  # the source tree; package.py copies it into scripts/
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "shared"))
    import sanduq_fs


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


write_json = sanduq_fs.write_json


class Repository:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._exists: dict[tuple[str, str], bool] = {}
        self._commits: set[str] = set()
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
        return self.blobs(commit, [path])[path]

    def immutable_commit(self, commit: str) -> None:
        if not isinstance(commit, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
            raise ArchiveError("Provenance must use a full immutable commit SHA.")
        if commit in self._commits:
            return
        if self.git("cat-file", "-t", commit).strip() != b"commit":
            raise ArchiveError("Provenance object must be a retained commit.")
        self._commits.add(commit)

    def blobs(self, commit: str, paths: list[str], *, batch_size=32, max_blob_bytes=16777216,
              max_batch_bytes=16777216):
        """Read exact blob bytes in bounded batches, checking framing, type, size and identity."""
        self.immutable_commit(commit)
        if type(batch_size) is not int or not 1 <= batch_size <= 128:
            raise ArchiveError("Blob batch size must be between 1 and 128.")
        if any(type(n) is not int or not 0 < n <= 67108864 for n in (max_blob_bytes, max_batch_bytes)):
            raise ArchiveError("Blob byte limits must be between 1 and 67108864.")
        unique = list(dict.fromkeys(paths))
        for path in unique:
            self.path(path)
            if '\n' in path or '\r' in path:
                raise ArchiveError("Batch paths cannot contain newlines.")
        result = {}
        for start in range(0, len(unique), batch_size):
            labels = unique[start:start + batch_size]
            queries = ''.join(f'{commit}:{p}\n' for p in labels).encode('utf-8')
            headers = self.git('cat-file', '--batch-check', stdin=queries).splitlines()
            if len(headers) != len(labels):
                raise ArchiveError("Unexpected blob batch header count.")
            expected = []
            for path, header in zip(labels, headers):
                fields = header.split()
                if (len(fields) != 3 or fields[1] != b'blob'
                        or not re.fullmatch(rb'(?:[0-9a-f]{40}|[0-9a-f]{64})', fields[0])
                        or not fields[2].isdigit()):
                    raise ArchiveError(f"Missing or invalid blob: {path}")
                size = int(fields[2])
                if size > min(max_blob_bytes, max_batch_bytes):
                    raise ArchiveError(f"Blob exceeds byte limit: {path}")
                expected.append((path, header, size))
            groups, group, size = [], [], 0
            for item in expected:
                if group and size + item[2] > max_batch_bytes:
                    groups.append(group)
                    group, size = [], 0
                group.append(item)
                size += item[2]
            if group:
                groups.append(group)
            for group in groups:
                data = self.git('cat-file', '--batch', stdin=''.join(f'{commit}:{p}\n' for p, _, _ in group).encode('utf-8'))
                offset = 0
                for path, expected_header, size in group:
                    end = data.find(b'\n', offset)
                    if end < 0 or data[offset:end] != expected_header:
                        raise ArchiveError("Invalid blob response framing.")
                    offset = end + 1
                    content = data[offset:offset + size]
                    if len(content) != size or data[offset + size:offset + size + 1] != b'\n':
                        raise ArchiveError("Truncated blob response.")
                    oid = expected_header.split()[0].decode('ascii')
                    algorithm = 'sha1' if len(oid) == 40 else 'sha256'
                    if hashlib.new(algorithm, b'blob ' + str(size).encode('ascii') + b'\0' + content).hexdigest() != oid:
                        raise ArchiveError("Blob identity mismatch.")
                    result[path] = content
                    offset += size + 1
                if offset != len(data):
                    raise ArchiveError("Unexpected trailing blob response bytes.")
        return result

    def ignored(self, paths: list[str]) -> list[str]:
        for path in paths:
            self.path(path)
        if not paths:
            return []
        return self.names('check-ignore', '--no-index', '--stdin', '-z', ok=(0, 1),
                          stdin=b'\0'.join(p.encode('utf-8') for p in paths))

    def local_runtime(self, paths: list[str]) -> set[str]:
        """The ignored `paths` that an owner's local runtime rule ignores: the deciding rule is a line of
        info/exclude that Workflow or Progress declared in `info/sanduq-runtime.json` as the exclude it writes
        for its own runtime files. They are disposable, never feature content; any other ignored path is not."""
        if not paths:
            return set()
        exclude = Path(self.git("rev-parse", "--git-path", "info/exclude").decode().strip())
        exclude = (exclude if exclude.is_absolute() else self.root / exclude).resolve()
        try:
            declared = json.loads((exclude.parent / "sanduq-runtime.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        owned = {pattern for lines in (declared.values() if isinstance(declared, dict) else ())
                 if isinstance(lines, list) for pattern in lines if isinstance(pattern, str)}
        # -v -z prints source, line number, pattern and path for each ignored path: git decides the match.
        fields = self.git("check-ignore", "--no-index", "--stdin", "-z", "-v", ok=(0, 1),
                          stdin=b"\0".join(p.encode("utf-8") for p in paths)).split(b"\0")
        result = set()
        for source, _line, pattern, path in zip(*[iter(fields)] * 4):
            source_path = Path(source.decode("utf-8"))
            if ((source_path if source_path.is_absolute() else self.root / source_path).resolve() == exclude
                    and pattern.decode("utf-8") in owned):
                result.add(path.decode("utf-8"))
        return result

    def exists_at(self, commit: str, paths: list[str]) -> dict[str, bool]:
        """Which paths are files at commit: one batched `cat-file --batch-check` over stdin, cached per (commit, path)."""
        self.immutable_commit(commit)
        cache = self._exists
        # A newline would desynchronize the batch protocol; such a path cannot be a valid repository file anyway.
        for path in paths:
            self.path(path)
            if "\n" in path or "\r" in path:
                cache[(commit, path)] = False
        missing = sorted({p for p in paths if (commit, p) not in cache})
        for start in range(0, len(missing), 128):
            batch = missing[start:start + 128]
            lines = self.git("cat-file", "--batch-check=%(objecttype)",
                             stdin="".join(f"{commit}:{p}\n" for p in batch).encode("utf-8")).decode("utf-8").splitlines()
            if len(lines) != len(batch):
                raise ArchiveError("git cat-file returned an unexpected batch result.")
            cache.update({(commit, p): line == "blob" for p, line in zip(batch, lines)})
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

    def stage_scopes(self, scopes: list[str], *, env: dict | None = None) -> None:
        """Stage the scopes like `add -A`, without Git's ignored-path refusal for tracked files under an ignored parent.

        `add -A` exits 1 when a pathspec reaches a tracked file below an ignored directory. `add -u` stages tracked
        edits and deletions without that check; unignored new files are added by name, as `commit` does. An
        untracked ignored file named exactly as a scope is still refused.
        """
        # `add -u` refuses a pathspec that matches no tracked file, which `add -A` accepted when it matched new files.
        tracked = self.names("ls-files", "-z", env=env)
        reach = set(tracked)
        for path in tracked:
            reach.update(str(parent) for parent in PurePosixPath(path).parents if str(parent) != ".")
        known = [s for s in scopes if s in reach]
        if known:
            self.git_paths("add", "-u", paths=known, env=env)
        ignored = set(self.names("ls-files", "--others", "--ignored", "--exclude-standard", "-z", env=env))
        named = sorted(p for p in scopes if p in ignored)
        if named:
            raise ArchiveError(f"Archive scope names ignored untracked paths: {named}")
        new = [p for p in self.names("ls-files", "--others", "--exclude-standard", "-z", env=env)
               if self.within(p, scopes)]
        if new:
            self.git_paths("add", paths=new, env=env)

    def expected_tree(self, scopes: list[str]) -> str:
        self.state.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="index-", dir=self.state)
        os.close(fd)
        os.unlink(name)
        env = dict(os.environ, GIT_INDEX_FILE=name)
        try:
            self.git("read-tree", "HEAD", env=env)
            self.stage_scopes(scopes, env=env)
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

    def lock(self):
        """The writer lock. A lock left by a writer that died on this host is taken over; a live one refuses."""
        return sanduq_fs.file_lock(self.state / "writer.lock", 0, "Archive writer lock exists", ArchiveError)
