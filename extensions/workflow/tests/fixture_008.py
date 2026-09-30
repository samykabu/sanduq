"""An anonymised copy of a real 1.3.0 checkpoint (a finished feature with 15 receipts).

The fixture keeps the recorded structure: every receipt with its input and
evidence manifests, explicit fingerprints and source fingerprints, lineage,
recoveries, the earlier migration and policy change. Names, URLs, tokens,
session ids and digests are replaced, and every path is renamed segment by
segment while its directory class (feature directory, other features,
`.specify/`, `User-Manual/`, source) is kept, because those classes decide
which inventory a path belongs to. Hashes are real SHA-256 values of the
content `content()` writes, so a materialised fixture passes the gate exactly
as the original did before its last evidence edit.
"""
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / 'fixtures/checkpoint-008-anonymised.json'
FEATURE = 'specs/008-fixture-feature'
ISSUE = 'acme/app#10'
BRANCH = 'fixture-008'
# The evidence path whose editorial change failed the original feature's gate
# (`STALE_RECEIPT: execute`); it is evidence of both execute and review.
AMENDED_EVIDENCE = FEATURE + '/evidence/review-fixes-web.md'


def content(path):
    """Deterministic bytes for a fixture path; structured where the gate parses them."""
    if path == FEATURE + '/scope-source.json':
        return json.dumps({'repo': 'acme/app', 'issue': 10}).encode()
    if path == FEATURE + '/workflow/task-issues.json':
        return json.dumps({'repo': 'acme/app', 'parent': 10, 'feature': FEATURE,
                           'tasks': {'T001': {'number': 11, 'linked': True}}}).encode()
    if path == FEATURE + '/tasks.md':
        return b'- [x] T001 Anonymised fixture task\n'
    return ('anonymised fixture content for ' + path + '\n').encode()


def load():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def paths(state):
    """Every file a receipt fingerprints, explicitly or as source."""
    found = set()
    for receipt in state['receipts'].values():
        found.update(receipt['fingerprints'])
        found.update(receipt.get('source_fingerprints') or {})
    return sorted(found)


def materialise(root, branch=BRANCH):
    """Write the fixture's files and its checkpoint, bound to `root` and `branch`.

    `repo_path` is deliberately left as the *original* machine's absolute
    path -- never `root` -- because this is a real anonymised 1.3.0
    checkpoint, and 1.3.0 checkpoints only ever recorded the path of the
    machine that ran `start`. Leaving it foreign proves the checkpoint loads
    here on its portable identity (established for `root`, which has its
    own remote and history, not by any resemblance to the original path).
    """
    state = load()
    for relative in paths(state):
        target = Path(root) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content(relative))
    state['repo_path'] = '/Users/original-author/workspace/acme-app'
    state['branch'] = branch
    checkpoint = Path(root) / FEATURE / 'workflow/checkpoint.json'
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    return state
