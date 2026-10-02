from pathlib import Path

import pytest

from dct.collectors.backend import FixtureBackend

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def backend() -> FixtureBackend:
    return FixtureBackend.load(FIXTURES / "healthy_rhel.json")
