"""Read durable archived feature reservations from the specs root."""
import argparse
import json
from pathlib import Path
import re
import sys


def reservations(specs: Path) -> tuple[int, set[int]]:
    path = specs / ".archive-index.json"
    if not path.exists():
        return 0, set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("archived"), dict):
        raise ValueError("Malformed archive registry")
    numbers = set()
    for name in data["archived"]:
        match = re.fullmatch(r"specs/(\d{3,})-[a-zA-Z0-9-]+", name)
        if match and not re.match(r"specs/\d{8}-\d{6}-", name):
            numbers.add(int(match.group(1)))
    floor = data["high_water"]
    if type(floor) is not int or floor < max(numbers, default=0):
        raise ValueError("Invalid archive high-water mark")
    return floor, numbers


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("specs")
    parser.add_argument("--number", type=int)
    args = parser.parse_args()
    try:
        floor, numbers = reservations(Path(args.specs))
        if args.number is not None and args.number in numbers:
            raise ValueError(f"Feature number {args.number} was already archived; choose a new number above {floor}")
        print(floor)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
