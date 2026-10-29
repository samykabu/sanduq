# SPDX-License-Identifier: MIT
"""Whole-record JSON pages with byte-exact limits and content-bound cursors."""
import hashlib
import json


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def page(records, *, view, max_bytes=16384, cursor=None):
    if type(max_bytes) is not int or not 512 <= max_bytes <= 1048576:
        raise ValueError('max-bytes must be between 512 and 1048576')
    revision = hashlib.sha256(encode(records)).hexdigest()
    offset = 0
    if cursor:
        token, separator, number = cursor.partition(':')
        if token != revision or not separator or not number.isdecimal():
            raise ValueError('Cursor does not match this projection; restart inspection')
        offset = int(number)
        if offset > len(records):
            raise ValueError('Cursor is outside this projection')
    result = {'success': True, 'schema': 'sanduq.inspection.v1', 'view': view, 'records': [], 'total': len(records),
              'returned': 0, 'offset': offset, 'next_cursor': None, 'truncated': False,
              'oversized_record': None, 'max_bytes': max_bytes}
    index = offset
    while index < len(records):
        trial = {**result, 'records': result['records'] + [records[index]],
                 'returned': result['returned'] + 1, 'truncated': index + 1 < len(records),
                 'next_cursor': f'{revision}:{index + 1}' if index + 1 < len(records) else None}
        if len(encode(trial)) + 1 > max_bytes:
            result['truncated'] = True
            result['next_cursor'] = f'{revision}:{index}'
            if not result['records']:
                # Keep the whole record available at a larger budget; never silently skip it.
                result['oversized_record'] = {'index': index, 'bytes': len(encode(records[index]))}
            break
        result = trial
        index += 1
    if len(encode(result)) + 1 > max_bytes:
        raise ValueError('Byte budget cannot hold projection metadata')
    return result
