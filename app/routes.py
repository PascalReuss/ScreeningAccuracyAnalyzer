from __future__ import annotations

import logging

from flask import Blueprint, current_app, render_template, request

from screening.analysis import analyze, analyze_assessments
from screening.api_client import ScreeningAPIError
from screening.demo import DemoDataMissing

from . import charts
from .services import load_assessment_records, load_decision_records

logger = logging.getLogger(__name__)

bp = Blueprint("insights", __name__)


def _render_error(title: str, detail: str, status: int) -> tuple[str, int]:
    return (
        render_template("error.html", title=title, detail=detail, status=status),
        status,
    )


@bp.app_errorhandler(ScreeningAPIError)
def _handle_api_error(exc: ScreeningAPIError) -> tuple[str, int]:
    logger.warning("Paulsjob API error: %s", exc)
    return _render_error(
        "The Paul's Job API is unavailable",
        f"{exc}. This is an upstream error — try again shortly, or check "
        "PAULSJOB_API_KEY and PAULSJOB_API_BASE_URL.",
        502,
    )


@bp.app_errorhandler(DemoDataMissing)
def _handle_demo_missing(exc: DemoDataMissing) -> tuple[str, int]:
    logger.warning("demo data problem: %s", exc)
    return _render_error("Demo data is not available", str(exc), 500)


@bp.app_errorhandler(500)
def _handle_internal(exc: object) -> tuple[str, int]:
    logger.exception("unhandled error rendering a page")
    return _render_error(
        "Something went wrong",
        "An unexpected error occurred while building this page. The details are "
        "in the server log.",
        500,
    )


@bp.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@bp.get("/")
def insights() -> str:
    deep = request.args.get("deep") == "1"
    refresh = request.args.get("refresh") == "1"

    records, meta = load_decision_records(
        current_app.config["SCREENING_CONFIG"], deep=deep, refresh=refresh
    )
    result = analyze(records)

    return render_template(
        "insights.html",
        result=result,
        meta=meta,
        deep=deep,
        figures={
            "decisions": charts.decision_breakdown(result),
            "reasons": charts.rejection_reasons(result),
            "by_job": charts.by_group(result.by_job, "Conclusions by job"),
            "by_step": charts.by_group(result.by_step, "Conclusions by pipeline step"),
            "agreement": charts.human_agreement(result),
            "opt_out": charts.opt_out_breakdown(result),
            "over_time": charts.decisions_over_time(result),
        },
    )


@bp.get("/assessments")
def assessments() -> str:
    refresh = request.args.get("refresh") == "1"

    config = current_app.config["SCREENING_CONFIG"]
    records, meta = load_assessment_records(config, refresh=refresh)

    decision_records, _ = load_decision_records(config)
    decision_by_slug = {r.person_slug: r.decision for r in decision_records}
    analysis = analyze_assessments(records, decision_by_slug)

    return render_template(
        "assessments.html",
        analysis=analysis,
        meta=meta,
        figures={
            "scores": charts.assessment_scores(analysis),
            "pass_rate": charts.assessment_pass_rate(analysis),
            "by_decision": charts.assessment_scores_by_decision(analysis),
            "by_job": charts.assessments_by_job(analysis),
        },
    )
