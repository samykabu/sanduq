"""Project root, feature resolution and layout paths."""
import os
import re
import subprocess
from pathlib import Path

from .util import read_json

ASSETS = Path(__file__).resolve().parent.parent.parent / 'assets' / 'ui'
EXCLUDES = ('specs/*/progress/.view/', '.specify/progress/bindings.json')


class ProgressError(Exception):
    def __init__(self, code, message='', exit_code=2):
        super().__init__(code)
        self.code, self.message, self.exit_code = code, message, exit_code

    def line(self):
        return f'progress: error {self.code}' + (f' {self.message}' if self.message else '')


def find_root(start=None):
    override = os.environ.get('SANDUQ_PROGRESS_ROOT')
    if override:
        return Path(override).resolve()
    here = Path(start or Path.cwd()).resolve()
    for marker in ('.specify', '.git'):
        for candidate in (here, *here.parents):
            if (candidate / marker).exists():
                return candidate
    return here


def git_dir(root):
    dot = root / '.git'
    if dot.is_dir():
        return dot
    try:
        text = dot.read_text(encoding='utf-8').strip()
    except OSError:
        return None
    if text.startswith('gitdir:'):
        target = Path(text[7:].strip())
        return target if target.is_absolute() else (root / target).resolve()
    return None


def current_branch(root):
    """Branch name from HEAD without spawning git (worktrees keep a .git file)."""
    gdir = git_dir(root)
    try:
        head = (gdir / 'HEAD').read_text(encoding='utf-8').strip() if gdir else ''
    except OSError:
        return None
    return head[len('ref: refs/heads/'):] if head.startswith('ref: refs/heads/') else None


def inside(path, base):
    """True when `path` is `base` or lies beneath it, compared by resolved path components (no prefix tricks)."""
    try:
        a, b = Path(os.path.realpath(str(path))), Path(os.path.realpath(str(base)))
    except OSError:
        return False
    a, b = Path(os.path.normcase(str(a))), Path(os.path.normcase(str(b)))
    return a == b or b in a.parents


def normalise_feature(root, value):
    """`specs/<dir>` (or a bare `<dir>`, or an absolute path inside the repo) for a real directory that, once symlinks are
    resolved, is a direct child of the resolved specs directory. Dot components are never accepted."""
    root = Path(root)
    path = Path(value)
    if not path.is_absolute() and any(p in ('.', '..') for p in re.split(r'[\\/]', str(value))):
        return None
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(root.resolve())
        except ValueError:
            return None
    text = path.as_posix().strip('/')
    if '/' not in text:
        text = 'specs/' + text
    parts = text.split('/')
    if len(parts) != 2 or parts[0] != 'specs' or any(p in ('', '.', '..') for p in parts):
        return None
    candidate = root / text
    if not candidate.is_dir():
        return None
    specs = Path(os.path.realpath(str(root / 'specs')))
    if not inside(specs, root):
        return None
    resolved = Path(os.path.realpath(str(candidate)))
    if os.path.normcase(str(resolved.parent)) != os.path.normcase(str(specs)):
        return None
    return text


def checkpoint_feature(root, branch):
    """The Workflow checkpoint's `feature` for the current branch (newest if several)."""
    best = None
    for path in sorted((root / 'specs').glob('*/workflow/checkpoint.json')):
        data = read_json(path, {})
        if isinstance(data, dict) and isinstance(data.get('feature'), str) and data.get('branch') == branch:
            stamp = str(data.get('updated_at') or '')
            if best is None or stamp > best[0]:
                best = (stamp, data['feature'])
    return best[1] if best else None


def resolve_feature(root, explicit=None):
    """--feature, SPECIFY_FEATURE, Workflow checkpoint, branch matching specs/<branch>."""
    branch = current_branch(root)
    for source in (explicit, os.environ.get('SPECIFY_FEATURE'),
                   checkpoint_feature(root, branch) if branch else None, branch):
        if source:
            found = normalise_feature(root, source)
            if found:
                return found
            if source == explicit:
                break
    raise ProgressError('PROGRESS_NO_FEATURE', 'pass --feature specs/<dir>')


class Ctx:
    def __init__(self, root, feature):
        self.root, self.feature = Path(root), feature
        self.feature_dir = self.root / feature
        self.dir = self.feature_dir / 'progress'
        self.facts = self.dir / 'facts.jsonl'
        self.view = self.dir / '.view'
        self.host_dir = self.view / 'host'
        self.state = self.view / 'state.json'
        self.report = self.view / 'report.json'
        self.data_js = self.view / 'data.js'
        self.lock = self.view / 'lock'
        self.diag = self.view / 'diagnostics.log'
        self.cfg_dir = self.root / '.specify' / 'progress'
        self.check_confined()
        self.config = self.cfg_dir / 'config.json'
        self.theme = self.cfg_dir / 'theme.json'
        self.bindings = self.cfg_dir / 'bindings.json'
        self.bindings_lock = self.cfg_dir / 'bindings.lock'

    def check_confined(self):
        """Raise unless the feature, its progress directory and the view directory stay beneath the resolved specs
        directory (a symlinked or forged feature or output directory must not move writes outside the repository)."""
        specs = self.root / 'specs'
        chain = ((specs, self.root), (self.cfg_dir, self.root), (self.feature_dir, specs), (self.dir, self.feature_dir),
                 (self.view, self.dir))
        parts = Path(self.feature).parts
        if len(parts) != 2 or parts[0] != 'specs' or any(p in ('', '.', '..') for p in parts):
            raise ProgressError('PROGRESS_NO_FEATURE', 'feature must be specs/<dir>', 2)
        for path, base in chain:
            if path.exists() or path.is_symlink():
                if not inside(path, base):
                    raise ProgressError('PROGRESS_NO_FEATURE', f'{path.name} resolves outside the repository', 2)
        return self

    def config_data(self):
        data = {'feature_dir_mode': 'auto', 'debounce_seconds': 5, 'stale_after_seconds': 600,
                'statusline': {'enabled': False, 'chained': None}}
        stored = read_json(self.config, {})
        if isinstance(stored, dict):
            data.update(stored)
        return data


def git_exclude(root, patterns=EXCLUDES):
    """Add patterns to the repository's info/exclude (never to a tracked .gitignore)."""
    try:
        out = subprocess.run(['git', 'rev-parse', '--git-path', 'info/exclude'], cwd=str(root), capture_output=True,
                             text=True, timeout=10)
        if out.returncode != 0 or not out.stdout.strip():
            return False
        target = Path(out.stdout.strip())
        target = target if target.is_absolute() else root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding='utf-8').splitlines() if target.exists() else []
        missing = [p for p in patterns if p not in existing]
        if missing:
            with open(target, 'a', encoding='utf-8') as stream:
                stream.write(('\n' if existing and existing[-1] != '' else '') + '\n'.join(missing) + '\n')
        return True
    except (OSError, subprocess.SubprocessError):
        return False
