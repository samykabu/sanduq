"""Atomic writers for report.json and data.js (a script file, so the view works from file://)."""
import json

from .util import atomic_write

PREFIX = 'window.__SANDUQ_PROGRESS__ = '


def _script(document):
    # ensure_ascii escapes U+2028/2029 and every non-ASCII character; '</' cannot end a script file but is escaped anyway.
    body = json.dumps(document, ensure_ascii=True, separators=(',', ':')).replace('</', '<\\/')
    return f'{PREFIX}{body};\n'


def write(ctx, report, display=None, layout=None):
    """report.json holds the projection (v3). data.js feeds the browser: the same document, or `display` (the v2
    compatibility document) when the theme layout is classic. The layout in force rides along as `ui.layout`, so an open
    page picks the right renderer with each data revision instead of keeping the one it loaded with."""
    atomic_write(ctx.report, json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    shown = display if display is not None else report
    atomic_write(ctx.data_js, _script(dict(shown, ui={'layout': layout}) if layout else shown))


def patch_collection(ctx, rev, **fields):
    """Patch `rev` and the collection flags into report.json and data.js without rebuilding anything. Raises ValueError,
    TypeError or OSError when either file is missing or not the expected shape; nothing is written then."""
    report = json.loads(ctx.report.read_text(encoding='utf-8'))
    text = ctx.data_js.read_text(encoding='utf-8')
    shown = json.loads(text[len(PREFIX):].rstrip().rstrip(';')) if text.startswith(PREFIX) else None
    if not isinstance(report, dict) or not isinstance(shown, dict):
        raise ValueError('unexpected shape')
    for doc in (report, shown):
        if not isinstance(doc.get('collection'), dict):
            raise ValueError('no collection')
    for doc in (report, shown):
        doc['rev'] = rev
        doc['collection'].update(fields)
    atomic_write(ctx.report, json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    atomic_write(ctx.data_js, _script(shown))
