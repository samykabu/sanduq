#!/usr/bin/env python3
"""Build reproducible extension archives including canonical bundled presets."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRESETS = {'workflow': ('workflow', 'scope-gate', 'scope-brainstorm'),
           'scope': ('scope-gate', 'scope-brainstorm')}
EXCLUDE = {'.git', '__pycache__', 'node_modules', '.specify', '.specify-dev', 'tests', 'test', 'runs',
           # Caches and reports a local test or lint run leaves behind, never package content.
           '.pytest_cache', '.mypy_cache', '.ruff_cache', '.hypothesis', '.tox', '.nox', 'htmlcov',
           '.coverage', '.nyc_output', 'coverage'}


def package(extension, output=None, root=ROOT):
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
