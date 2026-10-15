"""Atomic writers for report.json and data.js (a script file, so the view works from file://)."""
import json

from .util import atomic_write


def write(ctx, report):
    atomic_write(ctx.report, json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    # ensure_ascii escapes U+2028/2029 and every non-ASCII character; '</' cannot end a script file but is escaped anyway.
    body = json.dumps(report, ensure_ascii=True, separators=(',', ':')).replace('</', '<\\/')
    atomic_write(ctx.data_js, f'window.__SANDUQ_PROGRESS__ = {body};\n')
