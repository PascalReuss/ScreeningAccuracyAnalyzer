"""The only module that talks HTTP to the Paulsjob API.

Owns auth, the paul-correlation-id / paul-request-id tracing headers, retry/backoff,
and both pagination styles the API uses (Page/PerPage and LastEvaluatedKey cursor).
Everything it returns is plain dicts / lists.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Iterator

import requests

logger = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class ScreeningAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Paulsjob API {status_code}: {message}")
        self.status_code = status_code


class ScreeningClient:
    def __init__(
        self,
        config: Any,
        session: requests.Session | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._correlation_id = correlation_id or str(uuid.uuid4())

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    # -- low level ------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "x-company-api-key": self._config.api_key,
            "paul-correlation-id": self._correlation_id,
            "paul-request-id": str(uuid.uuid4()),
            "accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._config.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, self._config.max_retries + 1):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=self._headers(),
                    timeout=self._config.request_timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= self._config.max_retries:
                    break
                _sleep(attempt)
                continue

            if resp.status_code in RETRY_STATUS and attempt < self._config.max_retries:
                _sleep(attempt, resp)
                continue
            if resp.status_code >= 400:
                raise ScreeningAPIError(resp.status_code, _error_message(resp))
            if not resp.content:
                return {}
            return resp.json()

        raise ScreeningAPIError(0, f"request failed after retries: {last_exc}")

    # -- pagination --------------------------------------------------------

    def _paginate_pages(
        self, path: str, payload: dict[str, Any], *, data_key: str, per_page: int = 100
    ) -> Iterator[dict[str, Any]]:
        payload = dict(payload)
        payload["PerPage"] = per_page
        page = 1
        while True:
            payload["Page"] = page
            body = self._request("POST", path, json=payload).get("data", {}) or {}
            items = body.get(data_key) or []
            yield from items
            total_pages = body.get("TotalPage") or 0
            if not items or page >= total_pages:
                return
            page += 1

    def _paginate_cursor(
        self,
        method: str,
        path: str,
        *,
        data_key: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        payload = dict(payload or {})
        params = dict(params or {})
        while True:
            if method == "POST":
                body = self._request("POST", path, json=payload).get("data", {}) or {}
            else:
                body = self._request("GET", path, params=params).get("data", {}) or {}
            items = body.get(data_key) or []
            yield from items
            cursor = body.get("LastEvaluatedKey")
            if not items or not cursor:
                return
            if method == "POST":
                payload["LastEvaluatedKey"] = cursor
            else:
                params["LastEvaluatedKey"] = cursor

    # -- resources --------------------------------------------------------

    def iter_applications(
        self, search_payload: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        """POST /recruiting/applications/search-applications -> ApplicationSearchListData[]."""
        yield from self._paginate_pages(
            "/recruiting/applications/search-applications",
            search_payload or {},
            data_key="JobApplications",
        )

    def get_application_detail(
        self, person_slug: str, application_id: str
    ) -> dict[str, Any]:
        """GET /recruiting/person/{slug}/applications/{id} -> DetailedJobApplication."""
        return (
            self._request(
                "GET",
                f"/recruiting/person/{person_slug}/applications/{application_id}",
            ).get("data")
            or {}
        )

    def iter_jobs(
        self, search_payload: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        yield from self._paginate_pages(
            "/recruiting/jobs/search-jobs", search_payload or {}, data_key="Jobs"
        )

    def get_job_steps(self, paulsjob_job_id: str | int) -> list[dict[str, Any]]:
        return (
            self._request("GET", f"/recruiting/jobs/{paulsjob_job_id}/steps").get("data")
            or []
        )

    def get_person_assessments(self, person_slug: str) -> list[dict[str, Any]]:
        return (
            self._request(
                "GET", f"/company/person/{person_slug}/assessments"
            ).get("data")
            or []
        )


def _sleep(attempt: int, resp: requests.Response | None = None) -> None:
    retry_after: float | None = None
    if resp is not None:
        raw = resp.headers.get("retry-after")
        if raw:
            try:
                retry_after = float(raw)
            except ValueError:
                retry_after = None
    delay = retry_after if retry_after is not None else min(2**attempt, 30)
    logger.warning("retrying paulsjob request in %.1fs (attempt %d)", delay, attempt)
    time.sleep(delay)


def _error_message(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return resp.text[:200]
    if isinstance(payload, dict):
        msg = payload.get("message")
        if isinstance(msg, list):
            return "; ".join(str(m) for m in msg)
        if msg:
            return str(msg)
    return str(payload)[:200]
