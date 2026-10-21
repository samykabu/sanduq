sanduq_gh.py READY

# Round 5 notes: S-SH (shared and release tooling)

## SC8 / X22: `extensions/scripts/shared/sanduq_gh.py`

Interface as built (Amendment 1: transport only):

```python
GH_MISSING = 127
class GhError(Exception): returncode, stderr, stdout, timeout, rate_limited, reset_at
    # returncode: 127 gh absent; None on timeout; 0 for GraphQL errors on a successful exit; else gh's exit code
    # str(error): 'gh CLI not installed' | 'timeout: gh <a b c> gave no answer in <t> s'
    #             | 'gh <a b c> failed: <stderr or stdout, 700 chars>' | 'GraphQL failed: <errors JSON>'
    # rate_limited: rate_limited(stderr + stdout), or a GraphQL error of type RATE_LIMITED; reset_at: always None
    #               from this module (Scope's probe fills its own reset time)
def rate_limited(text) -> bool                     # moved from scope.py unchanged
def token_scopes(auth_text) -> set[str]            # as project_sync.py; None-safe
def safe_read(args, payload=None) -> bool          # the retry classification, public so callers can test it
def run_gh(args, *, payload=None, timeout=60, binary=False, cwd=None, retry=False) -> str | bytes
    # payload: str/bytes go to stdin as they are, anything else JSON-encoded; returns raw stdout (not stripped)
def api(endpoint, *, method='GET', payload=None, pages=False, timeout=60, cwd=None, retry=False)
    # args: api <endpoint> -H 'Accept: application/vnd.github+json' [--paginate --slurp] [--method M] [--input -]
    # parsed JSON, None for an empty body; pages flattens list pages (a dict page stays one item)
def graphql(query, *, timeout=60, cwd=None, retry=False, **variables)
    # gh api graphql --input - with {"query", "variables"}; returns data['data']; errors on exit 0 raise GhError
```

Retry rule: only with `retry=True`, only when `safe_read(args, payload)`, only after an HTTP 5xx (`HTTP 5dd` in
stderr or stdout) or a timeout; one more attempt after `RETRY_DELAY` (2 s); the second failure is raised.
`safe_read` is true only for `gh api` with no method other than GET (POST allowed for `graphql`), no
`-f/-F/--field/--raw-field/--input` for REST, and for `graphql` a readable query (from `-f query=`, or `--input -`
with a dict payload) containing no `mutation` token. `-F query=@file`, `--input <file>`, `gh project`, and every
non-`api` command are never retried. Additions over the plan's sketch (additive): `GhError.stdout` (Project joins
stdout and stderr in its messages), `retry` on `api`/`graphql`, `safe_read`, `GH_MISSING`, `RETRY_DELAY`.

Consumers import it like `sanduq_remote` (dev-tree fallback):

```python
try:
    import sanduq_gh
except ModuleNotFoundError:  # source tree; the packaged copy sits next to this file
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'shared'))
    import sanduq_gh
```

Tests patch `sanduq_gh.subprocess.run` (and `sanduq_gh.time.sleep` for retries), or keep their own seams above it.

Files: `extensions/scripts/shared/sanduq_gh.py` (new), `extensions/scripts/package.py` (`SHARED['sanduq_gh.py'] =
('scope', 'workflow', 'project', 'pr')`), `extensions/scripts/tests/test_sanduq_gh.py` (new),
`extensions/scripts/tests/test_sanduq_remote.py` (packaged-copy tests now cover `sanduq_gh.py`: archive bytes and
inventory hash in all four packages, installed-layout import with PyYAML and packaging blocked and no Workflow).

Tests: `python -m unittest discover -s extensions/scripts/tests -p "test_sanduq_*.py" -q`: 24 tests OK.

## X23: bump guard

- `package.py`: `package_files(extension, root)` split out of `package()` (the member-to-bytes map before
  `package-inventory.json`); `package()` behaviour unchanged.
- `release.py`:
  - `inventory_sha256(name, root)`: sha256 over the sorted `member NUL sha256(content)` lines of the final packaged
    inventory (injected helpers and bundled presets included), except `UNVERSIONED` =
    `<ext>/README.md`, `<ext>/CHANGELOG.md`, `<ext>/LICENSE`, `<ext>/docs/**` (top level only; nested
    `templates/CHANGELOG.md`, skill READMEs and preset READMEs stay covered). CRLF hashes as LF, so a Windows
    working copy with `core.autocrlf` (four such files in this tree today) agrees with CI.
  - `check_bumps(root)`: for each extension with a catalog entry (root `catalog.json`): passes when the manifest
    version or the `pending-releases.json` version is greater than the catalog's; else skips with a notice when
    the entry has no `inventory_sha256` (bootstrap); else fails when the hash differs. A pending version equal to or
    lower than the catalog's does not count. Extensions absent from the catalog are not checked.
  - `prepare` writes `inventory_sha256` into each released catalog entry (promote copies it into both catalogs).
  - CLI: `release.py check-bumps` prints `{ok, failures, notices}` and exits 1 when `ok` is false.
- Today's tree: `ok: true`, nine bootstrap notices (no catalog entry has the field yet). Every package released
  this round gets the field at its release; packages not released (expected: Assure, Memory) stay unguarded until
  their next release.
- Tests: `extensions/scripts/tests/test_release_check_bumps.py` (new, 11 tests): unchanged tree passes; command
  `.md` change without bump fails (exact message); README, CHANGELOG, LICENSE, docs edits pass while nested
  `templates/CHANGELOG.md`, `skills/x/README.md`, `commands/docs.md` fail; CRLF-only difference passes; injected
  `sanduq_gh.py` change fails in exactly scope, workflow, project, pr; bundled preset change fails in scope and
  workflow; manifest bump or greater pending version passes; equal or lower pending version fails; bootstrap
  notice; `prepare` records the hash and the guard then passes; CLI exits 0, then 1 with the failure line.

## CRLF: `release.py bump`

- Cause: the extension-block regex required `^extension:\n`, so a CRLF manifest had "no extension block".
- Fix: `^extension:\r?\n(?:[ \t]+.*\n|\r?\n)*`; the replacement touches only the version value, so every other
  byte (CRLF or LF, mixed too) stays as it was.
- Test: `test_release_bump.py` `test_bump_keeps_crlf_and_each_quote_style` (double, single and no quotes, each with
  CRLF and LF; exact bytes compared). Failed before the fix (3 errors, the CRLF cases), passes after.

## Test results (end of stream)

- `python -m unittest discover -s extensions/scripts/tests -q`: 185 tests OK (77.8 s), Python 3.11 via uv.
- `python extensions/scripts/test_check_docs.py`: passed. `python extensions/scripts/check_docs.py`: Documentation OK.

## Interface changes

None after READY.

## Requests

- **S-CI** (`.github/scripts/ci_matrix.py`, `INJECTED`): the `sanduq_gh.py` entry. Done by S-CI (commit 97e35ae).
- **S-CI** (`.github/workflows/ci.yml`, `lint` job): add after "Check documentation links and command coverage":

  ```yaml
      - name: Shipped files changed only with a version bump (X23)
        run: python3 extensions/scripts/release.py check-bumps
  ```

  The lint job already installs `pyyaml packaging`; the command takes about 0.4 s.
- **Orchestrator** (`CONTRIBUTING.md:169-171`, not S-SH's file): add one line to the release block:
  `python extensions/scripts/release.py check-bumps    # lint: shipped files changed without a bump`.
- No changelog entry: `extensions/scripts` is not an extension; X23 is maintainer-only (plan's migration table).
- **Orchestrator** (after S-SC and S-PM land): add `rate_limited` and `token_scopes` to
  `OneDefinition.MOVED['sanduq_gh.py']` in `extensions/scripts/tests/test_sanduq_remote.py` (S-SH can do it on
  request); not added now because `scope.py` and `project_sync.py` still define them.
