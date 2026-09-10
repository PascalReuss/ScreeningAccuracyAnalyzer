import pytest

from config import Config


def test_int_env_rejects_non_integer(monkeypatch):
    monkeypatch.setenv("SCREENING_DEMO", "1")
    monkeypatch.setenv("SCREENING_CACHE_TTL", "not-a-number")
    with pytest.raises(RuntimeError, match="SCREENING_CACHE_TTL must be an integer"):
        Config.from_env()


def test_int_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SCREENING_DEMO", "1")
    monkeypatch.delenv("SCREENING_CACHE_TTL", raising=False)
    assert Config.from_env().cache_ttl_seconds == 900


def test_missing_api_key_without_demo_raises(monkeypatch):
    monkeypatch.delenv("PAULSJOB_API_KEY", raising=False)
    monkeypatch.delenv("SCREENING_DEMO", raising=False)
    with pytest.raises(RuntimeError, match="PAULSJOB_API_KEY is not set"):
        Config.from_env()
