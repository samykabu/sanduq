#!/usr/bin/env python3
"""PostToolUse check for Claude Code and Codex: a written HTML diagram must pass the skill's own checks.

Opt-in: `.specify/workflow.yml` must set `illustrate: {hooks: {self_check: true}}`; otherwise, and
whenever that file is missing, this exits 0 at once. For a Write or Edit whose path ends in `.html`
and whose content contains `<svg`, it runs `self_check.py`, `verify-geometry.py` and
`illustration_theme.py validate` from the installed skill (`skill/scripts/` beside this hook, that is
`.specify/extensions/illustrate/skill/scripts/`) and reports the first failure on stderr with exit 2.
Anything unexpected (no stdin, bad JSON, another tool, no skill) allows: a hook must never break the host.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / 'skill' / 'scripts'
WRITE_TOOLS = ('Write', 'Edit', 'MultiEdit', 'write_file', 'edit_file', 'apply_patch')


def enabled(root):
    policy = root / '.specify' / 'workflow.yml'
    if not policy.is_file():
        return False
    try:
        import yaml
        data = yaml.safe_load(policy.read_text(encoding='utf-8-sig')) or {}
    except Exception:
        return False
    illustrate = data.get('illustrate') if isinstance(data, dict) else None
    hooks = illustrate.get('hooks') if isinstance(illustrate, dict) else None
    return isinstance(hooks, dict) and hooks.get('self_check') is True


def written_diagram(payload, root):
    """The written .html path when the tool wrote one containing <svg, else None."""
    tool_input = payload.get('tool_input')
    if payload.get('tool_name') not in WRITE_TOOLS or not isinstance(tool_input, dict):
        return None
    raw = tool_input.get('file_path') or tool_input.get('path')
    if not isinstance(raw, str) or not raw.lower().endswith('.html'):
        return None
    path = Path(raw)
    path = path if path.is_absolute() else root / path
    try:
        return path if '<svg' in path.read_text(encoding='utf-8', errors='replace') else None
    except OSError:
        return None


def checks(root, path):
    python = sys.executable or 'python'
    return (
        ('self_check.py', [python, str(SCRIPTS / 'self_check.py'), str(path)]),
        ('verify-geometry.py', [python, str(SCRIPTS / 'verify-geometry.py'), str(path)]),
        ('illustration_theme.py validate',
         [python, str(SCRIPTS / 'illustration_theme.py'), '--project-root', str(root), 'validate']),
    )


def first_failure(root, path):
    """`<script>: <first finding>` for the first failing check, or None."""
    for name, argv in checks(root, path):
        run = subprocess.run(argv, capture_output=True, text=True, cwd=str(root))
        if run.returncode == 0:
            continue
        lines = [line.strip() for line in (run.stdout + run.stderr).splitlines() if line.strip()]
        lines = [line for line in lines if not line.startswith(('FAIL ', 'OK ', 'Summary:'))] or lines
        return name + ': ' + (lines[0].lstrip('- ') if lines else 'exit ' + str(run.returncode))
    return None


def main(stdin=sys.stdin, environ=os.environ):
    try:
        payload = json.loads(stdin.read() or '{}')
    except (ValueError, OSError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    root = Path(environ.get('CLAUDE_PROJECT_DIR') or payload.get('cwd') or '.').resolve()
    if not enabled(root) or not SCRIPTS.is_dir():
        return 0
    path = written_diagram(payload, root)
    if path is None:
        return 0
    failure = first_failure(root, path)
    if failure:
        sys.stderr.write('Illustrate self-check: ' + failure + ' (' + str(path) + ')\n')
        return 2
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception:  # never crash the host on unexpected input
        code = 0
    sys.exit(code)
