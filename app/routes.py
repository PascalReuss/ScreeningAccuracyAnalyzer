from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from screening.analysis import analyze

from . import charts
from .services import load_decision_records

bp = Blueprint("insights", __name__)


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
        },
    )
