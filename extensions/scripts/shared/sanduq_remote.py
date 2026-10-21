"""One reading of a repository's GitHub identity for Workflow, Project and Scope.

Stdlib only: Project and Scope load it without Workflow or PyYAML. Moved from
`workflow.py` (round 4, D4) without behaviour change; see the docstrings there
in earlier releases for the round-1 and round-2 findings each rule answers.
"""
import re
import subprocess
import urllib.parse

_GITHUB = re.compile(r'github\.com(?::\d+)?/([^/]+/[^/]+)')


def _strip_dotgit(path):
    """Drop one trailing `.git` (case-insensitively -- real hosts vary), once."""
    return path[:-4] if path[-4:].lower() == '.git' else path


def _normalize_path_remote(path):
    """A local-filesystem remote: fold separator style only, never case (two
    case-distinct paths are two repositories), except a leading Windows drive
    letter, which is case-insensitive."""
    path = path.replace('\\', '/')
    while len(path) > 1 and path.endswith('/'):
        path = path[:-1]
    path = _strip_dotgit(path)
    drive = re.match(r'[A-Za-z]:(?=/|$)', path)
    if drive:
        path = drive.group().lower() + path[drive.end():]
    return path


def normalize_remote_url(url):
    """Fold scheme, credential, case and port-vs-path differences that name the same remote.

    ``https://user:pass@Github.com/Acme/App.git``, ``git@github.com:Acme/App.git`` and
    ``ssh://git@github.com/Acme/App/`` all become ``github.com/Acme/App``. The host is lowered
    (a trailing root ``.`` folded), credentials and the scheme dropped, a default port dropped,
    a trailing ``.git``/``/`` removed; the repository path keeps its case. A real URL goes through
    `urllib.parse`, so ``https://github.com@evil.com/...`` is ``evil.com`` and a non-numeric port
    falls through unfolded. SCP shorthand and local paths go to `_normalize_path_remote`.
    """
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == 'file':
        return _normalize_path_remote(parts.path or url)
    if parts.scheme and parts.netloc:
        try:
            host = parts.hostname
            if host is None:
                raise ValueError('no host')
            host = host.rstrip('.').lower()
            port = parts.port
            if port and port != {'ssh': 22, 'https': 443, 'http': 80}.get(parts.scheme):
                host += ':' + str(port)
            return host + '/' + _strip_dotgit(parts.path.strip('/'))
        except ValueError:
            pass  # malformed (e.g. a non-numeric port): fall through, unfolded
    if '://' not in url:
        scp = re.fullmatch(r'(?:[^@/\s]*@)?([^@/:\s]+):(.+)', url)
        if scp:
            host, path = scp.groups()
            if not (len(host) == 1 and host.isalpha()):  # else a Windows drive letter, not SCP
                return host.rstrip('.').lower() + '/' + _strip_dotgit(path.rstrip('/'))
    return _normalize_path_remote(url)


def github_slug(url):
    """`owner/repo` when `url` names a GitHub repository, else None. Case is preserved:
    compare with `same_github_repository`, never `==`. None-safe, so `github_slug(origin_url(root))` works."""
    if not url:
        return None
    match = _GITHUB.fullmatch(normalize_remote_url(url))
    return match[1] if match else None


def same_github_repository(a, b):
    """Case-insensitive equality of two `owner/repo` strings; False when either is None."""
    return a is not None and b is not None and a.lower() == b.lower()


def origin_url(root, timeout=10, resolve=False):
    """The `origin` URL, or None when it is not configured. Raw `remote.origin.url` by default, which
    Workflow's portable identity is built from; `resolve=True` applies `url.<base>.insteadOf` rewrites
    (`git remote get-url`), which is what a GitHub slug must be read from."""
    command = ['remote', 'get-url', 'origin'] if resolve else ['config', '--get', 'remote.origin.url']
    result = subprocess.run(['git', *command], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
