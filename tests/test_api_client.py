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


def test_iter_assessments_fans_out_and_skips_errors(config):
    client = ScreeningClient(config)
    base = "https://api.example.test/dev/v1/company/person"
    with requests_mock.Mocker() as m:
        m.get(f"{base}/p1/assessments", json={"data": [{"ID": "a1"}]})
        m.get(f"{base}/p2/assessments", status_code=500)
        m.get(f"{base}/p3/assessments", json={"data": []})
        out = dict(client.iter_assessments(["p1", "p2", "p3"]))

    assert out == {"p1": [{"ID": "a1"}], "p3": []}


def test_iter_assessments_propagates_when_not_continuing(config):
    client = ScreeningClient(config)
    base = "https://api.example.test/dev/v1/company/person"
    with requests_mock.Mocker() as m:
        m.get(f"{base}/p1/assessments", status_code=500)
        with pytest.raises(ScreeningAPIError):
            list(client.iter_assessments(["p1"], continue_on_error=False))


def test_malformed_success_body_raises_screening_error(config):
    client = ScreeningClient(config)
    with requests_mock.Mocker() as m:
        m.post(SEARCH_URL, status_code=200, text="<html>gateway error</html>")
        with pytest.raises(ScreeningAPIError) as exc:
            list(client.iter_applications())

    assert "malformed JSON" in str(exc.value)


def test_pagination_stops_on_empty_page_without_total_page(config):
    client = ScreeningClient(config)
    with requests_mock.Mocker() as m:
        m.post(
            SEARCH_URL,
            [
                {"json": {"data": {"JobApplications": [{"Application": {"ID": "JP-1"}}]}}},
                {"json": {"data": {"JobApplications": []}}},
            ],
        )
        items = list(client.iter_applications())

    assert [i["Application"]["ID"] for i in items] == ["JP-1"]
    assert m.call_count == 2


def test_raises_on_4xx_with_message(config):
    client = ScreeningClient(config)
    with requests_mock.Mocker() as m:
        m.post(SEARCH_URL, status_code=401, json={"status": 401, "message": "Unauthorized"})
        with pytest.raises(ScreeningAPIError) as exc:
            list(client.iter_applications())

    assert exc.value.status_code == 401
    assert "Unauthorized" in str(exc.value)
