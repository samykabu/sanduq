#!/usr/bin/env python3
"""Build reproducible extension archives including canonical bundled presets."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRESETS = {'workflow': ('workflow', 'scope-gate', 'scope-brainstorm'),
           'scope': ('scope-gate', 'scope-brainstorm')}
EXCLUDE = {'.git', '__pycache__', 'node_modules', '.specify', '.specify-dev', 'tests', 'test', 'runs',
           # Caches and reports a local test or lint run leaves behind, never package content.
           '.pytest_cache', '.mypy_cache', '.ruff_cache', '.hypothesis', '.tox', '.nox', 'htmlcov',
           '.coverage', '.nyc_output', 'coverage'}
# The one list of source files and folders (`<extension>/<path>`) that stay in the repository: nothing a
# consumer runs or an agent route names. A README link to one of them is rewritten to its GitHub URL.
EXCLUDE_PATHS = (
    # Progress: human reference docs (verbs.md calls them "not needed to run a verb") and their screenshots.
    'progress/docs',
    # Illustrate: preview PNGs and gallery variants nothing names, and the icon builder with its sources.
    'illustrate/skill/assets/technical-color/process-flow/examples/images',
    'illustrate/skill/assets/index-variation-1.html',
    'illustrate/skill/assets/index-variation-2.html',
    'illustrate/skill/scripts/vendor',
    'illustrate/skill/scripts/build-icons.py',
    'illustrate/skill/scripts/fix-mojibake.py',
    # Workflow: delegate-task's READMEs and their images; delegation needs SKILL.md, the .mjs drivers and contracts/.
    'workflow/assets/delegate-task/README.md',
    'workflow/assets/delegate-task/README.ar.md',
    'workflow/assets/delegate-task/assets',
)
BLOB = 'https://github.com/samykabu/sanduq/blob/main/extensions/'
# SEC-13: sections of the root THIRD_PARTY_NOTICES.md each vendoring package ships as its own notices file.
NOTICES = {'illustrate': ('Illustrate skill', 'Bundled icon sources'),
           'progress': ('Progress, Delegate Task and User Manual skills',),
           'workflow': ('Progress, Delegate Task and User Manual skills',),
           'user-manual': ('Progress, Delegate Task and User Manual skills',)}
SHARED = {'sanduq_remote.py': ('workflow', 'project', 'scope'), 'sanduq_pr_lint.py': ('pr', 'workflow'),
          'sanduq_gh.py': ('scope', 'workflow', 'project', 'pr'), 'sanduq_fs.py': ('workflow',)}


def excluded(name):
    # Each extension's own CHANGELOG.md stays in the repository too (X20); its README links go to GitHub.
    return re.fullmatch(r'[^/]+/CHANGELOG\.md', name) is not None or \
        any(name == path or name.startswith(path + '/') for path in EXCLUDE_PATHS)


def notices(extension, root=ROOT):
    """The package's THIRD_PARTY_NOTICES.md built from its sections of the root file, repository links made absolute."""
    blocks = (root / 'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8').split('\n## ')[1:]
    sections = {block.split('\n', 1)[0]: '## ' + block.rstrip() + '\n' for block in blocks}
    text = ('# Third-party notices\n\nThe `LICENSE` file in this package (MIT) covers Sanduq\'s original contributions. '
            'The material below remains under its upstream license.\n\n' + '\n'.join(sections[name] for name in NOTICES[extension]))
    return re.sub(r'\]\((?!https?:|#)([^)]+)\)', r'](https://github.com/samykabu/sanduq/blob/main/\1)', text).encode('utf-8')


def package_files(extension, root=ROOT):
    """{archive member: bytes} of everything the package ships, before `package-inventory.json`."""
    source = root / 'extensions' / extension
    if not source.is_dir() or not (source / 'extension.yml').is_file() or source.parent != root / 'extensions':
        raise ValueError('Unknown extension: ' + extension)
    files = {}
    def include(directory, prefix):
        for path in directory.rglob('*'):
            relative = path.relative_to(directory)
            if path.is_file() and not any(part in EXCLUDE for part in relative.parts) and path.suffix not in ('.pyc', '.pyo'):
                name = (Path(extension) / prefix / relative).as_posix()
                # Adapted and internal skill entrypoints are stored as SKILL.ext.md so `npx skills`
                # cannot install them from this repository; the package restores the real name.
                files[name[:-len('SKILL.ext.md')] + 'SKILL.md' if name.endswith('/SKILL.ext.md') else name] = path.read_bytes()
    include(source, Path())
    files = {name: value for name, value in files.items() if not excluded(name)}
    readme = extension + '/README.md'
    if readme in files:
        text = files[readme].decode('utf-8')
        for path in EXCLUDE_PATHS + (extension + '/CHANGELOG.md',):
            if path.startswith(extension + '/'):
                text = re.sub(r'\]\(' + re.escape(path[len(extension) + 1:]) + r'(?=[/)#])', '](' + BLOB + path, text)
        files[readme] = re.sub(r'(\]\([^)\s]*/)SKILL\.ext\.md(?=[)#])', r'\1SKILL.md', text).encode('utf-8')
    # Every package carries its licence (SEC-13): the extension's own, else the repository's.
    if extension + '/LICENSE' not in files and (root / 'LICENSE').is_file():
        files[extension + '/LICENSE'] = (root / 'LICENSE').read_bytes()
    if extension in NOTICES and (root / 'THIRD_PARTY_NOTICES.md').is_file():
        files[extension + '/THIRD_PARTY_NOTICES.md'] = notices(extension, root)
    for preset in PRESETS.get(extension, ()):
        include(root / 'presets' / preset, Path('presets') / preset)
    shared = root / 'extensions/scripts/shared/sanduq_freshness.py'
    if extension in ('assure', 'user-manual') and shared.exists():
        files[extension + '/scripts/sanduq_freshness.py'] = shared.read_bytes()
        files[extension + '/scripts/sanduq_hash.py'] = (root / 'extensions/workflow/scripts/sanduq_hash.py').read_bytes()
    # assure and user-manual render shipped CI assets too; workflow already
    # carries the module in its own scripts directory.
    ci = root / 'extensions/workflow/scripts/sanduq_ci.py'
    if extension in ('assure', 'user-manual') and ci.exists():
        files[extension + '/scripts/sanduq_ci.py'] = ci.read_bytes()
    # pr, assure and user-manual commands all call `deps.py ensure <id>` instead of repeating the
    # dependency-check instructions verbatim (B9); ship the one canonical implementation to each.
    deps_script = root / 'extensions/scripts/shared/deps.py'
    if extension in ('pr', 'assure', 'user-manual') and deps_script.exists():
        files[extension + '/scripts/deps.py'] = deps_script.read_bytes()
    if extension in ('memory', 'workflow'):
        helpers = ['check_inputs.py', 'bounded_json.py']
        if extension == 'workflow':
            helpers.append('evidence_snapshot.py')
        for helper in helpers:
            files[extension + '/scripts/' + helper] = (root / 'extensions/scripts/shared' / helper).read_bytes()
    # One source each, shipped next to its consumers' scripts: the GitHub remote reading (D4), the PR
    # closing-reference lint (PM21) and the `gh` transport (SC8). Fixture roots without the shared folder skip them.
    for helper, consumers in SHARED.items():
        shared_file = root / 'extensions/scripts/shared' / helper
        if extension in consumers and shared_file.exists():
            files[extension + '/scripts/' + helper] = shared_file.read_bytes()
    # Workflow's decisions reach Scope's Project transport without loading scope.py (SC8); Scope ships it natively.
    scope_github = root / 'extensions/scope/scripts/sanduq_scope_github.py'
    if extension == 'workflow' and scope_github.exists():
        files['workflow/scripts/sanduq_scope_github.py'] = scope_github.read_bytes()
    return files


def package(extension, output=None, root=ROOT):
    files = package_files(extension, root)
    inventory = {name: hashlib.sha256(value).hexdigest() for name, value in sorted(files.items())}
    files[extension + '/package-inventory.json'] = (json.dumps(inventory, indent=2) + '\n').encode()
    output = output or root / 'dist' / (extension + '.zip')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            item.external_attr = (0o755 if name.endswith('.sh') else 0o644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, content)
    return {'archive': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'files': len(files)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('extension')
    args = parser.parse_args()
    print(json.dumps(package(args.extension), indent=2))
