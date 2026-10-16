#!/usr/bin/env python3
"""Single hook entry for Spec Kit's event dispatcher: `dispatch.py` with the host JSON on stdin.

Spec Kit resolves an event's `command` to a template and runs its `scripts:` line with the payload on stdin, but it does
not pass the event name on to that script. This wrapper takes the name from the payload's `hook_event_name` (Claude
`PostToolUse`, Codex `post_tool_use` and so on), maps it to the snake_case name `scripts/hook.py` expects and hands over.
An unknown or missing name goes through as an empty event, which `hook.py` handles on its full path. Standard library
only; never prints, never raises, always exits 0."""
import io
import os
import re
import sys

EVENTS = ('session_start', 'pre_tool_use', 'post_tool_use', 'stop', 'session_end')


def event_name(raw):
    match = re.search(r'"hook_event_name"\s*:\s*"([A-Za-z_-]{1,40})"', raw or '')
    if not match:
        return ''
    name = re.sub(r'(?<!^)(?=[A-Z])', '_', match.group(1)).lower().replace('-', '_')
    return name if name in EVENTS else ''


def main():
    raw = '' if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
    here = os.path.dirname(os.path.abspath(__file__))
    entry = os.path.join(os.path.dirname(here), 'scripts', 'hook.py')
    import importlib.util
    spec = importlib.util.spec_from_file_location('progress_hook_entry', entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.stdin = io.StringIO(raw)
    return module.main(['hook.py', event_name(raw)])


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BaseException:  # the host must never see a failure from an automatic hook
        sys.exit(0)
