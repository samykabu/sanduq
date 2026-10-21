#!/usr/bin/env python3
"""Time shard units in CI and rebuild shard_weights.json from those times (stdlib only).

Usage:
    shard_times.py run NAME...                      # as `python -m unittest -q NAME...`
    shard_times.py rebuild --source TEXT LOG...     # rewrites .github/scripts/shard_weights.json

`run` keeps unittest's tests, output and exit code, and prints one `shard-unit-seconds <name> <seconds>` line per
name (a module for workflow, module.Class for memory). Each name runs as its own top-level suite, so its class
fixtures count towards it. `rebuild` reads those lines from downloaded job logs (`gh run view <id> --log`),
averages a unit seen more than once, and replaces each suite's table with the measured units; a suite with no
measured unit keeps its table.
"""
import argparse
import json
import os
import re
import sys
import time
import unittest
from pathlib import Path

PREFIX = "shard-unit-seconds"
LINE = re.compile(rf"{PREFIX} (\S+) (\d+(?:\.\d+)?)\s*$")


class TimedSuite(unittest.TestSuite):
    def __init__(self, named):
        super().__init__(suite for _, suite in named)
        self.names = [name for name, _ in named]

    def run(self, result, debug=False):
        lines = []
        for name, suite in zip(self.names, list(self)):
            start = time.perf_counter()
            suite.run(result)
            # The unit's top-level run already tore its class down; without this the next unit tears it down again.
            result._previousTestClass = None
            lines.append(f"{PREFIX} {name} {time.perf_counter() - start:.2f}")
        print("\n".join(lines), flush=True)
        return result


class TimedLoader(unittest.TestLoader):
    def loadTestsFromNames(self, names, module=None):
        return TimedSuite([(name, self.loadTestsFromName(name, module)) for name in names])


def read_times(paths):
    """{unit: mean seconds} over every timing line in the given logs."""
    seen = {}
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            match = LINE.search(line)
            if match:
                seen.setdefault(match[1], []).append(float(match[2]))
    return {unit: sum(values) / len(values) for unit, values in seen.items()}


def rebuild(times, table, source):
    """Return `table` with each sharded suite's units replaced by their measured seconds."""
    import ci_matrix
    table = dict(table, source=source)
    for suite in ci_matrix.WINDOWS_SHARDS:
        units = ci_matrix.shard_units(suite)
        measured = {unit: round(times[unit], 1) for unit in sorted(times) if unit in units}
        if measured:
            table[suite] = measured
    return table


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        sys.path[0] = os.getcwd()  # import path as under `python -m unittest`
        unittest.main(module=None, argv=[sys.argv[0], "-q", *argv[1:]], testLoader=TimedLoader())
    p = argparse.ArgumentParser(description="Rebuild shard_weights.json from shard-unit-seconds lines.")
    p.add_argument("command", choices=["rebuild"])
    p.add_argument("--source", required=True, help="which CI runs the logs come from, for the table's source key")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "shard_weights.json")
    p.add_argument("logs", nargs="+")
    a = p.parse_args(argv)
    times = read_times(a.logs)
    if not times:
        print(f"no '{PREFIX}' lines in {', '.join(a.logs)}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    old = json.loads(a.out.read_text(encoding="utf-8")) if a.out.is_file() else {}
    a.out.write_text(json.dumps(rebuild(times, old, a.source), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
