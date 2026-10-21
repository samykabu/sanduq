"""One `gh` transport for Scope, Workflow, Project and PR (round 5, SC8 / X22).

Stdlib only: each consumer loads it without Workflow or PyYAML. Transport only: one runner, one timeout
default, one retry rule and one rate-limit test. Callers keep their own clients, fallbacks and error codes,
and wrap `GhError` in their own error type.

Retries are opt-in (`retry=True`) and apply only to a read this module can prove safe: `gh api` with no
method other than GET and no fields or body, or `gh api graphql` whose query is not a mutation. Such a read
is tried once more after 2 s when it failed with an HTTP 5xx or timed out. Anything else, including every
`gh project` command, is never retried, so a timeout after a possible write is reported, not repeated.
"""
import json
import re
import subprocess
import time

GH_MISSING = 127
RETRY_DELAY = 2
# `gh api` flags that take a value, so the next argument is not the endpoint.
_VALUED = {'-X', '--method', '-f', '--raw-field', '-F', '--field', '-H', '--header', '--input', '-q', '--jq',
           '-t', '--template', '--hostname', '--cache', '-p', '--preview'}
_FIELDS = {'-f', '--raw-field', '-F', '--field'}


class GhError(Exception):
    """A failed `gh` call. `returncode` is 127 when gh is absent, None on a timeout, 0 for GraphQL errors
    reported on a successful exit."""

    def __init__(self, message, *, returncode=None, stderr='', stdout='', timeout=False, rate_limited=False,
                 reset_at=None):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        self.timeout = timeout
        self.rate_limited = rate_limited
        self.reset_at = reset_at


def rate_limited(text):
    """True when a GitHub message names a rate limit: "rate limit", "rate limited", "RATE_LIMIT", "rate-limit"."""
    return 'rate limit' in re.sub(r'[\s_\-]+', ' ', (text or '').lower())


def token_scopes(auth_text):
    """The scopes on gh's `Token scopes:` lines, as a set ('project' is not 'read:project')."""
    return {scope for line in (auth_text or '').splitlines() if 'Token scopes:' in line
            for scope in re.findall(r"'([^']+)'", line)}


def _flags(args):
    """(endpoint, [(flag, value)]) of a `gh api` argument list; `--flag=value` and `-Xvalue` are split."""
    endpoint, flags, rest = None, [], list(args[1:])
    while rest:
        item = rest.pop(0)
        if item.startswith('--') and '=' in item:
            flags.append(tuple(item.split('=', 1)))
        elif item in _VALUED:
            flags.append((item, rest.pop(0) if rest else ''))
        elif re.fullmatch(r'-[XfFHqtp].+', item):
            flags.append((item[:2], item[2:]))
        elif item.startswith('-'):
            flags.append((item, None))
        elif endpoint is None:
            endpoint = item
    return endpoint, flags


def _graphql_query(flags, payload):
    """The GraphQL document a call sends, or None when it cannot be read here (a file or an unknown body)."""
    for flag, value in flags:
        if flag in _FIELDS and value and value.startswith('query='):
            query = value[len('query='):]
            return None if flag in ('-F', '--field') and query.startswith('@') else query
        if flag == '--input':
            if value != '-' or not isinstance(payload, dict):
                return None
            return payload.get('query') if isinstance(payload.get('query'), str) else None
    return None


def safe_read(args, payload=None):
    """True when `gh <args>` is a read that may be repeated: REST GET without fields or body, or a GraphQL
    query that is not a mutation. `gh project` and every other command are never safe."""
    if not args or args[0] != 'api':
        return False
    endpoint, flags = _flags(args)
    method = [value for flag, value in flags if flag in ('-X', '--method')]
    if any((value or '').upper() != ('POST' if endpoint == 'graphql' else 'GET') for value in method):
        return False
    if endpoint == 'graphql':
        query = _graphql_query(flags, payload)
        # Comments and strings could hide the keyword; any `mutation` token at all counts as a write.
        return query is not None and re.search(r'\bmutation\b', query) is None
    return not any(flag in _FIELDS or flag == '--input' for flag, _ in flags)


def _transient(error):
    return error.timeout or re.search(r'\bHTTP 5\d\d\b', error.stderr + '\n' + error.stdout) is not None


def _run_once(args, payload, timeout, binary, cwd):
    data = payload if payload is None or isinstance(payload, (str, bytes)) else json.dumps(payload)
    if binary and isinstance(data, str):
        data = data.encode('utf-8')
    elif not binary and isinstance(data, bytes):
        data = data.decode('utf-8')
    name = 'gh ' + ' '.join(str(a) for a in args[:3])
    text = {} if binary else {'text': True, 'encoding': 'utf-8'}
    try:
        done = subprocess.run(['gh', *args], input=data, capture_output=True, timeout=timeout, cwd=cwd, **text)
    except FileNotFoundError:
        raise GhError('gh CLI not installed', returncode=GH_MISSING, stderr='gh CLI not installed') from None
    except subprocess.TimeoutExpired:
        raise GhError(f'timeout: {name} gave no answer in {timeout} s', timeout=True) from None
    if done.returncode:
        stderr = done.stderr.decode('utf-8', 'replace') if binary else (done.stderr or '')
        stdout = done.stdout.decode('utf-8', 'replace') if binary else (done.stdout or '')
        raise GhError(f'{name} failed: {(stderr.strip() or stdout.strip())[:700]}', returncode=done.returncode,
                      stderr=stderr, stdout=stdout, rate_limited=rate_limited(stderr + '\n' + stdout))
    return done.stdout


def run_gh(args, *, payload=None, timeout=60, binary=False, cwd=None, retry=False):
    """stdout of `gh <args>` (bytes when `binary`); `payload` goes to stdin, JSON-encoded unless str or bytes.
    Raises `GhError`. With `retry=True`, a `safe_read` is tried once more after a 5xx or a timeout."""
    try:
        return _run_once(args, payload, timeout, binary, cwd)
    except GhError as error:
        if not (retry and _transient(error) and safe_read(args, payload)):
            raise
    time.sleep(RETRY_DELAY)
    return _run_once(args, payload, timeout, binary, cwd)


def api(endpoint, *, method='GET', payload=None, pages=False, timeout=60, cwd=None, retry=False):
    """Parsed JSON of a REST call (None for an empty body); `pages` follows every page and flattens list pages."""
    args = ['api', endpoint, '-H', 'Accept: application/vnd.github+json']
    if pages:
        args += ['--paginate', '--slurp']
    if method != 'GET':
        args += ['--method', method]
    if payload is not None:
        args += ['--input', '-']
    out = run_gh(args, payload=payload, timeout=timeout, cwd=cwd, retry=retry)
    data = json.loads(out) if out.strip() else None
    if pages and data is not None:
        return [item for page in data for item in (page if isinstance(page, list) else [page])]
    return data


def graphql(query, *, timeout=60, cwd=None, retry=False, **variables):
    """`data` of a GraphQL call. GraphQL errors raise `GhError` even when gh exits 0."""
    payload = {'query': query, 'variables': variables}
    out = run_gh(['api', 'graphql', '--input', '-'], payload=payload, timeout=timeout, cwd=cwd, retry=retry)
    data = json.loads(out) if out.strip() else {}
    errors = data.get('errors')
    if errors:
        text = json.dumps(errors)
        limited = rate_limited(text) or any(isinstance(e, dict) and e.get('type') == 'RATE_LIMITED' for e in errors)
        raise GhError(f'GraphQL failed: {text[:700]}', returncode=0, stderr=text, stdout=out, rate_limited=limited)
    return data.get('data')
