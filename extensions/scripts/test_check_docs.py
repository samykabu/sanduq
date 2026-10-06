"""Regression check: a longer command must not satisfy a missing command."""
import re
from pathlib import Path
from unittest.mock import patch

import check_docs

read_text = Path.read_text
for guide, command, longer in (
    ('extensions.md', '$speckit-scope-plan', '$speckit-scope-plan-guard'),
    ('skill-guide.md', '$speckit-tasks', '$speckit-taskstoissues'),
):
    target = check_docs.ROOT / 'docs' / guide
    content = read_text(target, encoding='utf-8')
    assert longer in content
    content = re.sub(re.escape(command) + r'(?![\w-])', '', content)
    with patch.object(Path, 'read_text', lambda p, *a, **kw: content if p == target else read_text(p, *a, **kw)):
        try:
            check_docs.check()
        except SystemExit as failure:
            assert command.lstrip('$').replace('-', '.') in str(failure) or command in str(failure)
        else:
            raise AssertionError(f'Missing command accepted: {command}')
print('Command coverage regression checks passed.')
