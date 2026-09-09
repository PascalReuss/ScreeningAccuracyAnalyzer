import pytest
import requests_mock

from screening import api_client
from screening.api_client import ScreeningAPIError, ScreeningClient

SEARCH_URL = "https://api.example.test/dev/v1/recruiting/applications/search-applications"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(api_client.time, "sleep", lambda *_: None)


def test_iter_applications_walks_all_pages(config, load_fixture):
    client = ScreeningClient(config)
    with requests_mock.Mocker() as m:
        m.post(
            SEARCH_URL,
            [
                {"json": load_fixture("applications_search_page1.json")},
                {"json": load_fixture("applications_search_page2.json")},
            ],
        )
        items = list(client.iter_applications())

    assert [i["Application"]["ID"] for i in items] == ["JP-1001", "JP-1002", "JP-1003"]
    assert m.call_count == 2
    assert m.request_history[0].json()["Page"] == 1
    assert m.request_history[1].json()["Page"] == 2


def test_sends_auth_and_tracing_headers(config, load_fixture):
    client = ScreeningClient(config, correlation_id="corr-123")
    page = load_fixture("applications_search_page2.json")
    page["data"]["TotalPage"] = 1
    with requests_mock.Mocker() as m:
        m.post(SEARCH_URL, json=page)
        list(client.iter_applications())

    headers = m.request_history[0].headers
    assert headers["x-company-api-key"] == "test-key"
    assert headers["paul-correlation-id"] == "corr-123"
    assert headers["paul-request-id"]


def test_retries_on_429_then_succeeds(config, load_fixture):
    client = ScreeningClient(config)
    page = load_fixture("applications_search_page2.json")
    page["data"]["TotalPage"] = 1
    with requests_mock.Mocker() as m:
        m.post(
            SEARCH_URL,
            [
                {"status_code": 429, "headers": {"retry-after": "0"}},
                {"json": page},
            ],
        )
        items = list(client.iter_applications())

    assert len(items) == 1
    assert m.call_count == 2


def test_raises_on_4xx_with_message(config):
    client = ScreeningClient(config)
    with requests_mock.Mocker() as m:
        m.post(SEARCH_URL, status_code=401, json={"status": 401, "message": "Unauthorized"})
        with pytest.raises(ScreeningAPIError) as exc:
            list(client.iter_applications())

    assert exc.value.status_code == 401
    assert "Unauthorized" in str(exc.value)
