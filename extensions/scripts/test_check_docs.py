"""Regression checks for check_docs: command prefixes, banned terms, internal links, hooks drift."""
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import check_docs

read_text = Path.read_text



def reading(changes):
    """Path.read_text patched so each path in `changes` reads as its given content."""
    return patch.object(Path, 'read_text', lambda p, *a, **kw: changes[p] if p in changes else read_text(p, *a, **kw))


def fails_with(target, content, expected, errors):
    """`errors()` must name `expected` when `target` reads as `content`."""
    with reading({target: content}):
        found = '\n'.join(errors())
    assert expected in found, (expected, found[:500])


manifests = [check_docs.yaml.safe_load(p.read_text(encoding='utf-8'))
             for p in sorted(check_docs.ROOT.glob('extensions/*/extension.yml'))]


def facts():
    return check_docs.release_facts(manifests, {p: p.read_text(encoding='utf-8') for p in check_docs.GUIDES})


def drift():
    return check_docs.version_drift(manifests)


def check_fails_with(changes, expected):
    """check() must fail and name every `expected` when each path in `changes` reads as its content."""
    with reading(changes):
        try:
            check_docs.check()
        except SystemExit as failure:
            missed = [e for e in expected if e not in str(failure)]
            assert not missed, (missed, str(failure)[:500])
        else:
            raise AssertionError(f'check_docs accepted: {expected}')


# One full check() pass with the rules that live in check() itself broken at once; each must be reported.
broken, expected = {}, []
# A longer command must not satisfy a missing command.
for target, command, longer in (
    (check_docs.COMMANDS_PAGE, '/speckit-workflow-scope-plan', '/speckit-workflow-scope-plan-guard'),
    (check_docs.LIFECYCLE_PAGE, '/speckit-tasks', '/speckit-taskstoissues'),
):
    content = read_text(target, encoding='utf-8')
    assert longer in content
    broken[target] = re.sub(re.escape(command) + r'(?![\w-])', '', content)
    expected.append(command if target == check_docs.COMMANDS_PAGE else command.lstrip('/').replace('-', '.'))
# A banned word in prose fails, and a link to a missing anchor on a kept page fails.
guide = check_docs.DOCS / 'style-guide.md'
broken[guide] = read_text(guide, encoding='utf-8') + '\nYou simply run it.\n[record](reference/compatibility.md#no-such-anchor)\n'
expected += ['banned term "simply"', 'missing anchor']
hooks = read_text(check_docs.HOOKS_PAGE, encoding='utf-8')
broken[check_docs.HOOKS_PAGE] = hooks.replace('| mandatory |', '| optional |', 1)
check_fails_with(broken, expected + ['hooks.md is stale'])
# The generated errors page alone (hooks.md current this time), without the slow tree scan check() repeats.
errors_page = read_text(check_docs.ERRORS_PAGE, encoding='utf-8')
with patch.object(check_docs, 'history_references', return_value=[]):
    check_fails_with({check_docs.ERRORS_PAGE: errors_page.replace('| `WORKFLOW_INIT_REQUIRED` |',
                                                                 '| `WORKFLOW_INIT_REQUIRED` | edited |', 1)},
                     ['errors.md is stale'])
# Release facts: Workflow pins, extension counts, the add-all block and root CHANGELOG headings.
deps = read_text(check_docs.DEPENDENCIES, encoding='utf-8')
fails_with(check_docs.DEPENDENCIES, deps.replace('"pr": "', '"pr": "0.0.1-', 1), 'required.pr pins 0.0.1-', facts)
glossary = check_docs.DOCS / 'reference/glossary.md'
fails_with(glossary, read_text(glossary, encoding='utf-8') + '\nSanduq ships eight extensions.\n', 'says eight extensions',
           facts)
readme = check_docs.ROOT / 'README.md'
fails_with(readme, read_text(readme, encoding='utf-8').replace('Spec_Kit-9_extensions', 'Spec_Kit-8_extensions'),
           'says 8 extensions', facts)
install = read_text(check_docs.INSTALL_PAGE, encoding='utf-8')
fails_with(check_docs.INSTALL_PAGE, re.sub(r'specify extension add progress[^\n]*\n', '', install, count=1),
           "missing ['progress']", facts)
changelog = read_text(check_docs.CHANGELOG, encoding='utf-8')
first = changelog.index('\n## ') + 1
fails_with(check_docs.CHANGELOG, changelog[:first] + '## 2026-10-19 — Workflow 1.14.0 (pending release)\n\n' + changelog[first:],
           'catalog.json already lists Workflow 1.14.0', facts)
fails_with(check_docs.CHANGELOG, changelog[:first] + '## Undated entry\n\n' + changelog[first:], 'has no YYYY-MM-DD date',
           facts)
fails_with(check_docs.CHANGELOG, '# Changelog\n\n## 2026-10-20 — Workflow 9.0.0\n\n' + changelog.split('\n', 2)[2],
           'preamble must come before the first entry', facts)
# Version drift (X18): the Requires row, the README's "describes X.Y.Z", old "(unreleased)" headings.
page = check_docs.DOCS / 'extensions/assure.md'
text = read_text(page, encoding='utf-8')
assert '| Requires | Illustrate 2.x' in text
fails_with(page, text.replace('| Requires | Illustrate 2.x', '| Requires | Illustrate 2.5', 1),
           'Requires row says Illustrate 2.5; extension.yml requires illustrate >=2.0.0', drift)
fails_with(page, text.replace('| Requires | Illustrate 2.x', '| Requires | Nothing', 1),
           'Requires row does not name illustrate', drift)
pr_readme = check_docs.ROOT / 'extensions/pr/README.md'
fails_with(pr_readme, read_text(pr_readme, encoding='utf-8') + '\nThis README describes PR 4.0.0.\n',
           'describes 4.0.0; extension.yml has', drift)
pr_changelog = check_docs.ROOT / 'extensions/pr/CHANGELOG.md'
history = read_text(pr_changelog, encoding='utf-8')
fails_with(pr_changelog, history + '\n## 0.0.1 (unreleased)\n\n- Old.\n', '"0.0.1 (unreleased)" is marked unreleased below',
           drift)
fails_with(pr_changelog, history + '\n## Unreleased\n\n- Old.\n', '"Unreleased" is marked unreleased below', drift)
# A streams' "## Unreleased" heading above the manifest version's entry is allowed.
on_top = history.replace('\n## ', '\n## Unreleased\n\n- Next.\n\n## ', 1)
with reading({pr_changelog: on_top}):
    found = drift()
assert not [e for e in found if e.startswith(str(pr_changelog.relative_to(check_docs.ROOT)))], found
# Review history: a comment or docstring citing a round, finding or reviewer id fails, as does a round- or
# review-named test module; a stated rule and a string the script prints pass.
with tempfile.TemporaryDirectory() as folder:
    tree = Path(folder)
    (tree / 'extensions/x/scripts').mkdir(parents=True)
    (tree / 'extensions/x/tests').mkdir(parents=True)
    (tree / 'extensions/x/scripts/a.py').write_text(
        '"""Doc line.\n\nKeeps the lock (round 3, finding 2)."""\n# SAMY-03: keep the lock\nx = 1  # a claim stays live (B12)\n'
        '# F6: hash the text\nprint("## Return and wait rules (F2)")\n# A claim keeps its lock while its pid lives.\n',
        encoding='utf-8')
    (tree / 'extensions/x/scripts/b.sh').write_text('#!/bin/sh\n# review round 1: quote the path\necho ok\n', encoding='utf-8')
    for name in ('test_round4', 'test_review_fixes', 'test_scope_round5', 'test_scope_cancel'):
        (tree / f'extensions/x/tests/{name}.py').write_text('', encoding='utf-8')
    found = check_docs.history_references(tree)
    lines = sorted(e.split(': ', 1)[0] for e in found)
    assert lines == ['extensions/x/scripts/a.py:3', 'extensions/x/scripts/a.py:4', 'extensions/x/scripts/a.py:5',
                     'extensions/x/scripts/a.py:6', 'extensions/x/scripts/b.sh:2', 'extensions/x/tests/test_review_fixes.py',
                     'extensions/x/tests/test_round4.py', 'extensions/x/tests/test_scope_round5.py'], found
assert check_docs.history_references() == [], check_docs.history_references()
print('check_docs regression checks passed.')
