"""Patch a runtime name everywhere the runtime looks it up.

The runtime is `workflow.py` plus the modules it re-exports (W9). Each module binds the names it imports, so
`patch.object(w, name)` alone misses callers in the other modules. `patch_runtime` patches every runtime module
that binds the same object, which is what a patch on the single-file `workflow.py` did, and returns one mock.
"""
import contextlib
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workflow

MODULES = ('workflow', 'wf_core', 'wf_identity', 'wf_fingerprints', 'wf_policy', 'wf_health', 'wf_receipts')


@contextlib.contextmanager
def patch_runtime(name, new=mock.DEFAULT, **kwargs):
    real = getattr(workflow, name)
    modules = [sys.modules[m] for m in MODULES if getattr(sys.modules[m], name, None) is real]
    with contextlib.ExitStack() as stack:
        patched = stack.enter_context(mock.patch.object(modules[0], name, new, **kwargs))
        for module in modules[1:]:
            stack.enter_context(mock.patch.object(module, name, patched))
        yield patched
