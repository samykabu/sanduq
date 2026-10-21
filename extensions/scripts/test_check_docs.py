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
# Release facts: Workflow pins, extension counts, the add-all block and root CHANGELOG headings.
deps = read_text(check_docs.DEPENDENCIES, encoding='utf-8')
fails_with(check_docs.DEPENDENCIES, deps.replace('"pr": "', '"pr": "0.0.1-', 1), 'required.pr pins 0.0.1-')
glossary = check_docs.DOCS / 'reference/glossary.md'
fails_with(glossary, read_text(glossary, encoding='utf-8') + '\nSanduq ships eight extensions.\n', 'says eight extensions')
readme = check_docs.ROOT / 'README.md'
fails_with(readme, read_text(readme, encoding='utf-8').replace('Spec_Kit-9_extensions', 'Spec_Kit-8_extensions'),
           'says 8 extensions')
install = read_text(check_docs.INSTALL_PAGE, encoding='utf-8')
fails_with(check_docs.INSTALL_PAGE, re.sub(r'specify extension add progress[^\n]*\n', '', install, count=1), "missing ['progress']")
changelog = read_text(check_docs.CHANGELOG, encoding='utf-8')
first = changelog.index('\n## ') + 1
fails_with(check_docs.CHANGELOG, changelog[:first] + '## 2026-10-19 — Workflow 1.14.0 (pending release)\n\n' + changelog[first:],
           'catalog.json already lists Workflow 1.14.0')
fails_with(check_docs.CHANGELOG, changelog[:first] + '## Undated entry\n\n' + changelog[first:], 'has no YYYY-MM-DD date')
fails_with(check_docs.CHANGELOG, '# Changelog\n\n## 2026-10-20 — Workflow 9.0.0\n\n' + changelog.split('\n', 2)[2],
           'preamble must come before the first entry')
# Version drift (X18): the Requires row, the README's "describes X.Y.Z", old "(unreleased)" headings.
page = check_docs.DOCS / 'extensions/assure.md'
text = read_text(page, encoding='utf-8')
assert '| Requires | Illustrate 2.x' in text
fails_with(page, text.replace('| Requires | Illustrate 2.x', '| Requires | Illustrate 2.5', 1),
           'Requires row says Illustrate 2.5; extension.yml requires illustrate >=2.0.0')
fails_with(page, text.replace('| Requires | Illustrate 2.x', '| Requires | Nothing', 1),
           'Requires row does not name illustrate')
pr_readme = check_docs.ROOT / 'extensions/pr/README.md'
fails_with(pr_readme, read_text(pr_readme, encoding='utf-8') + '\nThis README describes PR 4.0.0.\n',
           'describes 4.0.0; extension.yml has')
pr_changelog = check_docs.ROOT / 'extensions/pr/CHANGELOG.md'
history = read_text(pr_changelog, encoding='utf-8')
fails_with(pr_changelog, history + '\n## 0.0.1 (unreleased)\n\n- Old.\n', '"0.0.1 (unreleased)" is marked unreleased below')
fails_with(pr_changelog, history + '\n## Unreleased\n\n- Old.\n', '"Unreleased" is marked unreleased below')
# A streams' "## Unreleased" heading above the manifest version's entry is allowed.
manifests = [check_docs.yaml.safe_load(p.read_text(encoding='utf-8'))
             for p in sorted(check_docs.ROOT.glob('extensions/*/extension.yml'))]
on_top = history.replace('\n## ', '\n## Unreleased\n\n- Next.\n\n## ', 1)
with patch.object(Path, 'read_text', lambda p, *a, **kw: on_top if p == pr_changelog else read_text(p, *a, **kw)):
    drift = check_docs.version_drift(manifests)
assert not [e for e in drift if e.startswith(str(pr_changelog.relative_to(check_docs.ROOT)))], drift
print('check_docs regression checks passed.')
