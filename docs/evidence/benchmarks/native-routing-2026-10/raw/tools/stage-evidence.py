"""Copy the raw T07 evidence, redacted, into a Sanduq checkout for commit (no git action here).

usage: python stage-evidence.py <sanduq-checkout> [<folder name>]
Target: <checkout>/docs/evidence/benchmarks/<folder>/raw/<run>/... : delegation ledger, lifecycle.jsonl,
checkpoint.json, each external driver result.json/meta.json, session stamps, and the logs/rows/*.json the
table was built from, plus the held-out test and the scripts. Every file is redacted (redact.py) and then
scanned; a deny-list hit exits 1 so nothing private is committed.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from redact import redact

BASE = Path('<sandbox>')
checkout = Path(sys.argv[1])
dest = checkout / 'docs/evidence/benchmarks' / (sys.argv[2] if len(sys.argv) > 2 else 'native-routing-2026-10') / 'raw'
sources = [(p, p.relative_to(BASE / 'evidence')) for p in (BASE / 'evidence').rglob('*') if p.is_file()]
sources += [(p, Path('rows') / p.name) for p in (BASE / 'logs/rows').glob('*.json')]
sources += [(BASE / 'heldout/test_heldout_t07.py', Path('heldout/test_heldout_t07.py')), (BASE / 'issue.md', Path('issue.md'))]
sources += [(p, Path('tools') / p.name) for p in (BASE / 'tools').iterdir() if p.suffix in ('.py', '.sh') and p.name != 'redact.py']
written = []
for src, rel in sources:
    out = dest / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(redact(src.read_text(encoding='utf-8', errors='replace')), encoding='utf-8', newline='\n')
    written.append(str(out))
print(len(written), 'files to', dest)
sys.exit(subprocess.call([sys.executable, str(BASE / 'tools/redact.py'), 'scan', *written]))
