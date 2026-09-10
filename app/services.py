"""Glue between the API client, the cache, and the analysis layer."""
from __future__ import annotations

import logging
from typing import Any

from screening import cache, demo
from screening.analysis import (
    AssessmentRecord,
    DecisionRecord,
    assessment_records_from_api,
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
    if getattr(config, "demo_mode", False):
        raw = demo.load_applications()
        records = [record_from_search_item(item) for item in raw]
        meta = {
            "source": "demo",
            "mode": "demo",
            "correlation_id": "demo",
            "raw_count": len(raw),
            "record_count": len(records),
        }
        return records, meta

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


def load_assessment_records(
    config: Any, *, refresh: bool = False
) -> tuple[list[AssessmentRecord], dict[str, Any]]:
    """Return structured-assessment records joined to the job each was taken for.

    Candidate slugs come from the cached application search; assessments are then
    pulled one call per candidate (there is no company-wide endpoint) and cached
    as ``{slug: Assessment[]}``.
    """
    if getattr(config, "demo_mode", False):
        raw = demo.load_assessments()
        job_lookup = _job_lookup_from_applications(demo.load_applications())
        records = assessment_records_from_api(raw, job_lookup)
        meta = {
            "source": "demo",
            "correlation_id": "demo",
            "candidates_queried": len(job_lookup),
            "candidates_with_assessments": sum(1 for v in raw.values() if v),
            "record_count": len(records),
        }
        return records, meta

    client = ScreeningClient(config)

    apps_key = "applications:current"
    cached_apps = (
        None if refresh else cache.read(config.cache_dir, apps_key, config.cache_ttl_seconds)
    )
    if cached_apps is None:
        applications = list(client.iter_applications())
        cache.write(config.cache_dir, apps_key, applications)
    else:
        applications = cached_apps

    job_lookup = _job_lookup_from_applications(applications)

    assess_key = "assessments"
    cached_assess = (
        None
        if refresh
        else cache.read(config.cache_dir, assess_key, config.cache_ttl_seconds)
    )
    if cached_assess is None:
        raw = dict(client.iter_assessments(job_lookup.keys()))
        cache.write(config.cache_dir, assess_key, raw)
        source = "api"
    else:
        raw = cached_assess
        source = "cache"

    records = assessment_records_from_api(raw, job_lookup)
    meta = {
        "source": source,
        "correlation_id": client.correlation_id,
        "candidates_queried": len(job_lookup),
        "candidates_with_assessments": sum(1 for v in raw.values() if v),
        "record_count": len(records),
    }
    return records, meta


def _job_lookup_from_applications(
    applications: list[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Map person slug -> the job they applied for (first application wins)."""
    lookup: dict[str, dict[str, str]] = {}
    for item in applications:
        slug = (item.get("Person") or {}).get("PersonSlug")
        if not slug:
            continue
        job = item.get("Job") or {}
        lookup.setdefault(
            slug,
            {
                "job_id": str(job.get("PaulsjobJobID") or ""),
                "job_title": job.get("JobPositionTitle") or "",
            },
        )
    return lookup


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
