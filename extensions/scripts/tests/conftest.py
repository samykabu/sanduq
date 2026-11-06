"""pytest only (unittest never imports this): `pytest -n <N> --dist loadgroup` keeps each class below on one
worker, so its expensive setUpClass runs once instead of once per worker."""
import pytest

GROUPED = {'BenchmarkFrontHalfTests'}


def pytest_collection_modifyitems(items):
    for item in items:
        if item.cls is not None and item.cls.__name__ in GROUPED:
            item.add_marker(pytest.mark.xdist_group(item.cls.__name__))
