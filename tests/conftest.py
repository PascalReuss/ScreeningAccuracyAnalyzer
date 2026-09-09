import json
import pathlib

import pytest

from config import Config

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(
        api_key="test-key",
        base_url="https://api.example.test/dev/v1",
        cache_dir=str(tmp_path / "cache"),
        max_retries=3,
    )


@pytest.fixture
def load_fixture():
    def _load(name: str):
        return json.loads((FIXTURES / name).read_text("utf-8"))

    return _load
