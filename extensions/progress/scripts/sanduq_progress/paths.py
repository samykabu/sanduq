"""Project root, report-target resolution (Spec Kit feature or plan) and layout paths."""
import os
import re
from pathlib import Path

from .util import ProgressError, read_json

ASSETS = Path(__file__).resolve().parent.parent.parent / 'assets' / 'ui'
PLAN_ROOT = '.progress'  # default home of plan-mode report directories: .progress/<name>/
PLAN_REGISTRY = PLAN_ROOT + '/plans.json'  # tracked; lists report directories that live outside .progress/
TASK_REF = r'[A-Z]{1,3}-?\d+'  # a task id as plans and tasks.md write it: T001, P012, US3
RESERVED_ID = re.compile(r'(?:[LWCBDN]|SD)\d+')  # lane, blocker, decision and note ids are never task ids
NAME = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}')


def project_dir(root):
    """Where project-level state lives (config, theme, bindings, diagnostics): `.specify/progress` in a Spec Kit project,
    `.progress/.project` everywhere else. An existing directory wins, so a project keeps one home once it has one."""
    root = Path(root)
    for candidate in ('.specify/progress', PLAN_ROOT + '/.project'):
        if (root / candidate).is_dir():
            return root / candidate
    return root / ('.specify/progress' if (root / '.specify').is_dir() else PLAN_ROOT + '/.project')


EXCLUDES = ('specs/*/progress/.view/', 'specs/*/progress/.host/', '.specify/progress/bindings.json',
            '.specify/progress/*.lock', '.specify/progress/diagnostics.log*')  # the Spec Kit set; see default_excludes


def is_default_plan_dir(directory):
    return directory.startswith(PLAN_ROOT + '/') and directory.count('/') == 1


def glob_escape(path):
    """A literal repo-relative path as a git ignore pattern: glob metacharacters, a leading `#` or `!` and trailing spaces
    are escaped, so a directory like `reports/[review]` excludes itself and nothing else."""
    text = re.sub(r'([\\*?\[\]])', r'\\\1', path)
    if text[:1] in ('#', '!'):
        text = '\\' + text
    return re.sub(r'(\s)$', r'\\\1', text)


def default_excludes(root, extra_dirs=()):
    base = project_dir(root).relative_to(Path(root)).as_posix()
    patterns = ['specs/*/progress/.view/', 'specs/*/progress/.host/', PLAN_ROOT + '/*/.view/', PLAN_ROOT + '/*/.host/',
                base + '/bindings.json', base + '/*.lock', base + '/diagnostics.log*']
    if base.startswith(PLAN_ROOT + '/'):
        patterns.append(base + '/config.json')  # local statusline state; without Spec Kit nothing else shares it
    for directory in (*registry_dirs(root), *extra_dirs):
        patterns += [glob_escape(directory) + '/.view/', glob_escape(directory) + '/.host/']
    return tuple(dict.fromkeys(patterns))


def find_root(start=None):
    override = os.environ.get('SANDUQ_PROGRESS_ROOT')
    if override:
        return Path(override).resolve()
    here = Path(start or Path.cwd()).resolve()
    for marker in ('.specify', '.git', PLAN_ROOT):
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


def feature_mode(target):
    """True for a Spec Kit feature id (`specs/<dir>`); any other target is a plan report directory."""
    return bool(re.fullmatch(r'specs/[^/]+', str(target)))


def slugify(text):
    slug = re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')[:64].strip('-')
    return slug or 'plan'


def normalise_plan_dir(root, value):
    """Repo-relative posix path for a plan report directory: no dot components, not under .git, nothing under `specs/`,
    and (symlinks resolved) strictly inside the repository. None when the value is not acceptable."""
    root = Path(root)
    text = str(value).replace('\\', '/')
    if Path(text).is_absolute() or re.match(r'[A-Za-z]:', text):
        try:
            text = Path(text).resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            return None
    text = text.strip('/')
    parts = text.split('/')
    if not text or any(p in ('', '.', '..') for p in parts) or parts[0] == '.git' or parts[0].lower() == 'specs':
        return None
    try:
        target = Path(os.path.realpath(str(root / text)))
        if not inside(target, root) or os.path.normcase(str(target)) == os.path.normcase(os.path.realpath(str(root))):
            return None
    except OSError:
        return None
    return text


def registry_dirs(root):
    data = read_json(Path(root) / PLAN_REGISTRY, {})
    dirs = data.get('dirs') if isinstance(data, dict) else None
    return [d for d in dirs if isinstance(d, str) and d] if isinstance(dirs, list) else []


def list_plans(root):
    """Report directories of initialised plans: `.progress/*/plan.json` plus registered custom directories."""
    root = Path(root)
    found = [p.parent.relative_to(root).as_posix() for p in sorted((root / PLAN_ROOT).glob('*/plan.json')) if p.is_file()]
    for directory in registry_dirs(root):
        if directory not in found and (root / directory / 'plan.json').is_file() and normalise_plan_dir(root, directory) == directory:
            found.append(directory)
    return found


def list_features(root):
    """Spec Kit features whose progress report has been initialised."""
    root = Path(root)
    return [p.parent.parent.relative_to(root).as_posix() for p in sorted(root.glob('specs/*/progress/facts.jsonl'))]


def plan_info(root, directory):
    data = read_json(Path(root) / directory / 'plan.json', {})
    return data if isinstance(data, dict) else {}


def plan_source(root, directory):
    """Absolute path of the plan file a report reads, or None. `external:<name>` sources keep their absolute path only in
    the git-ignored `.host/plan-source.json`; a repo-relative source must stay inside the repository."""
    root = Path(root)
    source = plan_info(root, directory).get('source')
    if not isinstance(source, str) or not source:
        return None
    if source.startswith('external:'):
        data = read_json(root / directory / '.host' / 'plan-source.json', {})
        path = data.get('path') if isinstance(data, dict) else None
        return Path(path) if isinstance(path, str) and path else None
    candidate = root / source
    return candidate if inside(candidate, root) else None


def find_plan(root, value):
    """A plan report directory from `--plan NAME|PATH`: a name, a report directory, or the plan file itself."""
    root = Path(root)
    text = str(value).strip()
    plans = list_plans(root)
    if NAME.fullmatch(text) and f'{PLAN_ROOT}/{text}' in plans:
        return f'{PLAN_ROOT}/{text}'
    for directory in plans:
        if plan_info(root, directory).get('name') == text:
            return directory
    candidates = [Path(text)] if Path(text).is_absolute() else [Path.cwd() / text, root / text]
    for candidate in candidates:
        if candidate.is_dir():
            relative = normalise_plan_dir(root, candidate)
            if relative in plans:
                return relative
        elif candidate.is_file():
            real = os.path.normcase(os.path.realpath(str(candidate)))
            for directory in plans:
                source = plan_source(root, directory)
                if source and os.path.normcase(os.path.realpath(str(source))) == real:
                    return directory
    return None


def no_target(root):
    names = [f"plan:{plan_info(root, d).get('name') or Path(d).name}" for d in list_plans(root)] + list_features(root)
    if names:
        return ProgressError('PROGRESS_NO_FEATURE', 'pass --plan NAME or --feature DIR (candidates: ' + ', '.join(names[:8])
                             + (', ...' if len(names) > 8 else '') + ')')
    return ProgressError('PROGRESS_NO_FEATURE', 'pass --feature specs/<dir>')


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


def resolve_target(root, plan=None, feature=None, creating=False):
    """The report a verb works on: `--plan`, `--feature`, or the one active report. Several candidates are an error
    that lists them (one line). `creating` (init without --plan) only considers Spec Kit features."""
    if plan and feature:
        raise ProgressError('PROGRESS_USAGE', 'give --plan or --feature, not both', 2)
    if plan:
        found = find_plan(root, plan)
        if not found:
            raise no_target(root)
        return found
    if feature or creating:
        return resolve_feature(root, feature)
    try:
        implicit = resolve_feature(root)
    except ProgressError:
        implicit = None
    if implicit and (Path(root) / implicit / 'progress' / 'facts.jsonl').is_file():
        return implicit
    active = list_features(root) + list_plans(root)
    if len(active) == 1:
        return active[0]
    if implicit and not active:
        return implicit
    raise no_target(root)


class Ctx:
    def __init__(self, root, feature):
        self.root, self.feature = Path(root), feature
        self.is_plan = not feature_mode(feature)
        self.feature_dir = self.root / feature
        self.dir = self.feature_dir if self.is_plan else self.feature_dir / 'progress'
        self.facts = self.dir / 'facts.jsonl'
        self.view = self.dir / '.view'
        self.host_dir = self.dir / '.host'  # durable host observations (child identity): git-ignored, not part of the disposable view
        self.plan_file = self.dir / 'plan.json'  # plan mode: tracked name, source reference and stable ids
        self.plan_source_file = self.host_dir / 'plan-source.json'  # plan mode: absolute path of an external plan (local only)
        self.state = self.view / 'state.json'
        self.report = self.view / 'report.json'
        self.data_js = self.view / 'data.js'
        self.lock = self.view / 'lock'
        self.diag = self.view / 'diagnostics.log'
        self.cfg_dir = project_dir(self.root)
        self.check_confined()
        self.config = self.cfg_dir / 'config.json'
        self.theme = self.cfg_dir / 'theme.json'
        self.bindings = self.cfg_dir / 'bindings.json'
        self.bindings_lock = self.cfg_dir / 'bindings.lock'

    def check_confined(self):
        """Raise unless the feature, its progress directory and the view directory stay beneath the resolved specs
        directory, or a plan's report directory stays beneath the repository (a symlinked or forged feature or output
        directory must not move writes outside the repository)."""
        if self.is_plan:
            if normalise_plan_dir(self.root, self.feature) != self.feature:
                raise ProgressError('PROGRESS_NO_FEATURE', 'plan directory must stay inside the repository', 2)
            chain = ((self.cfg_dir, self.root), (self.dir, self.root), (self.view, self.dir), (self.host_dir, self.dir))
        else:
            specs = self.root / 'specs'
            chain = ((specs, self.root), (self.cfg_dir, self.root), (self.feature_dir, specs), (self.dir, self.feature_dir),
                     (self.view, self.dir), (self.host_dir, self.dir))
            parts = Path(self.feature).parts
            if len(parts) != 2 or parts[0] != 'specs' or any(p in ('', '.', '..') for p in parts):
                raise ProgressError('PROGRESS_NO_FEATURE', 'feature must be specs/<dir>', 2)
        for path, base in chain:
            if path.exists() or path.is_symlink():
                if not inside(path, base):
                    raise ProgressError('PROGRESS_NO_FEATURE', f'{path.name} resolves outside the repository', 2)
        return self

    def config_data(self):
        data = {'debounce_seconds': 5, 'stale_after_seconds': 600,
                'statusline': {'enabled': False, 'chained': None}}
        stored = read_json(self.config, {})
        if isinstance(stored, dict):
            data.update(stored)
        return data


def git_exclude(root, patterns=None):
    """Add patterns to the repository's info/exclude (never to a tracked .gitignore)."""
    import subprocess
    try:
        patterns = default_excludes(root) if patterns is None else patterns
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
        # Memory treats a file ignored by one of these lines as disposable runtime, not feature content.
        declaration = target.parent / 'sanduq-runtime.json'
        declared = read_json(declaration, {})
        declared = declared if isinstance(declared, dict) else {}
        owned = declared.get('progress') if isinstance(declared.get('progress'), list) else []
        if not set(patterns) <= set(owned):
            from .util import write_json
            write_json(declaration, {**declared, 'progress': list(dict.fromkeys([*owned, *patterns]))})
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# Local-only files a report writes (names under `.host/` and `.view/`). A sample snapshot name stands for the hashed
# per-session files; the check is of the files themselves, so a rule that re-includes one of them is caught.
LOCAL_FILES = {'.host': ('plan-keys.json', 'plan-source.json', 'session-snapshot.json', 'self-report.json'),
               '.view': ('state.json', 'report.json', 'data.js', 'lock', 'diagnostics.log', 'index.html', 'base.css',
                         'blocks.js', 'theme.css', 'layout.js')}


def local_only_paths(directory):
    """Repo-relative paths of every local-only file a report in `directory` (its progress directory) can write."""
    return [f'{directory}/{leaf}/{name}' for leaf, names in LOCAL_FILES.items() for name in names]


def check_excluded(root, directory):
    """Fail with one line, before anything is written, unless git ignores every local-only file the report at `directory`
    (its progress directory, repo-relative) will write. Skipped when git or the repository is not there: nothing can be
    committed then."""
    import subprocess
    root = Path(root)
    if git_dir(root) is None:
        return
    wanted = local_only_paths(directory)
    try:
        out = subprocess.run(['git', 'check-ignore', '--stdin', '-z'], cwd=str(root), capture_output=True, timeout=20,
                             input=chr(0).join(wanted).encode('utf-8'))
    except (OSError, subprocess.SubprocessError):
        return  # git is not usable here
    if out.returncode not in (0, 1):
        return
    ignored = {item.decode('utf-8', errors='replace') for item in out.stdout.split(b'\x00') if item}
    loose = [p for p in wanted if p not in ignored]
    if loose:
        raise ProgressError('PROGRESS_EXCLUDE_FAILED', f'git does not ignore {loose[0]}; pick another --dir '
                            '(local-only files would be committed)', 3)


WORKFLOW_MINIMUM = (1, 17, 0)  # the first Sanduq Workflow that reads v3 and `runs --json` instead of `--schema v2`
WORKFLOW_UPGRADE = 'python .specify/extensions/workflow/scripts/upgrade.py --version 1.17.1 --apply'


def workflow_version(root):
    """The installed Sanduq Workflow version (`.specify/extensions/workflow/extension.yml`), or None."""
    try:
        text = (Path(root) / '.specify' / 'extensions' / 'workflow' / 'extension.yml').read_text(encoding='utf-8-sig')
    except OSError:
        return None
    match = re.search(r'^[ \t]+version:[ \t]*["\']?(\d+(?:\.\d+){0,2})\b', text, re.M)
    return match.group(1) if match else None


def workflow_outdated(root):
    """The installed Sanduq Workflow version when it is older than Progress needs, else None."""
    version = workflow_version(root)
    if version and tuple(int(part) for part in (version.split('.') + ['0', '0'])[:3]) < WORKFLOW_MINIMUM:
        return version
    return None


def removed(what, root):
    """The one-line error (exit 2) for a request of a removed v2 surface. It names an installed Sanduq Workflow and, when
    that Workflow is old enough to still ask for it, the upgrade."""
    message = f'{what} was removed in agent-tools 1.7.0'
    version = workflow_version(root)
    if version:
        message += f'; Sanduq Workflow {version} is installed'
        if workflow_outdated(root):
            message += f' and needs 1.17.0 or later: {WORKFLOW_UPGRADE}'
    return ProgressError('PROGRESS_REMOVED', message, 2)
