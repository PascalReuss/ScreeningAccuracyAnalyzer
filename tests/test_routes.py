import pytest

from app import routes
from screening.api_client import ScreeningAPIError
from screening.demo import DemoDataMissing


def test_api_error_renders_friendly_502(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise ScreeningAPIError(503, "upstream down")

    monkeypatch.setattr(routes, "load_decision_records", boom)
    resp = client.get("/")

    assert resp.status_code == 502
    assert b"Paul&#39;s Job API is unavailable" in resp.data


def test_demo_data_missing_renders_friendly_500(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise DemoDataMissing("demo/applications.json not found")

    monkeypatch.setattr(routes, "load_decision_records", boom)
    resp = client.get("/")

    assert resp.status_code == 500
    assert b"Demo data is not available" in resp.data


def test_unexpected_error_renders_generic_500(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("something odd")

    monkeypatch.setattr(routes, "load_decision_records", boom)
    resp = client.get("/")

    assert resp.status_code == 500
    assert b"Something went wrong" in resp.data


def test_healthz_ok(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}


def test_unknown_url_renders_friendly_404(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data


def test_demo_dashboards_render_with_all_sections(demo_client):
    home = demo_client.get("/")
    assert home.status_code == 200
    assert b"positive signals" in home.data.lower()
    assert b"Decisions over time" in home.data
    assert b"AI vs. human" in home.data

    assessments = demo_client.get("/assessments")
    assert assessments.status_code == 200
    assert b"Assessment score by AI decision" in assessments.data
