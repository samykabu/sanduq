"""Portable UTF-8 text hashing; SQL and explicitly binary files remain byte exact."""
import subprocess
from pathlib import Path


def text_attributes(root, paths):
    paths = sorted(set(paths))
    if not paths:
        return {}
    result = subprocess.run(['git', 'check-attr', '-z', '--stdin', 'text'], cwd=root,
                            input='\0'.join(paths).encode('utf-8') + b'\0', capture_output=True)
    if result.returncode:
        raise ValueError('Cannot inspect Git text attributes: ' + result.stderr.decode('utf-8', 'replace'))
    values = result.stdout.decode('utf-8').split('\0')
    return {values[i]: values[i + 2] for i in range(0, len(values) - 1, 3)}


def portable_content(path, content, text_attribute=None):
    # SQL can contain byte-sensitive definitions; never normalize it implicitly.
    # -text also takes precedence over a familiar filename extension.
    if Path(path).suffix.lower() == '.sql' or text_attribute == 'unset' or b'\0' in content:
        return content
    try:
        content.decode('utf-8')
    except UnicodeDecodeError:
        return content
    # Do not normalize lone CR: it can be meaningful data, not checkout conversion.
    return content.replace(b'\r\n', b'\n')
