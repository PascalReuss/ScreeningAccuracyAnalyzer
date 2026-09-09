"""Glue between the API client, the cache, and the analysis layer."""
from __future__ import annotations

import logging
from typing import Any

from screening import cache
from screening.analysis import (
    DecisionRecord,
    record_from_search_item,
    records_from_detail,
)
from screening.api_client import ScreeningAPIError, ScreeningClient

logger = logging.getLogger(__name__)


def load_decision_records(
    config: Any, *, deep: bool = False, refresh: bool = False
) -> tuple[list[DecisionRecord], dict[str, Any]]:
    """Return normalized decision records plus a small metadata dict for the UI.

    ``deep=False`` uses one paginated search call (current step per application).
    ``deep=True`` additionally pulls each application's full step history â slower,
    but gives the reason text for every past conclusion, not just the current one.
    """
    client = ScreeningClient(config)
    key = "applications:deep" if deep else "applications:current"

    cached = None if refresh else cache.read(config.cache_dir, key, config.cache_ttl_seconds)
    if cached is None:
        raw = _fetch_raw(client, deep=deep)
        cache.write(config.cache_dir, key, raw)
        source = "api"
    else:
        raw = cached
        source = "cache"

    if deep:
        records = [rec for detail in raw for rec in records_from_detail(detail)]
    else:
        records = [record_from_search_item(item) for item in raw]

    meta = {
        "source": source,
        "mode": "deep" if deep else "current",
        "correlation_id": client.correlation_id,
        "raw_count": len(raw),
        "record_count": len(records),
    }
    return records, meta


def _fetch_raw(client: ScreeningClient, *, deep: bool) -> list[dict[str, Any]]:
    applications = list(client.iter_applications())
    if not deep:
        return applications

    details: list[dict[str, Any]] = []
    for item in applications:
        person_slug = (item.get("Person") or {}).get("PersonSlug")
        application_id = (item.get("Application") or {}).get("ID")
        if not person_slug or not application_id:
            continue
        try:
            details.append(client.get_application_detail(person_slug, application_id))
        except ScreeningAPIError:
            logger.exception(
                "skipping detail for %s/%s", person_slug, application_id
            )
    return details
