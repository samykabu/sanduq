"""Link-safe, bounded log appends using only `os`, `stat` and `time`, so the fast hook entry can share the exact rules
of the main diagnostics writer (`util.diag`) without importing anything heavy."""
import os
import stat
import time

DIAG_LIMIT = 256 * 1024
LINK_TAGS = (0xA000000C, 0xA0000003)  # Windows symlink and junction (mount point) reparse tags


def is_link(path):
    """True for a symbolic link or a Windows junction. Other reparse points (cloud placeholders) are ordinary files."""
    try:
        info = os.lstat(str(path))
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, 'st_file_attributes', 0) & 0x400) and getattr(info, 'st_reparse_tag', 0) in LINK_TAGS


def append_line(path, line):
    """Append one line to a log that is bounded (rotate at 256 KB, keep one) and never reached through a link.
    Returns False, writing nothing, when the target is a link. Raises OSError like `open`."""
    path = str(path)
    if is_link(path) or is_link(os.path.dirname(path)):
        return False
    try:
        if os.path.getsize(path) > DIAG_LIMIT:
            os.replace(path, path + '.1')
    except OSError:
        pass
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(line + '\n')
    return True


def stamp(now=None):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() if now is None else now))
