"""Regression checks for check_docs: command prefixes, banned terms, internal links, hooks drift."""
import re
from pathlib import Path
from unittest.mock import patch

import check_docs

read_text = Path.read_text


def fails_with(target, content, expected):
    """check() must fail and mention `expected` when `target` reads as `content`."""
    with patch.object(Path, 'read_text', lambda p, *a, **kw: content if p == target else read_text(p, *a, **kw)):
        try:
            check_docs.check()
        except SystemExit as failure:
            assert expected in str(failure), (expected, str(failure)[:500])
        else:
            raise AssertionError(f'check_docs accepted: {expected}')


# A longer command must not satisfy a missing command.
for target, command, longer in (
    (check_docs.COMMANDS_PAGE, '$speckit-scope-plan', '$speckit-scope-plan-guard'),
    (check_docs.LIFECYCLE_PAGE, '$speckit-tasks', '$speckit-taskstoissues'),
):
    content = read_text(target, encoding='utf-8')
    assert longer in content
    content = re.sub(re.escape(command) + r'(?![\w-])', '', content)
    expected = command if target == check_docs.COMMANDS_PAGE else command.lstrip('$').replace('-', '.')
    fails_with(target, content, expected)

guide = check_docs.DOCS / 'style-guide.md'
original = read_text(guide, encoding='utf-8')
# A banned word in prose fails, and a user page must not link into docs/internal.
fails_with(guide, original + '\nYou simply run it.\n', 'banned term "simply"')
fails_with(guide, original + '\n[record](internal/workflow-pilot-review.md)\n', 'links to docs/internal')
hooks = read_text(check_docs.HOOKS_PAGE, encoding='utf-8')
fails_with(check_docs.HOOKS_PAGE, hooks.replace('| mandatory |', '| optional |', 1), 'hooks.md is stale')
print('check_docs regression checks passed.')
