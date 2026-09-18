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
EXCLUDE = {'.git', '__pycache__', 'node_modules', '.specify', '.specify-dev', 'tests'}


def package(extension, output=None, root=ROOT):
    source = root / 'extensions' / extension
    if not source.is_dir() or not (source / 'extension.yml').is_file() or source.parent != root / 'extensions':
        raise ValueError('Unknown extension: ' + extension)
    files = {}
    def include(directory, prefix):
        for path in directory.rglob('*'):
            relative = path.relative_to(directory)
            if path.is_file() and not any(part in EXCLUDE for part in relative.parts) and path.suffix != '.pyc':
                files[(Path(extension) / prefix / relative).as_posix()] = path.read_bytes()
    include(source, Path())
    for preset in PRESETS.get(extension, ()):
        include(root / 'presets' / preset, Path('presets') / preset)
    shared = root / 'extensions/scripts/shared/sanduq_freshness.py'
    if extension in ('assure', 'user-manual') and shared.exists():
        files[extension + '/scripts/sanduq_freshness.py'] = shared.read_bytes()
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
